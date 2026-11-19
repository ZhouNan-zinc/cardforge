from src.generator import DEFAULT_THEME, generate_fallback
from src.run import MAP_NODES, Run


def battle_node_index(run):
    for i, node in enumerate(run.map_options):
        if node["id"] == "battle":
            return i
    return 0


def test_run_rewards_and_progression():
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=3).cards
    run = Run(cards, seed=11)
    assert run.phase == "scarf"
    assert len(run.deck) == 12
    run.choose_scarf(0)
    assert run.phase == "map"

    run.choose_map(battle_node_index(run))
    assert run.phase == "battle"
    assert run.game is not None
    run.game.enemy.hp = 0
    run.game.winner = "player"
    run.after_player_action()
    assert run.phase == "reward"
    run.choose_reward(0)
    assert run.phase == "boon"
    run.choose_boon(0)
    if run.phase == "upgrade":
        run.choose_upgrade(0)
    assert run.phase == "map"
    assert len(run.deck) == 13
    run.choose_map(battle_node_index(run))
    assert run.phase == "battle"
    assert run.game.enemy.name.startswith("极光狐")


def test_run_can_reach_victory():
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=5).cards
    run = Run(cards, seed=12)
    run.choose_scarf(1)
    for _ in range(30):
        if run.phase == "victory":
            break
        if run.phase == "map":
            run.choose_map(battle_node_index(run))
        elif run.phase == "battle":
            assert run.game is not None
            run.game.enemy.hp = 0
            run.game.winner = "player"
            run.after_player_action()
        elif run.phase == "reward":
            run.choose_reward(0)
        elif run.phase == "boon":
            run.choose_boon(0)
        elif run.phase == "upgrade":
            run.choose_upgrade(0)
        elif run.phase == "rest":
            run.choose_rest(0)
        elif run.phase == "shop":
            run.leave_shop()
        elif run.phase == "event":
            run.choose_event(0)
        elif run.phase == "remove":
            run.choose_remove(0)
        else:
            break
    assert run.phase == "victory"
