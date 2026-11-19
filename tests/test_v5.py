from src.game import Game
from src.models import Card, CardType, Effect, EffectType, Element
from src.run import ENEMY_PATTERNS, SCARVES


def _cards():
    return [
        Card(
            id=f"t{i}",
            name=f"T{i}",
            cost=1,
            type=CardType.skill if i == 0 else CardType.attack,
            element=Element.ice if i == 0 else Element.wind,
            description="test",
            effects=[Effect(type=EffectType.block if i == 0 else EffectType.damage, amount=5)],
        )
        for i in range(8)
    ]


def test_ice_scarf_adds_block():
    game = Game(_cards(), seed=1, player_style="ice", second_player_bonus_hp=0)
    game.player.hand = [_cards()[0].model_copy(deep=True)]
    game.player.energy = 3
    game.player.block = 0
    game.play_card("player", 0)
    assert game.player.block == 7  # 5 base + 2 style bonus


def test_enemy_pattern_attack():
    game = Game(
        _cards(),
        seed=2,
        enemy_pattern=[{"type": "attack", "amount": 8}],
        second_player_bonus_hp=0,
    )
    game.end_turn("player")
    game.enemy_take_turn()
    assert game.player.hp == 22
    assert game.active == "player"


def test_scarf_and_enemy_data_shape():
    assert {"ice", "wind", "dragon"}.issubset({item["id"] for item in SCARVES})
    assert "霜原噬影" in ENEMY_PATTERNS
    assert ENEMY_PATTERNS["冰晶巨像"]
