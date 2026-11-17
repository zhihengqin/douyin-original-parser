#!/usr/bin/env bash
set -euo pipefail
umask 022

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("需要 Python 3.10 或更高版本")
PY

if [[ ! -d "${PROJECT_ROOT}/.venv" ]]; then
  "${PYTHON_BIN}" -m venv "${PROJECT_ROOT}/.venv"
fi
"${PROJECT_ROOT}/.venv/bin/python" -m pip install --upgrade pip
"${PROJECT_ROOT}/.venv/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements.txt"
"${PROJECT_ROOT}/.venv/bin/python" -m pip check
cd "${PROJECT_ROOT}"
"${PROJECT_ROOT}/.venv/bin/python" -m original_parser.check_runtime
export PLAYWRIGHT_BROWSERS_PATH="${PROJECT_ROOT}/.browsers"
"${PROJECT_ROOT}/.venv/bin/python" -m playwright install --with-deps chromium --no-shell
chmod -R a+rX "${PROJECT_ROOT}/.browsers"
echo "安装完成：${PROJECT_ROOT}/.venv/bin/python"
