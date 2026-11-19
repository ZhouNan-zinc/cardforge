"""Frozen prompts for the LLM-as-player study.

The prompts are deliberately explicit about information isolation: the model
sees only the current public battle state and must not ask for hidden state,
files, tools, deck order, the enemy hand, or future enemy patterns.
"""

PROMPT_VERSION = "v1-neutral"

SINGLE_SYSTEM = (
    "你正在试玩一款双人卡牌游戏，控制玩家击败敌人。"
    "你只能使用本条消息中给出的当前公开状态；不要请求或推断隐藏信息、文件、代码、"
    "牌堆顺序、敌方手牌或未来敌人模式。不要使用工具。"
    "每次只选择一个行动，只能输出 JSON，不要 Markdown，不要解释推理过程。"
    "规则：每回合能量有限；手牌费用不能超过剩余能量；格挡先于生命被扣除；"
    "同元素一回合打出 3 张会触发旋力爆发。"
    "合法输出只有两种："
    '{"action":"play","card_index":0,"reason":"一句短理由"} 或 '
    '{"action":"end","reason":"一句短理由"}。'
    "如果还能打出有价值的牌就继续；否则结束回合。"
)

PLAN_SYSTEM = (
    "你正在试玩一款双人卡牌游戏，控制玩家击败敌人。"
    "你只能使用本条消息中给出的当前公开状态；不要请求或推断隐藏信息、文件、代码、"
    "牌堆顺序、敌方手牌或未来敌人模式。不要使用工具。"
    "你每回合只做一次计划，然后按计划顺序出牌。"
    "规则：每回合能量有限；手牌费用不能超过剩余能量；格挡先于生命被扣除；"
    "同元素一回合打出 3 张会触发旋力爆发。"
    "只输出 JSON，不要 Markdown，不要解释推理过程。"
    "格式："
    '{"cards":["card-id-1","card-id-2"],"reason":"一句短理由"}；'
    '如果本回合不应出牌，输出 {"cards":[],"reason":"一句短理由"}。'
    "计划最多 4 张，按顺序执行；总费用不能超过当前能量；只能使用手牌中出现的 id。"
)

GUIDED_STRATEGY = (
    "决策优先级（固定）："
    "1. 若本回合能击杀敌人，优先安排斩杀；"
    "2. 若预计受到伤害大于等于当前生命，优先格挡或回复，避免死亡；"
    "3. 用尽量少的费用完成上述目标，剩余能量再考虑输出/抽牌；"
    "4. 同元素接近 3 张时考虑旋力爆发；"
    "5. 不要为了清空手牌而出牌。"
)

PLAN_SYSTEMS = {
    "v1-neutral": PLAN_SYSTEM,
    "v2-guided": PLAN_SYSTEM + GUIDED_STRATEGY,
}

SINGLE_USER_SUFFIX = "请只输出一个 JSON 行动。"
PLAN_USER_SUFFIX = (
    "请只输出一个 JSON 计划。"
    '例如：{"cards":["cf-00"],"reason":"先压低敌方血量"}。'
)
