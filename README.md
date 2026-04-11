# RetroLens 🔬

**A debugger for AI conversations — let any agent navigate, analyze, and learn from past chat sessions.**

[![PyPI](https://img.shields.io/pypi/v/retrolens)](https://pypi.org/project/retrolens/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/JoelYYoung/retrolens/actions/workflows/ci.yml/badge.svg)](https://github.com/JoelYYoung/retrolens/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is this?

Every day you use AI agents (VS Code Copilot, Claude Code, Cursor…) to write code. Those conversation logs are full of reusable workflows and hard-won lessons — but they're locked inside opaque log files.

**RetroLens** is a lightweight CLI + [Skill](skill/SKILL.md) that gives any general-purpose AI agent the ability to:

1. 📂 **Discover** log sessions across platforms
2. 🔍 **Navigate** sessions like a debugger — overview → turn → tool call
3. 💡 **Analyze** what happened and extract lessons, workflows, and agent directives

The CLI handles **only** what agents can't do well — parsing complex log formats and providing a structured traversal API. All analysis and writing is done by the agent itself, guided by `SKILL.md`.

```
┌─────────────────────────────────────────────┐
│  AI Agent (Copilot / Claude / Cursor / ...) │
│                                             │
│  Reads SKILL.md → learns how to use CLI     │
│  Calls CLI → gets structured JSON data      │
│  Analyzes → uses its own LLM reasoning      │
│  Writes → LESSONS.md, AGENTS.md, etc.       │
└──────────────────┬──────────────────────────┘
                   │ CLI calls
                   ▼
┌─────────────────────────────────────────────┐
│  retrolens CLI                              │
│                                             │
│  cfg  → configure log path & source         │
│  ls   → list sessions                       │
│  read → drill into turns & tool calls       │
└──────────────────┬──────────────────────────┘
                   │ Parses log files
                   ▼
┌─────────────────────────────────────────────┐
│  Log Files                                  │
│  VS Code Copilot · Claude Code · Custom     │
└─────────────────────────────────────────────┘
```

## Installation

```bash
pip install retrolens      # from PyPI
# or for development:
uv pip install -e .
```

Verify: `retrolens --version`

## Quick Start

### 1. Point at your logs

```bash
retrolens cfg set --path /path/to/log-directory   # auto-detects format
retrolens cfg show                                 # verify config
```

### 2. List sessions

```bash
retrolens ls
```
```
  #  ID             Source  Date        Model              Turns  Title
  ── ────────────── ──────  ────────    ────────────────── ────── ─────────────────────
  1  fb48c98d-523.. vscode  2026-04-09  claude-opus-4.6    9      Workflow extraction
  2  b1ab08d7-be1.. vscode  2026-04-01  claude-sonnet-4..  1      Traceback analysis
```

### 3. Navigate a session

```bash
retrolens read fb48c               # overview (prefix matching)
retrolens read fb48c --turn 3      # turn 3 detail
retrolens read fb48c -t 3 --tool 0 # first tool call in turn 3
retrolens read fb48c --turns 1-5   # turns 1–5 summaries
retrolens read fb48c --diff 1,5    # compare two turns
retrolens read latest --json       # JSON output for agent consumption
```

---

## How It Works — the Skill Model

RetroLens is designed to be used **by AI agents, not by humans directly**. The included [`SKILL.md`](skill/SKILL.md) teaches any general-purpose agent how to navigate and analyze conversation logs through a series of workflows:

| Workflow | What the Agent Does |
|----------|---------------------|
| **Discover & Connect** | Find log directories, auto-detect format, verify with `ls` |
| **Build Custom Reader** | Implement a reader for unsupported log formats |
| **Analyze a Session** | Progressive drill-down: `ls` → `read` → `read --turn` → `read --tool`, then map workflow phases |
| **Reflect & Extract Lessons** | Categorize findings into human lessons and agent directives |
| **Cross-Session Mining** | Compare multiple sessions for recurring patterns |

The agent reads structured JSON from the CLI and does all reasoning, categorization, and writing itself.

### Integrating the Skill

**VS Code Copilot** — add to `AGENTS.md`:
```markdown
## Conversation Analysis Skill
Use `retrolens` CLI to navigate conversation logs.
- List sessions: `retrolens ls --json`
- Browse session: `retrolens read <ID> --json`
- Drill into turns: `retrolens read <ID> --turn N --json`
Always use `--json` for structured output.
```

**Claude Code** — add to `CLAUDE.md`:
```markdown
Use `retrolens` CLI to navigate conversation logs.
Key commands: cfg set (point at logs), ls (list), read (navigate). Always use --json.
```

---

## CLI Reference

### `cfg` — Configure Working State

```bash
retrolens cfg set --path <dir>        # Set log directory (auto-detects format)
retrolens cfg set --source vscode     # Override detected source type
retrolens cfg set --reader ./r.py     # Register a custom reader
retrolens cfg show                    # Show current config
retrolens cfg clear                   # Reset
```

### `ls` — List Sessions

```bash
retrolens ls                          # List sessions (default: 20)
retrolens ls --limit 50 --json        # JSON output, up to 50
```

### `read` — Navigate Session Data

```bash
retrolens read <ID>                   # Session overview
retrolens read <ID> --turn N          # Turn N detail
retrolens read <ID> -t N --tool M     # Tool call M in turn N
retrolens read <ID> --turns 1-5       # Range of turn summaries
retrolens read <ID> --diff 1,3        # Compare two turns
retrolens read <ID> --raw -t N        # Raw JSON data for a turn
retrolens read <ID> --json            # JSON output (for agents)
```

`<ID>` can be a full UUID, a prefix (e.g. `fb48c`), or `latest`.

## Supported Formats

| Platform | Source Type | Format |
|----------|-------------|--------|
| VS Code Copilot Chat | `vscode` | JSONL (incremental state) |
| Claude Code | `claude_code` | JSONL (event stream) |
| Custom | any | Via custom reader (see [SKILL.md](skill/SKILL.md) Workflow B) |

## Custom Readers

For unsupported log formats, create a Python file that subclasses `BaseReader`:

```python
from pathlib import Path
from retrolens.readers import BaseReader
from retrolens import models

class MyReader(BaseReader):
    source_type = "myplatform"

    def scan(self, path: Path | None = None) -> list[models.SessionInfo]: ...
    def get_overview(self, session_id: str) -> models.SessionOverview: ...
    def get_turn(self, session_id: str, turn_number: int) -> models.TurnDetail: ...
```

Register it: `retrolens cfg set --reader ./my_reader.py`

Full guide: [`skill/SKILL.md`](skill/SKILL.md) → Workflow B, or [`skill/references/READER-API.md`](skill/references/READER-API.md).

## Bundled Scripts

| Script | Purpose |
|--------|---------|
| `skill/scripts/setup.sh` | Install RetroLens and verify |
| `skill/scripts/find_logs.sh` | Discover log directories on disk |
| `skill/scripts/sample_log.py` | Sample & pretty-print a log file to identify format |
| `skill/scripts/validate_reader.py` | Validate a reader against real log data |

## Project Structure

```
src/retrolens/
├── cli.py                  # Click CLI (cfg, ls, read)
├── config.py               # Persistent config state
├── detect.py               # Log format auto-detection
├── models.py               # Pydantic v2 data models
├── formatters.py           # Text / JSON dual-mode output
└── readers/
    ├── __init__.py         # BaseReader ABC + ReaderRegistry
    ├── vscode_copilot.py   # VS Code Copilot JSONL parser
    └── claude_code.py      # Claude Code JSONL parser
skill/
├── SKILL.md                # ⭐ Agent skill document
├── scripts/                # Helper scripts (setup, discovery, validation)
└── references/             # Reader API docs
tests/                      # 128 tests
```

## Development

```bash
uv pip install -e ".[dev]"       # Install with dev deps
python -m pytest tests/ -v       # Run tests
ruff check src/                  # Lint
```

## License

MIT — see [LICENSE](LICENSE)
