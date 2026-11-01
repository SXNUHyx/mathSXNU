#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo '请先运行 bash scripts/setup.sh' >&2
  exit 1
fi
exec .venv/bin/python manage.py runserver "${CLASSROOM_BIND:-0.0.0.0:8000}" --noreload
