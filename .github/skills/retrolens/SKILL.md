---
name: retrolens
description: "Navigate AI conversation logs like a debugger. Use when analyzing past agent sessions, understanding what happened in a conversation, building custom log readers, or extracting workflows and lessons from session data."
compatibility: "Requires Python >=3.10 and pip (or uv). Install with: pip install retrolens"
metadata:
  author: JoelYYoung
  version: "0.5.2"
  repository: "https://github.com/JoelYYoung/retrolens"
---

# RetroLens — AI Conversation Log Navigator

Navigate AI agent conversation logs like a debugger. Point at a log directory, list sessions, then drill into turns, tool calls, and raw data.

## Recommended Flow

The typical workflow follows these steps. Each step has a corresponding command (for Claude Code) and a detailed workflow section below.

```
/retrolens         → Discover log locations, see what's available
       ↓
/retrolens:connect → Choose a project, connect to its logs, verify
       ↓
/retrolens:analyze → Pick session(s), drill into turns, map phases
       ↓
/retrolens:reflect → Extract human lessons + agent directives
```

For non-Claude-Code agents, follow the same flow using the Workflow sections (A → B/C → D) directly.

## Quick Start

```bash
# Install the retrolens CLI tool (or run: bash scripts/setup.sh)
pip install retrolens
retrolens --version    # verify
```

---

## CLI Commands

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

## Workflow A: Discover & Connect to Logs ⭐⭐⭐

> Commands: `/retrolens` (discover) → `/retrolens:connect` (connect & verify)

**Goal**: Find where an AI assistant stores its conversation logs and point RetroLens at them.

> AI assistant platforms change their log storage paths and naming conventions
> across versions. **Never assume** a specific path — always **explore and verify**.

### Step 1: Try Auto-Detection First

```bash
retrolens cfg set --path <candidate-dir>   # auto-detects format
retrolens ls --json                        # see if sessions appear
```

If sessions appear, you're done. If not, proceed to manual discovery.

### Step 2: Explore the Filesystem

Search manually for JSONL log files (then validate candidates with `retrolens cfg set --path ...` + `retrolens ls --json`):

```bash
find ~ -name "*.jsonl" -path "*/chatSessions/*" -maxdepth 8 2>/dev/null | head -20
find ~ -name "*.jsonl" -path "*/.claude/*" -maxdepth 6 2>/dev/null | head -20
```

**Where to look** (hints — always verify):

| Platform | Typical Location Pattern |
|------|------|
| **VS Code / Cursor / Windsurf** | User data dir → `workspaceStorage/<hash>/chatSessions/` (parent has `workspace.json` mapping hash → project) |
| **Claude Code** | `~/.claude/projects/` with directory names derived from project paths |

### Step 3: Identify the Format

Sample a candidate file to identify its format:

```bash
# Option A: Use the bundled sampler (pretty-prints + guesses format)
python scripts/sample_log.py <some-file.jsonl>

# Option B: Manual inspection
head -3 <some-file.jsonl>
```

| If You See... | Format |
|------|------|
| `{"kind": 0, "v": {"sessionId": ...}}` | VS Code Copilot Chat (incremental state) |
| `{"type": "user"\|"assistant", "parentUuid": ...}` | Claude Code (event chain) |
| `{"role": "user"\|"assistant", "content": ...}` | Generic OpenAI-style (needs custom reader) |

### Step 4: Connect

```bash
retrolens cfg set --path <log-directory>
retrolens cfg set --source vscode          # override if auto-detect fails
retrolens ls --json                        # verify
```

### Narrowing to a Specific Project

Each platform maps project → logs differently. **Don't assume the mapping** — explore:

```bash
# VS Code: find workspace mapping files
find <candidate-dir> -name "workspace.json" -maxdepth 3 2>/dev/null
cat <some-workspace.json>   # read to understand the mapping
```

### Troubleshooting

| Problem | Likely Cause | Approach |
|------|------|------|
| "No sessions found" | Wrong path, or platform changed storage layout | `find` for `.jsonl` files, sample and verify format |
| Sessions found but 0 turns | Parser format mismatch | `head -3` the JSONL, compare with format indicators above |
| Missing tool calls | Response format changed in new version | Sample raw data, check tool item structure |
| Wrong project | Incorrect path mapping | Read a session and check content matches expected project |

---

## Workflow B: Build & Validate a Custom Reader ⭐⭐⭐

> Command: `/retrolens:connect --reader` (when format is unsupported)

**Goal**: Add support for a new agent log format (e.g., a new IDE, a custom agent framework).

### Step 1: Understand the Log Format

1. **Find sample log files** — locate 2-3 session files from the target platform.
2. **Identify the structure** — is it JSONL (one event per line), single JSON, SQLite, or something else?
3. **Map the key data** — for each session, you need to extract:

   | RetroLens Model | What to Find in Raw Logs |
   |------|------|
   | `SessionInfo` | Session ID, date, model name, title, turn count |
   | `TurnSummary` | Per-turn: user message preview, tool names, tool count |
   | `TurnDetail` | Full user message, assistant response, tool calls, files touched, commands run |
   | `ToolCallDetail` | Tool name, tool ID, input (full + preview), output (full + preview), success status |

### Step 2: Implement the Reader

Create a Python file that subclasses `BaseReader`:

```python
from pathlib import Path
from retrolens.readers import BaseReader
from retrolens import models

class MyPlatformReader(BaseReader):
    source_type = "myplatform"  # used with: retrolens cfg set --source myplatform

    def scan(self, path: Path | None = None) -> list[models.SessionInfo]:
        """Discover sessions at the given path. Return SessionInfo list."""
        ...

    def get_overview(self, session_id: str) -> models.SessionOverview:
        """Parse session -> metadata + per-turn summaries."""
        ...

    def get_turn(self, session_id: str, turn_number: int) -> models.TurnDetail:
        """Parse full turn detail including tool calls."""
        ...

    # Optional overrides (have default implementations):
    # get_turns_range(), get_turn_tool(), get_turn_raw(), diff_turns()
```

**Key models to populate** (from `retrolens.models`):

- `SessionInfo(session_id, source_type, date, model, title, turns_count)`
- `SessionOverview(info=SessionInfo, turns=[TurnSummary, ...])`
- `TurnSummary(turn_number, user_message_preview, tools_count, tool_names, has_error)`
- `TurnDetail(turn_number, user_message, assistant_response, tool_calls, files_touched, commands_run, timestamp, model)`
- `ToolCallDetail(index, tool_name, tool_id, input_preview, input_full, output_preview, output_full, success, invocation_message)`

### Step 3: Validate

**Always run a verification loop after implementing or modifying a reader.**

Use the bundled validation script or check manually:

```bash
# Automated validation (checks N turns, reports pass/fail per field)
python scripts/validate_reader.py --path /path/to/logs --turns 3
```

Or check manually:

1. **Register and test**:
   ```bash
   retrolens cfg set --path /path/to/logs --reader ./my_reader.py
   retrolens ls --json                    # Should list sessions
   retrolens read <ID> --json             # Should show overview
   retrolens read <ID> --turn 1 --json    # Should show turn detail
   ```

2. **Cross-check against raw data**:
   ```bash
   retrolens read <ID> --turn 1 --json > /tmp/parsed.json
   retrolens read <ID> --turn 1 --raw  > /tmp/raw.json
   # Compare: do tool counts match? Are tool names populated?
   ```

3. **Field-level checklist** — verify for at least 2-3 turns:
   - [ ] `tool_name` is populated (not empty string) for all tool calls
   - [ ] `tool_calls` count matches raw data
   - [ ] `files_touched` lists actual file paths
   - [ ] `user_message` and `assistant_response` are non-empty
   - [ ] Timestamps parse correctly (not null when raw data has them)
   - [ ] `input_full` / `output_full` contain the actual data

4. **Spot-check edge cases**:
   - Turns with 0 tool calls
   - Turns with very long outputs (>100KB)
   - Sessions with only 1 turn
   - Tool calls with nested/complex inputs

5. **Run the test suite** (if adding to retrolens core):
   ```bash
   python -m pytest tests/ -v
   ```

> **Common pitfall**: Field names in `--json` output (e.g., `tool_name`) differ
> from raw log fields (e.g., VS Code uses `toolId`). Always verify against the
> actual parsed output, not assumptions about field names.

### Step 4: Register for Permanent Use

For a standalone `.py` file:
```bash
retrolens cfg set --reader /path/to/my_reader.py
```

To contribute to retrolens core:
1. Add `src/retrolens/readers/my_platform.py`
2. Register in `create_default_registry()` in `readers/__init__.py`
3. Add test fixtures and tests

---

## Workflow C: Analyze a Session ⭐⭐⭐

> Command: `/retrolens:analyze`

**Goal**: Analyze a past session to understand what happened, identify phases, and extract the workflow.

### Step-by-Step

1. **Point at logs** (one-time setup):
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
   Returns session info + per-turn summaries: user messages, tools used, error status.

4. **Drill into key turns**:
   ```bash
   retrolens read <ID> --turn N --json    # Full turn detail
   retrolens read <ID> -t N --tool M      # Specific tool call
   retrolens read <ID> --turns 1-5 --json # Range of turns
   retrolens read <ID> --diff 1,5 --json  # Compare two turns
   ```

5. **Map phases** — identify distinct workflow stages:

   | Phase Pattern | Indicators |
   |------|------|
   | **Research/Exploration** | `read_file`, `semantic_search`, `grep_search`, `list_dir` dominant |
   | **Planning** | User discussing approach, agent proposing structure, `vscode_askQuestions` |
   | **Implementation** | `create_file`, `replace_string_in_file`, `insert_edit_into_file` dominant |
   | **Testing/Validation** | `run_in_terminal` with test commands, error checking |
   | **Iteration/Fix** | Repeated edits after errors, user corrections |
   | **Documentation** | `create_file` on .md files, `memory` tool usage |

6. **Document the workflow** as markdown, YAML, or any reusable format.

### Tips

- **Long sessions (>10 turns)**: Use sub-agents to process in batches.
- **Repeated patterns**: Same tool sequence 3+ times -> extract as a step.
- **User corrections**: "No, do X instead" -> the corrected path is the one to document.
- **Error-recovery loops**: The final successful approach is what matters.

---

## Workflow D: Reflect & Extract Lessons ⭐⭐⭐

> Command: `/retrolens:reflect`

**Goal**: Analyze a session from a learning perspective and produce actionable lessons for both humans and agents.

### Step 1: Analyze

Read the session with `retrolens read <ID> --json` and analyze each turn through these lenses:

| Lens | What to Look For |
|------|------|
| Red **Errors & Fixes** | Tool failures, user corrections, multiple retries |
| Yellow **Inefficiency** | File-by-file reads instead of grep, irrelevant exploration, repeated context gathering |
| Green **Effective Practices** | Smart tool selection, progressive drilling, clean commit points |
| Warning **Environment Traps** | API limits, network issues, version incompatibilities |
| Clipboard **Agent Directives** | Explicit rules the user stated, conventions discovered |

### Step 2: Categorize into Two Types

#### Human Lessons — Help humans interact with agents better

- **Prompt quality**: Which phrasing worked first try vs. caused confusion?
- **Context provision**: What upfront context (files, docs, examples) saved turns?
- **Task decomposition**: Which requests were too large and should be split?
- **Correction patterns**: What did the user repeatedly have to fix?
- **Expectation gaps**: Where did agent output diverge from what was wanted?

**Output**: project notes, team runbooks, personal reference docs.

**Example**:
```markdown
## Human Lessons — Session abc123
- Providing the test fixture path upfront saved 3 exploration turns
- "Fix the bug" was too vague -> "Fix the TypeError in auth.py line 42" worked first try
- Agent handles single-file refactors well but struggles with cross-module renames
```

#### Agent Lessons — Reusable directives for future sessions

- **Project conventions**: Coding style, naming, file structure, import order
- **Environment gotchas**: Proxy settings, API quirks, version constraints
- **Sequencing rules**: "Always run tests after editing" / "Build before deploy"
- **Tool heuristics**: "Use `grep_search` for exact strings, `semantic_search` for concepts"
- **Known pitfalls**: "CI uses tabs not spaces" / "Python 3.10 minimum"

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

- **Compare early vs late turns**: The agent often improves — document what changed.
- **Count wasted turns**: Turns 3-7 all failed? That's a significant inefficiency worth noting.
- **Look for "aha moments"**: Insights that changed the approach are valuable domain knowledge.
- **Separate audiences**: "Give the agent more context" -> human lesson. "Always check file exists before editing" -> agent lesson.

---

## Workflow E: Cross-Session Pattern Mining

**Goal**: Review multiple sessions to find recurring patterns.

1. **List recent sessions**: `retrolens ls --limit 10 --json`
2. **Read each session**: `retrolens read <ID> --json`
3. **Compare tool usage patterns** across sessions
4. **Identify recurring phases** that appear in multiple sessions
5. **Create a generalized workflow** that captures the common pattern

---

## Best Practices

### Data Flow

```
cfg set -> ls -> pick session -> read --json -> agent analysis -> output
```

### Key Rules

1. **Always use `--json`** for structured data processing.

2. **Use prefix matching** — you don't need the full UUID:
   ```bash
   retrolens read 01e7    # matches 01e70526-3d64-...
   ```

3. **Progressive drilling** — don't read everything at once:
   ```
   ls -> overview -> interesting turns -> tool details
   ```

4. **For long sessions (>10 turns)**, use sub-agents to process in parallel:
   - Sub-agent 1: `read <ID> --turns 1-5 --json`
   - Sub-agent 2: `read <ID> --turns 6-10 --json`
   - Main agent: Synthesize

5. **Use `latest`** keyword: `retrolens read latest --json`

---

## Supported Log Formats

| Source | Format | Built-in Reader |
|------|------|------|
| VS Code Copilot Chat | JSONL incremental state | `vscode` |
| Claude Code | JSONL event stream | `claude_code` |

Custom readers can be added via `retrolens cfg set --reader ./my_reader.py`.
Follow **Workflow B** to build one.

### Platform Integration

**VS Code Copilot Chat** — Add to `AGENTS.md`:
```
Use `retrolens` CLI to navigate conversation logs.
Key commands: cfg set (point at logs), ls (list), read (navigate).
Always use --json for structured output.
```

**Claude Code** — Add to `CLAUDE.md`:
```
Use `retrolens` CLI to navigate conversation logs.
Key commands: cfg set, ls, read. Always use --json.
```

---

## Bundled Files

| Path | Purpose |
|------|---------|
| `scripts/sample_log.py` | Sample JSONL files and auto-detect log format |
| `scripts/validate_reader.py` | Validate reader output with field-level checks |
| [references/READER-API.md](references/READER-API.md) | BaseReader interface and data model reference |
