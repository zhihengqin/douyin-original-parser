#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST_ADDRESS="${HOST_ADDRESS:-0.0.0.0}"
PORT="${PORT:-8765}"
MAX_CONCURRENT="${MAX_CONCURRENT:-6}"
COOKIE_FILE="${COOKIE_FILE:-}"
DETAIL_MODE="${DETAIL_MODE:-http}"
BROWSER_PROFILE="${BROWSER_PROFILE:-windows}"
if [[ ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  echo "没有找到虚拟环境，请先运行 deploy/linux/install.sh" >&2
  exit 1
fi
cd "${PROJECT_ROOT}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
"${PROJECT_ROOT}/.venv/bin/python" -m original_parser.check_runtime
ARGS=(run.py --serve --host "${HOST_ADDRESS}" --port "${PORT}" --max-concurrent "${MAX_CONCURRENT}")
ARGS+=(--detail-mode "${DETAIL_MODE}" --browser-profile "${BROWSER_PROFILE}")
ARGS+=(--parse-workers "${PARSE_WORKERS:-3}")
ARGS+=(--request-interval "${REQUEST_INTERVAL:-0.5-1}")
ARGS+=(--cache-ttl "${CACHE_TTL:-300}" --cache-max-entries "${CACHE_MAX_ENTRIES:-128}")
ARGS+=(--queue-wait-timeout "${QUEUE_WAIT_TIMEOUT:-150}" --failure-threshold "${FAILURE_THRESHOLD:-3}")
ARGS+=(--cooldown-seconds "${COOLDOWN_SECONDS:-900}")
if [[ -n "${COOKIE_FILE}" ]]; then
  ARGS+=(--cookie-file "${COOKIE_FILE}")
fi
exec "${PROJECT_ROOT}/.venv/bin/python" "${ARGS[@]}"
