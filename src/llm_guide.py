"""CLI: induce a reusable strategy guide from public play records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .opencode_chat import DEFAULT_PLAYER_MODEL, OpenCodeChat
from .strategy_coach import induce_guide, load_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Induce a guide from public CardForge records")
    parser.add_argument("--records", nargs="+", required=True)
    parser.add_argument("--out", default="results/llm-strategy-guide-pilot.md")
    parser.add_argument("--model", default=DEFAULT_PLAYER_MODEL)
    args = parser.parse_args()

    records = load_records(args.records)
    guide = induce_guide(records, chat_fn=OpenCodeChat(model=args.model))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# LLM 自动总结的 CardForge 攻略（pilot）\n\n"
        f"- 记录数：{len(records)}\n"
        f"- 模型：`{args.model}`\n"
        "- 输入：公开对局记录（无 seed、隐藏牌序、敌方手牌、未来商店/地图）\n\n"
        f"{guide}\n",
        encoding="utf-8",
    )
    print(json.dumps({"records": len(records), "out": str(out), "guide": guide}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
