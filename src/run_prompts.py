"""Frozen prompts for LLM decisions outside battle (run layer).

The long-term player sees only public run state and current options. It never
receives future map layers, hidden shop stock, enemy patterns, the random seed,
card-pool statistics, or project files.
"""

RUN_PROMPT_VERSION = "v1-neutral"

RUN_SYSTEM = (
    "你正在游玩一款雪原卡牌 roguelike，控制玩家完成一次完整 run。"
    "你只能使用本条消息中给出的公开状态和当前选项；不要请求或推断隐藏信息、"
    "文件、代码、随机种子、未来地图、未来商店库存、敌方手牌或敌人内部模式。"
    "不要使用工具。你只能输出一个 JSON 行动，不要 Markdown，不要解释推理过程。"
    "不同阶段的合法输出："
    '普通选择用 {"action":"choose","index":0,"reason":"一句短理由"}；'
    '商店可用 {"action":"buy","index":0,"reason":"..."}、'
    '{"action":"reroll","reason":"..."} 或 {"action":"leave","reason":"..."}。'
    "index 必须是当前选项中出现的下标，不能选择不可购买/不可负担的项。"
    '可选字段 "strategy"：写一句会公开给战斗玩家的短策略便签，只能基于公开状态。'
)

RUN_PHASE_LABELS = {
    "scarf": "选择流派",
    "map": "选择路线",
    "reward": "选择奖励牌",
    "boon": "选择增益",
    "upgrade": "选择升级牌",
    "rest": "休息点决策",
    "shop": "商店决策",
    "event": "神秘事件",
    "remove": "选择删除的牌",
}

RUN_USER_SUFFIX = "请只输出一个 JSON 行动。"
