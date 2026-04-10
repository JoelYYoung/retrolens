"""
RetroLens CLI — debugger-style AI conversation log navigator.

Commands:
    cfg    — Set/show working log path and source (persistent state)
    ls     — List sessions in the configured log path
    read   — Navigate session turns (overview → detail → tool → raw)

Usage:
    retrolens cfg set --path /path/to/logs
    retrolens cfg show
    retrolens ls
    retrolens read <session_id>
    retrolens read <session_id> --turn 1
    retrolens read <session_id> --turn 1 --tool 0
    retrolens read latest --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from . import config, formatters
from .detect import detect_format_for_dir, describe_detection
from .readers import BaseReader, ReaderRegistry, create_default_registry, load_custom_reader


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
@click.version_option(version="0.5.1", prog_name="retrolens")
@click.pass_context
def main(ctx: click.Context) -> None:
    """RetroLens — navigate AI conversation logs like a debugger."""
    ctx.ensure_object(dict)
    ctx.obj["registry"] = create_default_registry()

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


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
