# RetroLens — Log Discovery & Adapter Skill

Guide a general-purpose AI agent to **discover**, **sample**, and **parse** conversation logs from any AI coding assistant platform.

## When to Use

- Setting up RetroLens for the first time on a new machine
- The user wants to find sessions for a specific project
- `retrolens scan` returns no sessions and you need to locate logs manually
- Adding support for a new or unknown AI assistant platform
- Writing a custom reader for an unknown JSONL format

## Philosophy

AI assistant platforms change their log storage paths, naming conventions, and formats across versions. **Never assume** a specific path is correct — always **verify by exploration**.

RetroLens provides:
1. A **unified data model** (`SessionInfo`, `TurnDetail`, `ToolCallDetail`)
2. A **BaseReader** interface that any reader must implement
3. A `--path` flag on `scan` / `read` to point at any log directory
4. This **Discovery Skill** that teaches agents how to explore and find logs

The agent's job: **explore → verify → point retrolens at the right path**.

---

## Two Usage Scenarios

### Scenario A: Working Inside the Target Project

When the user is already working in the project they want to analyze:

1. **Try auto-scan first**: `retrolens scan --json`
   - Built-in readers have reasonable defaults that may just work
   - If sessions appear → done

2. **If no sessions found**, look for local log directories:
   ```bash
   # Check if this project has local logs
   ls logs/ .retrolens/ .claude/ 2>/dev/null
   find . -name "*.jsonl" -maxdepth 3 2>/dev/null | head -10
   ```

3. **Point retrolens at discovered path**:
   ```bash
   retrolens scan --path <discovered-path> --json
   ```

### Scenario B: Searching from Another Project

When the user wants to find sessions for a *different* project:

1. **Identify the target project path** (ask the user if unclear)

2. **Explore where the AI assistant stores logs**. Approaches:
   - Search the user's home directory for known log patterns
   - Check platform-specific config/data directories
   - Use `find` or `fd` to search for `.jsonl` files

   ```bash
   # Find JSONL files (conversation logs are typically JSONL)
   find ~ -name "*.jsonl" -path "*/chatSessions/*" -maxdepth 8 2>/dev/null | head -20
   find ~ -name "*.jsonl" -path "*/.claude/*" -maxdepth 6 2>/dev/null | head -20

   # Or use fd if available (faster)
   fd -e jsonl . ~ --max-depth 8 2>/dev/null | head -30
   ```

3. **Narrow to the target project**. Each platform maps project → logs differently:
   - Some use a hash-based directory with a `workspace.json` manifest
   - Some encode the project path into the directory name
   - Some store logs inside the project directory itself

   **Don't assume the mapping** — explore and verify:
   ```bash
   # Example: find workspace mapping files
   find <candidate-dir> -name "workspace.json" -maxdepth 3 2>/dev/null
   # Read one to understand the mapping scheme
   cat <some-workspace.json>
   ```

4. **Once you find the log directory**:
   ```bash
   retrolens scan --path <log-directory> --json
   ```

---

## Step 1: Explore & Find Log Locations

> **Important**: The paths below are *hints based on past observation*, not guarantees.
> Always verify that the path exists and contains the expected files before relying on it.

### Exploration Strategy

1. **Check environment variables and config files** — some platforms store their data path in config
2. **Search by file pattern** — conversation logs are almost always `.jsonl` files
3. **Read a sample file** — first 3 lines tell you the format
4. **Verify project mapping** — confirm the logs belong to the right project

### Hints: Where to Look (as of early 2026)

These are *starting points for exploration*, not hard-coded truths:

- **VS Code family** (VS Code, Cursor, Windsurf): Typically store chat sessions under their User data directory in a `workspaceStorage/<hash>/chatSessions/` structure. The parent of `chatSessions/` usually has a `workspace.json` that maps the hash to the project path.

- **Claude Code**: Has historically stored project logs under `~/.claude/projects/`, with directory names derived from project paths.

- **RetroLens Native**: Stores logs in a `logs/` directory within the project root, with an `index.json` manifest.

- **Other platforms**: Look for `.jsonl` files in the platform's data directory. Check `~/Library/Application Support/<PlatformName>/` (macOS), `~/.config/<platform>/` (Linux), or `%APPDATA%/<Platform>/` (Windows).

### How to Verify

```bash
# 1. Does the path exist?
ls <candidate-path>

# 2. Are there JSONL files?
ls <candidate-path>/*.jsonl 2>/dev/null | wc -l

# 3. Sample a file to confirm it's a conversation log
head -3 <some-file.jsonl>
```

---

## Step 2: Sample & Identify Format

Read the first 3-5 lines of a JSONL file to determine the format. Look for distinguishing fields:

### Common Format Indicators

| If you see... | It's likely... |
|---|---|
| `{"kind": 0, "v": {"sessionId": ...}}` | VS Code Copilot Chat (incremental state-machine format) |
| `{"type": "user"\|"assistant"\|"system", "parentUuid": ...}` | Claude Code (event-chain format) |
| A directory with `metadata.json` + `NNN_request.json` + `NNN_response.json` | RetroLens Native |
| `{"role": "user"\|"assistant", "content": ...}` | Generic OpenAI-style messages |

### If Format is Unknown

1. Sample 5 lines, look for common fields: `role`, `content`, `tool_calls`, `timestamp`
2. Identify the turn boundary pattern (what separates user/assistant exchanges)
3. Write a minimal reader following the BaseReader interface (see Step 3)

---

## Step 3: Use or Write a Reader

### Built-in Readers

```python
from retrolens.readers import create_default_registry

registry = create_default_registry()
print(registry.source_types)  # ['vscode', 'retrolens', 'claude_code']
```

All built-in readers accept `--path` to override their default search locations:
```bash
retrolens scan --source vscode --path /path/to/chatSessions/ --json
retrolens scan --source claude_code --path /path/to/project-logs/ --json
```

### Writing a New Reader

Follow the `BaseReader` interface:

```python
from retrolens.readers import BaseReader
from retrolens import models

class MyPlatformReader(BaseReader):
    source_type = "myplatform"

    def scan(self, path=None) -> list[models.SessionInfo]:
        """Discover sessions. Return SessionInfo with: session_id, source_type, date, model, title, turns_count."""
        ...

    def get_overview(self, session_id) -> models.SessionOverview:
        """Return session metadata + TurnSummary per turn."""
        ...

    def get_turn(self, session_id, turn_number) -> models.TurnDetail:
        """Return full turn detail: user_message, assistant_response, tool_calls, files_touched."""
        ...
```

Key model classes to populate:
- `SessionInfo`: session_id, source_type, date, model, title, turns_count
- `TurnSummary`: turn_number, user_message_preview, tools_count, tool_names
- `TurnDetail`: user_message, assistant_response, tool_calls (list[ToolCallDetail]), files_touched, commands_run
- `ToolCallDetail`: tool_name, input_preview, input_full, output_preview, output_full, success

### Register a Custom Reader

```python
from retrolens.readers import create_default_registry

registry = create_default_registry()
registry.register(MyPlatformReader())
```

---

## Step 4: Verify

```bash
# Test that sessions are found
retrolens scan --path <path> --json

# Read a specific session
retrolens read <session_id> --json

# Check turn details
retrolens read <session_id> --turn 1 --json
```

---

## Troubleshooting

| Problem | Likely Cause | Approach |
|---------|-------------|----------|
| "No sessions found" | Wrong path, or platform changed its storage layout | Explore with `find`, sample files, verify format |
| Sessions found but 0 turns | Parser format mismatch | `head -3` the JSONL file, compare with format indicators above |
| Missing tool calls | Response format changed in new platform version | Sample the raw data, check tool item structure |
| Wrong project | Incorrect path mapping | Verify by reading a session and checking its content matches the expected project |
