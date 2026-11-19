"""Isolated adapter that asks the current OpenCode model to act as a game player.

Each call uses a dedicated throw-away working directory and a custom OpenCode
agent with every tool denied. The game prompt therefore sees only the public
battle state supplied by ``LLMAgent`` -- no repository files, no deck order, no
enemy hand, no evaluation statistics, and no other conversation context.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .generator import LLMConfig

DEFAULT_PLAYER_MODEL = "opencode-go/deepseek-v4.1-flash#high"


class OpenCodeChat:
    def __init__(
        self,
        model: str = DEFAULT_PLAYER_MODEL,
        isolation_dir: str | Path = "/tmp/opencode/cardforge-llm-player",
        timeout: int = 180,
        agent_name: str = "cardforge-player",
        system: str | None = None,
    ) -> None:
        if shutil.which("opencode") is None:
            raise RuntimeError("opencode CLI not found")
        self.model = model
        self.isolation_dir = Path(isolation_dir)
        self.timeout = timeout
        self.agent_name = agent_name
        self.system = system or (
            "你是一个隔离的卡牌游戏玩家。只使用用户消息中给出的公开状态；"
            "不要请求文件、代码、工具、牌堆顺序、敌方手牌或未来信息。只输出用户要求的 JSON。"
        )
        self.isolation_dir.mkdir(parents=True, exist_ok=True)
        self._write_agent_config()

    def _write_agent_config(self) -> None:
        config = {
            "$schema": "https://opencode.ai/config.json",
            "model": self.model,
            "instructions": [],
            "skills": [],
            "agents": {
                self.agent_name: {
                    "description": "Isolated JSON-only CardForge agent",
                    "mode": "primary",
                    "model": self.model,
                    "system": self.system,
                    "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
                    "steps": 1,
                }
            },
        }
        (self.isolation_dir / "opencode.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _extract_text(stdout: str) -> str:
        pieces: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "text":
                text = (event.get("part") or {}).get("text")
                if text:
                    pieces.append(str(text))
        return "\n".join(pieces).strip()

    def __call__(self, messages: list[dict], _: LLMConfig) -> str | None:
        prompt = "\n\n".join(
            f"{message.get('role', 'user')}:\n{message.get('content', '')}"
            for message in messages
            if message.get("content")
        )
        env = os.environ.copy()
        env["PWD"] = str(self.isolation_dir)
        for key in (
            "OPENCODE_SESSION_ID",
            "OPENCODE",
            "OPENCODE_TERMINAL",
            "OPENCODE_CONFIG_CONTENT",
            "OPENCODE_CLI_CONFIG_CONTENT",
        ):
            env.pop(key, None)
        command = [
            "opencode",
            "run",
            "--agent",
            self.agent_name,
            "--model",
            self.model,
            "--format",
            "json",
            prompt,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.isolation_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        return self._extract_text(completed.stdout) or None
