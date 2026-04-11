# retrolens:analyze Command

Analyze a designated session by drilling into overview → turns → tool calls, then write an analysis artifact.

## CRITICAL: Read SKILL.md First

Read `../SKILL.md` → **Workflow C (Analyze a Session)** for the step-by-step drill-down method.

## Usage

```bash
/retrolens:analyze <session-id> [--out <file>] [--turns <range>] [--json]
```

## Arguments

- `<session-id>` - **Required.** Full ID, prefix, or `latest`

## Options

- `--out <file>` - Write analysis notes to a file (recommended)
- `--turns <range>` - Limit analysis scope (e.g., `1-10`)
- `--json` - Emit structured summary for downstream commands

## What This Command Does

- Reads session overview and turn summaries
- Spot-checks representative turns and tool calls
- Produces a compact analysis:
  - goal + constraints
  - phase breakdown
  - key pivots / failures / fixes
  - evidence links (turn numbers + tool names)

## Success Criteria

- Output includes phase map + at least 3 concrete evidence points from the session
