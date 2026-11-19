from src.agents import simulate
from src.generator import DEFAULT_THEME, generate_fallback


def test_simulation_is_deterministic_enough():
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=4).cards
    stats = simulate(cards, games=30, agent="heuristic", seed=5)
    assert stats["games"] == 30
    assert stats["player_wins"] + stats["enemy_wins"] + stats["draws"] == 30
    assert 0 <= stats["player_win_rate"] <= 1
    assert stats["avg_turns"] > 0
    assert len(stats["card_stats"]) == 24


def test_same_seed_produces_identical_summary():
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=4).cards
    first = simulate(cards, games=20, agent="heuristic", seed=17)
    second = simulate(cards, games=20, agent="heuristic", seed=17)
    assert first == second
