"""Cross-game strategy induction from public play records.

The coach is deliberately outside the game loop: it reads only public outcome
summaries/decisions, asks the model for a compact reusable guide, and writes
that guide for a later batch. It must never see seeds, hidden deck order, enemy
patterns, card-pool statistics, or project files beyond the public records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .generator import LLMConfig, _extract_json, _llm_chat

ChatFn = Callable[[list[dict], LLMConfig], str | None]

COACH_SYSTEM = (
    "你是一个卡牌游戏教练。你只能看到公开对局记录和玩家自己的决策，"
    "不能请求隐藏牌序、敌方手牌、随机种子、未来商店/地图、内部敌人模式或项目文件。"
    "请把记录总结成一套可复用、可执行的攻略，不要编造记录中没有的机制。"
    "只输出 JSON，不要 Markdown："
    '{"rules":["规则1","规则2","规则3"]}'
)


def compact_public_record(records: list[dict]) -> list[dict]:
    """Keep only fields that a player could know from the UI."""
    compact: list[dict] = []
    for record in records:
        battle = record.get("llm") or record.get("battle") or {}
        compact.append(
            {
                "result": record.get("result") or record.get("phase") or battle.get("winner"),
                "victory": record.get("victory", battle.get("winner") == "player"),
                "layer": record.get("layer_index", record.get("layer")),
                "hp": record.get("player_hp"),
                "gold": record.get("gold"),
                "deck_size": record.get("deck_size"),
                "relics": record.get("relics", []),
                "boons": record.get("boons", []),
                "map_history": record.get("map_history", []),
                "longterm": record.get("longterm", {}),
                "battle": record.get("battle", {}),
                "battle_result": battle,
                "decisions": (record.get("longterm_trace") or record.get("decisions") or [])[:40],
            }
        )
    return compact


def induce_guide(records: list[dict], chat_fn: ChatFn | None = None, config: LLMConfig | None = None) -> str:
    config = config or LLMConfig()
    public = compact_public_record(records)
    prompt = (
        "以下是对局的公开记录（没有种子、隐藏牌序、敌方手牌或未来内容）。\n"
        "请总结一套固定套路/攻略，回答：路线怎么选、牌组怎么构筑、商店/遗物/Boon 优先级、"
        "战斗中的出牌原则、常见失败模式。必须输出 5–7 条可执行规则（rules 数组），每条都能从记录中支持。\n"
        f"公开记录：{json.dumps(public, ensure_ascii=False)}\n"
        '只输出 JSON，格式为 {"rules":["..."]}，不要输出其他字段。'
    )
    messages = [
        {"role": "system", "content": COACH_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    if chat_fn is None:
        def chat(messages: list[dict], cfg: LLMConfig) -> str | None:
            return _llm_chat(messages, cfg, max_tokens=1200, temperature=0.3)

        chat_fn = chat
    content = chat_fn(messages, config)
    if not content:
        raise RuntimeError("strategy coach returned no content")
    raw = _extract_json(content)
    rules = raw.get("rules") if isinstance(raw, dict) else None
    if not isinstance(rules, list) or not rules:
        raise ValueError("strategy coach returned no rules")
    cleaned = [str(item).strip() for item in rules if str(item).strip()]
    if len(cleaned) < 3:
        raise ValueError("strategy coach returned too few rules")
    return "\n".join(f"{i}. {rule}" for i, rule in enumerate(cleaned, 1))


def load_records(paths: list[str]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "games" in data:
            records.extend(data["games"])
        elif isinstance(data, dict) and "summary" in data:
            records.append(data)
        else:
            records.append(data)
    return records
