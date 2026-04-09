# RetroLens 🔬

**Learn from your AI agent conversations — extract workflows, generate executable agents, accumulate lessons learned.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is this?

Every day you use AI agents like VS Code Copilot, Claude Code, or Cursor to write code. These conversation logs contain reusable workflows and hard-won lessons — but they're locked inside log files, inaccessible for reuse.

**RetroLens** provides a lightweight CLI + a SKILL.md guide that enables any general-purpose agent to:

1. 📂 **Scan** logs → discover conversation sessions
2. 🔍 **Browse** sessions → drill down like a debugger (overview → turn → tool call)
3. 🧬 **Extract** workflows → identify phases, steps, decision points → output YAML DSL
4. 🤖 **Generate** agents → auto-generate LangGraph executable code from YAML DSL
5. 💡 **Reflect** on lessons → analyze errors, inefficiencies, best practices → output LESSONS.md

```
Conversation Logs → scan → read → extract → YAML DSL → LangGraph Agent
                                    ↓
                                 reflect → LESSONS.md / AGENTS.md
```

## Installation

```bash
# Recommended: using uv
uv pip install -e .

# Or using pip
pip install -e .
```

Verify installation:
```bash
retrolens --version    # 0.4.0
retrolens --skill-path # prints SKILL.md path
```

## Quick Start: 5-Minute Walkthrough

### 1. Scan your VS Code conversation logs

```bash
retrolens scan
```
```
Found 5 session(s):

  #    ID             Source     Date         Model                  Turns  Title
  ──── ────────────── ────────── ──────────── ────────────────────── ────── ──────
  1    fb48c98d-523.. vscode     2026-04-09   claude-opus-4.6        9      Workflow extraction
  2    b1ab08d7-be1.. vscode     2026-04-01   claude-sonnet-4..      1      Traceback analysis
```

### 2. Browse a session

```bash
retrolens read fb48c  # prefix matching works
```
```
=== Session: fb48c98d-523 ===
Total Turns: 9

  #1   [User] The main goal of this project is...
       [Tools: 568] findFiles, readFile, runSubagent...
  #2   [User] I think it should be...
       [Tools: 8] memory, readFile
  ...
```

### 3. Drill into a specific turn

```bash
retrolens read fb48c --turn 5        # turn 5 details
retrolens read fb48c -t 5 --tool 0   # first tool call in turn 5
```

### 4. Extract workflow digest

```bash
retrolens extract fb48c --json   # structured SessionDigest output
```

### 5. Reflect on lessons learned

```bash
retrolens reflect fb48c --focus errors --json   # focus on error analysis
```

---

## ⭐ Core Feature: Refine Workflows with SKILL

This is RetroLens's most important capability. It works as a **Skill** — a standardized document that guides any general-purpose agent through analyzing conversation logs and distilling reusable workflows.

### How It Works

```
┌──────────────────────────────────────────────┐
│  General Agent (VS Code Copilot / Claude...) │
│                                              │
│  Reads SKILL.md → knows how to use CLI tools │
│  Calls CLI → gets structured log data        │
│  Analyzes data → uses its own LLM reasoning  │
│  Writes files → .retrolens/LESSONS.md etc.   │
└──────────────────────────────────────────────┘
         ▲                    │
    SKILL.md guidance     CLI calls
         │                    ▼
┌──────────────────────────────────────────────┐
│  retrolens CLI (lightweight)         │
│                                              │
│  scan    → discover log sessions             │
│  read    → traverse session data             │
│  extract → output SessionDigest (JSON)       │
│  reflect → output SessionDigest + hints      │
│  show    → view existing artifacts           │
└──────────────────────────────────────────────┘
         ▲
    Parses log files
         │
┌──────────────────────────────────────────────┐
│  Log Files                                   │
│  VS Code Copilot: JSONL (incremental state)  │
│  RetroLens Native: JSON                      │
└──────────────────────────────────────────────┘
```

### Workflow A: Extract Workflow & Generate Agent

The core use case. Full pipeline:

```bash
# Step 1: Find the target session
retrolens scan --json

# Step 2: Get structured digest
retrolens extract <ID> --json
# Output includes: user messages, tools used, files touched, commands run per turn

# Step 3: Agent analyzes the digest and identifies workflow phases
#   Research phase    → read_file, semantic_search dominant
#   Planning phase    → user discussion, agent asks questions
#   Implementation    → create_file, replace_string dominant
#   Testing phase     → run_in_terminal running tests
#   Documentation     → writing .md files

# Step 4: Agent writes analysis as YAML DSL
#   → .retrolens/my-workflow.workflow.yaml

# Step 5: Generate LangGraph code
retrolens extract --from-yaml .retrolens/my-workflow.workflow.yaml --langgraph
# → .retrolens/my_workflow_agent.py
```

Generated LangGraph code includes:
- **TypedDict state class** — with phase field and custom variables
- **Phase node functions** — one per workflow phase, with step comments
- **Tool function stubs** — placeholder implementations for each tool used
- **Phase router** — state-based phase transitions
- **Graph builder** — StateGraph + edges + compilation
- **Main entry point** — ready to run

### Workflow B: Reflect & Extract Lessons Learned

```bash
# Get reflection digest (with analysis hints)
retrolens reflect <ID> --focus errors --json

# Agent analyzes across 5 dimensions:
#   🔴 Errors & Fixes — tool call failures, user corrections
#   🟡 Inefficiency Patterns — repeated operations, unnecessary exploration
#   🟢 Effective Practices — correct tool selection, progressive exploration
#   ⚠️  Environment Traps — API quotas, network issues, version compat
#   📋 Agent Directives — explicit rules stated by the user

# Agent writes results to:
#   → .retrolens/LESSONS.md     (lessons learned)
#   → AGENTS.md / CLAUDE.md     (persistent agent directives)
```

### Workflow C: Navigate Logs Like a Debugger

```bash
retrolens read <ID>               # overview of all turns
retrolens read <ID> --turn 3      # turn 3 details
retrolens read <ID> -t 3 --tool 2 # 3rd tool call in turn 3
retrolens read <ID> --turns 1-5   # turns 1-5 comparison
retrolens read <ID> --diff 1,5    # diff between turns 1 and 5
```

### Workflow D: Cross-Session Mining

```bash
# Scan all sessions
retrolens scan --json

# For each relevant session: extract + reflect
for id in fb48c a1b2c d3e4f; do
  retrolens extract $id --json
  retrolens reflect $id --json
done

# Agent synthesizes findings across multiple sessions into consolidated lessons
```

---

## YAML Workflow DSL Format

```yaml
workflow:
  name: "Bug Fix Workflow"
  goal: "Fix a reported bug with tests"
  inputs: ["Bug description", "Affected file path"]
  outputs: ["Fixed code", "Updated tests"]

  phases:
    - name: Investigation
      description: Read the affected code and understand the bug
      entry_condition: Bug report received
      exit_condition: Root cause identified
      steps:
        - description: Read the affected file
          tools: [read_file]
        - description: Analyze the code for the bug
          decision: Is it a logic bug or data bug?

    - name: Fix
      description: Implement the fix
      steps:
        - description: Modify the code
          tools: [replace_string_in_file]
        - description: Add input validation
          tools: [replace_string_in_file]

    - name: Verification
      description: Run tests to verify the fix
      steps:
        - description: Run test suite
          tools: [run_in_terminal]
        - description: Check for regressions
          decision: All tests pass?

  dependencies:
    - "Fix requires Investigation results"
    - "Verification requires Fix to be complete"
```

---

## Integrating the SKILL into Your Project

RetroLens is designed as a **Skill** for any general-purpose agent. Here's how to integrate with each platform:

### VS Code Copilot Chat

Add to your project's `AGENTS.md`:
```markdown
## Conversation Analysis Skill
Use `retrolens` CLI to analyze conversation logs and extract workflows.
- Extract workflow: `retrolens extract <ID> --json`
- Reflect on lessons: `retrolens reflect <ID> --json`
- Browse session: `retrolens read <ID> --turn N`
- Full guide: `retrolens --skill-path`
Always use `--json` for structured output.
```

### Claude Code

Add to `CLAUDE.md`:
```markdown
Use `retrolens` CLI to extract workflows and lessons from conversation logs.
Full SKILL.md path: retrolens --skill-path
Key commands: scan, read, extract, reflect, show. Always use --json.
```

### Cursor

Add to `.cursorrules`:
```
When reviewing past sessions, use the retrolens CLI.
Commands: scan, extract, reflect, read, show. Always use --json flag.
```

---

## CLI Command Reference

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `scan` | Discover sessions | `--source vscode`, `--limit N`, `--json` |
| `read <ID>` | Browse session | `--turn N`, `--tool M`, `--turns 1-5`, `--diff 1,3`, `--raw`, `--json` |
| `extract <ID>` | Extract workflow digest | `--max-turns N`, `--from-yaml <file>`, `--langgraph`, `--json` |
| `reflect <ID>` | Reflect on lessons | `--focus {all,errors,inefficiency,practices,traps}`, `--json` |
| `show` | View existing artifacts | `--type {all,lessons,workflow}`, `--dir <path>`, `--json` |

> **Tip**: Session IDs support prefix matching (e.g., `fb48c` matches `fb48c98d-5233-...`) and the `latest` keyword.

## Supported Log Formats

| Source | Format | Log Location (macOS) |
|--------|--------|---------------------|
| VS Code Copilot Chat | JSONL (incremental state machine) | `~/Library/.../Code/User/workspaceStorage/*/GitHub.copilot-chat/debug-logs/*.jsonl` |
| RetroLens Native | JSON | `./logs/sessions/` |

> More formats (Claude Code, Cursor, etc.) are planned.

## Project Structure

```
src/retrolens/
├── __init__.py                 # Version info
├── cli.py                      # Click CLI (5 commands)
├── models.py                   # Pydantic v2 data models (16+ models)
├── formatters.py               # Text/JSON dual-mode output
├── workflow_dsl.py             # YAML DSL serialization + LangGraph codegen
├── readers/
│   ├── __init__.py             # BaseReader ABC + ReaderRegistry
│   ├── vscode_copilot.py       # VS Code Copilot JSONL parser
│   └── retrolens_native.py     # RetroLens native log reader
└── skills/
    ├── SKILL.md                # ⭐ Agent skill document (core artifact)
    └── templates/              # YAML, Python, Markdown templates
tests/
├── conftest.py
├── test_models.py              # 20 tests
├── test_workflow_dsl.py        # 38 tests
├── test_readers.py             # 36 tests
├── test_distill_cli.py         # 32 tests
└── fixtures/                   # Test data
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests (126 tests)
python -m pytest tests/ -v

# Lint
ruff check src/
```

## 📄 License

MIT License — see [LICENSE](LICENSE)
