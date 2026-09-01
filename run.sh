#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=== Starting CoolPath AI Server ==="
if [ -d ".venv" ]; then
    .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
