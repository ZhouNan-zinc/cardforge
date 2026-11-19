from src.generator import DEFAULT_THEME, generate_fallback
from src.llm_run_agent import LLMRunAgent
from src.llm_run_playtest import run_once
from src.run import Run


def make_run(seed=31):
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=4).cards
    return Run(cards, seed=seed)


def choose_zero(messages, config):
    return '{"action":"choose","index":0,"reason":"test"}'


def test_run_agent_uses_public_options_and_falls_back():
    run = make_run()
    agent = LLMRunAgent(chat_fn=choose_zero, label="test")
    assert agent.choose_style(run) == 0
    run.choose_scarf(0)
    assert agent.choose_map(run) == 0
    assert agent.summary()["valid_responses"] == 2

    # Invalid index must fall back rather than returning an invalid choice.
    invalid = LLMRunAgent(chat_fn=lambda messages, config: '{"action":"choose","index":99}', label="test")
    assert invalid.choose_map(run) in range(len(run.map_options))
    assert invalid.summary()["fallbacks"] == 1


def test_run_agent_shop_action_and_prompt_are_public_only():
    run = make_run()
    run.choose_scarf(0)
    run.gold = 100
    run._open_shop()
    agent = LLMRunAgent(chat_fn=lambda messages, config: '{"action":"leave","reason":"test"}', label="test")
    assert agent.choose_shop(run) == {"action": "leave"}

    prompt = agent._messages(run, "shop", run.shop_items, shop=True)[1]["content"]
    assert "当前金币" in prompt
    assert "seed" not in prompt.lower()
    assert "map_layers" not in prompt
    assert "未来" not in prompt


def test_full_run_heuristic_condition_reaches_terminal_phase():
    cards = generate_fallback(DEFAULT_THEME, count=24, seed=4).cards
    result = run_once(
        cards,
        seed=42,
        battle_mode="heuristic",
        longterm_mode="heuristic",
        player_model="unused",
        isolation_dir="/tmp/opencode/unused",
        max_steps=300,
    )
    assert result["phase"] in {"victory", "defeat"}
    assert result["layer_index"] >= 0
