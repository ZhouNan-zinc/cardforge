"""LLM red-team strategy proposer.

The LLM does not choose individual game actions here.  It proposes a small
policy (route/reward weights), the simulator executes it, and independent
seeds estimate whether the proposal is strong or unusually degenerate.  This
keeps the LLM in the loop without giving it hidden state or asking the
researcher to hand-write the exploit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .generator import LLMConfig, _extract_json, generate_cards
from .opencode_chat import DEFAULT_PLAYER_MODEL, OpenCodeChat
from .redteam_search import (
    BOON_TYPES,
    EFFECT_TYPES,
    NODE_TYPES,
    Genome,
    evaluate,
)
from .run import LEGACY_MAP_EDGES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"

SYSTEM = (
    "你是卡牌游戏的自动红队策略设计助手。"
    "你只看到公开规则，不读取代码、日志、seed、未来地图或项目文件。"
    "只输出一个 JSON 对象，不要 Markdown，不要解释。"
)

PROMPT = """你在为一个 24 卡、4 层有向地图的卡牌 roguelike 设计策略。
玩家每回合 3 能量、抽 5 张牌，敌人有意图；地图节点包括 battle / elite / event / shop / rest / treasure，最后有 Boss。
请提出 3 个不同的候选策略，目标是提高通关率，同时允许尝试非直觉的路线和奖励偏好。不要写代码，不要提任何具体漏洞名称。

只输出 JSON：
{
  "candidates": [
    {
      "name": "short-name",
      "node_weights": {"battle": -2..2, "elite": -2..2, "event": -2..2, "shop": -2..2, "rest": -2..2, "treasure": -2..2},
      "effect_weights": {"damage": -2..2, "block": -2..2, "draw": -2..2, "energy": -2..2, "heal": -2..2, "buff": -2..2, "debuff": -2..2},
      "boon_weights": {"max_hp": -2..2, "energy": -2..2, "draw": -2..2, "strength": -2..2, "heal": -2..2, "upgrade": -2..2},
      "temperature": 0..0.3
    }
  ]
}
不要输出其他字段。"""


def _number(value, default: float = 0.0) -> float:
    try:
        return max(-3.0, min(3.0, float(value)))
    except (TypeError, ValueError):
        return default


def parse_candidate(raw: dict, index: int) -> Genome:
    node = raw.get("node_weights") or {}
    effect = raw.get("effect_weights") or {}
    boon = raw.get("boon_weights") or {}
    return Genome(
        node_weights={key: _number(node.get(key, 0)) for key in NODE_TYPES},
        effect_weights={key: _number(effect.get(key, 0)) for key in EFFECT_TYPES},
        boon_weights={key: _number(boon.get(key, 0)) for key in BOON_TYPES},
        temperature=max(0.0, min(0.3, _number(raw.get("temperature", 0.05), 0.05))),
    )


def propose(model: str, timeout: int) -> tuple[list[dict], str | None]:
    chat = OpenCodeChat(
        model=model,
        isolation_dir="/tmp/opencode/cardforge-llm-redteam",
        timeout=timeout,
        system=SYSTEM,
    )
    content = chat([{"role": "user", "content": PROMPT}], LLMConfig())
    if not content:
        return [], None
    try:
        payload = _extract_json(content)
    except Exception:
        return [], content
    candidates = payload.get("candidates", [])
    if isinstance(payload, dict) and not candidates and "node_weights" in payload:
        candidates = [payload]
    if not isinstance(candidates, list):
        return [], content
    return [item for item in candidates if isinstance(item, dict)], content


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-proposed red-team strategies")
    parser.add_argument("--model", default=DEFAULT_PLAYER_MODEL)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seed-count", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--out", default="results/llm-redteam-results.json")
    args = parser.parse_args()

    raw_candidates, raw_output = propose(args.model, args.timeout)
    cards = generate_cards("霜旋", count=24, allow_llm=False, seed=42).cards
    results = []
    for index, raw in enumerate(raw_candidates):
        genome = parse_candidate(raw, index)
        current_runs = [
            evaluate(genome, cards, None, args.games, args.seed + offset)
            for offset in range(args.seed_count)
        ]
        legacy_runs = [
            evaluate(genome, cards, LEGACY_MAP_EDGES, args.games, args.seed + offset)
            for offset in range(args.seed_count)
        ]

        def aggregate(runs: list[dict]) -> dict:
            games = sum(run["games"] for run in runs)
            wins = sum(run["wins"] for run in runs)
            return {
                "seeds": args.seed_count,
                "games": games,
                "wins": wins,
                "win_rate": round(wins / max(1, games), 4),
                "avg_combat_nodes": round(
                    sum(run["avg_combat_nodes"] * run["games"] for run in runs) / max(1, games), 2
                ),
                "avg_draw_cards": round(
                    sum(run["avg_draw_cards"] * run["games"] for run in runs) / max(1, games), 2
                ),
                "zero_combat_wins": sum(run["zero_combat_wins"] for run in runs),
                "light_combat_wins": sum(run["light_combat_wins"] for run in runs),
                "per_seed": runs,
            }

        item = {
            "index": index,
            "name": str(raw.get("name", f"llm-{index}"))[:80],
            "genome": genome.__dict__,
            "current": aggregate(current_runs),
            "legacy_all_connected": aggregate(legacy_runs),
        }
        results.append(item)

    payload = {
        "setup": {
            "model": args.model,
            "games": args.games,
            "seed": args.seed,
            "seed_count": args.seed_count,
            "candidates": len(raw_candidates),
            "note": "LLM proposes only a policy; simulation validates it without hidden state.",
        },
        "raw_output": raw_output,
        "results": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
