#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
THEME="${THEME:-DeepSeek拟人形象（蓝色大肥鱼）}"
exec .venv/bin/python -m src.simulate --theme "$THEME" --games "${GAMES:-300}" --balance
