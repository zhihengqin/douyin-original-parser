#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST_ADDRESS="${HOST_ADDRESS:-0.0.0.0}"
PORT="${PORT:-8765}"
MAX_CONCURRENT="${MAX_CONCURRENT:-6}"
COOKIE_FILE="${COOKIE_FILE:-}"
if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  echo "没有找到虚拟环境，请先运行 deploy/linux/install.sh" >&2
  exit 1
fi
cd "${PROJECT_ROOT}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
ARGS=(run.py --serve --host "${HOST_ADDRESS}" --port "${PORT}" --max-concurrent "${MAX_CONCURRENT}")
if [[ -n "${COOKIE_FILE}" ]]; then
  ARGS+=(--cookie-file "${COOKIE_FILE}")
fi
exec "${PROJECT_ROOT}/.venv/bin/python" "${ARGS[@]}"
