#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv sync
echo "RainCell GPU 将在 http://127.0.0.1:${RAINFALL_PORT:-8000} 启动"
exec uv run python run.py

