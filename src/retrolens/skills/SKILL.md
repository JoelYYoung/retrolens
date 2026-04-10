---
name: retrolens
description: Navigate AI conversation logs like a debugger
version: 0.5.0
tools: [retrolens]
---

# RetroLens — AI Conversation Log Navigator

Navigate AI agent conversation logs like a debugger. Point at a log directory, list sessions, then drill into turns, tool calls, and raw data.

## Quick Start

```bash
pip install retrolens  # or: uv pip install retrolens
```

---

## Commands

### `cfg` — Set Working State (Do This First) ⭐

```bash
retrolens cfg set --path /path/to/logs   # Set log directory (auto-detects format)
retrolens cfg set --source vscode        # Override detected source type
retrolens cfg set --reader ./reader.py   # Register a custom reader
retrolens cfg show                       # View current config
retrolens cfg clear                      # Reset to defaults
```

Once set, all other commands (`ls`, `read`) use this path and source automatically.

### `ls` — List Sessions

```bash
retrolens ls                          # List sessions from configured path
retrolens ls --limit 10 --json        # JSON output (for agents)
```

> **Prerequisite**: Run `retrolens cfg set --path <dir>` first. If you don't
> know where logs are, consult the **Discovery Skill** (`DISCOVERY.md` bundled
> with retrolens) for exploration strategies.

### `read` — Navigate Session (Debugger ⭐)

```bash
retrolens read <ID>               # Session overview
retrolens read <ID> --turn 1      # Turn detail
retrolens read <ID> -t 1 --tool 0 # Tool call detail
retrolens read <ID> --turns 1-5   # Turn range summaries
retrolens read <ID> --diff 1,3    # Compare turns
retrolens read <ID> --raw -t 1    # Raw JSON data
```

---

## Workflow A: Analyze a Session & Extract Workflow ⭐⭐⭐

**Goal**: Analyze a past session, identify the hidden workflow, and document it.

### Step-by-Step

1. **Find the target session**:
   ```bash
   retrolens ls --json
   ```
   Pick a session that accomplished a meaningful goal (look for sessions with >3 turns).

2. **Get the session overview**:
   ```bash
   retrolens read <ID> --json
   ```
   This returns session info + per-turn summaries: user messages, tools used, error status.

3. **Drill into key turns**:
   ```bash
   retrolens read <ID> --turn N --json
   ```
   For each interesting turn, get full detail: user message, assistant response, tool calls with inputs/outputs, files touched, commands run.

4. **Identify the goal**: Read the first user message. What was the overall objective?

5. **Map phases**: Analyze the turn sequence and identify distinct phases:

   | Phase Pattern | Indicators |
   |------|------|
   | **Research/Exploration** | `read_file`, `semantic_search`, `grep_search`, `list_dir` dominant |
   | **Planning** | User discussing approach, agent proposing structure, `vscode_askQuestions` |
   | **Implementation** | `create_file`, `replace_string_in_file`, `insert_edit_into_file` dominant |
   | **Testing/Validation** | `run_in_terminal` with test commands, error checking |
   | **Iteration/Fix** | Repeated edits after errors, user corrections |
   | **Documentation** | `create_file` on .md files, `memory` tool usage |

   Look for natural boundaries: topic shifts in user messages, tool usage pattern changes.

6. **Document the workflow** as YAML, markdown, or any format suitable for reuse.

### Analysis Tips

- **Long sessions (>10 turns)**: Use sub-agents to process in batches.
- **Repeated patterns**: If the same tool sequence appears 3+ times, it's a step worth extracting.
- **User corrections**: When the user says "no, do X instead" — the correct path is the one to document.
- **Error-recovery loops**: The final successful approach is the one to keep.

---

## Workflow B: Reflect & Extract Lessons ⭐⭐⭐

**Goal**: Analyze a session from a learning perspective and produce actionable lessons.

### Step-by-Step

1. **Read the session**:
   ```bash
   retrolens read <ID> --json
   ```

2. **Analyze each turn** through these lenses:

   **🔴 Errors & Fixes** — What went wrong?
   - Tool call failures
   - User corrections ("No, that's wrong...")
   - Multiple retries for the same thing

   **🟡 Inefficiency Patterns** — What was wasteful?
   - Reading files one by one instead of grep/search
   - Exploring irrelevant code paths
   - Repeated context gathering

   **🟢 Effective Practices** — What worked well?
   - Smart tool selection (right tool for the job)
   - Progressive drilling (overview → detail)
   - Clean commit/save points

   **⚠️ Environment & Tool Traps**
   - API rate limits or quota exhaustion
   - Network/proxy issues
   - Version incompatibilities

   **📋 Agent Instructions**
   - Rules the user stated explicitly
   - Conventions discovered during the session

3. **Categorize lessons into two types**:

### 🧑 Human-Facing Lessons

Insights that help the **human** interact with agents more effectively:

- **Prompt quality**: Which phrasing led to correct results vs. confusion?
- **Context provision**: What upfront context (files, docs, examples) saved turns?
- **Task decomposition**: Which requests were too large and should be split?
- **Correction patterns**: What did the user have to repeatedly fix?
- **Expectation gaps**: Where did the agent's output diverge from what the human wanted?

**Output format**: Write to project notes, team runbooks, or personal reference docs.

**Example**:
```markdown
## Human Lessons — Session abc123
- Providing the test fixture path upfront saved 3 exploration turns
- "Fix the bug" was too vague → "Fix the TypeError in auth.py line 42" worked first try
- Agent handles single-file refactors well but struggles with cross-module renames
```

### 🤖 Agent-Facing Lessons (LESSONS.md)

Reusable directives that improve **future agent sessions** when included as prompt context:

- **Project conventions**: Coding style, naming, file structure, import order
- **Environment gotchas**: Proxy settings, API quirks, version constraints, auth requirements
- **Sequencing rules**: "Always run tests after editing" / "Build before deploy"
- **Tool heuristics**: "Use `grep_search` for exact strings, `semantic_search` for concepts"
- **Known pitfalls**: "The CI config uses tabs not spaces" / "Python 3.10 minimum"

**Output targets** (pick one or more):
- `AGENTS.md` — VS Code Copilot agent instructions
- `CLAUDE.md` — Claude Code agent instructions
- `.github/copilot-instructions.md` — Copilot global instructions
- `/memories/repo/` — Repository-scoped memory
- Project-level `LESSONS.md` — Standalone lessons file

**Example**:
```markdown
## Agent Lessons — Session abc123
- Always activate venv before running Python: `source .venv/bin/activate`
- This project uses `uv` not `pip` for package management
- Run `python -m pytest tests/ -v` after any code change
- The JSONL field is `tool_name`, not `name` — check actual schema before scripting
```

### Reflection Tips

- **Compare early vs late turns**: The agent often improves its approach — document what changed.
- **Count wasted turns**: If turns 3-7 were all failed attempts, that's a significant inefficiency.
- **Look for "aha moments"**: Key insights that changed the approach are valuable domain knowledge.
- **Separate the audiences**: A lesson about "give the agent more context" is for the human; a lesson about "always check file exists before editing" is for the agent.

---

## Workflow C: Session Navigation (read-only)

**Goal**: Explore a session in detail.

1. List sessions: `retrolens ls --json`
2. Overview: `retrolens read <ID>`
3. Drill into interesting turns: `retrolens read <ID> --turn N`
4. Inspect specific tool calls: `retrolens read <ID> -t N --tool M`
5. Compare turns: `retrolens read <ID> --diff 1,3`

---

## Workflow D: Validate a Custom Reader / Parser

**Goal**: Ensure a new or modified log reader correctly extracts all fields.

When building or modifying a log reader, always run a verification loop:

### Step-by-Step

1. **Parse a known session**:
   ```bash
   retrolens read <ID> --turn 1 --json > /tmp/parsed.json
   ```

2. **Get the raw source data** for comparison:
   ```bash
   retrolens read <ID> --turn 1 --raw > /tmp/raw.json
   ```

3. **Cross-check critical fields**:
   ```bash
   # Verify tool names are populated
   cat /tmp/parsed.json | python3 -c "
   import json, sys; d = json.load(sys.stdin)
   tools = d['tool_calls']
   empty = [t for t in tools if not t['tool_name']]
   print(f'Tools: {len(tools)} total, {len(empty)} missing name')
   assert len(empty) == 0, 'Bug: some tool_name fields are empty'
   "
   ```

   Checklist:
   - [ ] `tool_name` is populated (not empty string) for all tool calls
   - [ ] `tool_calls` count matches number of tool invocations in raw data
   - [ ] `files_touched` lists actual file paths
   - [ ] `user_message` and `assistant_response` are non-empty
   - [ ] Timestamps parse correctly (not null when raw data has them)
   - [ ] `input_full` and `output_full` contain the actual data

4. **Run the test suite**:
   ```bash
   python -m pytest tests/ -v
   ```

5. **Spot-check edge cases**:
   - Turns with 0 tool calls
   - Turns with very long tool outputs (>100KB)
   - Sessions with only 1 turn
   - Tool calls with nested/complex inputs

> **Common pitfall**: Field names in RetroLens `--json` output (e.g., `tool_name`,
> `tool_calls`) differ from the raw log format fields (e.g., VS Code uses `toolId`,
> `toolInvocationSerialized`). Always check the actual schema when writing scripts
> against the parsed output.

---

## Workflow E: Cross-Session Pattern Mining

**Goal**: Review multiple sessions to find recurring patterns.

1. **List recent sessions**: `retrolens ls --limit 10 --json`
2. **Read each session**: `retrolens read <ID> --json`
3. **Compare tool usage patterns** across sessions
4. **Identify recurring phases** that appear in multiple sessions
5. **Create a generalized workflow** that captures the common pattern

---

## For AI Agents — Best Practices

### Data Flow

```
cfg set → ls → pick session → read --json → agent analysis → output files
```

### Key Rules

1. **Always use `--json`** for structured data processing.

2. **Use prefix matching** — you don't need the full UUID:
   ```bash
   retrolens read 01e7    # matches 01e70526-3d64-...
   ```

3. **Progressive drilling** — don't read everything at once:
   ```
   ls → overview → interesting turns → tool details
   ```

4. **For long sessions (>10 turns)**, use sub-agents to process in parallel:
   - Sub-agent 1: `read <ID> --turns 1-5 --json`
   - Sub-agent 2: `read <ID> --turns 6-10 --json`
   - Main agent: Synthesize into unified analysis

5. **Use `latest`** keyword: `retrolens read latest --json`

### Platform Integration

**VS Code Copilot Chat**: Add to AGENTS.md:
```
Use `retrolens` CLI to analyze conversation logs.
Key commands: cfg set (point at logs), ls (list), read (navigate).
Always use --json for structured output.
```

**Claude Code**: Add to CLAUDE.md:
```
Use `retrolens` CLI to navigate conversation logs.
```

---

## Supported Log Formats

| Source | Format | Built-in Reader |
|------|------|------|
| VS Code Copilot Chat | JSONL incremental state | `vscode` |
| Claude Code | JSONL event stream | `claude_code` |
| RetroLens Native | JSON files per request/response | `retrolens` |

All platforms store sessions **per-project**. Use `retrolens cfg set --path <dir>` to point at a specific log directory.

> **Note**: Log storage paths change across platform versions. If `ls` returns nothing,
> consult the **Discovery Skill** (`DISCOVERY.md` bundled alongside this file) for
> exploration strategies to locate logs on your system.

### Adding New Log Formats

For unsupported platforms, see the **Discovery Skill** (`DISCOVERY.md`). It teaches agents how to:
1. Explore the filesystem to find log files
2. Sample and identify the format
3. Write a custom reader following the `BaseReader` interface
4. Register it via `retrolens cfg set --reader <path.py>`
