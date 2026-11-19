"""Automated red-team experiments for CardForge.

The normal balance pipeline asks: "is the average win rate near 50%?"
The red-team asks a different question: "can a policy find a degenerate
strategy that still wins?"  This module intentionally uses only the public
``Run`` API and the deterministic battle agent, so the experiments are cheap
and reproducible.  LLM players can be added later as another policy family.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import Counter
from pathlib import Path

from .agents import HeuristicAgent
from .generator import DEFAULT_THEME, generate_cards
from .llm_run_agent import HeuristicRunPolicy
from .models import CardSet
from .run import LEGACY_MAP_EDGES, Run

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"

COMBAT_NODES = {"battle", "elite"}


class RedTeamPolicy(HeuristicRunPolicy):
    """Run policy with deliberately exploitable route/reward preferences."""

    def __init__(self, mode: str = "balanced", reward_mode: str = "value") -> None:
        super().__init__(route_mode="balanced")
        self.mode = mode
        self.reward_mode = reward_mode

    def choose_map(self, run: Run) -> int:
        options = run.map_options
        if not options:
            return 0
        if self.mode == "random":
            return run.rng.randrange(len(options))
        if self.mode == "combat_avoider":
            order = ["event", "shop", "rest", "treasure", "battle", "elite"]
        elif self.mode == "elite_rusher":
            order = ["elite", "battle", "shop", "event", "rest", "treasure"]
        else:
            return super().choose_map(run)
        for wanted in order:
            for index, node in enumerate(options):
                if node.get("id") == wanted:
                    return index
        return 0

    def choose_reward(self, run: Run) -> int:
        if self.reward_mode == "random":
            return run.rng.randrange(len(run.reward_options)) if run.reward_options else 0
        if not run.reward_options:
            return 0
        if self.reward_mode == "draw_engine":
            def draw_value(card) -> float:
                value = 0.0
                for effect in card.effects:
                    if effect.type.value == "draw":
                        value += effect.amount * 4.0
                    elif effect.type.value == "energy":
                        value += effect.amount * 5.0
                    elif effect.type.value == "block":
                        value += effect.amount * 0.4
                    elif effect.type.value == "damage":
                        value += effect.amount * 0.5
                return value / max(1, card.cost)
            return max(range(len(run.reward_options)), key=lambda i: draw_value(run.reward_options[i]))
        if self.reward_mode == "damage":
            def damage_value(card) -> float:
                return sum(
                    effect.amount * (1.2 if effect.type.value == "damage" else 0.2)
                    for effect in card.effects
                ) / max(1, card.cost)
            return max(range(len(run.reward_options)), key=lambda i: damage_value(run.reward_options[i]))
        return super().choose_reward(run)

    def choose_boon(self, run: Run) -> int:
        if self.reward_mode == "draw_engine" and run.boon_options:
            priorities = {"draw": 0, "energy": 1, "max_hp": 2, "heal": 3, "strength": 4}
            return min(
                range(len(run.boon_options)),
                key=lambda i: priorities.get(run.boon_options[i].get("id"), 9),
            )
        return super().choose_boon(run)


def play_run(
    cards,
    seed: int,
    policy: RedTeamPolicy,
    map_edges=None,
    max_steps: int = 4000,
) -> dict:
    """Run one complete run and return red-team-observable metrics."""
    run = Run(cards, seed=seed, map_edges=map_edges)
    run.choose_scarf(policy.choose_style(run))
    battle_agent = HeuristicAgent()
    shop_moves = 0
    steps = 0

    while run.phase not in {"victory", "defeat"} and steps < max_steps:
        steps += 1
        try:
            if run.phase == "map":
                run.choose_map(policy.choose_map(run))
            elif run.phase == "battle" and run.game is not None:
                game = run.game
                if game.winner:
                    run.after_player_action()
                    continue
                if game.active == "player":
                    choice = battle_agent.choose(game, "player")
                    if choice is None:
                        game.end_turn("player")
                    else:
                        game.play_card("player", choice)
                else:
                    game.enemy_take_turn()
                run.after_player_action()
            elif run.phase == "reward":
                run.choose_reward(policy.choose_reward(run))
            elif run.phase == "boon":
                run.choose_boon(policy.choose_boon(run))
            elif run.phase == "upgrade":
                run.choose_upgrade(policy.choose_upgrade(run))
            elif run.phase == "rest":
                run.choose_rest(policy.choose_rest(run))
            elif run.phase == "shop":
                shop_moves += 1
                if shop_moves > 8:
                    run.leave_shop()
                    continue
                action = policy.choose_shop(run)
                if action.get("action") == "leave":
                    run.leave_shop()
                elif action.get("action") == "reroll":
                    run.reroll_shop()
                else:
                    run.choose_shop(int(action.get("index", 0)))
            elif run.phase == "event":
                run.choose_event(policy.choose_event(run))
            elif run.phase == "remove":
                run.choose_remove(policy.choose_remove(run))
            else:
                break
        except (ValueError, IndexError) as error:
            run.history.append(f"red-team run interrupted: {error}")
            break

    victory = run.phase == "victory"
    combat_nodes = sum(1 for node in run.map_choices if node in COMBAT_NODES)
    return {
        "seed": seed,
        "phase": run.phase,
        "victory": victory,
        "layer_index": run.layer_index,
        "steps": steps,
        "combat_nodes": combat_nodes,
        "battles_won": run.battles_won,
        "player_hp": run.player_hp,
        "max_hp": run.max_hp,
        "full_hp_win": victory and run.player_hp >= run.max_hp,
        "zero_combat_win": victory and combat_nodes == 0,
        "light_combat_win": victory and combat_nodes <= 1,
        "deck_size": len(run.deck),
        "draw_cards": sum(
            1 for card in run.deck if any(effect.type.value == "draw" for effect in card.effects)
        ),
        "gold": run.gold,
        "map_choices": list(run.map_choices),
    }


def summarize(rows: list[dict]) -> dict:
    wins = [row for row in rows if row["victory"]]
    return {
        "games": len(rows),
        "wins": len(wins),
        "win_rate": round(len(wins) / max(1, len(rows)), 4),
        "avg_layer": round(statistics.mean(row["layer_index"] for row in rows), 2) if rows else 0.0,
        "avg_combat_nodes": round(statistics.mean(row["combat_nodes"] for row in rows), 2) if rows else 0.0,
        "avg_deck_size": round(statistics.mean(row["deck_size"] for row in rows), 2) if rows else 0.0,
        "avg_draw_cards": round(statistics.mean(row["draw_cards"] for row in rows), 2) if rows else 0.0,
        "zero_combat_wins": sum(1 for row in rows if row["zero_combat_win"]),
        "light_combat_wins": sum(1 for row in rows if row["light_combat_win"]),
        "full_hp_wins": sum(1 for row in rows if row["full_hp_win"]),
        "route_types": dict(Counter(node for row in rows for node in row["map_choices"])),
    }


def load_card_sets(kind: str) -> list[tuple[str, list]]:
    template = generate_cards(DEFAULT_THEME, count=24, allow_llm=False, seed=42)
    sets: list[tuple[str, list]] = [("template", template.cards)]
    if kind == "all":
        for path in sorted(DOCS_DIR.glob("llm-generation-24*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            card_set = CardSet.model_validate(payload["card_set"])
            sets.append((path.stem.replace("llm-generation-", "llm-"), card_set.cards))
    return sets


def main() -> None:
    parser = argparse.ArgumentParser(description="CardForge automated red-team")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sets", choices=["template", "all"], default="template")
    parser.add_argument("--out", default="results/redteam-results.json")
    parser.add_argument("--legacy-map", action="store_true", help="also run the old fully connected map as an ablation")
    args = parser.parse_args()

    policy_specs = [
        ("balanced", "value"),
        ("combat_avoider", "value"),
        ("elite_rusher", "value"),
        ("draw_engine", "draw_engine"),
        ("random", "random"),
    ]
    sets = load_card_sets(args.sets)
    conditions = []
    rows_by_condition = {}
    for set_name, cards in sets:
        for map_name, map_edges in (
            [("current", None)] + ([("legacy_all_connected", LEGACY_MAP_EDGES)] if args.legacy_map else [])
        ):
            for mode, reward_mode in policy_specs:
                policy = RedTeamPolicy(mode=mode, reward_mode=reward_mode)
                rows = [
                    play_run(cards, seed=args.seed + i, policy=policy, map_edges=map_edges)
                    for i in range(args.games)
                ]
                key = f"{set_name}|{map_name}|{mode}"
                rows_by_condition[key] = rows
                conditions.append(
                    {
                        "card_set": set_name,
                        "map": map_name,
                        "policy": mode,
                        "reward": reward_mode,
                        **summarize(rows),
                    }
                )

    payload = {
        "setup": {
            "theme": args.theme,
            "games": args.games,
            "seed": args.seed,
            "card_sets": [name for name, _ in sets],
            "policies": [mode for mode, _ in policy_specs],
            "legacy_map": args.legacy_map,
        },
        "conditions": conditions,
        "examples": {
            key: [row for row in rows if row["light_combat_win"] or row["zero_combat_win"]][:3]
            for key, rows in rows_by_condition.items()
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(conditions, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
