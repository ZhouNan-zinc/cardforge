"""Multi-round auto-balance convergence experiment.

Each round uses the same seed and 1000 games. The card set is updated by one
rule-based balance pass after each measurement. This separates "the balancer
works" from "the balancer converges", which the single-round experiment cannot
show.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from .agents import simulate
from .generator import DEFAULT_THEME, balance_cards, generate_cards
from .balance_experiment import card_changes, summarize_card_stats


def main() -> None:
    parser = argparse.ArgumentParser(description="CardForge multi-round balance convergence")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="results/balance-rounds.json")
    args = parser.parse_args()

    card_set = generate_cards(args.theme, count=24, allow_llm=False, seed=args.seed)
    rounds = []
    previous_cards = card_set
    for round_no in range(args.rounds + 1):
        stats = simulate(card_set.cards, games=args.games, agent="heuristic", seed=args.seed)
        rounds.append({
            "round": round_no,
            "summary": {k: v for k, v in stats.items() if k != "card_stats"},
            "card_metrics": summarize_card_stats(stats),
            "changes_from_previous": card_changes(previous_cards, card_set) if round_no else {"cost": [], "effects": []},
        })
        if round_no < args.rounds:
            previous_cards = card_set
            card_set = balance_cards(card_set, stats)

    payload = {
        "setup": {"theme": args.theme, "rounds": args.rounds, "games": args.games, "seed": args.seed, "cards": 24},
        "rounds": rounds,
        "final_card_set": card_set.model_dump(),
        "note": "Same seed and 1000 games per round; one rule-based adjustment per round.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([
        {"round": r["round"], **r["summary"], **r["card_metrics"], "cost_changes": len(r["changes_from_previous"]["cost"])}
        for r in rounds
    ], ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
