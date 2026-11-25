#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python_cmd="${PYTHON_BIN:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  if ! "$python_cmd" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
    echo 'Python 3.12 or newer is required. Set PYTHON_BIN to your Python 3.12+ executable.' >&2
    exit 1
  fi
  "$python_cmd" -m venv .venv
fi
if ! .venv/bin/python -c 'import django, rest_framework, dotenv' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python manage.py runserver --noreload 127.0.0.1:8000
