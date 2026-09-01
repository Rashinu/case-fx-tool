#!/usr/bin/env bash
# Starts the service. It must listen on $PORT (default 8080) and read the
# upstream base URL from $FX_UPSTREAM_BASE — we point that at a fake upstream
# when we review your work, so nothing here may hardcode frankfurter.dev.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
"$PYTHON" --version >/dev/null 2>&1 || PYTHON=python

if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
fi

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
fi

pip install -q -r requirements.txt

exec uvicorn service.main:app --host 0.0.0.0 --port "${PORT:-8080}"
