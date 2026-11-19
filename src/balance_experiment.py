"""Clean before/after experiment for the rule-based auto-balancer.

The same card set, agent and random seed are used before and after one balance
pass. This is the experiment that supports the project's core claim: agent
statistics -> automatic adjustment -> re-measurement.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from .agents import simulate
from .generator import DEFAULT_THEME, balance_cards, generate_cards


def summarize_card_stats(stats: dict) -> dict:
    entries = [
        entry for entry in stats.get("card_stats", {}).values()
        if entry.get("plays", 0) >= 20
    ]
    rates = [entry["win_rate"] for entry in entries]
    return {
        "cards_seen": len(entries),
        "mean_card_win_rate": round(statistics.mean(rates), 4) if rates else 0.0,
        "std_card_win_rate": round(statistics.pstdev(rates), 4) if len(rates) > 1 else 0.0,
        "min_card_win_rate": round(min(rates), 4) if rates else 0.0,
        "max_card_win_rate": round(max(rates), 4) if rates else 0.0,
        "strong_cards": sum(1 for rate in rates if rate >= 0.62),
        "weak_cards": sum(1 for rate in rates if rate <= 0.38),
    }


def card_changes(before, after) -> dict:
    before_by_id = {card.id: card for card in before.cards}
    after_by_id = {card.id: card for card in after.cards}
    cost_changes = []
    effect_changes = []
    for card_id in before_by_id:
        old, new = before_by_id[card_id], after_by_id[card_id]
        if old.cost != new.cost:
            cost_changes.append({"id": card_id, "name": old.name, "old": old.cost, "new": new.cost})
        old_effects = [(e.type.value, e.amount, e.stat) for e in old.effects]
        new_effects = [(e.type.value, e.amount, e.stat) for e in new.effects]
        if old_effects != new_effects:
            effect_changes.append({"id": card_id, "name": old.name, "old": old_effects, "new": new_effects})
    return {"cost": cost_changes, "effects": effect_changes}


def main() -> None:
    parser = argparse.ArgumentParser(description="CardForge auto-balance before/after")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--games", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="results/balance-experiment.json")
    args = parser.parse_args()

    card_set = generate_cards(args.theme, count=24, allow_llm=False, seed=args.seed)
    before = simulate(card_set.cards, games=args.games, agent="heuristic", seed=args.seed)
    balanced = balance_cards(card_set, before)
    after = simulate(balanced.cards, games=args.games, agent="heuristic", seed=args.seed)

    payload = {
        "setup": {
            "theme": args.theme,
            "games": args.games,
            "seed": args.seed,
            "agent": "heuristic",
            "cards": len(card_set.cards),
        },
        "before": {
            "summary": {k: v for k, v in before.items() if k != "card_stats"},
            "card_metrics": summarize_card_stats(before),
            "card_stats": before["card_stats"],
        },
        "after": {
            "summary": {k: v for k, v in after.items() if k != "card_stats"},
            "card_metrics": summarize_card_stats(after),
            "card_stats": after["card_stats"],
        },
        "changes": card_changes(card_set, balanced),
        "balanced_card_set": balanced.model_dump(),
        "note": "One rule-based balance pass; same seed and games before/after. Small sample caveat applies.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "before": {**payload["before"]["summary"], **payload["before"]["card_metrics"]},
        "after": {**payload["after"]["summary"], **payload["after"]["card_metrics"]},
        "changes": {"cost": len(payload["changes"]["cost"]), "effects": len(payload["changes"]["effects"])},
    }, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
