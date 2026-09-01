#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=== Running CoolPath AI Test Suite ==="
if [ -d ".venv" ]; then
    .venv/bin/python -m pytest -v tests/
else
    python3 -m pytest -v tests/
fi
