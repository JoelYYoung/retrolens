"""
FlowCraft Distill CLI — debugger-style AI conversation log navigator.

Commands:
    scan   — Discover available sessions
    read   — Navigate session turns (overview → detail → tool → raw)
    show   — View existing .flowcraft/ artifacts

Usage:
    flowcraft-distill scan
    flowcraft-distill read <session_id>
    flowcraft-distill read <session_id> --turn 1
    flowcraft-distill read <session_id> --turn 1 --tool 0
    flowcraft-distill read latest --json
    flowcraft-distill show
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from . import formatters
from .models import ArtifactInfo, SessionDigest, TurnDigest, ToolUsage
from .readers import BaseReader, ReaderRegistry, create_default_registry


def _get_skill_path() -> str:
    """Return absolute path to the bundled SKILL.md."""
    return str(Path(__file__).parent / "skills" / "SKILL.md")


def _get_reader(
    registry: ReaderRegistry, source: str, path: Optional[str]
) -> tuple[BaseReader | None, ReaderRegistry]:
    """Get a specific reader or return None to use registry-level ops."""
    if source != "auto":
        try:
            reader = registry.get(source)
            return reader, registry
        except KeyError:
            click.echo(f"Error: Unknown source '{source}'. Available: {registry.source_types}", err=True)
            sys.exit(1)
    return None, registry


# ── CLI Group ───────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--skill-path", is_flag=True, help="Print the path to SKILL.md and exit")
@click.version_option(version="0.4.0", prog_name="flowcraft-distill")
@click.pass_context
def main(ctx: click.Context, skill_path: bool) -> None:
    """FlowCraft Distill — navigate AI conversation logs like a debugger."""
    ctx.ensure_object(dict)
    ctx.obj["registry"] = create_default_registry()

    if skill_path:
        click.echo(_get_skill_path())
        ctx.exit()

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ── scan ────────────────────────────────────────────────────────────────────

@main.command()
@click.option("--source", "-s", default="auto", help="Log source: auto, vscode, flowcraft")
@click.option("--path", "-p", "log_path", default=None, help="Custom log directory path")
@click.option("--limit", "-n", default=20, help="Max sessions to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def scan(ctx: click.Context, source: str, log_path: Optional[str], limit: int, as_json: bool) -> None:
    """Discover available sessions across all log sources."""
    registry: ReaderRegistry = ctx.obj["registry"]
    p = Path(log_path) if log_path else None

    reader, _ = _get_reader(registry, source, log_path)

    try:
        if reader:
            sessions = reader.scan(p)
        else:
            sessions = registry.auto_discover(p)
    except Exception as e:
        click.echo(f"Error scanning: {e}", err=True)
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
@click.option("--source", "-s", default="auto", help="Log source")
@click.option("--path", "-p", "log_path", default=None, help="Custom log path")
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
    source: str,
    log_path: Optional[str],
    turn_num: Optional[int],
    turns_range: Optional[str],
    tool_idx: Optional[int],
    diff_turns: Optional[str],
    raw: bool,
    as_json: bool,
) -> None:
    """Navigate a session — overview, turns, tool calls, raw data.

    SESSION_ID can be a full ID, a prefix, or 'latest'.

    \b
    Examples:
      flowcraft-distill read latest              # Session overview
      flowcraft-distill read 01e705 --turn 1     # Turn 1 detail
      flowcraft-distill read 01e705 -t 1 --tool 0  # First tool call
      flowcraft-distill read 01e705 --turns 1-5  # Turns 1-5 summaries
      flowcraft-distill read 01e705 --diff 1,3   # Compare turn 1 vs 3
      flowcraft-distill read latest --raw -t 1   # Raw JSON for turn 1
    """
    registry: ReaderRegistry = ctx.obj["registry"]
    p = Path(log_path) if log_path else None
    reader_specific, _ = _get_reader(registry, source, log_path)

    # Resolve session ID
    try:
        if reader_specific:
            full_id = reader_specific.resolve_session_id(session_id, p)
            reader = reader_specific
        else:
            reader, full_id = registry.resolve(session_id)
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
@click.option("--source", "-s", default="auto", help="Log source")
@click.option("--path", "-p", "log_path", default=None, help="Custom log path")
@click.option("--max-turns", "-n", default=0, help="Limit turns to process (0 = all)")
@click.option("--from-yaml", "yaml_path", default=None, help="Generate LangGraph from existing YAML DSL")
@click.option("--langgraph", is_flag=True, help="Also output LangGraph code template")
@click.option("--output-dir", "-o", default=".flowcraft", help="Output directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def extract(
    ctx: click.Context,
    session_id: str,
    source: str,
    log_path: Optional[str],
    max_turns: int,
    yaml_path: Optional[str],
    langgraph: bool,
    output_dir: str,
    as_json: bool,
) -> None:
    """Extract workflow from a session (prepare digest for agent analysis).

    \b
    Two modes:
    1. Session → Digest: Reads a session and outputs a structured digest
       for an agent to analyze and produce a WorkflowDSL.
    2. YAML → LangGraph: Convert an existing .workflow.yaml to Python code.

    \b
    Examples:
      flowcraft-distill extract latest --json      # Digest for agent
      flowcraft-distill extract 01e7 --json        # Specific session
      flowcraft-distill extract 01e7 --max-turns 5 # First 5 turns only
      flowcraft-distill extract --from-yaml .flowcraft/my.workflow.yaml --langgraph
    """
    from .workflow_dsl import (
        workflow_to_langgraph,
        workflow_to_yaml,
        yaml_to_workflow,
        save_workflow_yaml,
        save_langgraph_code,
    )

    # Mode 2: YAML → LangGraph
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
    p = Path(log_path) if log_path else None
    reader_specific, _ = _get_reader(registry, source, log_path)

    try:
        if reader_specific:
            full_id = reader_specific.resolve_session_id(session_id, p)
            reader = reader_specific
        else:
            reader, full_id = registry.resolve(session_id)
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
@click.option("--source", "-s", default="auto", help="Log source")
@click.option("--path", "-p", "log_path", default=None, help="Custom log path")
@click.option("--max-turns", "-n", default=0, help="Limit turns to process (0 = all)")
@click.option("--focus", "-f", default="all",
              help="Focus area: all, errors, inefficiency, practices, traps")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def reflect(
    ctx: click.Context,
    session_id: str,
    source: str,
    log_path: Optional[str],
    max_turns: int,
    focus: str,
    as_json: bool,
) -> None:
    """Reflect on a session (prepare digest for lesson extraction).

    Generates a SessionDigest annotated with focus hints. The agent
    uses this digest + SKILL.md guidance to produce ReflectionResult.

    \b
    Examples:
      flowcraft-distill reflect latest --json         # Full reflection
      flowcraft-distill reflect 01e7 --focus errors   # Focus on errors
      flowcraft-distill reflect latest -n 10 --json   # First 10 turns
    """
    registry: ReaderRegistry = ctx.obj["registry"]
    p = Path(log_path) if log_path else None
    reader_specific, _ = _get_reader(registry, source, log_path)

    try:
        if reader_specific:
            full_id = reader_specific.resolve_session_id(session_id, p)
            reader = reader_specific
        else:
            reader, full_id = registry.resolve(session_id)
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
@click.option("--dir", "-d", "fc_dir", default=".flowcraft", help="Artifacts directory")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show(artifact_type: str, fc_dir: str, as_json: bool) -> None:
    """View existing .flowcraft/ artifacts (LESSONS.md, workflows, etc.)."""
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
