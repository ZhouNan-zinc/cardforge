from src.generator import DEFAULT_THEME, generate_fallback
from src.run import MAP_LAYERS, Run


def make_run(seed=21):
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=4).cards
    return Run(cards, seed=seed)


def battle_node_index(run):
    return next(i for i, node in enumerate(run.map_options) if node["id"] == "battle")


def test_four_layer_map_and_style_starter():
    run = make_run()
    assert len(MAP_LAYERS) == 4
    run.choose_scarf(0)
    assert run.phase == "map"
    assert len(run.map_layers) == 4
    assert len(run.deck) == 12
    assert len(run.state()["deck"]) == 12


def test_potion_is_used_in_battle_and_deck_state_is_visible():
    run = make_run()
    run.choose_scarf(0)
    run.choose_map(battle_node_index(run))
    run.potions = ["heal"]
    run.player_hp = 10
    run.game.player.hp = 10
    run.use_potion(0)
    assert run.potions == []
    assert run.player_hp == 22
    assert len(run.state()["deck"]) == 12


def test_shop_has_potion_and_can_reroll():
    run = make_run()
    run.choose_scarf(0)
    run.gold = 100
    run._open_shop()
    assert run.phase == "shop"
    assert any(item["kind"] == "potion" for item in run.shop_items)
    before = list(run.shop_items)
    run.reroll_shop()
    assert run.gold == 85
    assert run.phase == "shop"
    assert run.shop_items is not before
