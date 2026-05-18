#!/bin/zsh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -x "/Users/zhangruiming/Desktop/python/python环境/.venv/bin/python3" ]; then
  PYTHON_BIN="/Users/zhangruiming/Desktop/python/python环境/.venv/bin/python3"
elif [ -x "/Users/zhangruiming/Desktop/python/.venv/bin/python3" ]; then
  PYTHON_BIN="/Users/zhangruiming/Desktop/python/.venv/bin/python3"
else
  PYTHON_BIN="python3"
fi

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" -m journal_automation "$@"
