# retrolens:connect Command

Connect RetroLens to a log directory: choose a project scope, configure the log path, and verify the connection.

> **Full skill reference**: Read `./SKILL.md` → Workflow A & B for detailed discovery and custom reader building.

## Usage

```bash
/retrolens:connect [--logs <dir>] [--platform <auto|vscode|claude_code>] [--reader <file.py>]
```

## Options

- `--logs <dir>` - Log directory to connect to (if omitted, asks user to choose)
- `--platform <...>` - Force source type if auto-detect is wrong
- `--reader <file.py>` - Use or create a custom reader for unsupported formats

## What This Command Does

### Step 1: Ask the user which project's logs to use

If `--logs` is not provided, ask:

> Which project's conversation logs would you like to analyze?
>
> 1. **This project** — search for logs related to the current workspace
> 2. **Specify a directory** — provide a path to an existing log directory
> 3. **Discover first** — run `/retrolens` to find log locations

### Step 2: Connect to the log directory

```bash
retrolens cfg set --path <log-directory>
retrolens cfg show                        # confirm config
```

If auto-detection fails, override the source type:

```bash
retrolens cfg set --source vscode         # or claude_code
```

### Step 3: Verify the connection

```bash
retrolens ls --json
```

Must return at least one session. If it does, show the user a summary:

> ✅ Connected to `<path>` (format: `vscode`)
> Found **N sessions** (oldest: YYYY-MM-DD, newest: YYYY-MM-DD)
>
> Run `/retrolens:analyze` to drill into a session.

### Step 4: Build a custom reader (only if format is unsupported)

If `retrolens ls` returns nothing and the files exist but aren't recognized:

1. Sample the raw log: `head -5 <some-file.jsonl>`
2. Implement a `BaseReader` subclass (see SKILL.md → Workflow B for the full contract):
   ```python
   from retrolens.readers import BaseReader
   from retrolens import models

   class MyReader(BaseReader):
       source_type = "myplatform"
       def scan(self, path=None) -> list[models.SessionInfo]: ...
       def get_overview(self, session_id) -> models.SessionOverview: ...
       def get_turn(self, session_id, turn_number) -> models.TurnDetail: ...
   ```
3. Register and verify:
   ```bash
   retrolens cfg set --path <dir> --reader ./my_reader.py
   retrolens ls --json
   retrolens read <ID> --turn 1 --json
   ```

## Success Criteria

- `retrolens cfg show` shows the correct path and source type
- `retrolens ls --json` returns sessions
- User is informed of available sessions and next steps
