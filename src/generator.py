"""Card generation: LLM-first, deterministic fallback, and a simple balancer."""

from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any

import requests

from .models import Card, CardSet, CardType, Effect, EffectType, Element

DEFAULT_THEME = "霜旋"


# ---------------------------------------------------------------------------
# Fallback generator
# ---------------------------------------------------------------------------
def _describe(effects: list[Effect]) -> str:
    parts = []
    for effect in effects:
        if effect.type == EffectType.damage:
            parts.append(f"造成 {effect.amount} 点伤害")
        elif effect.type == EffectType.block:
            parts.append(f"获得 {effect.amount} 点格挡")
        elif effect.type == EffectType.heal:
            parts.append(f"回复 {effect.amount} 点生命")
        elif effect.type == EffectType.draw:
            parts.append(f"抽 {effect.amount} 张牌")
        elif effect.type == EffectType.energy:
            parts.append(f"获得 {effect.amount} 点能量")
        elif effect.type == EffectType.buff:
            parts.append(f"获得 {effect.amount} 点力量")
        elif effect.type == EffectType.debuff:
            label = {"weak": "虚弱", "vulnerable": "易伤", "poison": "中毒"}.get(effect.stat, effect.stat or "异常")
            parts.append(f"施加 {effect.amount} 层{label}")
    return "；".join(parts)


def _make_card(
    index: int,
    name: str,
    cost: int,
    card_type: CardType,
    element: Element,
    effects: list[Effect],
    rarity: str = "common",
    flavor: str = "",
) -> Card:
    return Card(
        id=f"cf-{index:02d}",
        name=name,
        cost=cost,
        type=card_type,
        element=element,
        rarity=rarity,  # type: ignore[arg-type]
        description=_describe(effects),
        effects=effects,
        flavor=flavor,
    )


def generate_fallback(theme: str = DEFAULT_THEME, count: int = 24, seed: int | None = None) -> CardSet:
    """Create a deterministic, playable, snow-weasel-themed card set without an LLM."""
    cards: list[Card] = []
    index = 0

    def add(
        name: str,
        cost: int,
        card_type: CardType,
        element: Element,
        effects: list[Effect],
        rarity: str = "common",
        flavor: str = "雪原上，霜花沿尾巴炸开。",
    ) -> None:
        nonlocal index
        cards.append(_make_card(index, name, cost, card_type, element, effects, rarity, flavor))
        index += 1

    # ---------------- Ice: frost, block, control ----------------
    add("雪原横扫", 1, CardType.attack, Element.ice, [Effect(type=EffectType.damage, amount=6)])
    add("冰晶突刺", 1, CardType.attack, Element.ice, [Effect(type=EffectType.damage, amount=7)])
    add("寒鳞护盾", 1, CardType.skill, Element.ice, [Effect(type=EffectType.block, amount=12)])
    add("极光回响", 1, CardType.skill, Element.ice, [Effect(type=EffectType.block, amount=4), Effect(type=EffectType.draw, amount=1)])
    add("冰封之息", 2, CardType.skill, Element.ice, [Effect(type=EffectType.block, amount=8), Effect(type=EffectType.debuff, amount=2, stat="poison")])
    add("霜旋爆发", 2, CardType.attack, Element.ice, [Effect(type=EffectType.damage, amount=10), Effect(type=EffectType.block, amount=3)], rarity="rare")
    add("雪原疾走", 0, CardType.skill, Element.ice, [Effect(type=EffectType.block, amount=4)])
    add("冰龙鳞甲", 2, CardType.power, Element.ice, [Effect(type=EffectType.buff, amount=2, stat="strength"), Effect(type=EffectType.block, amount=4)], rarity="rare")

    # ---------------- Wind: tempo, draw, spin ----------------
    add("旋风尾击", 1, CardType.attack, Element.wind, [Effect(type=EffectType.damage, amount=7)])
    add("疾风回旋", 0, CardType.attack, Element.wind, [Effect(type=EffectType.damage, amount=4)])
    add("气流护体", 1, CardType.skill, Element.wind, [Effect(type=EffectType.block, amount=5), Effect(type=EffectType.energy, amount=1)])
    add("雪原疾驰", 1, CardType.skill, Element.wind, [Effect(type=EffectType.block, amount=8)])
    add("风眼", 2, CardType.power, Element.wind, [Effect(type=EffectType.buff, amount=2, stat="strength")], rarity="rare")
    add("旋力爆发", 2, CardType.attack, Element.wind, [Effect(type=EffectType.damage, amount=8), Effect(type=EffectType.draw, amount=1)], rarity="uncommon")

    # ---------------- Dragon: raw power, scaling ----------------
    add("龙息", 2, CardType.attack, Element.dragon, [Effect(type=EffectType.damage, amount=9)])
    add("冰龙咆哮", 2, CardType.attack, Element.dragon, [Effect(type=EffectType.damage, amount=7), Effect(type=EffectType.debuff, amount=1, stat="poison")], rarity="uncommon")
    add("龙鳞硬化", 1, CardType.skill, Element.dragon, [Effect(type=EffectType.block, amount=6), Effect(type=EffectType.buff, amount=1, stat="strength")])
    add("逆鳞", 2, CardType.attack, Element.dragon, [Effect(type=EffectType.damage, amount=11)], rarity="rare")
    add("龙威", 2, CardType.power, Element.dragon, [Effect(type=EffectType.buff, amount=3, stat="strength")], rarity="rare")
    add("极寒龙卷", 3, CardType.attack, Element.dragon, [Effect(type=EffectType.damage, amount=16), Effect(type=EffectType.block, amount=4)], rarity="rare")

    # ---------------- Neutral: scarf tricks, utility ----------------
    add("雪原回旋", 1, CardType.skill, Element.neutral, [Effect(type=EffectType.draw, amount=1), Effect(type=EffectType.block, amount=5)])
    add("雪球补给", 1, CardType.skill, Element.neutral, [Effect(type=EffectType.heal, amount=5)])
    add("霜旋步", 0, CardType.skill, Element.neutral, [Effect(type=EffectType.block, amount=3)])
    add("极光涌动", 2, CardType.skill, Element.neutral, [Effect(type=EffectType.draw, amount=1), Effect(type=EffectType.energy, amount=1), Effect(type=EffectType.block, amount=4)], rarity="uncommon")

    art_map = {
        "cf-00": "generated/cf-00.jpg",
        "cf-01": "generated/cf-01.jpg",
        "cf-02": "generated/cf-02.jpg",
        "cf-03": "generated/cf-03.jpg",
        "cf-04": "generated/cf-04.jpg",
        "cf-05": "generated/cf-05.jpg",
        "cf-06": "generated/cf-06.jpg",
        "cf-07": "generated/cf-07.jpg",
        "cf-08": "generated/cf-08.jpg",
        "cf-09": "generated/cf-09.jpg",
        "cf-10": "generated/cf-10.jpg",
        "cf-11": "generated/cf-11.jpg",
        "cf-12": "generated/cf-12.jpg",
        "cf-13": "generated/cf-13.jpg",
        "cf-14": "generated/cf-14.jpg",
        "cf-15": "generated/cf-15.jpg",
        "cf-16": "generated/cf-16.jpg",
        "cf-17": "generated/cf-17.jpg",
        "cf-18": "generated/cf-18.jpg",
        "cf-19": "generated/cf-19.jpg",
        "cf-20": "generated/cf-20.jpg",
        "cf-21": "generated/cf-21.jpg",
        "cf-22": "generated/cf-22.jpg",
        "cf-23": "generated/cf-23.jpg",
    }
    combo_cards = {"cf-08", "cf-13"}
    special_keywords = {
        "cf-02": ["消耗"],
        "cf-10": ["消耗"],
        "cf-11": ["保留"],
        "cf-16": ["保留"],
        "cf-19": ["消耗"],
        "cf-22": ["保留"],
    }
    for card in cards[:count]:
        if card.id in art_map:
            card.art = art_map[card.id]
        if card.id in combo_cards:
            card.keywords = ["连击"]
        if card.id in special_keywords:
            card.keywords = special_keywords[card.id]
    return CardSet(theme=theme, title=f"{theme} · 旋力卡组", source="fallback", cards=cards[:count])


# ---------------------------------------------------------------------------
# LLM generator
# ---------------------------------------------------------------------------
class LLMConfig:
    def __init__(self) -> None:
        self.base_url = (os.getenv("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY") or ""
        self.model = os.getenv("LLM_MODEL") or ""
        self.timeout = int(os.getenv("LLM_TIMEOUT", "90"))

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


LLM_SCHEMA = {
    "title": "string",
    "cards": [
        {
            "id": "slug-like-id",
            "name": "中文卡名",
            "cost": "0-3 integer",
            "type": "attack | skill | power",
            "element": "ice | wind | dragon | neutral",
            "rarity": "common | uncommon | rare",
            "description": "中文效果描述",
            "effects": [
                {"type": "damage | block | heal | draw | energy", "amount": "0-30 integer"},
                {"type": "buff", "amount": "1-5", "stat": "strength"},
                {"type": "debuff", "amount": "1-3", "stat": "weak | vulnerable"},
            ],
            "flavor": "一句短风味文本",
        }
    ],
}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def generate_with_llm(theme: str, count: int = 24, config: LLMConfig | None = None) -> CardSet | None:
    config = config or LLMConfig()
    if not config.configured:
        return None

    system = (
        "你是一个卡牌游戏设计师。只输出 JSON，不要 Markdown，不要解释。"
        "卡牌游戏是双人对战：每回合 3 点能量、抽 5 张牌、30 点生命。"
        "元素分为 ice / wind / dragon / neutral；同元素在一回合打出 3 张会触发旋力爆发。"
        "效果必须使用给定 schema，不要发明新字段。"
        "数值要平衡：0 费牌不能太强，2-3 费牌要有明显强度，但不要出现 20 点伤害。"
    )
    user = (
        f"主题：{theme}。主角是一只霜旋，元素是冰、风、龙；"
        "请让卡名、描述、风味文本都围绕雪原、极光、流派、旋力、冰晶、龙鳞。\n"
        f"生成 {count} 张卡牌，冰/风/龙各占约 1/3，少量 neutral。\n"
        "输出 JSON 对象，字段如下：\n"
        f"{json.dumps(LLM_SCHEMA, ensure_ascii=False, indent=2)}\n"
        "每张卡的 effects 至少 1 个、最多 3 个。"
    )
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.9,
        "max_tokens": 6000,
    }

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            raw = _extract_json(content)
            cards = [Card.model_validate(card) for card in raw.get("cards", [])]
            if len(cards) < 8:
                raise ValueError("LLM returned too few cards")
            return CardSet(
                theme=theme,
                title=str(raw.get("title") or f"{theme} · LLM 卡组"),
                source="llm",
                cards=cards[:count],
            )
        except Exception as error:  # noqa: BLE001 - fallback is intentional
            last_error = error
            payload["messages"].append(
                {
                    "role": "user",
                    "content": f"上一次输出无法解析：{error}。请只输出合法 JSON。",
                }
            )
    print(f"[generator] LLM generation failed, using fallback: {last_error}")
    return None


def generate_cards(
    theme: str = DEFAULT_THEME,
    count: int = 24,
    allow_llm: bool = True,
    seed: int | None = None,
) -> CardSet:
    if allow_llm:
        generated = generate_with_llm(theme, count=count)
        if generated is not None:
            return generated
    return generate_fallback(theme, count=count, seed=seed)


# ---------------------------------------------------------------------------
# Balance pass
# ---------------------------------------------------------------------------
def balance_cards(card_set: CardSet, stats: dict[str, Any]) -> CardSet:
    """A small, explainable balance pass driven by play/win statistics."""
    card_stats = stats.get("card_stats", {})
    new_cards: list[Card] = []
    for card in card_set.cards:
        entry = card_stats.get(card.id, {})
        plays = int(entry.get("plays", 0))
        win_rate = float(entry.get("win_rate", 0.5))
        cost = card.cost
        effects = [effect.model_copy(deep=True) for effect in card.effects]

        if plays >= 5:
            if win_rate >= 0.62:
                if cost < 3:
                    cost += 1
                else:
                    for i, effect in enumerate(effects):
                        if effect.type == EffectType.damage and effect.amount > 2:
                            effects[i] = effect.model_copy(update={"amount": effect.amount - 1})
                            break
            elif win_rate <= 0.38:
                if cost > 0:
                    cost -= 1
                else:
                    for i, effect in enumerate(effects):
                        if effect.type in {EffectType.damage, EffectType.block}:
                            effects[i] = effect.model_copy(update={"amount": effect.amount + 1})
                            break

        new_cards.append(
            card.model_copy(
                update={
                    "cost": cost,
                    "effects": effects,
                    "description": _describe(effects),
                }
            )
        )

    return CardSet(
        theme=card_set.theme,
        title=card_set.title + " · 平衡版",
        source="balanced",
        cards=new_cards,
    )


# ---------------------------------------------------------------------------
# C: LLM balance suggestions + card art prompts
# ---------------------------------------------------------------------------
def _llm_chat(messages: list[dict], config: LLMConfig, max_tokens: int = 4000, temperature: float = 0.4) -> str | None:
    if not config.configured:
        return None
    try:
        response = requests.post(
            f"{config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=config.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as error:  # noqa: BLE001
        print(f"[llm] request failed: {error}")
        return None


def balance_cards_with_llm(card_set: CardSet, stats: dict[str, Any]) -> CardSet | None:
    """Ask an LLM for small, safe cost/damage/block adjustments."""
    config = LLMConfig()
    if not config.configured:
        return None
    cards_payload = [
        {
            "id": card.id,
            "name": card.name,
            "cost": card.cost,
            "element": card.element.value,
            "effects": [effect.model_dump() for effect in card.effects],
            "plays": stats.get("card_stats", {}).get(card.id, {}).get("plays", 0),
            "win_rate": stats.get("card_stats", {}).get(card.id, {}).get("win_rate", 0.5),
        }
        for card in card_set.cards
    ]
    prompt = (
        "你在平衡一个双人卡牌游戏。只输出 JSON 对象，不要 Markdown。\n"
        '格式：{"changes": [{"id": "...", "cost": 0-3, '
        '"damage_delta": -3..3, "block_delta": -3..3}]}\n' 
        "规则：只做小幅调整；不要删除卡牌；不要改变元素；不要新增效果。\n"
        "目标：强卡降强度，弱卡升强度；控制先手优势和单卡胜率方差。\n"
        f"统计数据：{json.dumps({k: v for k, v in stats.items() if k != 'card_stats'}, ensure_ascii=False)}\n"
        f"卡牌：{json.dumps(cards_payload, ensure_ascii=False)}"
    )
    content = _llm_chat(
        [
            {"role": "system", "content": "你是严谨的卡牌游戏平衡设计师。"},
            {"role": "user", "content": prompt},
        ],
        config,
        max_tokens=5000,
    )
    if not content:
        return None
    try:
        raw = _extract_json(content)
        changes = {item["id"]: item for item in raw.get("changes", []) if "id" in item}
    except Exception as error:  # noqa: BLE001
        print(f"[balance] invalid LLM JSON: {error}")
        return None

    new_cards: list[Card] = []
    for card in card_set.cards:
        change = changes.get(card.id, {})
        cost = card.cost
        if isinstance(change.get("cost"), int):
            cost = max(0, min(3, change["cost"]))
        effects = [effect.model_copy(deep=True) for effect in card.effects]
        damage_delta = int(change.get("damage_delta", 0) or 0)
        block_delta = int(change.get("block_delta", 0) or 0)
        for i, effect in enumerate(effects):
            if effect.type == EffectType.damage and damage_delta:
                effects[i] = effect.model_copy(update={"amount": max(1, min(30, effect.amount + damage_delta))})
            elif effect.type == EffectType.block and block_delta:
                effects[i] = effect.model_copy(update={"amount": max(1, min(30, effect.amount + block_delta))})
        new_cards.append(
            card.model_copy(
                update={"cost": cost, "effects": effects, "description": _describe(effects)}
            )
        )
    return CardSet(
        theme=card_set.theme,
        title=card_set.title + " · LLM 平衡版",
        source="balanced",
        cards=new_cards,
    )


def generate_art_prompts(card_set: CardSet, use_llm: bool = True) -> list[dict[str, str]]:
    """Return one image-generation prompt per card.

    The fallback is deterministic and can be pasted into any image model.
    With an LLM configured, the model can rewrite prompts for a consistent style.
    """
    config = LLMConfig()
    if use_llm and config.configured:
        payload = [
            {
                "id": card.id,
                "name": card.name,
                "element": card.element.value,
                "type": card.type.value,
                "description": card.description,
                "flavor": card.flavor,
            }
            for card in card_set.cards
        ]
        content = _llm_chat(
            [
                {"role": "system", "content": "你是游戏卡牌美术总监。只输出 JSON，不要 Markdown。"},
                {
                    "role": "user",
                    "content": (
                        "为每张卡生成一段中文卡牌插画 prompt。\n"
                        "角色固定为疾旋鼬，外观严格参考微信表情包库存：蓝白短毛、大耳朵、圆脸、蓝色尾巴和爪子、白色胸腹；"
                        "不改变角色设计，不添加额外服饰/配件。\n"
                        "只根据卡牌改变动作、表情、元素特效和背景：雪原、极光、冰晶、冰洞、暴风雪等。\n"
                        "统一风格：干净边缘、卡牌插画、无文字、无边框。\n"
                        "统一比例：3:4 竖版（768×1024），主体居中，适合卡牌插画。\n"
                        '输出格式：{"prompts": [{"id": "...", "prompt": "..."}]}\n' 
                        f"卡牌：{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
            config,
            max_tokens=5000,
        )
        if content:
            try:
                raw = _extract_json(content)
                by_id = {item["id"]: item["prompt"] for item in raw.get("prompts", []) if "id" in item}
                if by_id:
                    return [
                        {"id": card.id, "name": card.name, "prompt": by_id.get(card.id, _fallback_art_prompt(card, card_set.theme))}
                        for card in card_set.cards
                    ]
            except Exception as error:  # noqa: BLE001
                print(f"[art] invalid LLM JSON: {error}")
    return [
        {"id": card.id, "name": card.name, "prompt": _fallback_art_prompt(card, card_set.theme)}
        for card in card_set.cards
    ]


CARD_ACTION_HINTS = {
    "cf-00": "在雪原上转身横扫，尾巴带起冰雪弧线，背景是极光雪坡",
    "cf-01": "向前突进，爪尖刺出冰晶，背景是冰洞",
    "cf-02": "蜷缩防御，周围升起冰晶护盾，背景是暴风雪",
    "cf-03": "站在雪原上仰头，极光在身后回响，周围漂浮冰晶",
    "cf-04": "张口吐出寒气，面前形成冰墙，背景是冰原",
    "cf-05": "跃起旋转，霜花与旋力爆发，背景是极光雪原",
    "cf-06": "在雪原上快速奔跑，脚下溅起雪粉，背景是远山",
    "cf-07": "站立蓄力，身周浮现冰龙鳞片护甲，背景是冰洞",
    "cf-08": "甩尾扫出青色旋风，背景是雪原",
    "cf-09": "在空中回旋，青色气流环绕，背景是极光",
    "cf-10": "站立，周围形成青色气流护罩，背景是雪坡",
    "cf-11": "贴地疾驰，身后拉出青色风轨，背景是雪原",
    "cf-12": "站在风眼中心，周围旋风环绕，背景是暴风雪",
    "cf-13": "跃起释放大型青色旋力爆发，背景是极光",
    "cf-14": "张口喷出龙息光束，背景是冰洞",
    "cf-15": "咆哮，身后浮现冰龙虚影，背景是暴风雪",
    "cf-16": "站立，龙鳞覆盖身体，背景是冰原",
    "cf-17": "愤怒反击，龙影在身后，背景是雷光",
    "cf-18": "站立释放威压，龙影盘旋，背景是极光",
    "cf-19": "召唤极寒龙卷，冰雪与龙影交织，背景是冰原",
    "cf-20": "在雪原上轻快回旋，雪花环绕，背景是极光",
    "cf-21": "抱着一颗大雪球，周围有暖色小光点，背景是雪地",
    "cf-22": "在雪原上迈步，脚下霜花旋开，背景是雪坡",
    "cf-23": "站在极光下，周围能量涌动，背景是雪原",
}


def _card_action_hint(card: Card) -> str:
    return CARD_ACTION_HINTS.get(card.id, f"围绕「{card.name}」设计动作，背景为雪原/极光，表现：{card.description}")


def _fallback_art_prompt(card: Card, theme: str) -> str:
    element_style = {
        Element.ice: "冰晶、霜花、冷蓝色光、雪雾",
        Element.wind: "旋风、飘雪、青绿色气流、极光",
        Element.dragon: "龙鳞、紫色雷光、冰洞、威压感",
        Element.neutral: "雪原、暖色小光点",
    }.get(card.element, "雪原、极光、冰晶")
    return (
        f"卡牌插画，角色固定为疾旋鼬，外观严格参考微信表情包库存：蓝白短毛、大耳朵、圆脸、"
        "蓝色尾巴和爪子、白色胸腹；不改变角色设计，不添加额外服饰/配件。"
        f"动作/背景：{_card_action_hint(card)}。"
        f"元素氛围：{element_style}。"
        "干净边缘，中心构图，卡牌美术，无文字，无边框，高细节，柔和体积光；"
        "画面比例 3:4 竖版（768×1024），主体居中，适合卡牌插画"
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def save_card_set(card_set: CardSet, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card_set.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_card_set(path: str | Path) -> CardSet:
    return CardSet.model_validate_json(Path(path).read_text(encoding="utf-8"))
