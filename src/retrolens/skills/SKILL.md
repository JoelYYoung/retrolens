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

Get the SKILL.md path for agent discovery:
```bash
retrolens --skill-path
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

**Goal**: Analyze a session from a learning perspective.

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

3. **Write the output** to project notes, AGENTS.md, CLAUDE.md, or memory files.

### Reflection Tips

- **Compare early vs late turns**: The agent often improves its approach — document what changed.
- **Count wasted turns**: If turns 3-7 were all failed attempts, that's a significant inefficiency.
- **Look for "aha moments"**: Key insights that changed the approach are valuable domain knowledge.

---

## Workflow C: Session Navigation (read-only)

**Goal**: Explore a session in detail.

1. List sessions: `retrolens ls --json`
2. Overview: `retrolens read <ID>`
3. Drill into interesting turns: `retrolens read <ID> --turn N`
4. Inspect specific tool calls: `retrolens read <ID> -t N --tool M`
5. Compare turns: `retrolens read <ID> --diff 1,3`

---

## Workflow D: Cross-Session Pattern Mining

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
See: retrolens --skill-path
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
