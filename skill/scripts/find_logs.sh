#!/usr/bin/env bash
# Find AI conversation log files on the system.
#
# Usage:
#   bash scripts/find_logs.sh [--project /path/to/project]
#
# Searches common locations for JSONL conversation logs from
# VS Code Copilot, Claude Code, and other AI assistants.

set -euo pipefail

PROJECT=""
MAX_DEPTH=8

while [[ $# -gt 0 ]]; do
    case $1 in
        --project) PROJECT="$2"; shift 2 ;;
        --depth)   MAX_DEPTH="$2"; shift 2 ;;
        *)         echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== Searching for AI conversation logs ==="
echo

# VS Code Copilot Chat sessions
echo "--- VS Code / Cursor / Windsurf chat sessions ---"
find "$HOME" -name "*.jsonl" -path "*/chatSessions/*" -maxdepth "$MAX_DEPTH" 2>/dev/null | head -20
echo

# Claude Code project logs
echo "--- Claude Code project logs ---"
if [ -d "$HOME/.claude/projects" ]; then
    find "$HOME/.claude/projects" -name "*.jsonl" -maxdepth 4 2>/dev/null | head -20
else
    echo "  ~/.claude/projects/ not found"
fi
echo

# If project specified, check for local logs
if [ -n "$PROJECT" ]; then
    echo "--- Local logs in project: $PROJECT ---"
    find "$PROJECT" -name "*.jsonl" -maxdepth 3 2>/dev/null | head -10
    find "$PROJECT" -name "index.json" -path "*/logs/*" -maxdepth 3 2>/dev/null | head -5
    echo
fi

# Generic JSONL search (broad)
echo "--- Other JSONL files (broad search) ---"
find "$HOME" -name "*.jsonl" -maxdepth 4 2>/dev/null | \
    grep -v "chatSessions" | grep -v ".claude" | head -10
echo

echo "=== Done ==="
