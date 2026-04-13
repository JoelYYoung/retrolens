# retrolens Command

Discover where AI conversation logs are stored and get started with RetroLens.

> **Full skill reference**: Read `./SKILL.md` for detailed workflows and data model.

## Usage

```bash
/retrolens [--platform <auto|vscode|claude_code>] [--project <path>] [--hint <dir>]
```

## Options

- `--platform <...>` - Prefer a platform when searching (default: `auto`)
- `--project <path>` - Narrow search to logs for a specific project
- `--hint <dir>` - A directory to start exploring from

## What This Command Does

This is the **entry point** — it discovers log locations but does NOT automatically connect or analyze.

### Step 1: Set up the retrolens CLI tool

Check whether `retrolens` is already installed:

```bash
retrolens --version
```

If the command is found, skip to Step 2.

If **not found**, ask the user which option they prefer:

1. **Already installed** — retrolens is installed but not on PATH. Ask the user where it is installed or how they installed it (e.g., which venv, conda env, or directory), then help activate the correct environment or adjust PATH.
2. **Agent installs** — let the agent install it. Ask the user which method to use:
   | Method | Command |
   |--------|---------|
   | pip | `pip install retrolens` |
   | uv | `uv pip install retrolens` |
   | pipx | `pipx install retrolens` |

   Run the selected command and verify with `retrolens --version`.
3. **Install manually** — the user will install it themselves. Provide the install options above for reference and wait for them to confirm it's ready.

### Step 2: Manual filesystem search (if auto-detection fails)

```bash
# VS Code / Cursor / Windsurf
find ~ -name "*.jsonl" -path "*/chatSessions/*" -maxdepth 8 2>/dev/null | head -20

# Claude Code
find ~ -name "*.jsonl" -path "*/.claude/*" -maxdepth 6 2>/dev/null | head -20
```

| Platform | Typical Location |
|----------|------------------|
| VS Code / Cursor / Windsurf | `workspaceStorage/<hash>/chatSessions/` |
| Claude Code | `~/.claude/projects/<path-derived-name>/` |

### Step 3: Identify the format by sampling

```bash
head -3 <some-file.jsonl>
```

| First line pattern | Source type |
|--------------------|------------|
| `{"kind": 0, "v": {"sessionId": …}}` | `vscode` |
| `{"type": "user"\|"assistant", "parentUuid": …}` | `claude_code` |
| Other JSON | Custom reader needed |

### Step 4: Prompt user with next steps

**Do NOT auto-run `cfg set`.** Instead, present the discovered log directories and ask the user:

> I found conversation logs at the following location(s):
>
> 1. `<path-A>` — detected format: `vscode`, N JSONL files
> 2. `<path-B>` — detected format: `claude_code`, M JSONL files
>
> **What would you like to do next?**
>
> - `/retrolens:connect` — Connect to a log directory and select a project to work with
> - `/retrolens:analyze` — Analyze a specific session (requires connection first)
> - `/retrolens:reflect` — Extract lessons from a session (requires analysis first)

## Failure Handling

| Problem | Fix |
|---------|-----|
| No JSONL files found | Broaden search: `find / -name "*.jsonl" 2>/dev/null \| head -50` |
| Files found but wrong format | Run `/retrolens:connect --reader` to build a custom reader |
| Platform not supported | See SKILL.md → Workflow B for building a custom reader |
