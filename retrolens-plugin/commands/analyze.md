# retrolens:analyze Command

Analyze one or more sessions: drill from overview → turns → tool calls, map phases, and produce an analysis artifact.

> **Full skill reference**: Read `retrolens-plugin/SKILL.md` → Workflow C for the detailed drill-down method.

## Prerequisites

Run `/retrolens:connect` first to connect to a log directory.

## Usage

```bash
/retrolens:analyze [<session-id>] [--out <file>] [--turns <range>] [--json]
```

## Arguments

- `<session-id>` - A session ID/prefix, `latest`, or omit to choose interactively

## Options

- `--out <file>` - Write analysis to a file (recommended)
- `--turns <range>` - Limit scope (e.g., `1-10`)
- `--json` - Emit structured summary

## What This Command Does

### Step 1: Ask the user which session(s) to analyze

If no `<session-id>` is provided, list available sessions and ask:

```bash
retrolens ls --json
```

> Found **N sessions**. Which would you like to analyze?
>
> | # | Date | Turns | Title/Preview |
> |---|------|-------|---------------|
> | 1 | 2026-04-10 | 23 | "Fix CI build errors..." |
> | 2 | 2026-04-09 | 8  | "Add custom reader..." |
> | 3 | 2026-04-08 | 45 | "Refactor plugin structure..." |
>
> Enter a number, session ID prefix, or `all` to compare multiple sessions.

### Step 2: Get session overview

```bash
retrolens read <ID> --json              # overview + turn summaries
```

### Step 3: Drill into key turns

```bash
retrolens read <ID> --turn N --json     # full turn detail
retrolens read <ID> -t N --tool M       # specific tool call
retrolens read <ID> --turns 1-5 --json  # range of turns
retrolens read <ID> --diff 1,5 --json   # compare two turns
```

### Step 4: Map phases

Identify workflow stages by tool usage patterns:

| Phase | Dominant Tools |
|-------|----------------|
| Research | `read_file`, `semantic_search`, `grep_search`, `list_dir` |
| Planning | Discussion turns, `vscode_askQuestions` |
| Implementation | `create_file`, `replace_string_in_file` |
| Testing | `run_in_terminal` with test/build commands |
| Iteration | Repeated edits after errors or user corrections |

### Step 5: Produce analysis artifact

Write to `--out` file (or present inline) with:
- **Goal**: what was the session trying to accomplish?
- **Phase map**: which turns → which phase?
- **Key pivots**: where did approach change and why?
- **Failures & fixes**: what went wrong, how resolved?
- **Evidence links**: turn numbers + tool names

For sessions >10 turns, use sub-agents to process turn ranges in parallel.

### Step 6: Prompt for next steps

> Analysis complete. **What would you like to do next?**
>
> - `/retrolens:reflect` — Extract reusable lessons and agent directives from this analysis
> - `/retrolens:analyze <another-id>` — Analyze another session
> - Compare with another session (provide two IDs)

## Success Criteria

- Analysis contains a phase map with at least 3 evidence-backed findings from actual turn data
