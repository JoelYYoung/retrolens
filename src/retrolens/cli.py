"""
RetroLens CLI — debugger-style AI conversation log navigator.

Commands:
    cfg    — Set/show working log path and source (persistent state)
    ls     — List sessions in the configured log path
    read   — Navigate session turns (overview → detail → tool → raw)
    show   — View existing .retrolens/ artifacts

Usage:
    retrolens cfg set --path /path/to/logs
    retrolens cfg show
    retrolens ls
    retrolens read <session_id>
    retrolens read <session_id> --turn 1
    retrolens read <session_id> --turn 1 --tool 0
    retrolens read latest --json
    retrolens show
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from . import config, formatters
from .detect import detect_format_for_dir, describe_detection
from .models import ArtifactInfo, SessionDigest, TurnDigest, ToolUsage
from .readers import BaseReader, ReaderRegistry, create_default_registry, load_custom_reader


def _get_skill_path() -> str:
    """Return absolute path to the bundled SKILL.md."""
    return str(Path(__file__).parent / "skills" / "SKILL.md")


def _ensure_configured() -> tuple[str, str]:
    """Ensure config has path and source. Returns (path, source).

    Exits with helpful message if not configured.
    """
    cfg_path = config.get_path()
    cfg_source = config.get_source()

    if not cfg_path:
        click.echo(
            "Error: No log path configured.\n"
            "Use `retrolens cfg set --path <dir>` to point at a log directory.",
            err=True,
        )
        sys.exit(1)

    if not cfg_source:
        click.echo(
            "Error: No source type configured.\n"
            "Use `retrolens cfg set --source <type>` or re-run `cfg set --path` to auto-detect.",
            err=True,
        )
        sys.exit(1)

    return cfg_path, cfg_source


def _get_reader_from_config(registry: ReaderRegistry) -> tuple[BaseReader, Path]:
    """Get the reader and path from current config. Loads custom reader if needed."""
    cfg_path, cfg_source = _ensure_configured()

    # Load custom reader if configured
    custom_reader_path = config.get_reader()
    if custom_reader_path:
        try:
            load_custom_reader(custom_reader_path, registry)
        except Exception as e:
            click.echo(f"Warning: Failed to load custom reader: {e}", err=True)

    try:
        reader = registry.get(cfg_source)
    except KeyError:
        click.echo(
            f"Error: Unknown source type '{cfg_source}'.\n"
            f"Available: {registry.source_types}\n"
            f"If you need a custom reader, use: retrolens cfg set --reader <path.py>",
            err=True,
        )
        sys.exit(1)

    return reader, Path(cfg_path)


# ── CLI Group ───────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--skill-path", is_flag=True, help="Print the path to SKILL.md and exit")
@click.version_option(version="0.5.0", prog_name="retrolens")
@click.pass_context
def main(ctx: click.Context, skill_path: bool) -> None:
    """RetroLens — navigate AI conversation logs like a debugger."""
    ctx.ensure_object(dict)
    ctx.obj["registry"] = create_default_registry()

    if skill_path:
        click.echo(_get_skill_path())
        ctx.exit()

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ── cfg ─────────────────────────────────────────────────────────────────────

@main.group(invoke_without_command=True)
@click.pass_context
def cfg(ctx: click.Context) -> None:
    """Manage working state (log path, source, custom reader).

    Set a log path once, then ls/read/extract/reflect use it automatically.
    Format is auto-detected when setting --path.

    \b
    Examples:
      retrolens cfg set --path /path/to/logs    # auto-detects format
      retrolens cfg set --source vscode          # override source type
      retrolens cfg set --reader ./my_reader.py  # register custom reader
      retrolens cfg show                         # show current state
      retrolens cfg clear                        # reset
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(cfg_show)


@cfg.command("set")
@click.option("--path", "-p", "log_path", default=None, help="Log directory path")
@click.option("--source", "-s", default=None, help="Source type: vscode, claude_code, retrolens, or custom")
@click.option("--reader", "-r", "reader_path", default=None, help="Custom reader .py file path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cfg_set(ctx: click.Context, log_path: Optional[str], source: Optional[str],
            reader_path: Optional[str], as_json: bool) -> None:
    """Set working log path, source type, and/or custom reader.

    When --path is set, the format is auto-detected by sampling files.
    Use --source to override auto-detection.
    Use --reader to load a custom BaseReader from a .py file.
    """
    if log_path is None and source is None and reader_path is None:
        click.echo("Nothing to set. Use --path, --source, and/or --reader.", err=True)
        sys.exit(1)

    registry: ReaderRegistry = ctx.obj["registry"]

    # If a custom reader is provided, validate and load it first
    if reader_path:
        try:
            loaded = load_custom_reader(reader_path, registry)
            # If no explicit source, use the custom reader's source_type
            if source is None:
                source = loaded.source_type
        except (FileNotFoundError, ValueError) as e:
            click.echo(f"Error loading reader: {e}", err=True)
            sys.exit(1)

    # Auto-detect format when path is set (and source not explicitly given)
    detected_source = None
    if log_path and source is None:
        p = Path(log_path)
        if not p.exists():
            click.echo(f"Warning: path does not exist: {log_path}", err=True)
        else:
            detected_source = detect_format_for_dir(p)
            if detected_source:
                source = detected_source
            else:
                click.echo(
                    f"Warning: Could not auto-detect log format in {log_path}\n"
                    f"Use --source to specify manually, or --reader to load a custom reader.",
                    err=True,
                )

    data = config.set_values(
        path=log_path,
        source=source,
        reader=reader_path,
    )

    if as_json:
        result = config.status()
        if detected_source:
            result["auto_detected"] = detected_source
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        click.echo("Config updated:")
        if "path" in data:
            click.echo(f"  path:   {data['path']}")
        if "source" in data:
            icon = " (auto-detected)" if detected_source else ""
            click.echo(f"  source: {data['source']}{icon}")
        if "reader" in data:
            click.echo(f"  reader: {data['reader']}")


@cfg.command("show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cfg_show(as_json: bool = False) -> None:
    """Show current working state."""
    st = config.status()

    if as_json:
        click.echo(json.dumps(st, ensure_ascii=False, indent=2))
        return

    if not st["exists"]:
        click.echo("No config set. Use `retrolens cfg set --path <dir>` to set a working directory.")
        return

    click.echo("RetroLens working state:")
    if st.get("path"):
        click.echo(f"  path:   {st['path']}")
    if st.get("source"):
        click.echo(f"  source: {st['source']}")
    if st.get("reader"):
        click.echo(f"  reader: {st['reader']}")
    click.echo(f"  file:   {st['config_file']}")


@cfg.command("clear")
def cfg_clear() -> None:
    """Clear all config (reset to defaults)."""
    config.clear()
    click.echo("Config cleared.")


# ── ls ──────────────────────────────────────────────────────────────────────

@main.command()
@click.option("--limit", "-n", default=20, help="Max sessions to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def ls(ctx: click.Context, limit: int, as_json: bool) -> None:
    """List sessions in the configured log path.

    Requires `cfg set --path <dir>` to be run first.

    \b
    Examples:
      retrolens ls              # List up to 20 sessions
      retrolens ls -n 50        # List up to 50
      retrolens ls --json       # JSON output for agents
    """
    registry: ReaderRegistry = ctx.obj["registry"]
    reader, log_path = _get_reader_from_config(registry)

    try:
        sessions = reader.scan(log_path)
    except Exception as e:
        click.echo(f"Error listing sessions: {e}", err=True)
        sys.exit(1)

    sessions = sessions[:limit]
    click.echo(formatters.format_session_list(sessions, as_json=as_json))


# ── read ────────────────────────────────────────────────────────────────────

def _parse_turns_range(value: str) -> tuple[int, int]:
    """Parse '1-5' into (1, 5)."""
    parts = value.split("-")
    if len(parts) != 2:
        raise click.BadParameter(f"Expected format N-M, got '{value}'")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        raise click.BadParameter(f"Expected integers in N-M, got '{value}'")


def _parse_diff(value: str) -> tuple[int, int]:
    """Parse '1,3' or '1 3' into (1, 3)."""
    # Try comma first, then space
    for sep in [",", " "]:
        if sep in value:
            parts = value.split(sep)
            if len(parts) == 2:
                try:
                    return int(parts[0].strip()), int(parts[1].strip())
                except ValueError:
                    pass
    raise click.BadParameter(f"Expected two turn numbers (e.g. '1,3'), got '{value}'")


@main.command()
@click.argument("session_id")
@click.option("--turn", "-t", "turn_num", type=int, default=None, help="Show specific turn detail")
@click.option("--turns", "turns_range", default=None, help="Show turns range (e.g. 1-5)")
@click.option("--tool", "tool_idx", type=int, default=None, help="Show specific tool call (with --turn)")
@click.option("--diff", "diff_turns", default=None, help="Compare two turns (e.g. '1,3')")
@click.option("--raw", is_flag=True, help="Show raw JSON data")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def read(
    ctx: click.Context,
    session_id: str,
    turn_num: Optional[int],
    turns_range: Optional[str],
    tool_idx: Optional[int],
    diff_turns: Optional[str],
    raw: bool,
    as_json: bool,
) -> None:
    """Navigate a session — overview, turns, tool calls, raw data.

    SESSION_ID can be a full ID, a prefix, or 'latest'.
    Requires `cfg set --path <dir>` to be run first.

    \b
    Examples:
      retrolens read latest              # Session overview
      retrolens read 01e705 --turn 1     # Turn 1 detail
      retrolens read 01e705 -t 1 --tool 0  # First tool call
      retrolens read 01e705 --turns 1-5  # Turns 1-5 summaries
      retrolens read 01e705 --diff 1,3   # Compare turn 1 vs 3
      retrolens read latest --raw -t 1   # Raw JSON for turn 1
    """
    registry: ReaderRegistry = ctx.obj["registry"]
    reader, log_path = _get_reader_from_config(registry)

    # Resolve session ID
    try:
        full_id = reader.resolve_session_id(session_id, log_path)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        # ── Diff mode ──
        if diff_turns:
            a, b = _parse_diff(diff_turns)
            result = reader.diff_turns(full_id, a, b)
            click.echo(formatters.format_diff(result, as_json=as_json))
            return

        # ── Turns range mode ──
        if turns_range:
            start, end = _parse_turns_range(turns_range)
            summaries = reader.get_turns_range(full_id, start, end)
            click.echo(formatters.format_turns_range(summaries, as_json=as_json))
            return

        # ── Single turn + tool ──
        if turn_num is not None:
            if raw:
                raw_data = reader.get_turn_raw(full_id, turn_num)
                click.echo(formatters.format_raw(raw_data))
                return

            if tool_idx is not None:
                tool = reader.get_turn_tool(full_id, turn_num, tool_idx)
                click.echo(formatters.format_tool_detail(tool, as_json=as_json))
                return

            turn = reader.get_turn(full_id, turn_num)
            click.echo(formatters.format_turn_detail(turn, as_json=as_json))
            return

        # ── Default: overview ──
        overview = reader.get_overview(full_id)
        click.echo(formatters.format_overview(overview, as_json=as_json))

    except (IndexError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ── show ────────────────────────────────────────────────────────────────────

# ── Helper: build SessionDigest ─────────────────────────────────────────────

def _build_session_digest(
    reader: BaseReader, session_id: str, max_turns: int = 0
) -> SessionDigest:
    """Build a SessionDigest from a reader — the structured input for agents.

    This reads the overview + each turn detail, and condenses them into
    a digest format optimized for workflow/reflection analysis.
    """
    from collections import Counter

    overview = reader.get_overview(session_id)
    info = overview.info

    turn_digests: list[TurnDigest] = []
    all_tools: Counter[str] = Counter()
    all_files: set[str] = set()
    all_commands: list[str] = []

    turns_to_process = overview.turns
    if max_turns > 0:
        turns_to_process = turns_to_process[:max_turns]

    for ts in turns_to_process:
        try:
            turn = reader.get_turn(session_id, ts.turn_number)
        except Exception:
            # If turn detail fails, use summary
            turn_digests.append(TurnDigest(
                turn_number=ts.turn_number,
                user_message=ts.user_message_preview,
                tools_used=ts.tool_names,
                tools_count=ts.tools_count,
                has_error=ts.has_error,
                timestamp=ts.timestamp,
            ))
            continue

        # Deduplicate tool names for this turn
        tool_names = list(dict.fromkeys(tc.tool_name for tc in turn.tool_calls))
        for name in tool_names:
            all_tools[name] += 1

        all_files.update(turn.files_touched)
        all_commands.extend(turn.commands_run)

        # Condense assistant response
        assistant_summary = ""
        if turn.assistant_response:
            assistant_summary = turn.assistant_response[:300]
            if len(turn.assistant_response) > 300:
                assistant_summary += "..."

        turn_digests.append(TurnDigest(
            turn_number=turn.turn_number,
            user_message=turn.user_message,
            assistant_summary=assistant_summary,
            tools_used=tool_names,
            tools_count=len(turn.tool_calls),
            files_touched=turn.files_touched,
            commands_run=turn.commands_run,
            has_error=ts.has_error,
            timestamp=turn.timestamp,
        ))

    tools_summary = [
        ToolUsage(tool_name=name, call_count=count)
        for name, count in all_tools.most_common()
    ]

    return SessionDigest(
        session_id=session_id,
        title=info.title,
        model=info.model,
        date=info.date,
        total_turns=info.turns_count,
        turns=turn_digests,
        all_tools_used=tools_summary,
        all_files_touched=sorted(all_files),
        all_commands_run=all_commands,
    )


# ── extract ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session_id", default="latest")
@click.option("--max-turns", "-n", default=0, help="Limit turns to process (0 = all)")
@click.option("--from-yaml", "yaml_path", default=None, help="Generate LangGraph from existing YAML DSL")
@click.option("--langgraph", is_flag=True, help="Also output LangGraph code template")
@click.option("--output-dir", "-o", default=".retrolens", help="Output directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def extract(
    ctx: click.Context,
    session_id: str,
    max_turns: int,
    yaml_path: Optional[str],
    langgraph: bool,
    output_dir: str,
    as_json: bool,
) -> None:
    """Extract workflow from a session (prepare digest for agent analysis).

    Requires `cfg set --path <dir>` to be run first (except --from-yaml mode).

    \b
    Two modes:
    1. Session → Digest: Reads a session and outputs a structured digest
       for an agent to analyze and produce a WorkflowDSL.
    2. YAML → LangGraph: Convert an existing .workflow.yaml to Python code.

    \b
    Examples:
      retrolens extract latest --json      # Digest for agent
      retrolens extract 01e7 --json        # Specific session
      retrolens extract 01e7 --max-turns 5 # First 5 turns only
      retrolens extract --from-yaml .retrolens/my.workflow.yaml --langgraph
    """
    from .workflow_dsl import (
        workflow_to_langgraph,
        workflow_to_yaml,
        yaml_to_workflow,
        save_workflow_yaml,
        save_langgraph_code,
    )

    # Mode 2: YAML → LangGraph (doesn't need config)
    if yaml_path:
        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            click.echo(f"Error: YAML file not found: {yaml_path}", err=True)
            sys.exit(1)

        yaml_content = yaml_file.read_text(encoding="utf-8")
        workflow = yaml_to_workflow(yaml_content)

        if langgraph:
            code = workflow_to_langgraph(workflow)
            if as_json:
                click.echo(_json_out_raw({
                    "workflow_name": workflow.name,
                    "langgraph_code": code,
                }))
            else:
                out_path = save_langgraph_code(workflow, Path(output_dir))
                click.echo(f"LangGraph code saved to: {out_path}")
        else:
            click.echo(formatters.format_workflow_dsl(workflow, as_json=as_json))
        return

    # Mode 1: Session → Digest
    registry: ReaderRegistry = ctx.obj["registry"]
    reader, log_path = _get_reader_from_config(registry)

    try:
        full_id = reader.resolve_session_id(session_id, log_path)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        digest = _build_session_digest(reader, full_id, max_turns)
        click.echo(formatters.format_session_digest(digest, as_json=as_json))
    except Exception as e:
        click.echo(f"Error building digest: {e}", err=True)
        sys.exit(1)


# ── reflect ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session_id", default="latest")
@click.option("--max-turns", "-n", default=0, help="Limit turns to process (0 = all)")
@click.option("--focus", "-f", default="all",
              help="Focus area: all, errors, inefficiency, practices, traps")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def reflect(
    ctx: click.Context,
    session_id: str,
    max_turns: int,
    focus: str,
    as_json: bool,
) -> None:
    """Reflect on a session (prepare digest for lesson extraction).

    Generates a SessionDigest annotated with focus hints. The agent
    uses this digest + SKILL.md guidance to produce ReflectionResult.
    Requires `cfg set --path <dir>` to be run first.

    \b
    Examples:
      retrolens reflect latest --json         # Full reflection
      retrolens reflect 01e7 --focus errors   # Focus on errors
      retrolens reflect latest -n 10 --json   # First 10 turns
    """
    registry: ReaderRegistry = ctx.obj["registry"]
    reader, log_path = _get_reader_from_config(registry)

    try:
        full_id = reader.resolve_session_id(session_id, log_path)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        digest = _build_session_digest(reader, full_id, max_turns)

        # Add focus hint to the output
        if as_json:
            data = digest.model_dump(mode="json")
            data["_reflection_focus"] = focus
            data["_reflection_hints"] = _get_focus_hints(focus)
            click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        else:
            click.echo(formatters.format_session_digest(digest, as_json=False))
            click.echo("")
            click.echo(f"{_C_BOLD}Reflection Focus: {focus}{_C_RESET}")
            for hint in _get_focus_hints(focus):
                click.echo(f"  💡 {hint}")

    except Exception as e:
        click.echo(f"Error building digest: {e}", err=True)
        sys.exit(1)


# ANSI constants for reflect command
_C_BOLD = "\033[1m"
_C_RESET = "\033[0m"


def _get_focus_hints(focus: str) -> list[str]:
    """Return analysis hints based on focus area."""
    hints = {
        "all": [
            "Analyze all turns for errors, inefficiencies, good practices, and traps",
            "Look for user corrections (agent was wrong and user redirected)",
            "Identify repeated patterns that could be automated",
            "Note any environment-specific issues or tool limitations",
        ],
        "errors": [
            "Focus on turns where tools failed or returned errors",
            "Look for user corrections: 'No, do X instead'",
            "Identify root causes and preventive measures",
        ],
        "inefficiency": [
            "Look for repetitive tool calls that could be batched",
            "Identify unnecessary exploration (reading too many files)",
            "Find cases where the agent took a long path to a simple solution",
        ],
        "practices": [
            "Identify effective patterns: what tools/sequences worked well",
            "Note decision points where the right choice was made",
            "Extract reusable techniques for similar tasks",
        ],
        "traps": [
            "Find environment issues (versions, network, permissions)",
            "Identify tool limitations that caused workarounds",
            "Note platform-specific gotchas",
        ],
    }
    return hints.get(focus, hints["all"])


def _json_out_raw(data: dict) -> str:
    """JSON output helper for non-model data."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# ── show ────────────────────────────────────────────────────────────────────

@main.command()
@click.option("--type", "-t", "artifact_type", default="all", help="Filter: lessons, workflow, all")
@click.option("--dir", "-d", "fc_dir", default=".retrolens", help="Artifacts directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show(artifact_type: str, fc_dir: str, as_json: bool) -> None:
    """View existing .retrolens/ artifacts (LESSONS.md, workflows, etc.)."""
    fc_path = Path(fc_dir)
    if not fc_path.exists():
        click.echo(f"Directory '{fc_dir}' does not exist.")
        if not as_json:
            click.echo(f"Hint: Agents create artifacts here after analyzing sessions.")
        return

    artifacts: list[ArtifactInfo] = []

    # Scan for all artifact types: .md, .yaml, .py
    patterns = ["*.md", "*.yaml", "*.yml", "*.py"]
    seen: set[str] = set()

    for pattern in patterns:
        for fp in sorted(fc_path.rglob(pattern)):
            fp_str = str(fp)
            if fp_str in seen:
                continue
            seen.add(fp_str)

            # Determine type
            name_lower = fp.name.lower()
            if "lesson" in name_lower or "reflection" in name_lower:
                atype = "lessons"
            elif "workflow" in name_lower or fp.suffix in (".yaml", ".yml"):
                atype = "workflow"
            elif "_agent.py" in name_lower or "langgraph" in name_lower:
                atype = "agent"
            elif fp.suffix == ".py":
                atype = "code"
            else:
                atype = "other"

            if artifact_type != "all" and atype != artifact_type:
                continue

            stat = fp.stat()
            preview = ""
            try:
                preview = fp.read_text(encoding="utf-8")[:200]
            except Exception:
                pass

            artifacts.append(ArtifactInfo(
                path=str(fp),
                type=atype,
                last_modified=datetime.fromtimestamp(stat.st_mtime),
                size_bytes=stat.st_size,
                preview=preview,
            ))

    click.echo(formatters.format_artifacts(artifacts, as_json=as_json))


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
