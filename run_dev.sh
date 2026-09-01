#!/usr/bin/env bash
# Quickstart development script for CoolPath AI
set -e

echo "=========================================="
echo " Starting CoolPath AI Development Server"
echo "=========================================="

# Activate virtualenv if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run uvicorn with auto-reload
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
