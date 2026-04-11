# retrolens Command

End-to-end session postmortem using the RetroLens skill.

## CRITICAL: Read SKILL.md First

**Before doing anything else, read `../SKILL.md`.** It defines the workflows and the verification loop. This command is intentionally brief and defers details to SKILL.md.

## Usage

```bash
/retrolens <session-or-scope> [--platform <auto|vscode|claude_code>] [--logs <dir>] [--out <file>]
```

## Arguments

- `<session-or-scope>` - **Required.** One of:
  - `latest` (default target)
  - a session ID / prefix
  - a scope like `this-repo` (agent resolves to project path → logs)

## What This Command Does

1. **Discover** a valid log directory (or uses `--logs`)
2. **Connect** by ensuring `retrolens` is available and the log format is readable
3. **Analyze** the designated session (goal, phases, pivots, tool usage)
4. **Reflect** and generate lessons + reusable directives

## Success Criteria

- The log directory is validated by a real `retrolens ls --json`
- The session can be read at overview + at least 1 turn
- The output artifact (`--out`) contains lessons and agent directives
