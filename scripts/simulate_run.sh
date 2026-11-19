#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m src.simulate_run --runs "${RUNS:-200}" --seed "${SEED:-42}"
