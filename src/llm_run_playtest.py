"""Full-run LLM-player evaluation (long-term + optional battle).

Conditions:
    --battle heuristic --longterm heuristic   baseline
    --battle llm       --longterm heuristic   tactical-only
    --battle llm       --longterm llm         full LLM player

This is an evaluation module, not part of the core generation/balancing code.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
from collections import Counter
from pathlib import Path

from .agents import HeuristicAgent
from .generator import DEFAULT_THEME, generate_cards
from .llm_agent import LLMAgent
from .llm_run_agent import HeuristicRunPolicy, LLMRunAgent
from .opencode_chat import DEFAULT_PLAYER_MODEL, OpenCodeChat
from .run import MAP_LAYERS, POTIONS_BY_ID, RELICS_BY_ID, Run


def _battle_stats(summaries: list[dict]) -> dict:
    if not summaries:
        return {"agents": 0, "calls": 0, "decisions": 0, "valid_rate": 0.0, "fallback_rate": 0.0, "avg_latency_ms": 0.0}
    calls = sum(s.get("calls", 0) for s in summaries)
    decisions = sum(s.get("decisions", 0) for s in summaries)
    valid = sum(s.get("valid_responses", 0) for s in summaries)
    invalid = sum(s.get("invalid_responses", 0) for s in summaries)
    fallbacks = sum(s.get("fallbacks", 0) for s in summaries)
    api_errors = sum(s.get("api_errors", 0) for s in summaries)
    latencies = [x for s in summaries for x in s.get("latencies_ms", [])]
    return {
        "agents": len(summaries),
        "calls": calls,
        "decisions": decisions,
        "valid_rate": round(valid / max(1, calls), 4),
        "invalid_rate": round(invalid / max(1, calls), 4),
        "fallback_rate": round(fallbacks / max(1, decisions), 4),
        "api_error_rate": round(api_errors / max(1, calls), 4),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))], 2) if latencies else 0.0,
    }


def run_once(
    cards,
    seed: int,
    battle_mode: str,
    longterm_mode: str,
    player_model: str,
    isolation_dir: str,
    battle_prompt_version: str = "v1-neutral",
    max_steps: int = 300,
    guide: str = "",
    route_mode: str = "balanced",
    legacy_map: bool = False,
) -> dict:
    from .run import LEGACY_MAP_EDGES

    run = Run(cards, seed=seed, map_edges=LEGACY_MAP_EDGES if legacy_map else None)
    longterm = (
        LLMRunAgent(
            chat_fn=OpenCodeChat(model=player_model, isolation_dir=isolation_dir),
            label=player_model,
            prompt_version="v1-neutral",
            guide=guide,
        )
        if longterm_mode == "llm"
        else HeuristicRunPolicy(route_mode=route_mode)
    )
    battle_summaries: list[dict] = []
    battle_agents: list[LLMAgent] = []
    current_battle_agent: LLMAgent | None = None
    current_game = None
    battle_recorded = False
    shop_moves = 0
    steps = 0
    timeout = False

    while run.phase not in {"victory", "defeat"} and steps < max_steps:
        steps += 1
        phase = run.phase
        try:
            if phase == "scarf":
                run.choose_scarf(longterm.choose_style(run))
            elif phase == "map":
                run.choose_map(longterm.choose_map(run))
            elif phase == "reward":
                run.choose_reward(longterm.choose_reward(run))
            elif phase == "boon":
                run.choose_boon(longterm.choose_boon(run))
            elif phase == "rest":
                run.choose_rest(longterm.choose_rest(run))
            elif phase == "event":
                run.choose_event(longterm.choose_event(run))
            elif phase == "upgrade":
                run.choose_upgrade(longterm.choose_upgrade(run))
            elif phase == "remove":
                run.choose_remove(longterm.choose_remove(run))
            elif phase == "shop":
                shop_moves += 1
                if shop_moves > 8:
                    run.leave_shop()
                    continue
                action = longterm.choose_shop(run)
                if action.get("action") == "leave":
                    run.leave_shop()
                elif action.get("action") == "reroll":
                    run.reroll_shop()
                else:
                    run.choose_shop(int(action.get("index", 0)))
            elif phase == "battle":
                game = run.game
                assert game is not None
                if current_game is not game:
                    current_game = game
                    shop_moves = 0
                    battle_recorded = False
                    if battle_mode == "llm":
                        current_battle_agent = LLMAgent(
                            chat_fn=OpenCodeChat(model=player_model, isolation_dir=isolation_dir),
                            label=player_model,
                            plan_turn=True,
                            prompt_version=battle_prompt_version,
                            context_note=(
                                (guide + "\n" + longterm.strategy_memo).strip()
                                if isinstance(longterm, LLMRunAgent)
                                else guide
                            ),
                        )
                        battle_agents.append(current_battle_agent)
                    else:
                        current_battle_agent = None
                if game.winner:
                    run.after_player_action()
                    continue
                if game.active == "player":
                    choice = current_battle_agent.choose(game, "player") if current_battle_agent else HeuristicAgent().choose(game, "player")
                    if choice is None:
                        game.end_turn("player")
                    else:
                        game.play_card("player", choice)
                    run.after_player_action()
                else:
                    game.enemy_take_turn()
                    run.after_player_action()
                if run.phase != "battle" and not battle_recorded:
                    battle_recorded = True
                    if isinstance(longterm, LLMRunAgent):
                        longterm.observe_battle(
                            {
                                "winner": game.winner,
                                "turns": game.turn,
                                "player_hp": game.player.hp,
                                "enemy_hp": game.enemy.hp,
                                "deck_size": len(run.deck),
                            }
                        )
            else:
                break
        except (ValueError, IndexError) as error:
            # A policy/state mismatch should end the run as a failed evaluation
            # rather than corrupting the result.
            run.history.append(f"评测中断：{error}")
            break
    else:
        if run.phase not in {"victory", "defeat"}:
            timeout = True

    battle_summaries = [agent.summary() for agent in battle_agents]
    long_summary = longterm.summary() if isinstance(longterm, LLMRunAgent) else None
    return {
        "seed": seed,
        "phase": run.phase,
        "victory": run.phase == "victory",
        "defeat": run.phase == "defeat",
        "timeout": timeout,
        "layer_index": run.layer_index,
        "steps": steps,
        "player_hp": run.player_hp,
        "max_hp": run.max_hp,
        "gold": run.gold,
        "deck_size": len(run.deck),
        "relics": run.relics,
        "boons": run.boons,
        "potions": run.potions,
        "map_history": run.map_history,
        "longterm": long_summary,
        "battle": _battle_stats(battle_summaries),
        "longterm_trace": longterm.trace() if isinstance(longterm, LLMRunAgent) else [],
    }


def summarize(rows: list[dict]) -> dict:
    games = len(rows)
    wins = sum(1 for row in rows if row["victory"])
    layers = [row["layer_index"] for row in rows]
    decks = [row["deck_size"] for row in rows]
    gold = [row["gold"] for row in rows]
    route_counter: Counter[str] = Counter()
    relic_counter: Counter[str] = Counter()
    boon_counter: Counter[str] = Counter()
    long_summaries = [row["longterm"] for row in rows if row.get("longterm")]
    long_calls = sum(item["calls"] for item in long_summaries)
    long_decisions = sum(item["decisions"] for item in long_summaries)
    long_valid = sum(item["valid_responses"] for item in long_summaries)
    long_invalid = sum(item["invalid_responses"] for item in long_summaries)
    long_fallbacks = sum(item["fallbacks"] for item in long_summaries)
    long_latencies = [x for item in long_summaries for x in item.get("latencies_ms", [])]
    for row in rows:
        for item in row.get("map_history", []):
            for node_id in ["普通战斗", "精英战斗", "休息", "商店", "神秘事件", "宝箱"]:
                if node_id in item:
                    route_counter[node_id] += 1
        for relic in row.get("relics", []):
            relic_counter[relic] += 1
        for boon in row.get("boons", []):
            boon_counter[boon] += 1
    battle_stats = {
        "calls": sum(row["battle"]["calls"] for row in rows),
        "decisions": sum(row["battle"]["decisions"] for row in rows),
        "valid_rate": round(sum(row["battle"]["calls"] * row["battle"]["valid_rate"] for row in rows) / max(1, sum(row["battle"]["calls"] for row in rows)), 4),
        "fallback_rate": round(sum(row["battle"]["decisions"] * row["battle"]["fallback_rate"] for row in rows) / max(1, sum(row["battle"]["decisions"] for row in rows)), 4),
        "avg_latency_ms": round(statistics.mean([row["battle"]["avg_latency_ms"] for row in rows if row["battle"]["calls"]]), 2) if any(row["battle"]["calls"] for row in rows) else 0.0,
    }
    return {
        "games": games,
        "victories": wins,
        "win_rate": round(wins / max(1, games), 4),
        "avg_layer": round(statistics.mean(layers), 2) if layers else 0.0,
        "avg_deck_size": round(statistics.mean(decks), 2) if decks else 0.0,
        "avg_gold": round(statistics.mean(gold), 2) if gold else 0.0,
        "route_types": dict(route_counter),
        "relics": dict(relic_counter),
        "boons": dict(boon_counter),
        "longterm": {
            "calls": long_calls,
            "decisions": long_decisions,
            "valid_rate": round(long_valid / max(1, long_calls), 4) if long_calls else None,
            "invalid_rate": round(long_invalid / max(1, long_calls), 4) if long_calls else None,
            "fallback_rate": round(long_fallbacks / max(1, long_decisions), 4) if long_decisions else None,
            "avg_latency_ms": round(statistics.mean(long_latencies), 2) if long_latencies else 0.0,
            "p95_latency_ms": round(sorted(long_latencies)[min(len(long_latencies) - 1, int(len(long_latencies) * 0.95))], 2) if long_latencies else 0.0,
        } if long_summaries else None,
        "battle": battle_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CardForge full-run LLM evaluation")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--battle", choices=["heuristic", "llm"], default="heuristic")
    parser.add_argument("--longterm", choices=["heuristic", "llm"], default="heuristic")
    parser.add_argument("--player-model", default=DEFAULT_PLAYER_MODEL)
    parser.add_argument("--isolation-dir", default="/tmp/opencode/cardforge-llm-run-player")
    parser.add_argument("--battle-prompt-version", choices=["v1-neutral", "v2-guided"], default="v1-neutral")
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--guide-file", default=None, help="optional public strategy guide text")
    parser.add_argument("--route-mode", choices=["balanced", "value", "random", "battle", "shop", "elite"], default="balanced")
    parser.add_argument("--legacy-map", action="store_true", help="use the old fully connected map for an ablation")
    parser.add_argument("--out", default="results/llm_run_playtest.json")
    args = parser.parse_args()
    if args.longterm == "llm" and shutil.which("opencode") is None:
        raise SystemExit("opencode CLI not found")
    if args.battle == "llm" and shutil.which("opencode") is None:
        raise SystemExit("opencode CLI not found")
    guide = Path(args.guide_file).read_text(encoding="utf-8") if args.guide_file else ""

    card_set = generate_cards(args.theme, count=24, allow_llm=False, seed=args.seed)
    rng = random.Random(args.seed)
    rows = []
    for _ in range(args.games):
        game_seed = rng.randint(0, 10**9)
        rows.append(
            run_once(
                card_set.cards,
                game_seed,
                battle_mode=args.battle,
                longterm_mode=args.longterm,
                player_model=args.player_model,
                isolation_dir=args.isolation_dir,
                battle_prompt_version=args.battle_prompt_version,
                max_steps=args.max_steps,
                guide=guide,
                route_mode=args.route_mode,
                legacy_map=args.legacy_map,
            )
        )
    payload = {
        "condition": {"battle": args.battle, "longterm": args.longterm},
        "model": args.player_model if args.battle == "llm" or args.longterm == "llm" else None,
        "prompt_version": {"battle": args.battle_prompt_version, "longterm": "v1-neutral"},
        "player_model": args.player_model,
        "guide": guide,
        "route_mode": args.route_mode,
        "legacy_map": args.legacy_map,
        "summary": summarize(rows),
        "games": rows,
        "note": "n is a pilot unless expanded; long-term decisions are an evaluation dimension, not part of auto-balancing.",
    }
    print(json.dumps({k: v for k, v in payload["summary"].items() if k != "games"}, ensure_ascii=False, indent=2))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
