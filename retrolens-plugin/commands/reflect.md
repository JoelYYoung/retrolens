# retrolens:reflect Command

Reflect on an analyzed session and generate reusable lessons and agent directives.

## CRITICAL: Read SKILL.md First

Read `../SKILL.md` → **Workflow D (Reflect & Extract Lessons)** for lesson formats and writing standards.

## Usage

```bash
/retrolens:reflect <session-id-or-analysis> [--out <file>] [--format <md|json>]
```

## Arguments

- `<session-id-or-analysis>` - **Required.** A session ID/prefix (including `latest`) or a prior analysis artifact

## Options

- `--out <file>` - Write lessons/directives to a file (recommended)
- `--format <md|json>` - Output format (default: `md`)

## What This Command Does

- Converts analysis into two outputs:
  - **Human lessons** (what to do next time)
  - **Agent directives** (actionable instructions an agent can follow)
- Ensures lessons are grounded in evidence from the session
- Produces a clean artifact that can be pasted into `notes/`, `AGENTS.md`, or a team playbook

## Success Criteria

- At least 5 lessons + 5 directives
- Each item is specific (no generic advice) and traceable to session behavior
