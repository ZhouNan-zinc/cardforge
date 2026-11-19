import json
import re

from src.game import Game
from src.llm_agent import LLMAgent
from src.models import Card, CardType, Effect, EffectType, Element


def tiny_cards():
    return [
        Card(
            id=f"test-{i}",
            name=f"测试牌{i}",
            cost=0,
            type=CardType.attack,
            element=Element.ice,
            description="造成 1 点伤害",
            effects=[Effect(type=EffectType.damage, amount=1)],
        )
        for i in range(8)
    ]


def test_llm_agent_accepts_valid_play_and_end():
    game = Game(tiny_cards(), seed=3)
    agent = LLMAgent(chat_fn=lambda messages, config: '{"action":"play","card_index":0,"reason":"test"}', label="test")
    assert agent.choose(game, "player") == 0
    summary = agent.summary()
    assert summary["valid_responses"] == 1
    assert summary["fallbacks"] == 0
    assert summary["play_actions"] == 1

    game2 = Game(tiny_cards(), seed=3)
    end_agent = LLMAgent(chat_fn=lambda messages, config: '{"action":"end","reason":"test"}', label="test")
    assert end_agent.choose(game2, "player") is None
    assert end_agent.summary()["end_actions"] == 1


def test_llm_agent_repairs_invalid_output_and_falls_back():
    game = Game(tiny_cards(), seed=4)
    agent = LLMAgent(
        chat_fn=lambda messages, config: '{"action":"play","card_index":99}',
        label="test",
    )
    choice = agent.choose(game, "player")
    assert choice is not None
    summary = agent.summary()
    assert summary["fallbacks"] == 1
    assert summary["invalid_responses"] == 2
    assert summary["valid_responses"] == 0


def test_llm_turn_planner_executes_plan_and_ends():
    game = Game(tiny_cards(), seed=5)
    def plan_from_prompt(messages, config):
        ids = re.findall(r"(test-\d+)", messages[-1]["content"])
        return json.dumps({"cards": ids[:2], "reason": "plan"})

    agent = LLMAgent(chat_fn=plan_from_prompt, label="test", plan_turn=True)
    first = agent.choose(game, "player")
    assert first == 0
    game.play_card("player", first)
    second = agent.choose(game, "player")
    assert second == 0
    game.play_card("player", second)
    assert agent.choose(game, "player") is None
    summary = agent.summary()
    assert summary["valid_responses"] == 1
    assert summary["play_actions"] == 2


def test_prompt_contains_only_public_battle_state():
    game = Game(tiny_cards(), seed=6)
    agent = LLMAgent(chat_fn=lambda messages, config: '{"action":"end"}', label="test")
    prompt = agent._plan_messages(game)[1]["content"]
    assert "手牌：" in prompt
    assert "敌人意图：" in prompt
    assert "seed" not in prompt.lower()
    assert "draw_pile" not in prompt
    assert "discard" not in prompt.lower()
    assert "enemy_pattern" not in prompt
    assert "card_pool" not in prompt


def test_opencode_isolation_config_has_no_tools(tmp_path):
    import json
    import shutil

    import pytest

    from src.opencode_chat import OpenCodeChat

    if shutil.which("opencode") is None:
        pytest.skip("opencode CLI not installed")
    OpenCodeChat(isolation_dir=tmp_path)
    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert config["instructions"] == []
    assert config["skills"] == []
    agent = config["agents"]["cardforge-player"]
    assert agent["permissions"][0]["effect"] == "deny"
    assert agent["steps"] == 1
