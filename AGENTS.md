# FlowCraft — Agent Instructions

## Environment

- Python venv is managed by `uv` at `.venv/`
- Always activate venv before running Python: `source .venv/bin/activate`
- Run tests with: `python -m pytest tests/ -v`

## Project Overview

FlowCraft is a lightweight CLI + SKILL that lets any general-purpose AI agent extract workflows and lessons from conversation logs.

- **Entry point**: `flowcraft-distill` (installed via `pip install -e .`)
- **Source**: `src/flowcraft/` (flat package — no sub-packages except `readers/` and `skills/`)
- **Tests**: `tests/` (126 tests, all passing)

## Key Commands

```bash
flowcraft-distill scan                        # Discover sessions
flowcraft-distill read <ID> --json            # Browse session data
flowcraft-distill extract <ID> --json         # Extract workflow digest
flowcraft-distill reflect <ID> --json         # Reflect on lessons
flowcraft-distill show                        # View existing artifacts
```

## Conversation Analysis Skill

Use `flowcraft-distill` CLI to analyze conversation logs and extract workflows.
- Extract workflow: `flowcraft-distill extract <ID> --json`
- Reflect on lessons: `flowcraft-distill reflect <ID> --json`
- Browse session: `flowcraft-distill read <ID> --turn N`
- Full guide: `flowcraft-distill --skill-path`

Always use `--json` for structured output when processing programmatically.