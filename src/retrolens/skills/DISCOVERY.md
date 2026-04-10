# RetroLens — Log Discovery & Adapter Skill

Guide a general-purpose AI agent to **discover**, **sample**, and **parse** conversation logs from any AI coding assistant platform.

## When to Use

- Setting up RetroLens for the first time on a new machine
- Adding support for a new AI assistant platform (Cursor, Windsurf, Aider, etc.)
- Troubleshooting "no sessions found" in `retrolens scan`
- Writing a custom reader for an unknown JSONL format

## Philosophy

Rather than hard-coding every log format, RetroLens provides:
1. A **unified data model** (`SessionInfo`, `TurnDetail`, `ToolCallDetail`)
2. A **BaseReader** interface that any reader must implement
3. This **Discovery Skill** that teaches agents how to find logs and write readers

The agent's job: **find logs → sample format → write/select reader → register it**.

---

## Step 1: Discover Log Locations

### Known Platforms & Paths

| Platform | Path Pattern (macOS) | Path Pattern (Linux) | Path Pattern (Windows) |
|----------|---------------------|---------------------|----------------------|
| **VS Code Copilot Chat** | `~/Library/Application Support/Code/User/workspaceStorage/<hash>/chatSessions/*.jsonl` | `~/.config/Code/User/workspaceStorage/<hash>/chatSessions/*.jsonl` | `%APPDATA%/Code/User/workspaceStorage/<hash>/chatSessions/*.jsonl` |
| **Claude Code** | `~/.claude/projects/<encoded-path>/*.jsonl` | `~/.claude/projects/<encoded-path>/*.jsonl` | `%USERPROFILE%/.claude/projects/<encoded-path>/*.jsonl` |
| **RetroLens Native** | `./logs/sessions/<session-id>/` | same | same |
| **Cursor** | `~/Library/Application Support/Cursor/User/workspaceStorage/<hash>/chatSessions/*.jsonl` | `~/.config/Cursor/User/workspaceStorage/...` | `%APPDATA%/Cursor/User/workspaceStorage/...` |
| **Windsurf** | `~/Library/Application Support/Windsurf/User/workspaceStorage/<hash>/chatSessions/*.jsonl` | similar | similar |

### Discovery Steps

```bash
# 1. Check known locations
ls ~/.claude/projects/           # Claude Code
ls ~/Library/Application\ Support/Code/User/workspaceStorage/*/chatSessions/  # VS Code
ls ~/Library/Application\ Support/Cursor/User/workspaceStorage/*/chatSessions/  # Cursor

# 2. Find JSONL files by pattern
find ~ -path "*/chatSessions/*.jsonl" -maxdepth 8 2>/dev/null | head -20
find ~ -path "*/.claude/projects/*/*.jsonl" -maxdepth 6 2>/dev/null | head -20

# 3. Discover workspace → project mapping
# VS Code/Cursor: read workspace.json in parent dir
cat <workspaceStorage>/<hash>/workspace.json  # → {"folder": "file:///path/to/project"}
# Claude Code: decode directory name (/ → -)
# e.g. -Users-joel-Projects-myapp → /Users/joel/Projects/myapp
```

### Project Filtering

All platforms store sessions per-project. To find sessions for a specific project:

- **VS Code/Cursor**: Search `workspace.json` files for the project path, then look in that hash's `chatSessions/`
- **Claude Code**: Encode the project path (`/` → `-`), look in `~/.claude/projects/<encoded>/`
- **RetroLens Native**: Check `./logs/` in the project root

---

## Step 2: Sample & Identify Format

Read the first 3-5 lines of a JSONL file to determine the format:

### VS Code Copilot Chat Format
```
Indicators:
- Line 1 has {"kind": 0, "v": {"sessionId": ..., "inputState": ...}}
- Subsequent lines have {"kind": 1|2, "k": [...], "v": ...}
- Incremental state-machine: kind:0=init, kind:1=UI, kind:2=data patches

Key fields:
- kind:0 → v.sessionId, v.inputState.selectedModel, v.creationDate
- kind:2 + k:["requests"] → new request objects with message.text
- kind:2 + k:["requests", N, "response"] → response items
- Response tool items: kind:"toolInvocationSerialized", toolId, result
```

### Claude Code Format
```
Indicators:
- Each line has {"type": "user"|"assistant"|"system"|"file-history-snapshot", ...}
- Has "parentUuid" field (chain structure)
- Has "sessionId", "cwd", "version", "gitBranch"

Key fields:
- type:"user" → message.role:"user", message.content (text or structured)
- type:"assistant" → message.role:"assistant", message.content (array of text/tool_use)
- type:"system" + subtype:"api_error" → error events
- type:"system" + subtype:"turn_duration" → timing info
- tool_use in content: {"type":"tool_use", "name":..., "input":..., "id":...}
- tool_result in next user message: {"type":"tool_result", "tool_use_id":..., "content":...}
```

### RetroLens Native Format
```
Indicators:
- Directory structure: sessions/<id>/metadata.json + NNN_request.json + NNN_response.json
- metadata.json has session_id, start_time, client, model, request_count
- Request files contain raw_request with Anthropic message format
- Response files contain raw_response with content array
```

### Unknown Format
If none of the above match:
1. Sample 5 lines, look for common fields: `role`, `content`, `tool_calls`, `timestamp`
2. Identify the turn boundary pattern (what separates user/assistant exchanges)
3. Write a minimal reader following the BaseReader interface

---

## Step 3: Use or Write a Reader

### Existing Built-in Readers

```python
from retrolens.readers import create_default_registry

registry = create_default_registry()
print(registry.source_types)  # ['vscode', 'retrolens', 'claude_code']
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
# Test that the reader works
retrolens scan --source <source_type> --json

# Read a specific session
retrolens read <session_id> --json

# Check turn details
retrolens read <session_id> --turn 1 --json
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "No sessions found" | Wrong path or platform not supported | Run discovery steps, check paths exist |
| Sessions found but 0 turns | Parser didn't extract requests | Sample JSONL, check format indicators |
| Missing tool calls | Response format changed | Check tool item structure in JSONL |
| Wrong project mapping | Hash → path mapping failed | Read workspace.json for VS Code, decode dir name for Claude Code |
