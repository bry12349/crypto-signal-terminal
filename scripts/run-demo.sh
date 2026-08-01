#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CST_MODE=demo
export PYTHONPATH="$PROJECT_ROOT/src"
exec "$PROJECT_ROOT/.venv/bin/python" -m crypto_signal_terminal.main
