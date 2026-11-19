"""CardForge run state: 4-layer branching map, relics, shop, events, potions, boss."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .game import Game
from .models import Card, Element

SCARVES = [
    {"id": "ice", "name": "霜纹徽记", "description": "冰牌额外获得 +2 格挡"},
    {"id": "wind", "name": "疾风徽记", "description": "每回合第一张风牌抽 1 张"},
    {"id": "dragon", "name": "龙鳞徽记", "description": "龙牌额外造成 +1 伤害"},
    {"id": "guard", "name": "霜甲徽记", "description": "最大生命 +8"},
    {"id": "focus", "name": "洞察徽记", "description": "每回合多抽 1 张牌"},
    {"id": "berserk", "name": "狂锋徽记", "description": "每场战斗开始 +2 力量"},
]

BOONS = [
    {"id": "upgrade", "name": "淬炼", "description": "升级一张牌"},
    {"id": "max_hp", "name": "霜心", "description": "最大生命 +6，并回复 6 点生命"},
    {"id": "energy", "name": "风能", "description": "每回合最大能量 +1"},
    {"id": "draw", "name": "洞察", "description": "每回合多抽 1 张牌"},
    {"id": "strength", "name": "锋芒", "description": "每场战斗开始获得 1 点力量"},
    {"id": "heal", "name": "雪泉", "description": "回复 12 点生命"},
]

RELICS = [
    {"id": "iron_shell", "name": "铁壳", "description": "每场战斗开始获得 8 点格挡"},
    {"id": "storm_eye", "name": "风眼", "description": "每回合多抽 1 张牌"},
    {"id": "dragon_heart", "name": "龙心", "description": "每场战斗开始 +2 力量"},
    {"id": "blood_pact", "name": "血契", "description": "每回合能量 +1，最大生命 -5"},
    {"id": "golden_coin", "name": "金币护符", "description": "立即获得 30 金币"},
    {"id": "thorn_mail", "name": "棘甲", "description": "受到攻击时反伤 2"},
    {"id": "frost_core", "name": "霜核", "description": "冰牌额外获得 +2 格挡（可叠加）"},
    {"id": "bloodstone", "name": "血石", "description": "每场战斗胜利后回复 4 点生命"},
    {"id": "stone_heart", "name": "石心", "description": "最大生命 +10，并回复 10 点生命"},
]
RELICS_BY_ID = {item["id"]: item for item in RELICS}

POTIONS = [
    {"id": "heal", "name": "霜泉药", "description": "回复 12 点生命"},
    {"id": "strength", "name": "龙血药", "description": "本场战斗 +2 力量"},
    {"id": "draw", "name": "风铃药", "description": "抽 2 张牌"},
]
POTIONS_BY_ID = {item["id"]: item for item in POTIONS}

PLAYER_NAMES = ["小霜", "阿雪", "团子", "小鼬", "雪球", "霜团", "小蓝", "阿团"]
PLAYER_AVATARS = ["player1", "player2", "player3", "player4"]

ENEMIES = [
    # name, hp, damage bonus, block bonus
    ("霜原噬影", 42, 0, 0),
    ("极光狐", 54, 2, -2),
    ("冰晶巨像", 66, -1, 4),
    ("雪原狼", 52, 3, -1),
    ("极光巨像", 86, 0, 6),
]

ENEMY_PATTERNS: dict[str, list[dict]] = {
    "霜原噬影": [
        {"type": "attack", "amount": 10},
        {"type": "attack", "amount": 12},
        {"type": "debuff", "stat": "poison", "amount": 2},
        {"type": "attack", "amount": 15},
    ],
    "极光狐": [
        {"type": "attack", "amount": 8},
        {"type": "buff", "amount": 2},
        {"type": "attack", "amount": 15},
        {"type": "debuff", "stat": "poison", "amount": 2},
    ],
    "冰晶巨像": [
        {"type": "debuff", "stat": "poison", "amount": 2},
        {"type": "attack", "amount": 17},
        {"type": "block", "amount": 15},
        {"type": "attack", "amount": 22},
    ],
    "雪原狼": [
        {"type": "attack", "amount": 11},
        {"type": "debuff", "stat": "poison", "amount": 2},
        {"type": "attack", "amount": 16},
        {"type": "attack", "amount": 19},
    ],
    "极光巨像": [
        {"type": "block", "amount": 15},
        {"type": "attack", "amount": 21},
        {"type": "buff", "amount": 2},
        {"type": "attack", "amount": 26},
        {"type": "debuff", "stat": "poison", "amount": 3},
        {"type": "attack", "amount": 31},
    ],
}

ENEMY_PHASE2_PATTERNS: dict[str, list[dict]] = {
    "极光巨像": [
        {"type": "attack", "amount": 24},
        {"type": "debuff", "stat": "poison", "amount": 3},
        {"type": "attack", "amount": 30},
        {"type": "buff", "amount": 3},
        {"type": "attack", "amount": 36},
        {"type": "block", "amount": 19},
    ],
}

ELITE_MODIFIERS = [
    {"id": "thorn", "name": "荆棘", "description": "玩家攻击时受到 3 点反伤"},
    {"id": "regen", "name": "再生", "description": "每回合回复 4 点生命"},
    {"id": "enrage", "name": "狂怒", "description": "HP 低于 50% 时力量 +2"},
]

MAP_NODES = {
    "battle": {"id": "battle", "name": "普通战斗", "icon": "⚔", "description": "获得金币与卡牌奖励"},
    "elite": {"id": "elite", "name": "精英战斗", "icon": "👑", "description": "更强，胜利获得遗物/额外 Boon"},
    "rest": {"id": "rest", "name": "休息", "icon": "🔥", "description": "回复生命或升级一张牌"},
    "shop": {"id": "shop", "name": "商店", "icon": "🛒", "description": "用金币买卡、遗物或删牌"},
    "event": {"id": "event", "name": "神秘事件", "icon": "❓", "description": "三选一，有代价也有收益"},
    "treasure": {"id": "treasure", "name": "宝箱", "icon": "🎁", "description": "获得遗物和金币"},
}

CONTRACTS = [
    {"id": "elite_hunter", "name": "精英猎手", "description": "本局击败 2 个精英"},
    {"id": "burst_master", "name": "爆发契约", "description": "本局触发 5 次旋力爆发"},
    {"id": "lean_deck", "name": "苦行契约", "description": "通关时牌组不超过 14 张"},
    {"id": "survivor", "name": "幸存者契约", "description": "通关时生命不低于 20"},
]

MAP_LAYERS = [
    ["battle", "event", "elite"],
    ["battle", "shop", "rest"],
    ["elite", "battle", "event"],
    ["battle", "rest", "shop"],
]

# Each source node connects to 1--2 nodes in the next layer. This prevents
# "every node is reachable from everywhere" and makes route commitment matter.
LEGACY_MAP_EDGES = [
    [[0, 1, 2], [0, 1, 2], [0, 1, 2]],
    [[0, 1, 2], [0, 1, 2], [0, 1, 2]],
    [[0, 1, 2], [0, 1, 2], [0, 1, 2]],
]

MAP_EDGES = [
    # L0 -> L1: event forces a battle; no path starts as all-noncombat.
    [[0, 1], [0], [1, 2]],
    # L1 -> L2: battle/shop/rest all lead into a combat node.
    [[0, 1], [0, 1], [1, 2]],
    # L2 -> L3: event is only reachable from an elite/rest route and
    # must pass through a battle; two fights are mandatory on every path.
    [[0, 1], [1, 2], [0]],
]

# Balance pass: make pure battle routes less dominant and give non-combat
# nodes more relative value. Values are intentionally small and easy to tune.
NORMAL_BATTLE_GOLD = 12
ELITE_BATTLE_GOLD = 35
BATTLE_REWARD_HEAL = 3
REST_HEAL = 18
ENEMY_HP_GROWTH = 4
# Run-level tuning: the 4-card draw package is intentionally scarce, so
# enemy stats are slightly more forgiving than the single-battle benchmark.
ENEMY_HP_SCALE = 0.9
ENEMY_DAMAGE_SCALE = 0.9
SHOP_RELIC_PRICE = 70
TREASURE_GOLD = 25


def describe_effects(effects) -> str:
    parts = []
    for effect in effects:
        if effect.type.value == "damage":
            parts.append(f"造成 {effect.amount} 点伤害")
        elif effect.type.value == "block":
            parts.append(f"获得 {effect.amount} 点格挡")
        elif effect.type.value == "heal":
            parts.append(f"回复 {effect.amount} 点生命")
        elif effect.type.value == "draw":
            parts.append(f"抽 {effect.amount} 张牌")
        elif effect.type.value == "energy":
            parts.append(f"获得 {effect.amount} 点能量")
        elif effect.type.value == "buff":
            parts.append(f"获得 {effect.amount} 点力量")
        elif effect.type.value == "debuff":
            label = {"weak": "虚弱", "vulnerable": "易伤", "poison": "中毒"}.get(effect.stat, effect.stat or "异常")
            parts.append(f"施加 {effect.amount} 层{label}")
    return "；".join(parts)


def upgrade_card(card: Card) -> Card:
    if card.upgraded:
        return card
    effects = []
    for effect in card.effects:
        if effect.type.value in {"damage", "block", "heal"}:
            amount = effect.amount + 2
        elif effect.type.value in {"draw", "buff", "debuff", "energy"}:
            amount = effect.amount + 1
        else:
            amount = effect.amount
        effects.append(effect.model_copy(update={"amount": amount}))
    return card.model_copy(
        update={
            "upgraded": True,
            "effects": effects,
            "description": describe_effects(effects),
        }
    )


@dataclass
class Run:
    card_pool: list[Card]
    seed: int | None = None
    max_hp: int = 30
    player_hp: int = 30
    layer_index: int = 0
    style_id: str | None = None
    player_name: str | None = None
    player_avatar: str | None = None
    boons: list[str] = field(default_factory=list)
    relics: list[str] = field(default_factory=list)
    bonus_energy: int = 0
    bonus_draw: int = 0
    bonus_strength: int = 0
    gold: int = 50
    potions: list[str] = field(default_factory=list)
    deck: list[Card] = field(default_factory=list)
    reward_options: list[Card] = field(default_factory=list)
    boon_options: list[dict] = field(default_factory=list)
    upgrade_options: list[Card] = field(default_factory=list)
    map_layers: list[list[dict]] = field(default_factory=list)
    map_options: list[dict] = field(default_factory=list)
    map_history: list[str] = field(default_factory=list)
    map_choices: list[str] = field(default_factory=list)
    map_edges: list[list[list[int]]] | None = None
    combat_nodes: int = 0
    battles_won: int = 0
    elite_pending: bool = False
    elite_modifier: dict | None = None
    elites_defeated: int = 0
    bursts_triggered: int = 0
    contract: dict | None = None
    current_node_index: int | None = None
    style_options: list[dict] = field(default_factory=list)
    shop_items: list[dict] = field(default_factory=list)
    event_options: list[dict] = field(default_factory=list)
    rest_options: list[dict] = field(default_factory=list)
    remove_options: list[Card] = field(default_factory=list)
    phase: str = "scarf"  # scarf | map | battle | reward | boon | upgrade | rest | shop | remove | event | victory | defeat
    game: Game | None = None
    history: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        if not self.style_options:
            self.style_options = self.rng.sample(SCARVES, 3)
        if self.player_name is None:
            self.player_name = self.rng.choice(PLAYER_NAMES)
        if self.player_avatar is None:
            self.player_avatar = self.rng.choice(PLAYER_AVATARS)
        if not self.deck:
            self.deck = self._make_starter()
        if not self.potions:
            self.potions = [self.rng.choice(POTIONS)["id"]]
        self.map_layers = [
            [dict(MAP_NODES[node_id]) for node_id in layer]
            for layer in MAP_LAYERS
        ]
        if self.map_edges is None:
            self.map_edges = MAP_EDGES
        self.rest_options = [
            {"id": "heal", "name": "休息", "description": "回复 15 点生命"},
            {"id": "upgrade", "name": "强化", "description": "选择一张牌升级"},
        ]
        if self.contract is None:
            self.contract = dict(self.rng.choice(CONTRACTS))
        self._preview_game()

    def _make_starter(self, style_id: str | None = None) -> list[Card]:
        preferred = {
            "ice": Element.ice,
            "wind": Element.wind,
            "dragon": Element.dragon,
            "guard": Element.ice,
            "focus": Element.neutral,
            "berserk": Element.dragon,
        }.get(style_id or "")
        starter: list[Card] = []
        if preferred is not None:
            starter.extend([card for card in self.card_pool if card.element == preferred][:5])
        for element in (Element.ice, Element.wind, Element.dragon, Element.neutral):
            for card in self.card_pool:
                if card.element == element and card not in starter and len(starter) < 12:
                    starter.append(card)
                if len(starter) >= 12:
                    break
            if len(starter) >= 12:
                break
        for card in self.card_pool:
            if card not in starter:
                starter.append(card)
            if len(starter) >= 12:
                break
        return [card.model_copy(deep=True) for card in starter[:12]]

    def _preview_game(self) -> None:
        name, hp, damage_bonus, block_bonus = ENEMIES[0]
        self.game = Game(
            self.deck,
            seed=self.rng.randint(0, 10**9),
            starting_actor="player",
            player_hp=self.player_hp,
            player_max_hp=self.max_hp,
            enemy_hp=hp,
            enemy_max_hp=hp,
            enemy_name=name,
            second_player_bonus_hp=0,
            enemy_damage_bonus=damage_bonus,
            enemy_block_bonus=block_bonus,
            player_style=self.style_id,
            enemy_pattern=ENEMY_PATTERNS[name],
            player_name=self.player_name,
            player_max_energy=3 + self.bonus_energy,
            player_draw=5 + self.bonus_draw,
            player_strength=self.bonus_strength,
        )

    def choose_scarf(self, index: int) -> None:
        if self.phase != "scarf":
            raise ValueError("not in style phase")
        if index < 0 or index >= len(self.style_options):
            raise ValueError("invalid style index")
        self.style_id = self.style_options[index]["id"]
        if self.style_id == "guard":
            self.max_hp += 8
            self.player_hp += 8
        elif self.style_id == "focus":
            self.bonus_draw += 1
        elif self.style_id == "berserk":
            self.bonus_strength += 2
        self.deck = self._make_starter(self.style_id)
        self._preview_game()
        self.phase = "map"
        self.map_options = self.map_layers[0]

    def choose_map(self, index: int) -> None:
        if self.phase != "map":
            raise ValueError("not in map phase")
        if index < 0 or index >= len(self.map_options):
            raise ValueError("invalid map index")
        node = self.map_options[index]
        self.current_node_index = next(
            (i for i, item in enumerate(self.map_layers[self.layer_index]) if item["id"] == node["id"]),
            0,
        )
        self.map_options = []
        self.map_history.append(f"第{self.layer_index + 1}层：{node['name']}")
        self.map_choices.append(node["id"])
        if node["id"] in {"battle", "elite"}:
            self.combat_nodes += 1
        self.elite_pending = node["id"] == "elite"
        self.elite_modifier = None
        if node["id"] in {"battle", "elite"}:
            if self.elite_pending:
                self.elite_modifier = self.rng.choice(ELITE_MODIFIERS)
                self.history.append(f"精英词缀：{self.elite_modifier['name']}")
            self.start_battle(self.layer_index)
        elif node["id"] == "rest":
            self.phase = "rest"
            self.rest_options = [
                {"id": "heal", "name": "休息", "description": "回复 15 点生命"},
                {"id": "upgrade", "name": "强化", "description": "选择一张牌升级"},
            ]
        elif node["id"] == "shop":
            self._open_shop()
        elif node["id"] == "event":
            self._open_event()
        elif node["id"] == "treasure":
            relic = self._grant_random_relic()
            self.gold += TREASURE_GOLD
            self.history.append(f"宝箱：获得 {relic['name']} + {TREASURE_GOLD} 金币")
            self._advance_layer()

    def _start_battle(self, layer: int) -> None:
        if layer >= len(MAP_LAYERS):
            name, hp, damage_bonus, block_bonus = ENEMIES[-1]
            hp = int(hp * 1.20)
            damage_bonus += 2
            display_name = name
            elite = False
            self.elite_pending = False
        else:
            name, hp, damage_bonus, block_bonus = ENEMIES[layer % (len(ENEMIES) - 1)]
            hp += layer * ENEMY_HP_GROWTH
            damage_bonus += layer
            display_name = name
            elite = self.elite_pending
        hp = max(1, int(hp * ENEMY_HP_SCALE))
        damage_bonus = int(damage_bonus * ENEMY_DAMAGE_SCALE)
        if elite:
            hp = int(hp * 1.25)
            damage_bonus += 2
            block_bonus += 2
            display_name = f"{name}·精英"
        starting_block = 8 if "iron_shell" in self.relics else 0
        self.game = Game(
            self.deck,
            seed=self.rng.randint(0, 10**9),
            starting_actor="player",
            player_hp=self.player_hp,
            player_max_hp=self.max_hp,
            enemy_hp=hp,
            enemy_max_hp=hp,
            enemy_name=display_name,
            second_player_bonus_hp=0,
            enemy_damage_bonus=damage_bonus,
            enemy_block_bonus=block_bonus,
            player_style=self.style_id,
            enemy_pattern=[
                {**step, "amount": max(1, round(step["amount"] * ENEMY_DAMAGE_SCALE))}
                if step["type"] == "attack" else dict(step)
                for step in ENEMY_PATTERNS[name]
            ],
            enemy_phase2_pattern=(
                [
                    {**step, "amount": max(1, round(step["amount"] * ENEMY_DAMAGE_SCALE))}
                    if step["type"] == "attack" else dict(step)
                    for step in ENEMY_PHASE2_PATTERNS[name]
                ]
                if name in ENEMY_PHASE2_PATTERNS else None
            ),
            enemy_elite_modifier=self.elite_modifier if elite else None,
            player_name=self.player_name,
            player_max_energy=3 + self.bonus_energy,
            player_draw=5 + self.bonus_draw,
            player_strength=self.bonus_strength,
            player_starting_block=starting_block,
            player_ice_bonus=2 if "frost_core" in self.relics else 0,
            player_thorn=2 if "thorn_mail" in self.relics else 0,
        )
        self.phase = "battle"
        self.history.append(f"第 {layer + 1} 层：{display_name}")

    def start_battle(self, layer: int | None = None) -> None:
        self._start_battle(self.layer_index if layer is None else layer)

    def after_player_action(self) -> None:
        if self.game is None:
            return
        if self.game.winner == "player":
            self.battles_won += 1
            self.player_hp = max(1, self.game.player.hp)
            self.bursts_triggered = max(self.bursts_triggered, getattr(self.game, "player_bursts", 0))
            if self.elite_pending:
                self.elites_defeated += 1
            if "bloodstone" in self.relics:
                self.player_hp = min(self.max_hp, self.player_hp + 4)
            self.gold += ELITE_BATTLE_GOLD if self.elite_pending else NORMAL_BATTLE_GOLD
            if self.elite_pending:
                relic = self._grant_random_relic()
                self.history.append(f"精英战利品：{relic['name']}")
            if self.layer_index >= len(MAP_LAYERS):
                self.phase = "victory"
                self.history.append("通关！")
                return
            self.phase = "reward"
            self.reward_options = self._draw_cards(3, exclude_ids={card.id for card in self.deck})
            self.history.append("战斗胜利，选择一张奖励牌")
        elif self.game.winner == "enemy":
            self.phase = "defeat"
            self.history.append("挑战失败")

    def _draw_cards(self, count: int, exclude_ids: set[str] | None = None) -> list[Card]:
        pool = [card for card in self.card_pool if not exclude_ids or card.id not in exclude_ids]
        if not pool:
            pool = list(self.card_pool)
        weights = {"common": 1.0, "uncommon": 0.45, "rare": 0.15}
        chosen: list[Card] = []
        for _ in range(min(count, len(pool))):
            total = sum(weights.get(card.rarity, 1.0) for card in pool)
            roll = self.rng.random() * total
            for card in pool:
                roll -= weights.get(card.rarity, 1.0)
                if roll <= 0:
                    chosen.append(card.model_copy(deep=True))
                    pool.remove(card)
                    break
        return chosen

    def choose_reward(self, index: int) -> None:
        if self.phase != "reward":
            raise ValueError("not in reward phase")
        if index < -1 or index >= len(self.reward_options):
            raise ValueError("invalid reward index")
        if index >= 0:
            self.deck.append(self.reward_options[index])
        self.reward_options = []
        self.player_hp = min(self.max_hp, self.player_hp + BATTLE_REWARD_HEAL)
        self.phase = "boon"
        self.boon_options = [self.rng.choice(BOONS) for _ in range(3)]

    def _apply_boon(self, boon: dict) -> None:
        self.boons.append(boon["id"])
        if boon["id"] == "max_hp":
            self.max_hp += 6
            self.player_hp = min(self.max_hp, self.player_hp + 6)
        elif boon["id"] == "energy":
            self.bonus_energy += 1
        elif boon["id"] == "draw":
            self.bonus_draw += 1
        elif boon["id"] == "strength":
            self.bonus_strength += 1
        elif boon["id"] == "heal":
            self.player_hp = min(self.max_hp, self.player_hp + 12)

    def choose_boon(self, index: int) -> None:
        if self.phase != "boon":
            raise ValueError("not in boon phase")
        if index < 0 or index >= len(self.boon_options):
            raise ValueError("invalid boon index")
        boon = self.boon_options[index]
        self.boon_options = []
        if boon["id"] == "upgrade":
            candidates = [card for card in self.deck if not card.upgraded]
            if candidates:
                self.upgrade_options = [card.model_copy(deep=True) for card in candidates]
                self.phase = "upgrade"
                return
            self.player_hp = min(self.max_hp, self.player_hp + 10)
        else:
            self._apply_boon(boon)
        self._advance_layer()

    def choose_upgrade(self, index: int) -> None:
        if self.phase != "upgrade":
            raise ValueError("not in upgrade phase")
        if index < 0 or index >= len(self.upgrade_options):
            raise ValueError("invalid upgrade index")
        chosen = self.upgrade_options[index]
        for i, card in enumerate(self.deck):
            if card.id == chosen.id:
                self.deck[i] = upgrade_card(card)
                break
        self.upgrade_options = []
        self._advance_layer()

    def _advance_layer(self) -> None:
        self.layer_index += 1
        if self.layer_index >= len(MAP_LAYERS):
            self._start_battle(len(MAP_LAYERS))
            return
        self.phase = "map"
        prev_layer = self.layer_index - 1
        if prev_layer >= 0 and self.current_node_index is not None:
            targets = self.map_edges[prev_layer][self.current_node_index]
            self.map_options = [self.map_layers[self.layer_index][i] for i in targets]
        else:
            self.map_options = self.map_layers[self.layer_index]

    def choose_rest(self, index: int) -> None:
        if self.phase != "rest":
            raise ValueError("not in rest phase")
        if index == 0:
            self.player_hp = min(self.max_hp, self.player_hp + REST_HEAL)
            self.history.append(f"休息：回复 {REST_HEAL} HP")
            self._advance_layer()
        elif index == 1:
            candidates = [card for card in self.deck if not card.upgraded]
            if candidates:
                self.upgrade_options = [card.model_copy(deep=True) for card in candidates]
                self.phase = "upgrade"
            else:
                self.player_hp = min(self.max_hp, self.player_hp + 10)
                self._advance_layer()
        else:
            raise ValueError("invalid rest index")

    def _open_shop(self) -> None:
        self.phase = "shop"
        cards = self._draw_cards(3)
        self.shop_items = [
            {
                "kind": "card",
                "name": card.name,
                "description": card.description,
                "price": 35 + card.cost * 10,
                "card": card,
            }
            for card in cards
        ]
        relic = self.rng.choice([r for r in RELICS if r["id"] not in self.relics] or RELICS)
        self.shop_items.append(
            {"kind": "relic", "name": relic["name"], "description": relic["description"], "price": SHOP_RELIC_PRICE, "relic": relic}
        )
        potion = self.rng.choice(POTIONS)
        self.shop_items.append(
            {"kind": "potion", "name": potion["name"], "description": potion["description"], "price": 30, "potion": potion}
        )
        if len(self.deck) > 5:
            self.shop_items.append(
                {"kind": "remove", "name": "删牌服务", "description": "从牌组中删除一张牌", "price": 50}
            )

    def choose_shop(self, index: int) -> None:
        if self.phase != "shop":
            raise ValueError("not in shop phase")
        if index < 0 or index >= len(self.shop_items):
            raise ValueError("invalid shop index")
        item = self.shop_items[index]
        if self.gold < item["price"]:
            raise ValueError("not enough gold")
        if item["kind"] == "remove":
            self.gold -= item["price"]
            self.shop_items.pop(index)
            self.remove_options = [card.model_copy(deep=True) for card in self.deck]
            self.phase = "remove"
            return
        self.gold -= item["price"]
        if item["kind"] == "card":
            self.deck.append(item["card"].model_copy(deep=True))
        elif item["kind"] == "relic":
            self._add_relic(item["relic"]["id"])
        elif item["kind"] == "potion":
            if len(self.potions) < 2:
                self.potions.append(item["potion"]["id"])
            else:
                self.gold += item["price"]
        self.shop_items.pop(index)

    def choose_remove(self, index: int) -> None:
        if self.phase != "remove":
            raise ValueError("not in remove phase")
        if index < 0 or index >= len(self.remove_options):
            raise ValueError("invalid remove index")
        chosen = self.remove_options[index]
        self.deck = [card for card in self.deck if card.id != chosen.id]
        self.remove_options = []
        self.phase = "shop"

    def use_potion(self, index: int) -> None:
        if self.phase != "battle" or self.game is None:
            raise ValueError("potion can only be used in battle")
        if index < 0 or index >= len(self.potions):
            raise ValueError("invalid potion index")
        potion = POTIONS_BY_ID[self.potions[index]]
        if potion["id"] == "heal":
            self.game.player.heal(12)
        elif potion["id"] == "strength":
            self.game.player.strength += 2
        elif potion["id"] == "draw":
            self.game.player.draw_cards(2)
        self.player_hp = self.game.player.hp
        self.potions.pop(index)
        self.history.append(f"使用药水：{potion['name']}")

    def reroll_shop(self) -> None:
        if self.phase != "shop":
            raise ValueError("not in shop phase")
        if self.gold < 15:
            raise ValueError("not enough gold")
        self.gold -= 15
        self._open_shop()
        self.history.append("商店刷新：-15 金币")

    def leave_shop(self) -> None:
        if self.phase != "shop":
            raise ValueError("not in shop phase")
        self.shop_items = []
        self._advance_layer()

    def _open_event(self) -> None:
        self.phase = "event"
        pool = [
            {"id": "heal", "name": "雪泉", "description": "回复 15 点生命"},
            {"id": "gold", "name": "风险交易", "description": "失去 8 点生命，获得 30 金币"},
            {"id": "relic", "name": "遗物", "description": "获得一个随机遗物"},
            {"id": "card", "name": "新卡", "description": "获得一张随机卡牌"},
            {"id": "upgrade", "name": "淬炼", "description": "随机升级一张牌"},
            {"id": "max_hp", "name": "霜心", "description": "最大生命 +5，回复 5 点生命；花费 20 金币"},
            {"id": "transform", "name": "换牌", "description": "随机将一张牌换成同元素的另一张牌"},
            {"id": "potion", "name": "药水", "description": "获得一瓶随机药水"},
            {"id": "remove", "name": "断舍", "description": "随机删除一张牌"},
        ]
        self.event_options = self.rng.sample(pool, 3)

    def choose_event(self, index: int) -> None:
        if self.phase != "event":
            raise ValueError("not in event phase")
        if index < 0 or index >= len(self.event_options):
            raise ValueError("invalid event index")
        option = self.event_options[index]
        if option["id"] == "heal":
            self.player_hp = min(self.max_hp, self.player_hp + 15)
        elif option["id"] == "gold":
            self.player_hp = max(1, self.player_hp - 8)
            self.gold += 30
        elif option["id"] == "relic":
            self._grant_random_relic()
        elif option["id"] == "card":
            self.deck.append(self._draw_cards(1)[0])
        elif option["id"] == "upgrade":
            candidates = [i for i, card in enumerate(self.deck) if not card.upgraded]
            if candidates:
                i = self.rng.choice(candidates)
                self.deck[i] = upgrade_card(self.deck[i])
            else:
                self.player_hp = min(self.max_hp, self.player_hp + 10)
        elif option["id"] == "max_hp":
            self.gold = max(0, self.gold - 20)
            self.max_hp += 5
            self.player_hp = min(self.max_hp, self.player_hp + BATTLE_REWARD_HEAL)
        elif option["id"] == "transform":
            card = self.rng.choice(self.deck)
            candidates = [c for c in self.card_pool if c.element == card.element and c.id != card.id]
            if candidates:
                self.deck[self.deck.index(card)] = self.rng.choice(candidates).model_copy(deep=True)
        elif option["id"] == "potion":
            if len(self.potions) < 2:
                self.potions.append(self.rng.choice(POTIONS)["id"])
            else:
                self.gold += 20
        elif option["id"] == "remove":
            if len(self.deck) > 5:
                self.deck.pop(self.rng.randrange(len(self.deck)))
        self.event_options = []
        self._advance_layer()

    def _add_relic(self, relic_id: str) -> None:
        if relic_id in self.relics:
            self.gold += 20
            return
        self.relics.append(relic_id)
        if relic_id == "storm_eye":
            self.bonus_draw += 1
        elif relic_id == "dragon_heart":
            self.bonus_strength += 2
        elif relic_id == "blood_pact":
            self.bonus_energy += 1
            self.max_hp = max(10, self.max_hp - 5)
            self.player_hp = min(self.player_hp, self.max_hp)
        elif relic_id == "golden_coin":
            self.gold += 30
        elif relic_id == "stone_heart":
            self.max_hp += 10
            self.player_hp = min(self.max_hp, self.player_hp + 10)

    def _grant_random_relic(self) -> dict:
        available = [r for r in RELICS if r["id"] not in self.relics]
        relic = self.rng.choice(available or RELICS)
        self._add_relic(relic["id"])
        return relic

    def _contract_done(self) -> bool:
        if not self.contract:
            return False
        cid = self.contract.get("id")
        if cid == "elite_hunter":
            return self.elites_defeated >= 2
        if cid == "burst_master":
            return self.bursts_triggered >= 5
        if cid == "lean_deck":
            return self.phase == "victory" and len(self.deck) <= 14
        if cid == "survivor":
            return self.phase == "victory" and self.player_hp >= 20
        return False

    def _score(self) -> int:
        score = self.layer_index * 100 + self.player_hp * 2 + self.gold // 2
        score += self.elites_defeated * 50 + self.bursts_triggered * 10
        if self.phase == "victory":
            score += 100
        if self._contract_done():
            score += 100
        return max(0, score)

    def _rank(self) -> str:
        score = self._score()
        return "S" if score >= 600 else "A" if score >= 450 else "B" if score >= 300 else "C"

    def state(self) -> dict:
        if self.game is None:
            self._preview_game()
        assert self.game is not None
        if self.phase != "battle":
            self.game.player.hp = self.player_hp
            self.game.player.max_hp = self.max_hp
        return {
            "phase": self.phase,
            "layer": min(self.layer_index + 1, len(MAP_LAYERS) + 1),
            "layers": len(MAP_LAYERS) + 1,
            "battle": min(self.layer_index + 1, len(MAP_LAYERS) + 1),
            "battles": len(MAP_LAYERS) + 1,
            "player_hp": self.player_hp,
            "max_hp": self.max_hp,
            "deck": [card.model_dump() for card in self.deck],
            "deck_size": len(self.deck),
            "style": self.style_id,
            "scarf_options": self.style_options,
            "player_name": self.player_name,
            "player_avatar": self.player_avatar,
            "gold": self.gold,
            "potions": [POTIONS_BY_ID[p] for p in self.potions],
            "relics": [RELICS_BY_ID[r] for r in self.relics],
            "boons": self.boons,
            "reward_options": [card.model_dump() for card in self.reward_options],
            "boon_options": self.boon_options,
            "upgrade_options": [card.model_dump() for card in self.upgrade_options],
            "map_options": self.map_options,
            "map_edges": self.map_edges,
            "map_history": self.map_history[-8:],
            "map_preview": [
                {
                    "layer": index + 1,
                    "nodes": [{"id": node["id"], "name": node["name"], "icon": node["icon"]} for node in layer],
                    "chosen": self.map_choices[index] if index < len(self.map_choices) else None,
                }
                for index, layer in enumerate(self.map_layers)
            ],
            "elite_pending": self.elite_pending,
            "elite_modifier": self.elite_modifier,
            "elites_defeated": self.elites_defeated,
            "bursts_triggered": self.bursts_triggered,
            "combat_nodes": self.combat_nodes,
            "battles_won": self.battles_won,
            "contract": {**self.contract, "done": self._contract_done()} if self.contract else None,
            "score": self._score(),
            "rank": self._rank(),
            "shop_items": [
                {
                    "kind": item["kind"],
                    "name": item["name"],
                    "description": item["description"],
                    "price": item["price"],
                    "card": item["card"].model_dump() if item.get("card") else None,
                }
                for item in self.shop_items
            ],
            "event_options": self.event_options,
            "rest_options": self.rest_options,
            "remove_options": [card.model_dump() for card in self.remove_options],
            "enemy_name": self.game.enemy.name,
            "game": self.game.state_for_player(),
            "history": self.history[-6:],
        }
