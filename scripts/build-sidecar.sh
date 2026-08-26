#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_TRIPLE="${CST_TARGET_TRIPLE:-aarch64-apple-darwin}"
OUTPUT_NAME="crypto-signal-service-${TARGET_TRIPLE}"

"$PROJECT_ROOT/.venv/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --onefile \
  --name "$OUTPUT_NAME" \
  --distpath "$PROJECT_ROOT/desktop/src-tauri/binaries" \
  --workpath "$PROJECT_ROOT/build/pyinstaller" \
  --specpath "$PROJECT_ROOT/build" \
  --collect-all keyring \
  "$PROJECT_ROOT/scripts/service_entry.py"
