# retrolens:discover Command

Discover where conversation logs live, then verify the directory is readable by RetroLens.

## CRITICAL: Read SKILL.md First

Read `../SKILL.md` → **Workflow A (Discover & Connect to Logs)** for the full methodology.

## Usage

```bash
/retrolens:discover [--platform <auto|vscode|claude_code>] [--project <path>] [--hint <dir>] [--json]
```

## Options

- `--platform <...>` - Prefer a platform when searching (default: `auto`)
- `--project <path>` - Project path to help narrow candidates
- `--hint <dir>` - A starting directory to explore first
- `--json` - Emit machine-readable results (candidates + verification status)

## What This Command Does

- Searches for likely log roots (platform-specific) and candidate JSONL files
- Samples a few files to identify format
- Verifies candidates by running:
  - `retrolens cfg set --path <candidate>`
  - `retrolens ls --json`

## Output (Conceptual)

- A ranked list of candidate directories
- For each candidate: detected source type + whether `retrolens ls` returned sessions

## Failure Handling

- If no candidates validate, it switches to manual filesystem exploration (per SKILL.md) and asks for a tighter `--hint` or `--project`.
