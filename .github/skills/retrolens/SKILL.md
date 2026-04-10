---
name: retrolens
description: "Navigate AI conversation logs like a debugger. Use when: analyzing past sessions, understanding what happened in a conversation, extracting workflows and lessons from session data."
argument-hint: "Session ID or 'latest' to analyze"
---

# RetroLens — Conversation Log Navigator

Navigate AI agent conversation logs like a debugger. Point at a log directory, list sessions, then drill into turns, tool calls, and diffs.

## When to Use

- Analyzing past AI conversation sessions for patterns
- Understanding what happened in a specific session
- Extracting workflows or lessons from completed tasks
- Comparing different turns within a session
- Mining insights across multiple sessions

## Prerequisites

```bash
pip install retrolens  # or: uv pip install retrolens
retrolens --version    # verify
```

## Workflow A: Analyze a Session ⭐

1. **Point at logs**:
   ```bash
   retrolens cfg set --path <log-dir>   # auto-detects format
   ```

2. **List sessions**:
   ```bash
   retrolens ls --json
   ```
   Pick a session with >3 turns that accomplished a meaningful goal.

3. **Get overview**:
   ```bash
   retrolens read <ID> --json
   ```
   Returns session info + per-turn summaries (user message, tools used, error status).

4. **Drill into interesting turns**:
   ```bash
   retrolens read <ID> --turn 3 --json    # Full turn detail
   retrolens read <ID> -t 3 --tool 0      # Specific tool call
   retrolens read <ID> --turns 1-5 --json # Range of turns
   retrolens read <ID> --diff 1,5 --json  # Compare two turns
   retrolens read <ID> --raw -t 3         # Raw JSON data
   ```

5. **Analyze**: Use the structured data to identify phases, extract workflows, or reflect on lessons. All analysis is done by you (the agent) — retrolens provides the data.

### Phase Identification Guide

| Phase Pattern | Indicators |
|------|------|
| Research / Exploration | `read_file`, `semantic_search`, `grep_search`, `list_dir` |
| Planning | User discussion, `vscode_askQuestions`, agent proposals |
| Implementation | `create_file`, `replace_string_in_file`, `insert_edit_into_file` |
| Testing / Validation | `run_in_terminal` with test commands |
| Iteration / Fix | Repeated edits after errors, user corrections |
| Documentation | `create_file` on `.md` files, `memory` tool |

## Workflow B: Reflect & Extract Lessons ⭐

1. **Read session** with `retrolens read <ID> --json`
2. **Analyze each turn** through these lenses:
   - 🔴 **Errors & Fixes** — tool failures, user corrections, wrong assumptions
   - 🟡 **Inefficiency** — repeated operations, unnecessary exploration
   - 🟢 **Effective Practices** — smart tool selection, progressive drilling
   - ⚠️ **Environment Traps** — API limits, network issues, version compat
   - 📋 **Agent Directives** — explicit rules the user stated
3. **Categorize lessons into two types**:

   **🧑 Human Lessons** — Help humans interact with agents more effectively:
   - What prompt phrasing led to better results?
   - Where did ambiguous instructions cause wasted turns?
   - What context (files, docs, examples) should humans provide upfront?
   - Which tasks are better split into smaller requests?
   - Write to: project notes, team docs, or personal notes.

   **🤖 Agent Lessons** — Reusable directives for future agent sessions:
   - Project-specific conventions (coding style, file structure, naming)
   - Environment gotchas (proxy settings, API quirks, version constraints)
   - "Always do X before Y" rules discovered through trial and error
   - Tool selection heuristics that worked (e.g., "use grep before semantic_search for exact strings")
   - Write to: `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, or memory files.

4. **Write output** — Keep the two categories separate for clarity

## Workflow C: Cross-Session Mining

```bash
retrolens ls --limit 10 --json
# For each relevant session: read --json, analyze, compare
# Synthesize findings into consolidated lessons
```

## Workflow D: Validate a Custom Reader / Parser

When building or modifying a log reader, always verify correctness:

1. **Run the reader** against a known session:
   ```bash
   retrolens read <ID> --turn 1 --json > /tmp/parsed.json
   ```
2. **Read the raw source** for comparison:
   ```bash
   retrolens read <ID> --turn 1 --raw > /tmp/raw.json
   ```
3. **Cross-check critical fields**:
   - `tool_name` is populated (not empty string)
   - `tool_calls` count matches raw data
   - `files_touched` lists real file paths
   - `user_message` and `assistant_response` are non-empty
   - Timestamps parse correctly
4. **Run the test suite** after any parser change:
   ```bash
   python -m pytest tests/ -v
   ```
5. **Spot-check with the original JSONL** if anything looks wrong:
   ```bash
   # Example: verify tool count in raw JSONL
   cat <session.jsonl> | python3 -c "import sys,json; ..."
   ```

> **Common pitfall**: JSON field names from `--json` output (e.g., `tool_name`) may
> differ from raw JSONL fields (e.g., `toolId`). Always check the actual schema.

## Best Practices

1. **Always use `--json`** for structured data processing
2. **Use prefix matching** — `fb48c` matches `fb48c98d-5233-...`
3. **Progressive drilling** — cfg set → ls → read → turns → tool details
4. **For sessions >10 turns**, use sub-agents to process in parallel
5. **Use `latest`** keyword to quickly access the most recent session

## Command Reference

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `cfg set` | Configure working state | `--path <dir>`, `--source <type>`, `--reader <file.py>` |
| `cfg show` | Show current config | `--json` |
| `cfg clear` | Reset config | |
| `ls` | List sessions | `--limit N`, `--json` |
| `read <ID>` | Browse session | `--turn N`, `--tool M`, `--turns 1-5`, `--diff 1,3`, `--raw`, `--json` |

> **Tip**: Use `cfg set --path <dir>` once. Format is auto-detected. All subsequent
> commands (`ls`, `read`) use the configured path automatically.

## Full Reference

For complete documentation including supported log formats and custom reader guide,
see the bundled SKILL.md at `src/retrolens/skills/SKILL.md`.
