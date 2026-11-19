"""Pydantic models for CardForge cards and card sets."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CardType(str, Enum):
    attack = "attack"
    skill = "skill"
    power = "power"


class Element(str, Enum):
    ice = "ice"
    wind = "wind"
    dragon = "dragon"
    neutral = "neutral"


class EffectType(str, Enum):
    damage = "damage"
    block = "block"
    heal = "heal"
    draw = "draw"
    buff = "buff"
    debuff = "debuff"
    energy = "energy"


class Effect(BaseModel):
    type: EffectType
    amount: int = Field(ge=0, le=30)
    stat: Literal["strength", "weak", "vulnerable", "poison"] | None = None

    @field_validator("stat")
    @classmethod
    def validate_stat(cls, value: str | None, info):
        effect_type = info.data.get("type")
        if effect_type == EffectType.buff and value not in {"strength"}:
            raise ValueError("buff currently supports stat='strength'")
        if effect_type == EffectType.debuff and value not in {"weak", "vulnerable", "poison"}:
            raise ValueError("debuff supports stat='weak', 'vulnerable' or 'poison'")
        if effect_type not in {EffectType.buff, EffectType.debuff} and value is not None:
            raise ValueError("stat is only valid for buff/debuff effects")
        return value


class Card(BaseModel):
    id: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=48)
    cost: int = Field(ge=0, le=3)
    type: CardType
    element: Element = Element.neutral
    rarity: Literal["common", "uncommon", "rare"] = "common"
    description: str = Field(min_length=1, max_length=240)
    effects: list[Effect] = Field(min_length=1, max_length=3)
    flavor: str = Field(default="", max_length=160)
    keywords: list[str] = Field(default_factory=list, max_length=4)
    art: str | None = None
    upgraded: bool = False

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str):
        cleaned = value.strip().lower().replace(" ", "-")
        if not cleaned:
            raise ValueError("id cannot be empty")
        return cleaned

    @field_validator("effects")
    @classmethod
    def validate_effects(cls, effects: list[Effect]):
        damage_like = [e for e in effects if e.type in {EffectType.damage, EffectType.block, EffectType.heal}]
        if not effects:
            raise ValueError("a card needs at least one effect")
        if len(damage_like) > 2:
            raise ValueError("too many numeric effects")
        return effects

    def summary(self) -> str:
        parts = []
        for effect in self.effects:
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
                label = "虚弱" if effect.stat == "weak" else "易伤"
                parts.append(f"施加 {effect.amount} 层{label}")
        return "；".join(parts)


class CardSet(BaseModel):
    theme: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=80)
    source: Literal["fallback", "llm", "balanced"] = "fallback"
    cards: list[Card] = Field(min_length=8, max_length=40)

    @field_validator("cards")
    @classmethod
    def unique_ids(cls, cards: list[Card]):
        ids = [card.id for card in cards]
        if len(ids) != len(set(ids)):
            raise ValueError("card ids must be unique")
        return cards
