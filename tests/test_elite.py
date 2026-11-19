from src.generator import DEFAULT_THEME, generate_fallback
from src.run import MAP_NODES, Run


def test_elite_modifier_and_map_history():
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=3).cards
    run = Run(cards, seed=21)
    run.choose_scarf(0)
    run.phase = "map"
    run.layer_index = 1
    run.map_options = [dict(MAP_NODES["elite"])]
    run.choose_map(0)
    assert run.phase == "battle"
    assert run.elite_pending is True
    assert run.elite_modifier is not None
    assert run.map_history
    assert run.game is not None
    assert run.game.enemy_elite_modifier is not None
    assert "·精英" in run.game.enemy.name
