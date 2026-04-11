# retrolens:connect Command

Ensure the `retrolens` CLI is installed and usable, then ensure the log format is readable (build/validate a custom reader if needed).

## CRITICAL: Read SKILL.md First

Read `../SKILL.md` → **Workflow B (Build & Validate a Custom Reader)** for the detailed reader contract and validation checklist.

## Usage

```bash
/retrolens:connect --logs <dir> [--platform <auto|vscode|claude_code>] [--reader <file.py>] [--turns <n>]
```

## Options

- `--logs <dir>` - **Required.** Directory containing logs
- `--platform <...>` - Force source type if auto-detect is wrong
- `--reader <file.py>` - Use or create a custom reader implementation
- `--turns <n>` - Validation depth (default: 3)

## What This Command Does

1. Ensures `retrolens` is available (`retrolens --version`), installing if missing
2. Connects to the log directory via `retrolens cfg set --path <dir>` (and `--source` if needed)
3. If the format is unsupported, implements or updates a `BaseReader` subclass
4. Validates parsing via:
   - `python scripts/validate_reader.py --path <dir> --turns <n>`
   - `retrolens ls --json` and `retrolens read <ID> --turn 1 --json`

## Success Criteria

- `retrolens ls --json` returns sessions
- `retrolens read <ID> --turn 1 --json` returns a non-empty turn with consistent tool call counts
