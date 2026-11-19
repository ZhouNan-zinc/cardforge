"""LLM player agent for the CardForge playtest study.

The agent exposes the same ``choose`` interface as the heuristic/random agents.
It sends one compact textual state to an OpenAI-compatible chat endpoint and
expects a single JSON action. Invalid or failed outputs fall back to the
heuristic agent, so the research runner can measure both model quality and
failure modes without crashing a match.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from .agents import HeuristicAgent
from .game import Actor, Game
from .generator import LLMConfig, _extract_json, _llm_chat
from .player_prompts import PLAN_SYSTEMS, PLAN_USER_SUFFIX, PROMPT_VERSION, SINGLE_SYSTEM, SINGLE_USER_SUFFIX

ChatFn = Callable[[list[dict], LLMConfig], str | None]


@dataclass
class LLMDecision:
    turn: int
    action: str
    card_index: int | None
    card_name: str | None
    valid: bool
    fallback: bool
    latency_ms: float
    reason: str = ""
    error: str | None = None


@dataclass
class LLMAgent:
    """Ask an LLM for one action at a time, with rule-checked fallback."""

    config: LLMConfig = field(default_factory=LLMConfig)
    chat_fn: ChatFn | None = None
    seed: int | None = None
    temperature: float = 0.2
    max_tokens: int = 400
    max_retries: int = 1
    label: str = "llm"
    prompt_version: str = PROMPT_VERSION
    context_note: str = ""
    plan_turn: bool = False
    fallback: HeuristicAgent = field(default_factory=HeuristicAgent)
    plan: list[str] = field(default_factory=list)
    plan_key: tuple[int, str] | None = None
    plan_reason: str = ""
    plan_latency_ms: float = 0.0
    invalid_log: list[dict] = field(default_factory=list)
    decisions: list[LLMDecision] = field(default_factory=list)
    calls: int = 0
    valid_responses: int = 0
    invalid_responses: int = 0
    fallbacks: int = 0
    api_errors: int = 0
    no_playable: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    last_prompt: str = ""

    def __post_init__(self) -> None:
        if self.chat_fn is None:
            config = self.config

            def default_chat(messages: list[dict], _: LLMConfig) -> str | None:
                return _llm_chat(
                    messages,
                    config,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )

            self.chat_fn = default_chat

    @property
    def model_label(self) -> str:
        if self.label in {"llm", "mock"}:
            return self.config.model or self.label
        return self.label

    def choose(self, game: Game, actor: Actor) -> int | None:
        # The study is LLM-as-player; the enemy remains the controlled
        # heuristic baseline unless an experiment explicitly wraps it.
        if actor != "player":
            return self.fallback.choose(game, actor)

        if self.plan_turn:
            return self._choose_plan(game, actor)

        combatant = game.player
        playable = [i for i, card in enumerate(combatant.hand) if card.cost <= combatant.energy]
        if not playable:
            self.no_playable += 1
            return None

        messages = self._messages(game)
        self.last_prompt = messages[-1]["content"]
        last_error: str | None = None

        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            content = self.chat_fn(messages, self.config) if self.chat_fn else None
            latency_ms = (time.perf_counter() - started) * 1000
            self.calls += 1
            self.latencies_ms.append(latency_ms)

            if not content:
                self.api_errors += 1
                last_error = "empty response or API failure"
                continue

            try:
                choice, action, card_name = self._parse(content, combatant)
            except ValueError as error:
                self.invalid_responses += 1
                last_error = str(error)
                self.invalid_log.append(
                    {"turn": game.turn, "mode": "single", "error": str(error), "content": content[:500]}
                )
                if attempt < self.max_retries:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                f"上一次输出不合法：{error}。"
                                "请只输出一个合法 JSON，不要 Markdown，不要解释。"
                            ),
                        },
                    ]
                continue

            self.valid_responses += 1
            self.decisions.append(
                LLMDecision(
                    turn=game.turn,
                    action=action,
                    card_index=choice,
                    card_name=card_name,
                    valid=True,
                    fallback=False,
                    latency_ms=round(latency_ms, 2),
                    reason=self._reason(content),
                )
            )
            return choice

        # Model failed after repair: use the same heuristic opponent baseline.
        choice = self.fallback.choose(game, actor)
        self.fallbacks += 1
        card_name = combatant.hand[choice].name if choice is not None and choice < len(combatant.hand) else None
        self.decisions.append(
            LLMDecision(
                turn=game.turn,
                action="play" if choice is not None else "end",
                card_index=choice,
                card_name=card_name,
                valid=False,
                fallback=True,
                latency_ms=round(self.latencies_ms[-1] if self.latencies_ms else 0.0, 2),
                reason="heuristic fallback",
                error=last_error,
            )
        )
        return choice

    @staticmethod
    def _reason(content: str) -> str:
        try:
            raw = _extract_json(content)
            return str(raw.get("reason", ""))[:180]
        except Exception:
            return ""

    @staticmethod
    def _parse(content: str, combatant) -> tuple[int | None, str, str | None]:
        raw = _extract_json(content)
        if not isinstance(raw, dict):
            raise ValueError("response must be a JSON object")
        action = str(raw.get("action", "")).strip().lower()
        if action == "end":
            return None, "end", None
        if action != "play":
            raise ValueError("action must be 'play' or 'end'")
        index = raw.get("card_index")
        if isinstance(index, bool) or index is None:
            raise ValueError("card_index must be an integer")
        try:
            index = int(index)
        except (TypeError, ValueError) as error:
            raise ValueError("card_index must be an integer") from error
        if index < 0 or index >= len(combatant.hand):
            raise ValueError(f"card_index out of range: {index}")
        card = combatant.hand[index]
        if card.cost > combatant.energy:
            raise ValueError(f"card {index} costs {card.cost}, only {combatant.energy} energy left")
        return index, "play", card.name

    def _choose_plan(self, game: Game, actor: Actor) -> int | None:
        combatant = game.player
        playable = [i for i, card in enumerate(combatant.hand) if card.cost <= combatant.energy]
        if not playable:
            self.no_playable += 1
            return None

        key = (game.turn, game.active)
        if self.plan_key != key:
            self.plan_key = key
            self.plan = []
            ids, reason, error = self._request_plan(game, combatant)
            if error:
                choice = self.fallback.choose(game, actor)
                self.fallbacks += 1
                card_name = combatant.hand[choice].name if choice is not None and choice < len(combatant.hand) else None
                self.decisions.append(
                    LLMDecision(
                        turn=game.turn,
                        action="play" if choice is not None else "end",
                        card_index=choice,
                        card_name=card_name,
                        valid=False,
                        fallback=True,
                        latency_ms=round(self.latencies_ms[-1] if self.latencies_ms else 0.0, 2),
                        reason="heuristic fallback",
                        error=error,
                    )
                )
                return choice
            self.plan = ids
            self.plan_reason = reason
            if not ids:
                self.decisions.append(
                    LLMDecision(
                        turn=game.turn,
                        action="end",
                        card_index=None,
                        card_name=None,
                        valid=True,
                        fallback=False,
                        latency_ms=round(self.plan_latency_ms, 2),
                        reason=reason,
                    )
                )
                return None

        while self.plan:
            card_id = self.plan.pop(0)
            index = next((i for i, card in enumerate(combatant.hand) if card.id == card_id), None)
            if index is None:
                continue
            card = combatant.hand[index]
            if card.cost > combatant.energy:
                continue
            latency = self.plan_latency_ms
            self.plan_latency_ms = 0.0
            self.decisions.append(
                LLMDecision(
                    turn=game.turn,
                    action="play",
                    card_index=index,
                    card_name=card.name,
                    valid=True,
                    fallback=False,
                    latency_ms=round(latency, 2),
                    reason=self.plan_reason,
                )
            )
            return index
        return None

    def _request_plan(self, game: Game, combatant) -> tuple[list[str], str, str | None]:
        messages = self._plan_messages(game)
        self.last_prompt = messages[-1]["content"]
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            content = self.chat_fn(messages, self.config) if self.chat_fn else None
            latency_ms = (time.perf_counter() - started) * 1000
            self.calls += 1
            self.latencies_ms.append(latency_ms)
            self.plan_latency_ms = latency_ms
            if not content:
                self.api_errors += 1
                last_error = "empty response or API failure"
                continue
            try:
                raw = _extract_json(content)
                ids = raw.get("cards") if isinstance(raw, dict) else None
                if not isinstance(ids, list):
                    raise ValueError("cards must be a list of card ids")
                if len(ids) > 4:
                    raise ValueError("plan has more than 4 cards")
                ids = [str(item) for item in ids]
                if len(ids) != len(set(ids)):
                    raise ValueError("plan contains duplicate card ids")
                hand_by_id = {card.id: card for card in combatant.hand}
                missing = [card_id for card_id in ids if card_id not in hand_by_id]
                if missing:
                    raise ValueError(f"card ids not in hand: {missing}")
                total_cost = sum(hand_by_id[card_id].cost for card_id in ids)
                if total_cost > combatant.energy:
                    raise ValueError(f"plan costs {total_cost}, only {combatant.energy} energy")
                reason = str(raw.get("reason", ""))[:180]
                self.valid_responses += 1
                return ids, reason, None
            except Exception as error:  # noqa: BLE001
                self.invalid_responses += 1
                last_error = str(error)
                self.invalid_log.append(
                    {"turn": game.turn, "mode": "plan", "error": str(error), "content": content[:500]}
                )
                if attempt < self.max_retries:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                f"上一次计划不合法：{error}。"
                                "只输出合法 JSON；cards 只能使用手牌中出现的 id，"
                                "按顺序执行，总费用不能超过当前能量。"
                            ),
                        },
                    ]
                continue
        self.api_errors += 0
        return [], "", last_error

    def _state_user(self, game: Game, use_ids: bool = False) -> str:
        player = game.player
        enemy = game.enemy
        intent = game.current_enemy_intent()
        state = game.state_for_player()
        incoming = state.get("incoming_damage", 0)
        hand_lines = []
        for i, card in enumerate(player.hand):
            selector = card.id if use_ids else f"[{i}]"
            keywords = f" | 关键词:{','.join(card.keywords)}" if card.keywords else ""
            hand_lines.append(
                f"{selector} {card.name} | 费用 {card.cost} | {card.type.value} | {card.element.value} | "
                f"{card.description}{keywords}"
            )
        history = "\n".join(game.log[-8:]) or "（无）"
        return (
            f"第 {game.turn} 回合，当前行动方：{game.active}。\n"
            f"玩家：HP {player.hp}/{player.max_hp}，格挡 {player.block}，能量 {player.energy}/{player.max_energy}，"
            f"力量 {player.strength}，虚弱 {player.weak}，易伤 {player.vulnerable}，"
            f"本回合已出牌 {player.cards_played_this_turn} 张，元素计数 {player.element_counts}。\n"
            f"敌人：{enemy.name}，HP {enemy.hp}/{enemy.max_hp}，格挡 {enemy.block}，"
            f"力量 {enemy.strength}，虚弱 {enemy.weak}，易伤 {enemy.vulnerable}。\n"
            f"敌人意图：{intent['label'] if intent else '无'}；预计本回合受到伤害：{incoming}。\n"
            f"公开策略便签：{self.context_note or '无'}\n"
            f"手牌：\n" + ("\n".join(hand_lines) if hand_lines else "（空）") + "\n"
            f"最近日志：\n{history}\n"
        )

    def _messages(self, game: Game) -> list[dict]:
        return [
            {"role": "system", "content": SINGLE_SYSTEM},
            {"role": "user", "content": self._state_user(game) + SINGLE_USER_SUFFIX},
        ]

    def _plan_messages(self, game: Game) -> list[dict]:
        return [
            {"role": "system", "content": PLAN_SYSTEMS.get(self.prompt_version, PLAN_SYSTEMS["v1-neutral"])},
            {"role": "user", "content": self._state_user(game, use_ids=True) + PLAN_USER_SUFFIX},
        ]

    def summary(self) -> dict:
        latencies = sorted(self.latencies_ms)
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
        decisions = len(self.decisions)
        return {
            "agent": self.label,
            "model": self.model_label,
            "prompt_version": self.prompt_version,
            "calls": self.calls,
            "decisions": decisions,
            "valid_responses": self.valid_responses,
            "invalid_responses": self.invalid_responses,
            "fallbacks": self.fallbacks,
            "api_errors": self.api_errors,
            "no_playable": self.no_playable,
            "valid_rate": round(self.valid_responses / max(1, self.calls), 4),
            "invalid_rate": round(self.invalid_responses / max(1, self.calls), 4),
            "fallback_rate": round(self.fallbacks / max(1, decisions), 4),
            "play_actions": sum(1 for d in self.decisions if d.action == "play"),
            "end_actions": sum(1 for d in self.decisions if d.action == "end"),
            "avg_latency_ms": round(mean(self.latencies_ms), 2) if self.latencies_ms else 0.0,
            "p95_latency_ms": round(p95, 2),
            "invalid_examples": self.invalid_log[:5],
            "latencies_ms": [round(value, 2) for value in self.latencies_ms],
        }

    def trace(self) -> list[dict]:
        return [
            {
                "turn": d.turn,
                "action": d.action,
                "card_index": d.card_index,
                "card_name": d.card_name,
                "valid": d.valid,
                "fallback": d.fallback,
                "latency_ms": d.latency_ms,
                "reason": d.reason,
                "error": d.error,
            }
            for d in self.decisions
        ]
