# CardForge

**LLM 卡牌游戏的自动红队与平衡评测**

主题：**霜旋**

CardForge 是一个可玩的 24 卡卡牌 roguelike 原型，同时也是一个实验平台：LLM/模板生成卡牌，规则引擎执行对局，Agent 自动模拟，常规平衡作为基线，自动红队搜索路线和奖励策略，最后用独立 seed 验证结构修复是否消除了退化策略。

## 研究问题

> 常用卡牌平衡指标能否预测自动 Agent 发现的结构性退化策略？这些策略来自卡牌内容，还是来自游戏骨架？

项目的核心结论：

- 自动平衡可以降低卡牌胜率方差和强卡数量；
- 卡牌指标改善不等于结构漏洞消失；
- 旧全连通地图上，多个 Agent 都能发现零战斗路线；
- 改为有向地图后，零战斗通关消失，正常战斗仍可通关。

## 功能

- 24 卡、6 流派、4 层有向路线；
- 战斗、精英、Boss、商店、事件、休息、遗物、药水；
- 手牌上限、奖励跳过、消耗/保留/中毒、元素爆发；
- LLM 生成卡组，schema 校验，本地模板兜底；
- 启发式/随机 Agent 模拟；
- 自动平衡和红队策略搜索；
- LLM 提出红队策略，动作级 LLM 路线验证；
- 浏览器 Demo。

## 快速开始

```bash
cd /home/zinc/AAASchool/model/cardforge
./scripts/setup_venv.sh
./scripts/smoke.sh
./scripts/run_server.sh
```

打开：

```text
http://127.0.0.1:8000
```

## 主要实验命令

```bash
# 单元测试
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q

# 单场模拟
.venv/bin/python -m src.simulate --theme 霜旋 --games 300 --seed 42

# 自动平衡 before/after
.venv/bin/python -m src.balance_experiment --games 1000 --seed 42

# 整局与路线评测
.venv/bin/python -m src.simulate_run --runs 200 --seed 42
.venv/bin/python -m src.llm_run_playtest --battle heuristic --longterm heuristic --games 100 --route-mode battle

# 手工红队探针
.venv/bin/python -m src.redteam --games 100 --seed 42 --legacy-map

# 策略权重搜索（不在代码里写“躲战斗”）
.venv/bin/python -m src.redteam_search --generations 5 --population 16 --games 15 --validate-games 100 --map both

# LLM 提出策略并做多 seed 验证
.venv/bin/python -m src.llm_redteam --games 100 --seed 42 --seed-count 5

# 平衡前后 vs 可利用性
.venv/bin/python -m src.redteam_balance --games 100 --seed 42

# 动作级 LLM 低战斗 pilot
.venv/bin/python -m src.llm_run_playtest --battle heuristic --longterm llm --games 10 --seed 42 --guide-file prompts/redteam-guide-lowcombat.md --legacy-map
```

## 目录

```text
cardforge/
├── src/                 # 游戏引擎、生成、模拟、平衡、红队
├── tests/               # 回归测试
├── web/                 # 网页 Demo 与卡图
├── scripts/             # 环境、启动、smoke
├── data/cards/          # 本地生成卡组（运行时）
├── results/             # 运行时模拟输出
├── README.md
└── requirements.txt
```

## 实验产物

实验运行结果写入 `results/`；`docs/` 和最终报告不随代码仓库提交。

## LLM 配置（可选）

没有 API Key 时使用本地模板。

```bash
export LLM_BASE_URL="https://你的-openai-兼容服务/v1"
export LLM_API_KEY="your-key"
export LLM_MODEL="your-model"
```

## 说明

这是课程项目原型，与任何商业卡牌游戏官方无关；卡图、界面和角色素材为自绘/本地生成或已注明来源的素材。
