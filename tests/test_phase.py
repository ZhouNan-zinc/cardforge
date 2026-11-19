from src.game import Game
from src.models import Card, CardType, Effect, EffectType


def _cards():
    return [
        Card(
            id=f"p{i}",
            name=f"P{i}",
            cost=0,
            type=CardType.attack,
            description="test",
            effects=[Effect(type=EffectType.damage, amount=15 if i == 0 else 5)],
        )
        for i in range(8)
    ]


def test_boss_enters_phase_two_and_uses_new_pattern():
    game = Game(
        _cards(),
        seed=1,
        enemy_hp=20,
        enemy_max_hp=20,
        enemy_pattern=[{"type": "attack", "amount": 5}],
        enemy_phase2_pattern=[{"type": "attack", "amount": 20}],
        second_player_bonus_hp=0,
    )
    game.player.hand = [_cards()[0].model_copy(deep=True)]
    game.player.energy = 3
    game.play_card("player", 0)
    assert game.enemy.hp == 5
    assert game.enemy_phase == 2
    assert game.current_enemy_intent()["amount"] == 20

    game.end_turn("player")
    game.enemy_take_turn()
    assert game.player.hp == 10
