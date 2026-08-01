#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${CST_PYTHON_BIN:-python3}"

if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$PROJECT_ROOT/.venv"
fi

"$PROJECT_ROOT/.venv/bin/pip" install -e "$PROJECT_ROOT[dev]"

if ! command -v cargo >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
fi

if [[ -f "$PROJECT_ROOT/desktop/package.json" ]]; then
  PNPM_BIN="${CST_PNPM_BIN:-pnpm}"
  "$PNPM_BIN" --dir "$PROJECT_ROOT/desktop" install
fi
