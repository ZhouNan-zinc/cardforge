"""Simple agents and headless simulation for CardForge."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Protocol

from .game import Actor, Game
from .models import Card, EffectType


class Agent(Protocol):
    def choose(self, game: Game, actor: Actor) -> int | None:
        ...


class RandomAgent:
    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def choose(self, game: Game, actor: Actor) -> int | None:
        combatant = game.player if actor == "player" else game.enemy
        playable = [i for i, card in enumerate(combatant.hand) if card.cost <= combatant.energy]
        if not playable:
            return None
        if self.rng.random() < 0.08:
            return None
        return self.rng.choice(playable)


class HeuristicAgent:
    def _score(self, game: Game, actor: Actor, card: Card) -> float:
        combatant = game.player if actor == "player" else game.enemy
        opponent = game.enemy if actor == "player" else game.player
        value = 0.0
        for effect in card.effects:
            if effect.type == EffectType.damage:
                value += effect.amount * 1.25 + combatant.strength
                if opponent.vulnerable:
                    value += effect.amount * 0.25
            elif effect.type == EffectType.block:
                value += effect.amount * (1.7 if combatant.hp < 15 else 0.9)
            elif effect.type == EffectType.heal:
                value += effect.amount * (1.8 if combatant.hp < combatant.max_hp * 0.5 else 0.3)
            elif effect.type == EffectType.draw:
                value += effect.amount * 1.6
            elif effect.type == EffectType.energy:
                value += effect.amount * 2.2
            elif effect.type == EffectType.buff:
                value += effect.amount * 2.4
            elif effect.type == EffectType.debuff:
                value += effect.amount * 1.1
        # Prefer efficient cards, but avoid dumping the whole hand for no reason.
        return value / max(1, card.cost)

    def choose(self, game: Game, actor: Actor) -> int | None:
        combatant = game.player if actor == "player" else game.enemy
        playable = [
            (i, card)
            for i, card in enumerate(combatant.hand)
            if card.cost <= combatant.energy
        ]
        if not playable:
            return None
        playable.sort(key=lambda item: self._score(game, actor, item[1]), reverse=True)
        best_score = self._score(game, actor, playable[0][1])
        # If the best card is very weak and HP is safe, consider ending the turn.
        if best_score < 1.0 and combatant.hp > combatant.max_hp * 0.6:
            return None
        return playable[0][0]


def make_agent(name: str, seed: int | None = None) -> Agent:
    if name == "random":
        return RandomAgent(seed=seed)
    if name == "heuristic":
        return HeuristicAgent()
    raise ValueError(f"unknown agent: {name}")


def play_match(
    cards: list[Card],
    agent_player: Agent,
    agent_enemy: Agent,
    seed: int | None = None,
    starting_actor: Actor = "player",
    max_steps: int = 300,
) -> dict:
    game = Game(cards, seed=seed, starting_actor=starting_actor)
    played_by: dict[Actor, list[str]] = {"player": [], "enemy": []}
    steps = 0
    while not game.winner and steps < max_steps:
        steps += 1
        actor = game.active
        combatant = game.player if actor == "player" else game.enemy
        agent = agent_player if actor == "player" else agent_enemy
        choice = agent.choose(game, actor)
        if choice is None:
            game.end_turn(actor)
            continue
        if choice < 0 or choice >= len(combatant.hand):
            game.end_turn(actor)
            continue
        card = combatant.hand[choice]
        if card.cost > combatant.energy:
            game.end_turn(actor)
            continue
        played_by[actor].append(card.id)
        try:
            game.play_card(actor, choice)
        except ValueError:
            game.end_turn(actor)
    winner = game.winner or "draw"
    return {
        "winner": winner,
        "turns": game.turn,
        "steps": steps,
        "played_by": played_by,
        "player_hp": game.player.hp,
        "enemy_hp": game.enemy.hp,
        "log": game.log,
    }


def simulate(
    cards: list[Card],
    games: int = 200,
    agent: str = "heuristic",
    seed: int = 42,
) -> dict:
    rng = random.Random(seed)
    player_wins = 0
    enemy_wins = 0
    draws = 0
    total_turns = 0
    first_player_wins = 0
    card_plays: dict[str, int] = defaultdict(int)
    card_wins: dict[str, int] = defaultdict(int)

    for i in range(games):
        start: Actor = "player" if i % 2 == 0 else "enemy"
        agent_a = make_agent(agent, seed=rng.randint(0, 10**9))
        agent_b = make_agent(agent, seed=rng.randint(0, 10**9))
        result = play_match(cards, agent_a, agent_b, seed=rng.randint(0, 10**9), starting_actor=start)
        winner = result["winner"]
        total_turns += result["turns"]
        if winner == "player":
            player_wins += 1
        elif winner == "enemy":
            enemy_wins += 1
        else:
            draws += 1
        if winner == start:
            first_player_wins += 1
        for actor, card_ids in result["played_by"].items():
            for card_id in card_ids:
                card_plays[card_id] += 1
        if winner in {"player", "enemy"}:
            for card_id in result["played_by"][winner]:
                card_wins[card_id] += 1

    card_stats = {}
    for card in cards:
        plays = card_plays.get(card.id, 0)
        wins = card_wins.get(card.id, 0)
        card_stats[card.id] = {
            "name": card.name,
            "plays": plays,
            "wins": wins,
            "win_rate": round(wins / plays, 4) if plays else 0.5,
        }

    return {
        "games": games,
        "agent": agent,
        "player_wins": player_wins,
        "enemy_wins": enemy_wins,
        "draws": draws,
        "player_win_rate": round(player_wins / max(1, games), 4),
        "enemy_win_rate": round(enemy_wins / max(1, games), 4),
        "first_player_win_rate": round(first_player_wins / max(1, games), 4),
        "avg_turns": round(total_turns / max(1, games), 2),
        "card_stats": card_stats,
    }
