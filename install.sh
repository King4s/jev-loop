#!/usr/bin/env bash
# One-time / update setup for Claude Code on Linux or macOS: creates a venv,
# installs dependencies, copies the skill, registers the MCP server (user scope)
# and runs a live self-check. Safe to run again after `git pull`.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo "python3-venv missing: sudo apt install python3-venv" >&2; exit 1; }
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

mkdir -p "$HOME/.claude/skills/jev-loop"
cp skill/jev-loop/SKILL.md "$HOME/.claude/skills/jev-loop/SKILL.md"
echo "Skill installed: $HOME/.claude/skills/jev-loop"

claude mcp remove jev-loop --scope user >/dev/null 2>&1 || true
claude mcp add jev-loop --scope user -- "$ROOT/.venv/bin/python" "$ROOT/jev_mcp.py"
echo "MCP server registered: jev-loop -> $ROOT/jev_mcp.py"

KEY_FILE="$HOME/.config/jev-loop/typesafe_api_key"
if [ -z "${TYPESAFE_API_KEY:-}" ] && [ ! -s "$KEY_FILE" ]; then
  echo "WARNING: no TypeSafe key. Put it in $KEY_FILE (chmod 600) or export TYPESAFE_API_KEY." >&2
  exit 0
fi
.venv/bin/python jev_mcp.py --check
