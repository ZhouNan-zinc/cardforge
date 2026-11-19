"""Run a paired LLM-as-player evaluation.

Example (real model):
    export LLM_BASE_URL=https://api.openai.com/v1
    export LLM_API_KEY=...
    export LLM_MODEL=...
    .venv/bin/python -m src.llm_playtest --agent llm --games 30

Example (no API, pipeline check only):
    .venv/bin/python -m src.llm_playtest --agent mock --games 10
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import statistics
from collections import Counter
from pathlib import Path

from .agents import HeuristicAgent, play_match
from .game import Actor
from .generator import DEFAULT_THEME, LLMConfig, _llm_chat, generate_cards, load_card_set
from .llm_agent import LLMAgent
from .opencode_chat import DEFAULT_PLAYER_MODEL, OpenCodeChat


def mock_chat(messages: list[dict], _: LLMConfig) -> str | None:
    """Tiny rule-based stand-in used to validate the evaluation pipeline."""
    text = messages[-1]["content"]
    energy_match = re.search(r"能量\s*(\d+)\s*/\s*\d+", text)
    energy = int(energy_match.group(1)) if energy_match else 0
    hand = text.split("手牌：", 1)[-1].split("最近日志：", 1)[0]
    for line in hand.splitlines():
        match = re.match(r"\[(\d+)\].*?费用\s*(\d+)", line)
        if match and int(match.group(2)) <= energy:
            return json.dumps(
                {"action": "play", "card_index": int(match.group(1)), "reason": "mock: first affordable card"},
                ensure_ascii=False,
            )
    return json.dumps({"action": "end", "reason": "mock: no affordable card"}, ensure_ascii=False)


def real_chat_factory(temperature: float, max_tokens: int):
    def chat(messages: list[dict], config: LLMConfig) -> str | None:
        return _llm_chat(messages, config, max_tokens=max_tokens, temperature=temperature)

    return chat


def summarize(rows: list[dict], key: str) -> dict:
    wins = sum(1 for row in rows if row[key]["winner"] == "player")
    turns = [row[key]["turns"] for row in rows]
    return {
        "wins": wins,
        "win_rate": round(wins / max(1, len(rows)), 4),
        "avg_turns": round(statistics.mean(turns), 2) if turns else 0.0,
    }


def run_study(
    cards,
    games: int,
    seed: int,
    agent_name: str,
    temperature: float,
    max_tokens: int,
    max_steps: int,
    player_model: str = DEFAULT_PLAYER_MODEL,
    isolation_dir: str = "/tmp/opencode/cardforge-llm-player",
    plan_turn: bool = False,
    prompt_version: str = "v1-neutral",
) -> dict:
    config = LLMConfig()
    if agent_name == "llm" and not config.configured:
        raise SystemExit(
            "LLM 未配置。请设置 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL；"
            "如果只想验证管线，请使用 --agent mock；"
            "如果要用当前 OpenCode 模型，请使用 --agent opencode。"
        )
    if agent_name == "opencode" and shutil.which("opencode") is None:
        raise SystemExit("opencode CLI not found")
    effective_plan = plan_turn or agent_name == "opencode"

    rng = random.Random(seed)
    rows: list[dict] = []
    all_llm_summaries: list[dict] = []
    all_traces: list[dict] = []
    llm_card_plays: Counter[str] = Counter()
    baseline_card_plays: Counter[str] = Counter()

    for i in range(games):
        game_seed = rng.randint(0, 10**9)
        starting_actor: Actor = "player" if i % 2 == 0 else "enemy"
        if agent_name == "mock":
            player_agent = LLMAgent(chat_fn=mock_chat, label="mock", config=config)
        elif agent_name == "opencode":
            player_agent = LLMAgent(
                chat_fn=OpenCodeChat(model=player_model, isolation_dir=isolation_dir),
                label=player_model,
                plan_turn=True,
                prompt_version=prompt_version,
            )
        else:
            player_agent = LLMAgent(
                config=config,
                chat_fn=real_chat_factory(temperature, max_tokens),
                label="llm",
                temperature=temperature,
                max_tokens=max_tokens,
                plan_turn=effective_plan,
                prompt_version=prompt_version,
            )
        llm_result = play_match(
            cards,
            player_agent,
            HeuristicAgent(),
            seed=game_seed,
            starting_actor=starting_actor,
            max_steps=max_steps,
        )
        baseline_result = play_match(
            cards,
            HeuristicAgent(),
            HeuristicAgent(),
            seed=game_seed,
            starting_actor=starting_actor,
            max_steps=max_steps,
        )
        llm_summary = player_agent.summary()
        all_llm_summaries.append(llm_summary)
        for card_id in llm_result["played_by"]["player"]:
            llm_card_plays[card_id] += 1
        for card_id in baseline_result["played_by"]["player"]:
            baseline_card_plays[card_id] += 1
        trace = player_agent.trace()
        all_traces.extend(trace)
        rows.append(
            {
                "seed": game_seed,
                "starting_actor": starting_actor,
                "llm": {
                    "winner": llm_result["winner"],
                    "turns": llm_result["turns"],
                    "steps": llm_result["steps"],
                    "player_hp": llm_result["player_hp"],
                    "enemy_hp": llm_result["enemy_hp"],
                },
                "baseline": {
                    "winner": baseline_result["winner"],
                    "turns": baseline_result["turns"],
                    "steps": baseline_result["steps"],
                    "player_hp": baseline_result["player_hp"],
                    "enemy_hp": baseline_result["enemy_hp"],
                },
                "llm_agent": llm_summary,
                "decisions": trace,
            }
        )

    llm_stats = summarize(rows, "llm")
    baseline_stats = summarize(rows, "baseline")
    calls = sum(item["calls"] for item in all_llm_summaries)
    decisions = sum(item["decisions"] for item in all_llm_summaries)
    valid = sum(item["valid_responses"] for item in all_llm_summaries)
    invalid = sum(item["invalid_responses"] for item in all_llm_summaries)
    fallbacks = sum(item["fallbacks"] for item in all_llm_summaries)
    api_errors = sum(item["api_errors"] for item in all_llm_summaries)
    latencies = [
        value
        for item in all_llm_summaries
        for value in item.get("latencies_ms", [])
        if value > 0
    ]
    p95 = sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
    invalid_examples = [
        example
        for item in all_llm_summaries
        for example in item.get("invalid_examples", [])
    ][:5]

    summary = {
        "agent": agent_name,
        "model": player_model if agent_name == "opencode" else (config.model if agent_name == "llm" else "mock"),
        "plan_turn": effective_plan,
        "prompt_version": all_llm_summaries[0]["prompt_version"] if all_llm_summaries else "unknown",
        "games": games,
        "seed": seed,
        "starting_actor": "alternating",
        "llm": {
            **llm_stats,
            "calls": calls,
            "decisions": decisions,
            "valid_rate": round(valid / max(1, calls), 4),
            "invalid_rate": round(invalid / max(1, calls), 4),
            "fallback_rate": round(fallbacks / max(1, decisions), 4),
            "api_error_rate": round(api_errors / max(1, calls), 4),
            "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p95_latency_ms": round(p95, 2),
            "play_actions": sum(item["play_actions"] for item in all_llm_summaries),
            "end_actions": sum(item["end_actions"] for item in all_llm_summaries),
            "invalid_examples": invalid_examples,
        },
        "baseline": baseline_stats,
        "delta_win_rate": round(llm_stats["win_rate"] - baseline_stats["win_rate"], 4),
        "llm_card_plays": dict(llm_card_plays.most_common()),
        "baseline_card_plays": dict(baseline_card_plays.most_common()),
        "note": (
            "mock 结果只用于验证评测管线，不代表真实 LLM 表现。"
            if agent_name == "mock"
            else "真实 LLM 评测；同种子与 heuristic 基线配对。"
        ),
    }
    return {"summary": summary, "games": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="CardForge LLM-as-player study")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--cards", default=None, help="optional card-set JSON")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agent", choices=["llm", "opencode", "mock"], default="opencode")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--player-model", default=DEFAULT_PLAYER_MODEL)
    parser.add_argument("--isolation-dir", default="/tmp/opencode/cardforge-llm-player")
    parser.add_argument("--plan-turn", action="store_true", help="ask for a whole-turn card sequence (opencode uses this by default)")
    parser.add_argument("--prompt-version", choices=["v1-neutral", "v2-guided"], default="v1-neutral")
    parser.add_argument("--out", default="results/llm_playtest.json")
    args = parser.parse_args()

    if args.cards:
        card_set = load_card_set(args.cards)
    else:
        card_set = generate_cards(args.theme, count=24, allow_llm=False, seed=args.seed)

    payload = run_study(
        card_set.cards,
        games=args.games,
        seed=args.seed,
        agent_name=args.agent,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_steps=args.max_steps,
        player_model=args.player_model,
        isolation_dir=args.isolation_dir,
        plan_turn=args.plan_turn,
        prompt_version=args.prompt_version,
    )
    summary = payload["summary"]
    print(json.dumps({k: v for k, v in summary.items() if k not in {"llm_card_plays", "baseline_card_plays"}}, ensure_ascii=False, indent=2))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
