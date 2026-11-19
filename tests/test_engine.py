from src.game import Game
from src.models import Card, CardType, Effect, EffectType


def make_card(card_id, name, cost, effects, card_type=CardType.attack):
    return Card(
        id=card_id,
        name=name,
        cost=cost,
        type=card_type,
        description="test",
        effects=effects,
    )


def test_damage_and_block():
    cards = [
        make_card("a1", "Strike", 1, [Effect(type=EffectType.damage, amount=6)]),
        make_card("a2", "Guard", 1, [Effect(type=EffectType.block, amount=5)]),
        make_card("a3", "Bash", 2, [Effect(type=EffectType.damage, amount=8)]),
        make_card("a4", "Heal", 1, [Effect(type=EffectType.heal, amount=4)]),
        make_card("a5", "Draw", 1, [Effect(type=EffectType.draw, amount=2)]),
        make_card("a6", "Buff", 1, [Effect(type=EffectType.buff, amount=2, stat="strength")]),
        make_card("a7", "Weaken", 1, [Effect(type=EffectType.debuff, amount=1, stat="weak")]),
        make_card("a8", "Vulnerable", 1, [Effect(type=EffectType.debuff, amount=1, stat="vulnerable")]),
    ]
    game = Game(cards, seed=1)
    game.player.hand = [cards[0].model_copy(deep=True)]
    game.enemy.hp = 20
    game.player.energy = 3
    before = game.enemy.hp
    game.play_card("player", 0)
    assert game.enemy.hp == before - 6


def test_win_condition():
    cards = [
        make_card(f"a{i}", f"Card {i}", 0, [Effect(type=EffectType.damage, amount=30)])
        for i in range(8)
    ]
    game = Game(cards, seed=2)
    game.player.hand = [cards[0].model_copy(deep=True)]
    game.player.energy = 3
    game.enemy.hp = 5
    game.play_card("player", 0)
    assert game.winner == "player"


def test_energy_validation():
    cards = [
        make_card(f"a{i}", f"Card {i}", 3, [Effect(type=EffectType.damage, amount=5)])
        for i in range(8)
    ]
    game = Game(cards, seed=3)
    game.player.hand = [cards[0].model_copy(deep=True)]
    game.player.energy = 0
    try:
        game.play_card("player", 0)
    except ValueError as error:
        assert "energy" in str(error)
    else:
        raise AssertionError("expected an energy error")


def test_energy_cannot_exceed_max_and_strength_adds_damage():
    energy_card = make_card(
        "energy", "Energy", 0, [Effect(type=EffectType.energy, amount=2)], card_type=CardType.skill
    )
    attack = make_card("attack", "Attack", 0, [Effect(type=EffectType.damage, amount=6)])
    cards = [energy_card, attack] + [make_card(f"f{i}", f"Filler {i}", 1, [Effect(type=EffectType.block, amount=1)]) for i in range(6)]
    game = Game(cards, seed=9)
    game.player.max_energy = 3
    game.player.energy = 3
    game.player.hand = [energy_card.model_copy(deep=True)]
    game.play_card("player", 0)
    assert game.player.energy == 3

    game.player.hand = [attack.model_copy(deep=True)]
    game.player.energy = 3
    game.player.strength = 2
    before = game.enemy.hp
    game.play_card("player", 0)
    assert game.enemy.hp == before - 8


def test_enemy_poison_ignores_block_and_ticks():
    cards = [make_card(f"p{i}", f"P{i}", 1, [Effect(type=EffectType.damage, amount=1)]) for i in range(8)]
    game = Game(
        cards,
        seed=11,
        enemy_hp=30,
        enemy_max_hp=30,
        enemy_pattern=[{"type": "debuff", "stat": "poison", "amount": 2}],
        second_player_bonus_hp=0,
    )
    game.player.block = 10
    game.end_turn("player")
    game.enemy_take_turn()
    assert game.player.poison == 1
    assert game.player.hp == 28


def test_every_map_path_has_at_least_two_battles():
    from src.run import MAP_EDGES, MAP_LAYERS

    combat = {"battle", "elite"}
    paths = []

    def walk(layer, index, path):
        current = path + [index]
        if layer == len(MAP_LAYERS) - 1:
            paths.append(current)
            return
        for target in MAP_EDGES[layer][index]:
            walk(layer + 1, target, current)

    for start in range(len(MAP_LAYERS[0])):
        walk(0, start, [])
    assert paths
    assert min(
        sum(MAP_LAYERS[layer][path[layer]] in combat for layer in range(len(MAP_LAYERS)))
        for path in paths
    ) >= 2
