# retrolens:reflect Command

Extract reusable human lessons and agent directives from a session analysis.

> **Full skill reference**: Read `retrolens-plugin/SKILL.md` → Workflow D for lesson formats and writing standards.

## Prerequisites

Run `/retrolens:analyze` first to produce a session analysis.

## Usage

```bash
/retrolens:reflect [<session-id>] [--out <file>] [--format <md|json>]
```

## Arguments

- `<session-id>` - Session ID/prefix, `latest`, or omit to use the most recently analyzed session

## Options

- `--out <file>` - Write output to a file (default: `notes/session-<ID>-lessons.md`)
- `--format <md|json>` - Output format (default: `md`)

## What This Command Does

### Step 1: Read the session through learning lenses

For each turn, identify:

| Signal | What to look for |
|--------|------------------|
| 🔴 Errors & Fixes | Tool failures, repeated retries, user corrections |
| 🟡 Inefficiency | Unnecessary exploration, redundant reads, off-target tool calls |
| 🟢 Effective practices | Right tool first try, clean drill-down, good commit points |
| ⚠️ Environment traps | API limits, version issues, proxy failures |

### Step 2: Produce two output sections

**Human lessons** — how to interact with agents better:
- Which prompts worked first try vs. caused confusion?
- What upfront context would have saved turns?
- Which tasks were too large and should be split?

**Agent directives** — reusable rules for future sessions:
- Project conventions (naming, file structure, import order)
- Environment gotchas (proxy, API keys, version constraints)
- Sequencing rules ("always run tests after editing")
- Known pitfalls discovered in this session

### Step 3: Write the artifact

Ask the user where to save:

> Where should I write the lessons?
>
> 1. `notes/session-<ID>-lessons.md` — standalone file
> 2. Append to `AGENTS.md` — VS Code Copilot instructions
> 3. Append to `CLAUDE.md` — Claude Code instructions
> 4. Append to `.github/copilot-instructions.md` — Copilot global
> 5. Custom path

## Success Criteria

- At least 5 human lessons + 5 agent directives
- Each item is specific (no generic advice) and traceable to session behavior (cite turn numbers)
