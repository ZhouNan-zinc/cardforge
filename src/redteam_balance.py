"""Balance-vs-exploitability ablation.

Runs the same red-team policies before and after the rule-based balance pass,
on both the old fully connected map and the current directed map.  This tests
whether improving card-level win-rate statistics also removes structural
degenerate strategies.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .generator import generate_cards
from .models import CardSet
from .redteam import RedTeamPolicy, play_run, summarize
from .run import LEGACY_MAP_EDGES

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_sets() -> dict[str, list]:
    before = generate_cards("霜旋", count=24, allow_llm=False, seed=42).cards
    payload = json.loads((PROJECT_ROOT / "data/balance-final.json").read_text(encoding="utf-8"))
    after = CardSet.model_validate(payload["balanced_card_set"]).cards
    return {"before_balance": before, "after_balance": after}


def main() -> None:
    parser = argparse.ArgumentParser(description="Balance vs exploitability ablation")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="results/redteam-balance-attribution.json")
    args = parser.parse_args()

    sets = load_sets()
    policies = [
        ("balanced", "value"),
        ("combat_avoider", "value"),
        ("draw_engine", "draw_engine"),
    ]
    conditions = []
    for set_name, cards in sets.items():
        for map_name, map_edges in (("legacy_all_connected", LEGACY_MAP_EDGES), ("current", None)):
            for mode, reward_mode in policies:
                policy = RedTeamPolicy(mode=mode, reward_mode=reward_mode)
                rows = [
                    play_run(cards, args.seed + i, policy=policy, map_edges=map_edges)
                    for i in range(args.games)
                ]
                conditions.append({
                    "card_set": set_name,
                    "map": map_name,
                    "policy": mode,
                    **summarize(rows),
                })
    payload = {
        "setup": {
            "theme": "霜旋",
            "games": args.games,
            "seed": args.seed,
            "policies": [mode for mode, _ in policies],
            "note": "The before/after balance card sets use the same red-team policies and map ablation.",
        },
        "conditions": conditions,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in conditions:
        print(f"{item['card_set']:14} {item['map']:20} {item['policy']:16} "
              f"win={item['win_rate']:.2f} zero={item['zero_combat_wins']} "
              f"light={item['light_combat_wins']} combats={item['avg_combat_nodes']:.2f}")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
