"""Run-level simulation: style + 4 map layers + boss + rewards/boons."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from .agents import HeuristicAgent
from .generator import DEFAULT_THEME, generate_cards
from .run import ENEMIES, Run


def simulate_run(cards, seed: int) -> dict:
    run = Run(cards, seed=seed)
    rng = random.Random(seed + 17)
    run.choose_scarf(rng.randrange(3))
    agent = HeuristicAgent()
    steps = 0
    while run.phase not in {"victory", "defeat"} and steps < 4000:
        steps += 1
        if run.phase == "battle" and run.game is not None:
            game = run.game
            if game.winner:
                run.after_player_action()
                continue
            if game.active == "player":
                choice = agent.choose(game, "player")
                if choice is None:
                    game.end_turn("player")
                    game.enemy_take_turn()
                else:
                    try:
                        game.play_card("player", choice)
                    except ValueError:
                        game.end_turn("player")
                        game.enemy_take_turn()
                run.after_player_action()
            else:
                game.enemy_take_turn()
                run.after_player_action()
        elif run.phase == "reward":
            run.choose_reward(rng.randrange(len(run.reward_options)))
        elif run.phase == "boon":
            run.choose_boon(rng.randrange(len(run.boon_options)))
        elif run.phase == "upgrade":
            run.choose_upgrade(rng.randrange(len(run.upgrade_options)))
        elif run.phase == "map":
            # Neutral route sampling: do not hard-code a battle preference.
            run.choose_map(rng.randrange(len(run.map_options)))
        elif run.phase == "rest":
            run.choose_rest(0)
        elif run.phase == "shop":
            run.leave_shop()
        elif run.phase == "event":
            run.choose_event(0)
        elif run.phase == "remove":
            run.choose_remove(0)
        else:
            break
    return {
        "phase": run.phase,
        "layer_index": run.layer_index,
        "battles": 5,
        "player_hp": run.player_hp,
        "max_hp": run.max_hp,
        "deck_size": len(run.deck),
        "style": run.style_id,
        "boons": run.boons,
        "upgraded": sum(1 for card in run.deck if card.upgraded),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CardForge run-level simulation")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="results/run_simulation.json")
    args = parser.parse_args()

    card_set = generate_cards(args.theme, count=24, allow_llm=False, seed=args.seed)
    results = [simulate_run(card_set.cards, seed=args.seed + i) for i in range(args.runs)]

    victories = sum(1 for r in results if r["phase"] == "victory")
    defeats = sum(1 for r in results if r["phase"] == "defeat")
    styles = Counter(r["style"] for r in results)
    boons = Counter(b for r in results for b in r["boons"])
    upgraded = sum(r["upgraded"] for r in results)
    summary = {
        "runs": args.runs,
        "victories": victories,
        "defeats": defeats,
        "victory_rate": round(victories / max(1, args.runs), 4),
        "defeat_rate": round(defeats / max(1, args.runs), 4),
        "avg_layer_reached": round(sum(r["layer_index"] for r in results) / max(1, args.runs), 2),
        "avg_deck_size": round(sum(r["deck_size"] for r in results) / max(1, args.runs), 2),
        "avg_upgraded": round(upgraded / max(1, args.runs), 2),
        "styles": dict(styles),
        "boons": dict(boons),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
