#!/usr/bin/env bash
# AI Compare Studio launcher (Linux / macOS)
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && . .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
else
  . .venv/bin/activate
fi
exec python -m ai_compare "$@"
