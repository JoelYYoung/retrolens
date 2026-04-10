# RetroLens — Agent Instructions

## Environment

- Python venv is managed by `uv` at `.venv/`
- Always activate venv before running Python: `source .venv/bin/activate`
- Run tests with: `python -m pytest tests/ -v`

## Project Overview

RetroLens is a lightweight CLI + SKILL that lets any general-purpose AI agent extract workflows and lessons from conversation logs.

- **Entry point**: `retrolens` (installed via `pip install -e .`)
- **Source**: `src/retrolens/` (flat package — no sub-packages except `readers/` and `skills/`)
- **Tests**: `tests/`

## Key Commands

```bash
retrolens cfg set --path <dir>        # Set working log directory (auto-detects format)
retrolens cfg set --source vscode     # Override source type
retrolens cfg set --reader ./r.py     # Register custom reader
retrolens cfg show                    # Show current working state
retrolens ls                          # List sessions in configured path
retrolens read <ID> --json            # Browse session data
retrolens extract <ID> --json         # Extract workflow digest
retrolens reflect <ID> --json         # Reflect on lessons
retrolens show                        # View existing artifacts
```

## Conversation Analysis Skill

Use `retrolens` CLI to analyze conversation logs and extract workflows.
- Extract workflow: `retrolens extract <ID> --json`
- Reflect on lessons: `retrolens reflect <ID> --json`
- Browse session: `retrolens read <ID> --turn N`
- Full guide: `retrolens --skill-path`

Always use `--json` for structured output when processing programmatically.