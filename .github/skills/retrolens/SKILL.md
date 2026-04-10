---
name: retrolens
description: "Extract workflows and lessons from AI agent conversation logs. Use when: analyzing past sessions, distilling reusable workflows, generating LangGraph agents from conversation patterns, reflecting on errors and best practices, mining cross-session insights."
argument-hint: "Session ID or 'latest' to analyze"
---

# RetroLens — Conversation Log Analysis Skill

Extract **reusable workflows**, **LangGraph agents**, and **lessons learned** from AI agent conversation logs. Navigate sessions like a debugger, identify hidden workflow patterns, and build executable agents from real conversation data.

## When to Use

- Analyzing past AI conversation sessions for patterns
- Extracting a reusable workflow from a completed task
- Generating a LangGraph agent from an observed workflow
- Reflecting on errors, inefficiencies, and best practices
- Mining lessons across multiple sessions
- Building AGENTS.md / CLAUDE.md directives from real experience

## Prerequisites

```bash
pip install retrolens  # or: uv pip install retrolens
retrolens --version  # verify
```

## Workflow A: Extract Workflow & Generate Agent ⭐

**Goal**: Turn a past session into a reusable YAML workflow and optionally a LangGraph agent.

1. **Find the target session**:
   ```bash
   retrolens cfg set --path <log-dir>   # point at logs (auto-detects format)
   retrolens ls --json                   # list available sessions
   ```
   Pick a session with >3 turns that accomplished a meaningful goal.

2. **Get the structured digest**:
   ```bash
   retrolens extract <ID> --json
   ```
   Returns per-turn info: user messages, tools used, files touched, commands run.

3. **Identify phases** by analyzing tool usage patterns:

   | Phase Pattern | Indicators |
   |------|------|
   | Research / Exploration | `read_file`, `semantic_search`, `grep_search`, `list_dir` |
   | Planning | User discussion, `vscode_askQuestions`, agent proposals |
   | Implementation | `create_file`, `replace_string_in_file`, `insert_edit_into_file` |
   | Testing / Validation | `run_in_terminal` with test commands |
   | Iteration / Fix | Repeated edits after errors, user corrections |
   | Documentation | `create_file` on `.md` files, `memory` tool |

4. **Write YAML DSL** to `.retrolens/<name>.workflow.yaml`:
   ```yaml
   workflow:
     name: "my-workflow"
     goal: "What this workflow achieves"
     inputs: ["what it needs"]
     outputs: ["what it produces"]
     phases:
       - name: "research"
         description: "Understand the problem"
         entry_condition: "User provides requirements"
         exit_condition: "Codebase structure understood"
         steps:
           - description: "Read project structure"
             tools: ["read_file", "list_dir"]
           - description: "Decide approach"
             decision: "Is this a refactor or new feature?"
   ```

5. **Generate LangGraph code** (optional):
   ```bash
   retrolens extract --from-yaml .retrolens/<name>.workflow.yaml --langgraph
   ```

## Workflow B: Reflect & Extract Lessons ⭐

**Goal**: Learn from a session — find errors, inefficiencies, good practices, and environment traps.

1. **Get the reflection digest** (requires `cfg set --path` first):
   ```bash
   retrolens reflect <ID> --focus errors --json
   ```

2. **Analyze through 5 lenses**:
   - 🔴 **Errors & Fixes** — tool failures, user corrections, wrong assumptions
   - 🟡 **Inefficiency** — repeated operations, unnecessary exploration
   - 🟢 **Effective Practices** — smart tool selection, progressive drilling
   - ⚠️ **Environment Traps** — API limits, network issues, version compat
   - 📋 **Agent Directives** — explicit rules the user stated

3. **Write output** to `.retrolens/LESSONS.md`

4. **Promote directives** to `AGENTS.md` or `CLAUDE.md` for persistence.

## Workflow C: Navigate Sessions

```bash
retrolens read <ID>               # overview of all turns
retrolens read <ID> --turn 3      # turn 3 details
retrolens read <ID> -t 3 --tool 2 # 3rd tool call in turn 3
retrolens read <ID> --diff 1,5    # diff between turns 1 and 5
```

## Workflow D: Cross-Session Mining

```bash
retrolens ls --limit 10 --json
# For each relevant session: extract + reflect
# Synthesize findings into consolidated lessons
```

## Best Practices

1. **Always use `--json`** for structured data processing
2. **Use prefix matching** — `fb48c` matches `fb48c98d-5233-...`
3. **Progressive drilling** — cfg set → ls → read → turns → tool details
4. **Use `--max-turns`** on long sessions to manage context
5. **Use `--focus`** with reflect to narrow analysis scope
6. **Check existing artifacts** with `retrolens show` before writing
7. **For sessions >10 turns**, use sub-agents to process in parallel
8. **Use `latest`** keyword to quickly access the most recent session

## Command Reference

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `cfg set` | Configure working state | `--path <dir>`, `--source <type>`, `--reader <file.py>`, `--json` |
| `cfg show` | Show current config | `--json` |
| `cfg clear` | Reset config | |
| `ls` | List sessions | `--limit N`, `--json` |
| `read <ID>` | Browse session | `--turn N`, `--tool M`, `--turns 1-5`, `--diff 1,3`, `--json` |
| `extract <ID>` | Extract workflow | `--max-turns N`, `--from-yaml`, `--langgraph`, `--json` |
| `reflect <ID>` | Reflect on lessons | `--focus {all,errors,inefficiency,practices,traps}`, `--json` |
| `show` | View artifacts | `--type {all,lessons,workflow}`, `--json` |

> **Tip**: Use `cfg set --path <dir>` once. Format is auto-detected. All subsequent
> commands (`ls`, `read`, `extract`, `reflect`) use the configured path automatically.

## Full Reference

For complete documentation including YAML DSL format, LangGraph code structure, templates, and supported log formats, see:
```bash
retrolens --skill-path  # prints path to bundled SKILL.md with full reference
```
