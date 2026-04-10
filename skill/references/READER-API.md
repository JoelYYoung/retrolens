# RetroLens Reader API Reference

## BaseReader Interface

Every reader must subclass `BaseReader` and implement three abstract methods:

```python
from pathlib import Path
from retrolens.readers import BaseReader
from retrolens import models

class MyReader(BaseReader):
    source_type = "my-platform"

    def scan(self, path: Path | None = None) -> list[models.SessionInfo]:
        """Discover sessions at the given path."""
        ...

    def get_overview(self, session_id: str) -> models.SessionOverview:
        """Parse session → metadata + per-turn summaries."""
        ...

    def get_turn(self, session_id: str, turn_number: int) -> models.TurnDetail:
        """Parse full turn detail including tool calls."""
        ...
```

### Optional Overrides

These have default implementations but can be overridden for efficiency:

| Method | Default Behavior |
|--------|-----------------|
| `get_turns_range(session_id, start, end)` | Calls `get_overview()` and filters |
| `get_turn_tool(session_id, turn, tool_index)` | Calls `get_turn()` and indexes |
| `get_turn_raw(session_id, turn)` | Calls `get_turn()` and dumps to dict |
| `diff_turns(session_id, a, b)` | Compares two turns' tools and files |
| `resolve_session_id(prefix, path)` | Scans and prefix-matches |

## Data Models

All models are Pydantic v2 `BaseModel` subclasses.

### SessionInfo

```python
class SessionInfo(BaseModel):
    session_id: str
    source_type: str = "unknown"
    date: datetime | None = None
    model: str | None = None
    title: str | None = None
    turns_count: int = 0
```

### SessionOverview

```python
class SessionOverview(BaseModel):
    info: SessionInfo
    turns: list[TurnSummary] = []
```

### TurnSummary

```python
class TurnSummary(BaseModel):
    turn_number: int
    user_message_preview: str = ""
    tools_count: int = 0
    tool_names: list[str] = []
    has_error: bool = False
```

### TurnDetail

```python
class TurnDetail(BaseModel):
    turn_number: int
    user_message: str = ""
    assistant_response: str = ""
    tool_calls: list[ToolCallDetail] = []
    files_touched: list[str] = []
    commands_run: list[str] = []
    timestamp: datetime | None = None
    model: str | None = None
    mode: str | None = None
```

### ToolCallDetail

```python
class ToolCallDetail(BaseModel):
    index: int = 0
    tool_name: str = ""
    tool_id: str = ""
    input_preview: str = ""
    input_full: str = ""
    output_preview: str = ""
    output_full: str = ""
    success: bool | None = None
    invocation_message: str = ""
    past_tense_message: str = ""
```

### DiffResult

```python
class DiffResult(BaseModel):
    turn_a: int
    turn_b: int
    summary: str = ""
    tools_only_in_a: list[str] = []
    tools_only_in_b: list[str] = []
    files_only_in_a: list[str] = []
    files_only_in_b: list[str] = []
```

## Registration

### Built-in

```python
from retrolens.readers import create_default_registry
registry = create_default_registry()
# Built-in: 'vscode', 'claude_code'
```

### Custom Reader File

```bash
retrolens cfg set --reader /path/to/my_reader.py
```

The file is loaded via `importlib`, the first `BaseReader` subclass is found, instantiated, and registered.

### Adding to Core

1. Add `src/retrolens/readers/my_platform.py`
2. Register in `create_default_registry()` in `readers/__init__.py`
3. Add test fixtures under `tests/fixtures/`
4. Add tests
