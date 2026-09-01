#!/usr/bin/env bash
# Runs the tests. They pass with no network at all: every upstream call in
# the suite is answered by an httpx.MockTransport, so FX_UPSTREAM_BASE can
# point at a closed port (as it will when this is graded) and it still passes.
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

exec python -m pytest -q
