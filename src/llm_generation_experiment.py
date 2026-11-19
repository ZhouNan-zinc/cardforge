"""E1: generate a real card set with the current OpenCode model.

This is a generation experiment, not an agent-playtest experiment. The model
runs in an isolated directory with tools denied; the prompt contains only the
theme, schema and output requirements.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .agents import simulate
from .generator import DEFAULT_THEME, LLM_SCHEMA, _extract_json, save_card_set
from .models import CardSet
from .opencode_chat import DEFAULT_PLAYER_MODEL, OpenCodeChat


def prompt(theme: str, count: int) -> list[dict]:
    system = (
        "你是一个隔离的卡牌游戏设计师。只输出 JSON，不要 Markdown，不要解释。"
        "不要调用工具或读取文件。"
    )
    user = (
        f"主题：{theme}。主角是雪原上的霜旋，元素是冰、风、龙。\n"
        f"请生成 {count} 张可玩的卡牌。卡牌会进入双人对战引擎：30 HP、每回合 3 能量、抽 5 张。\n"
        "每张卡必须有唯一 id、中文名、0-3 费、attack/skill/power、元素、效果和短描述。\n"
        "effects 至少 1 个、最多 3 个；数值不要超过 20；不要发明 schema 之外的字段。\n"
        "冰/风/龙各约占三分之一，少量 neutral。\n"
        "输出 JSON 对象："
        '{"title":"主题卡组","cards":[ ... ]}\n'
        "schema：\n"
        f"{json.dumps(LLM_SCHEMA, ensure_ascii=False, indent=2)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a real CardForge card set")
    parser.add_argument("--theme", default=DEFAULT_THEME)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--model", default=DEFAULT_PLAYER_MODEL)
    parser.add_argument("--out", default="results/llm-generation-pilot.json")
    parser.add_argument("--cards-out", default="data/cards/llm_generated.json")
    parser.add_argument("--games", type=int, default=100)
    args = parser.parse_args()

    chat = OpenCodeChat(
        model=args.model,
        isolation_dir="/tmp/opencode/cardforge-llm-designer",
        timeout=300,
        agent_name="cardforge-designer",
        system=(
            "你是一个隔离的卡牌游戏设计师。只输出用户要求的 JSON；"
            "不要使用工具、文件、代码或网络。"
        ),
    )
    messages = prompt(args.theme, args.count)
    content = chat(messages, None)
    if not content:
        raise SystemExit("LLM generation returned no content")
    raw = _extract_json(content)
    cards = raw.get("cards", [])
    card_set = CardSet(
        theme=args.theme,
        title=str(raw.get("title") or f"{args.theme} · LLM 卡组"),
        source="llm",
        cards=cards,
    )
    save_card_set(card_set, args.cards_out)
    stats = simulate(card_set.cards, games=args.games, agent="heuristic", seed=42)
    payload = {
        "model": args.model,
        "theme": args.theme,
        "count": len(card_set.cards),
        "title": card_set.title,
        "elements": dict(Counter(card.element.value for card in card_set.cards)),
        "types": dict(Counter(card.type.value for card in card_set.cards)),
        "rarity": dict(Counter(card.rarity for card in card_set.cards)),
        "costs": dict(Counter(card.cost for card in card_set.cards)),
        "schema_valid": True,
        "simulation": {k: v for k, v in stats.items() if k != "card_stats"},
        "card_set": card_set.model_dump(),
        "raw_output": content,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ["model", "count", "title", "elements", "types", "rarity", "costs", "schema_valid", "simulation"]}, ensure_ascii=False, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
