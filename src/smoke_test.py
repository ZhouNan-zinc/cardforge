"""A no-LLM smoke test for CardForge."""

from __future__ import annotations

from .agents import simulate
from .game import Game
from .generator import DEFAULT_THEME, generate_cards


def main() -> None:
    card_set = generate_cards(DEFAULT_THEME, count=24, allow_llm=False, seed=7)
    assert len(card_set.cards) == 24, len(card_set.cards)
    assert all(card.effects for card in card_set.cards)

    game = Game(card_set.cards, seed=1)
    assert game.player.hand, "player should draw an opening hand"
    first = game.player.hand[0]
    if first.cost <= game.player.energy:
        game.play_card("player", 0)
    game.end_turn("player")
    game.enemy_take_turn()
    assert game.player.hp >= 0 and game.enemy.hp >= 0

    stats = simulate(card_set.cards, games=20, agent="heuristic", seed=3)
    assert stats["games"] == 20
    assert stats["player_wins"] + stats["enemy_wins"] + stats["draws"] == 20
    print("CardForge smoke test PASS")
    print(f"theme: {card_set.theme}")
    print(f"cards: {len(card_set.cards)}")
    print(f"simulated: {stats['games']} games, player win rate {stats['player_win_rate']:.1%}, avg turns {stats['avg_turns']}")


if __name__ == "__main__":
    main()
