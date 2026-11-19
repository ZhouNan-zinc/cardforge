"""CardForge battle engine: a small 2-player card game."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from .models import Card, EffectType, Element

Actor = Literal["player", "enemy"]
MAX_HAND = 8


@dataclass
class Combatant:
    name: str
    hp: int
    max_hp: int
    block: int = 0
    energy: int = 3
    max_energy: int = 3
    strength: int = 0
    weak: int = 0
    vulnerable: int = 0
    poison: int = 0
    draw_per_turn: int = 5
    cards_played_this_turn: int = 0
    element_counts: dict[str, int] = field(default_factory=dict)
    draw_pile: list[Card] = field(default_factory=list)
    hand: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    rng: random.Random = field(default_factory=random.Random)

    def reset_turn(self, draw: int | None = None) -> None:
        self.block = 0
        self.energy = self.max_energy
        self.hand = [card for card in self.hand if "保留" in card.keywords]
        self.element_counts = {}
        self.cards_played_this_turn = 0
        self.draw_cards(self.draw_per_turn if draw is None else draw)

    def draw_cards(self, count: int) -> None:
        for _ in range(count):
            if len(self.hand) >= MAX_HAND:
                return
            if not self.draw_pile:
                if not self.discard:
                    return
                self.draw_pile = self.discard[:]
                self.discard = []
                self.rng.shuffle(self.draw_pile)
            if self.draw_pile:
                self.hand.append(self.draw_pile.pop())

    def take_damage(self, amount: int) -> int:
        amount = max(0, amount)
        absorbed = min(self.block, amount)
        self.block -= absorbed
        self.hp = max(0, self.hp - (amount - absorbed))
        return amount - absorbed

    def heal(self, amount: int) -> int:
        before = self.hp
        self.hp = min(self.max_hp, self.hp + max(0, amount))
        return self.hp - before

    def to_state(self, reveal_hand: bool = True) -> dict:
        state = {
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "block": self.block,
            "energy": self.energy,
            "max_energy": self.max_energy,
            "strength": self.strength,
            "weak": self.weak,
            "vulnerable": self.vulnerable,
            "poison": self.poison,
            "element_counts": dict(self.element_counts),
            "hand_count": len(self.hand),
            "draw_count": len(self.draw_pile),
            "discard_count": len(self.discard),
        }
        if reveal_hand:
            state["hand"] = [card.model_dump() for card in self.hand]
        return state


class Game:
    """A small Slay-the-Spire-like duel.

    Both sides use the same card pool. The player controls one side; the
    other side can be driven by the built-in heuristic AI or an external agent.
    """

    def __init__(
        self,
        cards: list[Card],
        seed: int | None = None,
        starting_actor: Actor = "player",
        player_hp: int = 30,
        player_max_hp: int | None = None,
        enemy_hp: int = 30,
        enemy_max_hp: int | None = None,
        enemy_name: str = "霜原噬影",
        second_player_bonus_hp: int = 10,
        enemy_damage_bonus: int = 0,
        enemy_block_bonus: int = 0,
        player_style: str | None = None,
        enemy_pattern: list[dict] | None = None,
        player_name: str = "你",
        player_max_energy: int = 3,
        player_draw: int = 5,
        player_strength: int = 0,
        player_starting_block: int = 0,
        enemy_phase2_pattern: list[dict] | None = None,
        enemy_elite_modifier: dict | None = None,
        player_ice_bonus: int = 0,
        player_thorn: int = 0,
    ) -> None:
        if len(cards) < 8:
            raise ValueError("need at least 8 cards")
        if player_max_hp is None:
            player_max_hp = player_hp
        if enemy_max_hp is None:
            enemy_max_hp = enemy_hp
        # Mirror decks have a strong first-player advantage; give the second
        # player a small HP bonus so the demo is not decided by the coin flip.
        if starting_actor == "player":
            enemy_hp += second_player_bonus_hp
            enemy_max_hp += second_player_bonus_hp
        else:
            player_hp += second_player_bonus_hp
            player_max_hp += second_player_bonus_hp
        self.seed = seed
        self.enemy_damage_bonus = enemy_damage_bonus
        self.enemy_block_bonus = enemy_block_bonus
        self.player_style = player_style
        self.player_ice_bonus = player_ice_bonus
        self.player_thorn = player_thorn
        self.enemy_pattern = enemy_pattern
        self.enemy_phase2_pattern = enemy_phase2_pattern
        self.enemy_elite_modifier = enemy_elite_modifier
        self.elite_enraged = False
        self.enemy_phase = 1
        self.enemy_intent_index = 0
        self.wind_style_used = False
        self.player_bursts = 0
        self.rng = random.Random(seed)
        self.player = Combatant(
            player_name,
            player_hp,
            player_max_hp,
            max_energy=player_max_energy,
            draw_per_turn=player_draw,
            draw_pile=[c.model_copy(deep=True) for c in cards],
        )
        self.player.strength = player_strength
        self.player.block = max(0, player_starting_block)
        self.enemy = Combatant(
            enemy_name,
            enemy_hp,
            enemy_max_hp,
            draw_pile=[c.model_copy(deep=True) for c in cards],
        )
        self.player.rng = self.rng
        self.enemy.rng = self.rng
        self.rng.shuffle(self.player.draw_pile)
        self.rng.shuffle(self.enemy.draw_pile)
        self.active: Actor = starting_actor
        self.turn = 1
        self.winner: Actor | None = None
        self.log: list[str] = []
        self._start_turn(self.active)

    # ------------------------------------------------------------------
    # Turn flow
    # ------------------------------------------------------------------
    def _start_turn(self, actor: Actor) -> None:
        combatant = self._actor(actor)
        combatant.reset_turn()
        if combatant.poison > 0 and combatant.hp > 0:
            tick = combatant.poison
            combatant.hp = max(0, combatant.hp - tick)
            combatant.poison -= 1
            self.log.append(f"☠ {combatant.name} 受到 {tick} 点中毒伤害（无视格挡）")
            self._check_winner()
        if actor == "player":
            self.wind_style_used = False
        if actor == "enemy" and self.enemy_elite_modifier and self.enemy_elite_modifier.get("id") == "regen" and combatant.hp > 0:
            healed = combatant.heal(4)
            self.log.append(f"💚 精英再生：回复 {healed} 点生命")
        self.log.append(f"—— {combatant.name} 的回合 ——")

    def _other(self, actor: Actor) -> Actor:
        return "enemy" if actor == "player" else "player"

    def _actor(self, actor: Actor) -> Combatant:
        return self.player if actor == "player" else self.enemy

    def _check_winner(self) -> None:
        if self.player.hp <= 0 and self.enemy.hp <= 0:
            self.winner = "player" if self.player.hp >= self.enemy.hp else "enemy"
        elif self.player.hp <= 0:
            self.winner = "enemy"
        elif self.enemy.hp <= 0:
            self.winner = "player"
        if self.winner:
            self.log.append(f"🏁 {self._actor(self.winner).name} 获胜！")

    # ------------------------------------------------------------------
    # Card play
    # ------------------------------------------------------------------
    def play_card(self, actor: Actor, index: int) -> dict:
        if self.winner:
            raise ValueError("game is already over")
        if actor != self.active:
            raise ValueError("not this actor's turn")
        combatant = self._actor(actor)
        if index < 0 or index >= len(combatant.hand):
            raise ValueError("invalid hand index")
        card = combatant.hand[index]
        if card.cost > combatant.energy:
            raise ValueError("not enough energy")
        combatant.energy -= card.cost
        combatant.hand.pop(index)
        if "消耗" not in card.keywords:
            combatant.discard.append(card)
        self.log.append(f"{combatant.name} 打出「{card.name}」：{card.summary()}")
        self._apply_card(actor, card)
        self._element_burst(actor, card.element)
        self._maybe_enter_phase2()
        self._maybe_elite_enrage()
        self._check_winner()
        return self.state_for_player()

    def _apply_card(self, actor: Actor, card: Card) -> None:
        source = self._actor(actor)
        target = self._actor(self._other(actor))
        combo_bonus = 2 if "连击" in card.keywords and source.cards_played_this_turn > 0 else 0
        for effect in card.effects:
            if effect.type == EffectType.damage:
                raw = effect.amount + source.strength + combo_bonus
                if actor == "enemy":
                    raw += self.enemy_damage_bonus
                if actor == "player" and self.player_style == "dragon" and card.element == Element.dragon:
                    raw += 1
                raw = max(0, raw)
                if source.weak > 0:
                    raw = int(raw * 0.75)
                if target.vulnerable > 0:
                    raw = int(raw * 1.5)
                dealt = target.take_damage(raw)
                self.log.append(f"  {target.name} 受到 {dealt} 点伤害（格挡后）")
                if (
                    actor == "player"
                    and self.enemy_elite_modifier
                    and self.enemy_elite_modifier.get("id") == "thorn"
                ):
                    reflected = source.take_damage(3)
                    self.log.append(f"  🩸 精英荆棘：{source.name} 受到 {reflected} 点反伤")
            elif effect.type == EffectType.block:
                amount = effect.amount + combo_bonus
                if actor == "enemy":
                    amount += self.enemy_block_bonus
                if actor == "player" and card.element == Element.ice:
                    amount += (2 if self.player_style == "ice" else 0) + self.player_ice_bonus
                amount = max(0, amount)
                source.block += amount
                self.log.append(f"  {source.name} 获得 {amount} 点格挡")
            elif effect.type == EffectType.heal:
                healed = source.heal(effect.amount)
                self.log.append(f"  {source.name} 回复 {healed} 点生命")
            elif effect.type == EffectType.draw:
                source.draw_cards(effect.amount)
                self.log.append(f"  {source.name} 抽了 {effect.amount} 张牌")
            elif effect.type == EffectType.energy:
                source.energy = min(source.max_energy, source.energy + effect.amount)
                self.log.append(f"  {source.name} 获得 {effect.amount} 点能量")
            elif effect.type == EffectType.buff:
                source.strength += effect.amount
                self.log.append(f"  {source.name} 获得 {effect.amount} 点力量")
            elif effect.type == EffectType.debuff:
                if effect.stat == "weak":
                    target.weak += effect.amount
                    self.log.append(f"  {target.name} 获得 {effect.amount} 层虚弱")
                elif effect.stat == "vulnerable":
                    target.vulnerable += effect.amount
                    self.log.append(f"  {target.name} 获得 {effect.amount} 层易伤")
                elif effect.stat == "poison":
                    target.poison += effect.amount
                    self.log.append(f"  {target.name} 获得 {effect.amount} 层中毒")
        if (
            actor == "player"
            and self.player_style == "wind"
            and card.element == Element.wind
            and not self.wind_style_used
        ):
            self.wind_style_used = True
            source.draw_cards(1)
            self.log.append("🌪 疾风徽记：本回合第一张风牌，抽 1 张")
        source.cards_played_this_turn += 1

    def _element_burst(self, actor: Actor, element: Element) -> None:
        if element == Element.neutral:
            return
        source = self._actor(actor)
        target = self._actor(self._other(actor))
        key = element.value
        source.element_counts[key] = source.element_counts.get(key, 0) + 1
        if source.element_counts[key] % 3 != 0:
            return
        if actor == "player":
            self.player_bursts += 1
        if element == Element.ice:
            source.block += 6
            target.weak += 1
            self.log.append("❄️ 旋力爆发·霜：获得 6 点格挡，敌方虚弱 +1")
        elif element == Element.wind:
            source.draw_cards(1)
            source.energy = min(source.max_energy, source.energy + 1)
            self.log.append("🌪 旋力爆发·风：抽 1 张牌，能量 +1")
        elif element == Element.dragon:
            dealt = target.take_damage(6 + source.strength)
            source.strength += 1
            self.log.append(f"🐉 旋力爆发·龙：造成 {dealt} 点伤害，力量 +1")

    # ------------------------------------------------------------------
    # End turn
    # ------------------------------------------------------------------
    def end_turn(self, actor: Actor) -> dict:
        if self.winner:
            raise ValueError("game is already over")
        if actor != self.active:
            raise ValueError("not this actor's turn")
        combatant = self._actor(actor)
        retained = [card for card in combatant.hand if "保留" in card.keywords]
        combatant.discard.extend(card for card in combatant.hand if "保留" not in card.keywords)
        combatant.hand = retained
        combatant.weak = max(0, combatant.weak - 1)
        combatant.vulnerable = max(0, combatant.vulnerable - 1)
        self.active = self._other(actor)
        if self.active == "player":
            self.turn += 1
        self._start_turn(self.active)
        return self.state_for_player()

    def enemy_take_turn(self, max_cards: int = 12) -> dict:
        """Run the enemy's turn, then hand control back to the player."""
        if self.winner:
            return self.state_for_player()
        if self.active != "enemy":
            return self.state_for_player()
        if self.enemy_pattern:
            return self._enemy_pattern_turn()
        for _ in range(max_cards):
            index = self._enemy_choice()
            if index is None:
                break
            try:
                self.play_card("enemy", index)
            except ValueError:
                break
            if self.winner:
                return self.state_for_player()
        if self.active == "enemy" and not self.winner:
            self.end_turn("enemy")
        return self.state_for_player()

    def _enemy_pattern_turn(self) -> dict:
        self._maybe_enter_phase2()
        pattern = self.enemy_phase2_pattern if self.enemy_phase == 2 and self.enemy_phase2_pattern else self.enemy_pattern
        assert pattern
        intent = pattern[self.enemy_intent_index % len(pattern)]
        self.enemy_intent_index += 1
        kind = intent.get("type", "attack")
        amount = int(intent.get("amount", 0))
        if kind == "attack":
            raw = amount + self.enemy_damage_bonus + self.enemy.strength
            if self.player.vulnerable > 0:
                raw = int(raw * 1.5)
            dealt = self.player.take_damage(raw)
            self.log.append(f"👹 {self.enemy.name} 攻击：造成 {dealt} 点伤害")
            if self.player_thorn > 0:
                reflected = self.enemy.take_damage(self.player_thorn)
                self.log.append(f"  棘甲反伤：{reflected} 点")
        elif kind == "block":
            gained = amount + self.enemy_block_bonus
            self.enemy.block += max(0, gained)
            self.log.append(f"🛡 {self.enemy.name} 防御：获得 {max(0, gained)} 点格挡")
        elif kind == "buff":
            self.enemy.strength += amount
            self.log.append(f"⬆ {self.enemy.name} 强化：力量 +{amount}")
        elif kind == "debuff":
            stat = intent.get("stat", "weak")
            if stat == "vulnerable":
                self.player.vulnerable += amount
                self.log.append(f"⬇ {self.enemy.name} 施加 {amount} 层易伤")
            elif stat == "poison":
                self.player.poison += amount
                self.log.append(f"⬇ {self.enemy.name} 施加 {amount} 层中毒")
            else:
                self.player.weak += amount
                self.log.append(f"⬇ {self.enemy.name} 施加 {amount} 层虚弱")
        elif kind == "heal":
            healed = self.enemy.heal(amount)
            self.log.append(f"💚 {self.enemy.name} 回复 {healed} 点生命")
        self._check_winner()
        if not self.winner:
            self.end_turn("enemy")
        return self.state_for_player()

    def _maybe_elite_enrage(self) -> None:
        if (
            self.enemy_elite_modifier
            and self.enemy_elite_modifier.get("id") == "enrage"
            and not self.elite_enraged
            and self.enemy.hp > 0
            and self.enemy.hp <= self.enemy.max_hp // 2
        ):
            self.elite_enraged = True
            self.enemy.strength += 2
            self.log.append("😡 精英狂怒：力量 +2")

    def _maybe_enter_phase2(self) -> None:
        if (
            self.enemy_phase2_pattern
            and self.enemy_phase == 1
            and self.enemy.hp > 0
            and self.enemy.hp <= self.enemy.max_hp // 2
        ):
            self.enemy_phase = 2
            self.enemy_intent_index = 0
            self.log.append(f"⚡ {self.enemy.name} 进入第二阶段！")

    def current_enemy_intent(self) -> dict | None:
        pattern = self.enemy_phase2_pattern if self.enemy_phase == 2 and self.enemy_phase2_pattern else self.enemy_pattern
        if not pattern:
            return None
        intent = pattern[self.enemy_intent_index % len(pattern)]
        kind = intent.get("type", "attack")
        amount = int(intent.get("amount", 0))
        if kind == "attack":
            amount += self.enemy_damage_bonus + self.enemy.strength
        labels = {
            "attack": f"攻击 {amount}",
            "block": f"防御 {amount}",
            "buff": f"强化 +{amount}",
            "debuff": f"削弱 {amount}",
            "heal": f"回复 {amount}",
        }
        return {"type": kind, "amount": amount, "label": labels.get(kind, kind)}

    def _enemy_choice(self) -> int | None:
        enemy = self.enemy
        affordable = [
            (i, card)
            for i, card in enumerate(enemy.hand)
            if card.cost <= enemy.energy
        ]
        if not affordable:
            return None

        def score(item: tuple[int, Card]) -> float:
            _, card = item
            value = 0.0
            for effect in card.effects:
                if effect.type == EffectType.damage:
                    value += effect.amount * 1.2
                elif effect.type == EffectType.block:
                    value += effect.amount * (1.4 if enemy.hp < 15 else 0.8)
                elif effect.type == EffectType.heal:
                    value += effect.amount * (1.5 if enemy.hp < enemy.max_hp * 0.5 else 0.3)
                elif effect.type == EffectType.buff:
                    value += effect.amount * 2.0
                elif effect.type == EffectType.debuff:
                    value += effect.amount * 1.0
                elif effect.type == EffectType.draw:
                    value += effect.amount * 1.5
                elif effect.type == EffectType.energy:
                    value += effect.amount * 2.0
            return value / max(1, card.cost)

        affordable.sort(key=score, reverse=True)
        return affordable[0][0]

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def state_for_player(self) -> dict:
        intent = self.current_enemy_intent()
        incoming = 0
        if intent and intent.get("type") == "attack":
            raw = int(intent.get("amount", 0))
            if self.enemy.weak > 0:
                raw = int(raw * 0.75)
            if self.player.vulnerable > 0:
                raw = int(raw * 1.5)
            incoming = max(0, raw - self.player.block)
        return {
            "player": self.player.to_state(reveal_hand=True),
            "enemy": self.enemy.to_state(reveal_hand=False),
            "active": self.active,
            "turn": self.turn,
            "winner": self.winner,
            "log": self.log[-18:],
            "seed": self.seed,
            "enemy_intent": intent,
            "incoming_damage": incoming,
            "enemy_phase": self.enemy_phase,
            "enemy_elite_modifier": self.enemy_elite_modifier,
            "player_style": self.player_style,
        }
