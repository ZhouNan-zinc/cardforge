"""CLI: generate a card set, simulate games, and optionally balance it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents import simulate
from .generator import DEFAULT_THEME, balance_cards, generate_cards, load_card_set, save_card_set


def main() -> None:
    parser = argparse.ArgumentParser(description="CardForge headless simulation")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--cards", type=str, default=None, help="load an existing card set JSON")
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--agent", choices=["random", "heuristic"], default="heuristic")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="results/simulation.json")
    parser.add_argument("--balance", action="store_true", help="apply one balance pass and save")
    args = parser.parse_args()

    if args.cards:
        card_set = load_card_set(args.cards)
    else:
        card_set = generate_cards(args.theme, count=args.count, allow_llm=False, seed=args.seed)

    stats = simulate(card_set.cards, games=args.games, agent=args.agent, seed=args.seed)
    print(json.dumps({k: v for k, v in stats.items() if k != "card_stats"}, ensure_ascii=False, indent=2))

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"card_set": card_set.model_dump(), "stats": stats}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {path}")

    if args.balance:
        balanced = balance_cards(card_set, stats)
        out = path.with_name("balanced_cards.json")
        save_card_set(balanced, out)
        print(f"balanced card set saved: {out}")


if __name__ == "__main__":
    main()
