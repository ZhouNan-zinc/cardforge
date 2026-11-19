"""LLM policy for run-layer decisions (map/reward/boon/shop/event/...).

This module is intentionally separate from the battle ``LLMAgent``: the
research design treats long-term decisions as an evaluation dimension, not as
part of the game's core auto-balancing contribution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from .generator import LLMConfig, _extract_json, _llm_chat
from .models import Card, EffectType
from .run import BOONS, MAP_LAYERS, POTIONS_BY_ID, RELICS_BY_ID, Run
from .run_prompts import RUN_PHASE_LABELS, RUN_SYSTEM, RUN_USER_SUFFIX

ChatFn = Callable[[list[dict], LLMConfig], str | None]


@dataclass
class RunDecision:
    phase: str
    action: str
    index: int | None
    valid: bool
    fallback: bool
    latency_ms: float
    reason: str = ""
    error: str | None = None


class HeuristicRunPolicy:
    """Deterministic fallback/baseline for long-term choices.

    ``route_mode`` is an evaluation knob, not a game rule: it forces the
    heuristic to prefer battle / shop / elite nodes so route viability can be
    measured separately from card-balance changes.
    """

    def __init__(self, route_mode: str = "balanced") -> None:
        self.route_mode = route_mode

    def choose_style(self, run: Run) -> int:
        return 0

    def choose_map(self, run: Run) -> int:
        options = run.map_options
        if not options:
            return 0
        if self.route_mode == "random":
            return run.rng.randrange(len(options))
        hp_ratio = run.player_hp / max(1, run.max_hp)
        if self.route_mode == "battle":
            order = ["battle", "elite", "rest", "shop", "event", "treasure"]
        elif self.route_mode == "shop":
            order = ["shop", "battle", "rest", "event", "elite", "treasure"]
        elif self.route_mode == "elite":
            order = ["elite", "battle", "rest", "shop", "event", "treasure"]
        elif self.route_mode in {"balanced", "value"}:
            # Expected-value policy: no hard-coded "battle first" preference.
            scores = []
            for i, node in enumerate(options):
                node_id = node.get("id")
                if node_id == "rest":
                    score = 0.8 + (1.0 - hp_ratio) * 2.2
                elif node_id == "shop":
                    score = 0.7
                    if run.gold >= 40:
                        score += 0.8
                    if len(run.deck) < 16:
                        score += 0.4
                elif node_id == "elite":
                    score = 0.9 + (1.2 if hp_ratio > 0.7 else -0.4)
                    if len(run.deck) >= 15:
                        score += 0.4
                elif node_id == "battle":
                    score = 1.0 + (0.3 if hp_ratio > 0.6 else 0.0)
                elif node_id == "treasure":
                    score = 1.2
                else:  # event
                    score = 0.9 + (0.2 if hp_ratio > 0.6 else 0.0)
                scores.append((score, i))
            return max(scores, key=lambda pair: pair[0])[1]
        else:
            order = ["battle", "rest", "shop", "event", "elite", "treasure"]
        for wanted in order:
            for i, node in enumerate(options):
                if node.get("id") == wanted:
                    return i
        return 0

    def choose_reward(self, run: Run) -> int:
        if not run.reward_options:
            return 0
        return max(range(len(run.reward_options)), key=lambda i: self.card_value(run.reward_options[i]))

    def choose_boon(self, run: Run) -> int:
        if not run.boon_options:
            return 0
        priorities = {"max_hp": 0, "energy": 1, "draw": 2, "strength": 3, "heal": 4, "upgrade": 5}
        return min(range(len(run.boon_options)), key=lambda i: priorities.get(run.boon_options[i].get("id"), 9))

    def choose_rest(self, run: Run) -> int:
        if run.player_hp < run.max_hp * 0.6:
            return 0
        return 1 if len(run.rest_options) > 1 else 0

    def choose_shop(self, run: Run) -> dict:
        # Keep fallback simple: buy one affordable card only if the deck is small.
        if len(run.deck) < 18:
            for i, item in enumerate(run.shop_items):
                if item.get("kind") == "card" and item.get("price", 999) <= run.gold:
                    return {"action": "buy", "index": i}
        return {"action": "leave"}

    def choose_event(self, run: Run) -> int:
        return 0

    def choose_upgrade(self, run: Run) -> int:
        return 0

    def choose_remove(self, run: Run) -> int:
        if not run.remove_options:
            return 0
        # Remove the least valuable card first.
        return min(range(len(run.remove_options)), key=lambda i: self.card_value(run.remove_options[i]))

    @staticmethod
    def card_value(card: Card) -> float:
        value = 0.0
        for effect in card.effects:
            if effect.type == EffectType.damage:
                value += effect.amount * 1.2
            elif effect.type == EffectType.block:
                value += effect.amount * 0.8
            elif effect.type == EffectType.heal:
                value += effect.amount * 0.5
            elif effect.type == EffectType.draw:
                value += effect.amount * 1.4
            elif effect.type == EffectType.energy:
                value += effect.amount * 2.0
            elif effect.type in {EffectType.buff, EffectType.debuff}:
                value += effect.amount * 1.0
        return value / max(1, card.cost)


@dataclass
class LLMRunAgent:
    """LLM policy with rule-checked fallback for every run phase."""

    config: LLMConfig = field(default_factory=LLMConfig)
    chat_fn: ChatFn | None = None
    label: str = "llm-run"
    prompt_version: str = "v1-neutral"
    guide: str = ""
    strategy_memo: str = ""
    battle_history: list[dict] = field(default_factory=list)
    fallback_policy: HeuristicRunPolicy = field(default_factory=HeuristicRunPolicy)
    max_retries: int = 1
    decisions: list[RunDecision] = field(default_factory=list)
    calls: int = 0
    valid_responses: int = 0
    invalid_responses: int = 0
    fallbacks: int = 0
    api_errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    invalid_log: list[dict] = field(default_factory=list)
    last_prompt: str = ""

    def __post_init__(self) -> None:
        if self.chat_fn is None:
            config = self.config

            def default_chat(messages: list[dict], _: LLMConfig) -> str | None:
                return _llm_chat(messages, config, max_tokens=400, temperature=0.2)

            self.chat_fn = default_chat

    @property
    def model_label(self) -> str:
        return self.config.model or self.label

    def choose_style(self, run: Run) -> int:
        return self._choose(run, "scarf", run.style_options)

    def choose_map(self, run: Run) -> int:
        return self._choose(run, "map", run.map_options)

    def choose_reward(self, run: Run) -> int:
        return self._choose(run, "reward", run.reward_options)

    def choose_boon(self, run: Run) -> int:
        return self._choose(run, "boon", run.boon_options)

    def choose_rest(self, run: Run) -> int:
        return self._choose(run, "rest", run.rest_options)

    def choose_event(self, run: Run) -> int:
        return self._choose(run, "event", run.event_options)

    def choose_upgrade(self, run: Run) -> int:
        return self._choose(run, "upgrade", run.upgrade_options)

    def choose_remove(self, run: Run) -> int:
        return self._choose(run, "remove", run.remove_options)

    def choose_shop(self, run: Run) -> dict:
        return self._choose_shop(run)

    def _choose(self, run: Run, phase: str, options: list) -> int:
        if not options:
            return 0
        messages = self._messages(run, phase, options)
        self.last_prompt = messages[-1]["content"]
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            content = self.chat_fn(messages, self.config) if self.chat_fn else None
            latency = (time.perf_counter() - started) * 1000
            self.calls += 1
            self.latencies_ms.append(latency)
            if not content:
                self.api_errors += 1
                last_error = "empty response or API failure"
                continue
            try:
                raw = _extract_json(content)
                if not isinstance(raw, dict) or str(raw.get("action", "")).lower() != "choose":
                    raise ValueError("action must be 'choose'")
                index = int(raw.get("index"))
                if index < 0 or index >= len(options):
                    raise ValueError(f"index {index} out of range")
                self.valid_responses += 1
                reason = str(raw.get("reason", ""))[:180]
                strategy = str(raw.get("strategy", "")).strip()
                if strategy:
                    self.strategy_memo = strategy[:300]
                self.decisions.append(
                    RunDecision(phase, "choose", index, True, False, round(latency, 2), reason)
                )
                return index
            except Exception as error:  # noqa: BLE001
                self.invalid_responses += 1
                last_error = str(error)
                self.invalid_log.append(
                    {"phase": phase, "error": str(error), "content": content[:500]}
                )
                if attempt < self.max_retries:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": f"上一次输出不合法：{error}。只输出合法 JSON，index 必须在选项范围内。",
                        },
                    ]
        fallback_method = {"scarf": "choose_style"}.get(phase, f"choose_{phase}")
        index = getattr(self.fallback_policy, fallback_method)(run)
        self.fallbacks += 1
        self.decisions.append(
            RunDecision(phase, "choose", index, False, True, round(self.latencies_ms[-1] if self.latencies_ms else 0, 2), "heuristic fallback", last_error)
        )
        return index

    def _choose_shop(self, run: Run) -> dict:
        options = run.shop_items
        messages = self._messages(run, "shop", options, shop=True)
        self.last_prompt = messages[-1]["content"]
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            content = self.chat_fn(messages, self.config) if self.chat_fn else None
            latency = (time.perf_counter() - started) * 1000
            self.calls += 1
            self.latencies_ms.append(latency)
            if not content:
                self.api_errors += 1
                last_error = "empty response or API failure"
                continue
            try:
                raw = _extract_json(content)
                if not isinstance(raw, dict):
                    raise ValueError("response must be an object")
                action = str(raw.get("action", "")).lower()
                strategy = str(raw.get("strategy", "")).strip()
                if strategy:
                    self.strategy_memo = strategy[:300]
                if action == "leave":
                    self.valid_responses += 1
                    decision = {"action": "leave"}
                    self.decisions.append(RunDecision("shop", "leave", None, True, False, round(latency, 2), str(raw.get("reason", ""))[:180]))
                    return decision
                if action == "reroll":
                    if run.gold < 10:
                        raise ValueError("reroll costs 10 gold")
                    self.valid_responses += 1
                    self.decisions.append(RunDecision("shop", "reroll", None, True, False, round(latency, 2), str(raw.get("reason", ""))[:180]))
                    return {"action": "reroll"}
                if action != "buy":
                    raise ValueError("shop action must be buy/reroll/leave")
                index = int(raw.get("index"))
                if index < 0 or index >= len(options):
                    raise ValueError(f"index {index} out of range")
                item = options[index]
                if item.get("price", 999) > run.gold:
                    raise ValueError("item is not affordable")
                if item.get("kind") == "potion" and len(run.potions) >= 2:
                    raise ValueError("potion slots are full")
                self.valid_responses += 1
                self.decisions.append(RunDecision("shop", "buy", index, True, False, round(latency, 2), str(raw.get("reason", ""))[:180]))
                return {"action": "buy", "index": index}
            except Exception as error:  # noqa: BLE001
                self.invalid_responses += 1
                last_error = str(error)
                self.invalid_log.append({"phase": "shop", "error": str(error), "content": content[:500]})
                if attempt < self.max_retries:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": f"上一次输出不合法：{error}。只输出 buy/reroll/leave 的合法 JSON。"},
                    ]
        fallback = self.fallback_policy.choose_shop(run)
        self.fallbacks += 1
        self.decisions.append(RunDecision("shop", fallback.get("action", "leave"), fallback.get("index"), False, True, round(self.latencies_ms[-1] if self.latencies_ms else 0, 2), "heuristic fallback", last_error))
        return fallback

    def observe_battle(self, public_summary: dict) -> None:
        """Receive only public battle results for coordination."""
        self.battle_history.append(public_summary)
        self.battle_history = self.battle_history[-5:]

    def _messages(self, run: Run, phase: str, options: list, shop: bool = False) -> list[dict]:
        relics = " / ".join(
            f"{RELICS_BY_ID[item]['name']}（{RELICS_BY_ID[item]['description']}）"
            for item in run.relics
            if item in RELICS_BY_ID
        ) or "无"
        boons = " / ".join(
            next((b["name"] for b in BOONS if b["id"] == item), item)
            for item in run.boons
        ) or "无"
        potions = " / ".join(
            f"{POTIONS_BY_ID[item]['name']}（{POTIONS_BY_ID[item]['description']}）"
            for item in run.potions
            if item in POTIONS_BY_ID
        ) or "无"
        deck = "\n".join(
            f"- {card.id} {card.name} | 费用 {card.cost} | {card.type.value} | {card.element.value} | {card.description}"
            for card in run.deck
        )
        history = " / ".join(run.map_history[-8:]) or "无"
        option_lines = []
        for i, option in enumerate(options):
            if isinstance(option, Card):
                option_lines.append(
                    f"[{i}] {option.name} | 费用 {option.cost} | {option.type.value} | {option.element.value} | {option.description}"
                )
            elif isinstance(option, dict):
                if shop:
                    option_lines.append(
                        f"[{i}] {option.get('kind', '?')} | {option.get('name', '')} | 价格 {option.get('price', '?')} | {option.get('description', '')}"
                    )
                else:
                    option_lines.append(
                        f"[{i}] {option.get('name', '')} | {option.get('description', '')}"
                    )
            else:
                option_lines.append(f"[{i}] {option}")
        shop_hint = (
            f"\n当前金币：{run.gold}；刷新商品价格 15G。"
            "若是商店，合法输出为 buy/reroll/leave。"
            if shop else ""
        )
        user = (
            f"阶段：{RUN_PHASE_LABELS.get(phase, phase)}\n"
            f"层数：{run.layer_index + 1}/{len(MAP_LAYERS) + 1}\n"
            f"HP：{run.player_hp}/{run.max_hp}；金币：{run.gold}\n"
            f"已走路线：{history}\n"
            f"牌组（{len(run.deck)} 张）：\n{deck}\n"
            f"遗物：{relics}\n"
            f"Boon：{boons}\n"
            f"药水：{potions}\n"
            f"公共攻略（可为空）：{self.guide or '无'}\n"
            f"本局策略便签（公开）：{self.strategy_memo or '无'}\n"
            f"最近战斗摘要（公开）：{self.battle_history}\n"
            "当前选项：\n" + "\n".join(option_lines) + shop_hint + "\n"
            + RUN_USER_SUFFIX
        )
        return [
            {"role": "system", "content": RUN_SYSTEM},
            {"role": "user", "content": user},
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
            "valid_rate": round(self.valid_responses / max(1, self.calls), 4),
            "invalid_rate": round(self.invalid_responses / max(1, self.calls), 4),
            "fallback_rate": round(self.fallbacks / max(1, decisions), 4),
            "api_error_rate": round(self.api_errors / max(1, self.calls), 4),
            "avg_latency_ms": round(mean(self.latencies_ms), 2) if self.latencies_ms else 0.0,
            "p95_latency_ms": round(p95, 2),
            "phase_counts": {
                phase: sum(1 for d in self.decisions if d.phase == phase)
                for phase in sorted({d.phase for d in self.decisions})
            },
            "invalid_examples": self.invalid_log[:5],
            "latencies_ms": [round(value, 2) for value in self.latencies_ms],
        }

    def trace(self) -> list[dict]:
        return [
            {
                "phase": d.phase,
                "action": d.action,
                "index": d.index,
                "valid": d.valid,
                "fallback": d.fallback,
                "latency_ms": d.latency_ms,
                "reason": d.reason,
                "error": d.error,
            }
            for d in self.decisions
        ]
