"""Policy search for automated red-teaming.

Unlike the hand-written ``combat_avoider`` policy in ``src.redteam``, this
module does not contain a rule such as "prefer events" or "avoid battles".
It searches a vector of route/reward weights, keeps the best policy in each
behavior cell (MAP-Elites style), and only afterwards inspects which cells won.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .generator import DEFAULT_THEME, generate_cards
from .models import CardSet
from .redteam import play_run
from .run import LEGACY_MAP_EDGES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"

NODE_TYPES = ["battle", "elite", "event", "shop", "rest", "treasure"]
EFFECT_TYPES = ["damage", "block", "draw", "energy", "heal", "buff", "debuff"]
BOON_TYPES = ["max_hp", "energy", "draw", "strength", "heal", "upgrade"]


@dataclass
class Genome:
    node_weights: dict[str, float] = field(default_factory=dict)
    effect_weights: dict[str, float] = field(default_factory=dict)
    boon_weights: dict[str, float] = field(default_factory=dict)
    temperature: float = 0.0

    @classmethod
    def random(cls, rng: random.Random) -> "Genome":
        return cls(
            node_weights={key: rng.gauss(0.0, 1.0) for key in NODE_TYPES},
            effect_weights={key: rng.gauss(0.0, 1.0) for key in EFFECT_TYPES},
            boon_weights={key: rng.gauss(0.0, 1.0) for key in BOON_TYPES},
            temperature=max(0.0, rng.gauss(0.08, 0.06)),
        )

    def mutate(self, rng: random.Random) -> "Genome":
        child = copy.deepcopy(self)
        for group_name in ("node_weights", "effect_weights", "boon_weights"):
            group = getattr(child, group_name)
            for key in group:
                roll = rng.random()
                if roll < 0.08:
                    group[key] = rng.gauss(0.0, 1.2)
                elif roll < 0.45:
                    group[key] = max(-3.0, min(3.0, group[key] + rng.gauss(0.0, 0.6)))
        child.temperature = max(0.0, min(0.5, child.temperature + rng.gauss(0.0, 0.03)))
        return child


class GenomePolicy:
    """A policy whose behavior is determined only by the genome weights."""

    def __init__(self, genome: Genome) -> None:
        self.genome = genome

    def choose_style(self, run) -> int:
        return 0

    def choose_map(self, run) -> int:
        if not run.map_options:
            return 0
        scores = []
        for index, node in enumerate(run.map_options):
            score = self.genome.node_weights.get(node.get("id"), 0.0)
            score += run.rng.gauss(0.0, self.genome.temperature)
            scores.append((score, index))
        return max(scores, key=lambda item: item[0])[1]

    def choose_reward(self, run) -> int:
        if not run.reward_options:
            return 0
        def score(card) -> float:
            value = 0.0
            for effect in card.effects:
                value += self.genome.effect_weights.get(effect.type.value, 0.0) * effect.amount
            return value / max(1, card.cost)
        return max(range(len(run.reward_options)), key=lambda i: score(run.reward_options[i]))

    def choose_boon(self, run) -> int:
        if not run.boon_options:
            return 0
        return max(
            range(len(run.boon_options)),
            key=lambda i: self.genome.boon_weights.get(run.boon_options[i].get("id"), 0.0),
        )

    def choose_rest(self, run) -> int:
        return 0 if run.player_hp < run.max_hp * 0.6 else 1

    def choose_shop(self, run) -> dict:
        return {"action": "leave"}

    def choose_event(self, run) -> int:
        return run.rng.randrange(len(run.event_options)) if run.event_options else 0

    def choose_upgrade(self, run) -> int:
        return run.rng.randrange(len(run.upgrade_options)) if run.upgrade_options else 0

    def choose_remove(self, run) -> int:
        return run.rng.randrange(len(run.remove_options)) if run.remove_options else 0


def behavior_key(summary: dict) -> tuple[int, int, int]:
    """Descriptors used for quality-diversity. They do not enter the action policy."""
    combat = min(3, int(round(summary["avg_combat_nodes"])))
    draw = 0 if summary["avg_draw_cards"] < 1 else 1 if summary["avg_draw_cards"] < 3 else 2
    deck = 0 if summary["avg_deck_size"] <= 12 else 1 if summary["avg_deck_size"] <= 15 else 2
    return combat, draw, deck


def evaluate(genome: Genome, cards, map_edges, games: int, seed: int) -> dict:
    policy = GenomePolicy(genome)
    rows = [play_run(cards, seed + i, policy=policy, map_edges=map_edges) for i in range(games)]
    wins = sum(1 for row in rows if row["victory"])
    return {
        "games": games,
        "wins": wins,
        "win_rate": round(wins / max(1, games), 4),
        "avg_layer": round(sum(row["layer_index"] for row in rows) / max(1, games), 2),
        "avg_combat_nodes": round(sum(row["combat_nodes"] for row in rows) / max(1, games), 2),
        "avg_draw_cards": round(sum(row["draw_cards"] for row in rows) / max(1, games), 2),
        "avg_deck_size": round(sum(row["deck_size"] for row in rows) / max(1, games), 2),
        "zero_combat_wins": sum(1 for row in rows if row["zero_combat_win"]),
        "light_combat_wins": sum(1 for row in rows if row["light_combat_win"]),
    }


def search(cards, map_edges, generations: int, population: int, games: int, seed: int) -> dict:
    rng = random.Random(seed)
    genomes = [Genome.random(rng) for _ in range(population)]
    archive: dict[tuple[int, int, int], dict] = {}
    history = []
    for generation in range(generations + 1):
        evaluated = []
        for genome in genomes:
            summary = evaluate(genome, cards, map_edges, games, seed + generation * 10000)
            key = behavior_key(summary)
            record = {"generation": generation, "key": key, "summary": summary, "genome": asdict(genome)}
            evaluated.append((summary["win_rate"], key, genome, record))
            if key not in archive or summary["win_rate"] > archive[key]["summary"]["win_rate"]:
                archive[key] = record
        history.append({
            "generation": generation,
            "best_win_rate": max(item[0] for item in evaluated),
            "cells": len(archive),
            "best": max(evaluated, key=lambda item: item[0])[3],
        })
        if generation == generations:
            break
        ranked = sorted(evaluated, key=lambda item: item[0], reverse=True)
        parents = [item[2] for item in ranked[: max(2, population // 4)]]
        genomes = []
        while len(genomes) < population:
            if rng.random() < 0.25:
                genomes.append(Genome.random(rng))
            else:
                genomes.append(rng.choice(parents).mutate(rng))
    return {"archive": list(archive.values()), "history": history}


def load_sets(kind: str) -> list[tuple[str, list]]:
    template = generate_cards(DEFAULT_THEME, count=24, allow_llm=False, seed=42)
    sets = [("template", template.cards)]
    if kind == "all":
        for path in sorted(DOCS_DIR.glob("llm-generation-24*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            sets.append((path.stem.replace("llm-generation-", "llm-"), CardSet.model_validate(payload["card_set"]).cards))
    return sets


def main() -> None:
    parser = argparse.ArgumentParser(description="Search for red-team policies")
    parser.add_argument("--games", type=int, default=20, help="games per candidate during search")
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--validate-games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sets", choices=["template", "all"], default="template")
    parser.add_argument("--map", choices=["current", "legacy", "both"], default="both")
    parser.add_argument("--out", default="results/redteam-search.json")
    args = parser.parse_args()

    results = {}
    for set_name, cards in load_sets(args.sets):
        for map_name, edges in (
            [("current", None), ("legacy_all_connected", LEGACY_MAP_EDGES)]
            if args.map == "both"
            else [("current", None)] if args.map == "current" else [("legacy_all_connected", LEGACY_MAP_EDGES)]
        ):
            print(f"searching {set_name} / {map_name}")
            result = search(cards, edges, args.generations, args.population, args.games, args.seed)
            # Re-evaluate every archive cell on a disjoint seed range.
            for entry in result["archive"]:
                genome = Genome(**entry["genome"])
                entry["validation"] = evaluate(
                    genome, cards, edges, args.validate_games, args.seed + 900000
                )
            results[f"{set_name}|{map_name}"] = result

    payload = {
        "setup": {
            "theme": DEFAULT_THEME,
            "sets": args.sets,
            "map": args.map,
            "generations": args.generations,
            "population": args.population,
            "search_games": args.games,
            "validate_games": args.validate_games,
            "seed": args.seed,
            "note": "Policy weights are searched; no explicit combat-avoidance rule is given to the agent.",
        },
        "results": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for key, result in results.items():
        print(f"\n{key}")
        for entry in sorted(result["archive"], key=lambda item: item["validation"]["win_rate"], reverse=True):
            v = entry["validation"]
            print(
                f"  cell={entry['key']} win={v['win_rate']:.2f} "
                f"combat={v['avg_combat_nodes']:.2f} draw={v['avg_draw_cards']:.2f} "
                f"zero={v['zero_combat_wins']} light={v['light_combat_wins']}"
            )
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
