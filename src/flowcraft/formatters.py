"""
Output formatters for FlowCraft Distill CLI.

Two modes:
  - Text: Human-readable with simple ANSI colors
  - JSON: Machine-readable (--json flag)
"""

from __future__ import annotations

import json
from typing import Any

from .models import (
    ArtifactInfo,
    DiffResult,
    ReflectionResult,
    SessionDigest,
    SessionInfo,
    SessionOverview,
    ToolCallDetail,
    TurnDetail,
    TurnDigest,
    TurnSummary,
    WorkflowDSL,
)


# ── ANSI helpers ────────────────────────────────────────────────────────────

class _C:
    """Minimal ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"


def _truncate(text: str, max_len: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _json_out(data: Any) -> str:
    """Serialize to pretty JSON."""
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    elif isinstance(data, list) and data and hasattr(data[0], "model_dump"):
        data = [d.model_dump(mode="json") for d in data]
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# ── Session list (scan) ────────────────────────────────────────────────────

def format_session_list(sessions: list[SessionInfo], as_json: bool = False) -> str:
    if as_json:
        return _json_out(sessions)

    if not sessions:
        return "No sessions found."

    lines = [
        f"{_C.BOLD}Found {len(sessions)} session(s):{_C.RESET}",
        "",
        f"  {'#':<4} {'ID':<14} {'Source':<10} {'Date':<12} {'Model':<28} {'Turns':<6} Title",
        f"  {'─'*4} {'─'*14} {'─'*10} {'─'*12} {'─'*28} {'─'*6} {'─'*30}",
    ]

    for i, s in enumerate(sessions, 1):
        date_str = s.date.strftime("%Y-%m-%d") if s.date else "?"
        sid = s.session_id[:12] + ".."
        model = _truncate(s.model, 26)
        title = _truncate(s.title, 40) if s.title else f"{_C.DIM}[no title]{_C.RESET}"

        lines.append(
            f"  {_C.DIM}{i:<4}{_C.RESET} "
            f"{_C.CYAN}{sid:<14}{_C.RESET} "
            f"{s.source_type:<10} "
            f"{date_str:<12} "
            f"{model:<28} "
            f"{s.turns_count:<6} "
            f"{title}"
        )

    return "\n".join(lines)


# ── Session overview (read <id>) ───────────────────────────────────────────

def format_overview(overview: SessionOverview, as_json: bool = False) -> str:
    if as_json:
        return _json_out(overview)

    info = overview.info
    date_str = info.date.strftime("%Y-%m-%d %H:%M") if info.date else "?"

    lines = [
        f"{_C.BOLD}=== Session: {info.session_id[:12]} ==={_C.RESET}",
        f"Source: {info.source_type} | Date: {date_str} | Model: {info.model}",
    ]
    if info.title:
        lines.append(f"Title: {info.title}")
    lines.append(f"Total Turns: {info.turns_count}")
    lines.append("")
    lines.append(f"{_C.BOLD}Turns:{_C.RESET}")

    for t in overview.turns:
        preview = _truncate(t.user_message_preview, 70)
        tools_str = ""
        if t.tool_names:
            # Group and count tool names
            from collections import Counter
            counts = Counter(t.tool_names)
            parts = []
            for name, count in counts.most_common(5):
                short_name = name.replace("copilot_", "").replace("Copilot_", "")
                parts.append(f"{short_name}×{count}" if count > 1 else short_name)
            if len(counts) > 5:
                parts.append(f"+{len(counts)-5} more")
            tools_str = ", ".join(parts)

        err_mark = f" {_C.RED}⚠{_C.RESET}" if t.has_error else ""

        lines.append(
            f"  {_C.GREEN}#{t.turn_number:<3}{_C.RESET} "
            f"{_C.CYAN}[User]{_C.RESET} {preview}"
        )
        if tools_str:
            lines.append(
                f"       {_C.DIM}[Tools: {t.tools_count}]{_C.RESET} {tools_str}{err_mark}"
            )
        lines.append("")

    return "\n".join(lines)


# ── Turn detail (read <id> --turn N) ───────────────────────────────────────

def format_turn_detail(turn: TurnDetail, as_json: bool = False) -> str:
    if as_json:
        return _json_out(turn)

    ts_str = turn.timestamp.strftime("%Y-%m-%d %H:%M:%S") if turn.timestamp else "?"

    lines = [
        f"{_C.BOLD}=== Turn {turn.turn_number} ==={_C.RESET}",
        f"Timestamp: {ts_str} | Model: {turn.model}",
        "",
        f"{_C.BOLD}{_C.CYAN}[User Message]{_C.RESET}",
        turn.user_message or "(empty)",
        "",
    ]

    if turn.tool_calls:
        lines.append(f"{_C.BOLD}{_C.YELLOW}[Tool Calls] ({len(turn.tool_calls)} total){_C.RESET}")
        for tc in turn.tool_calls:
            short_name = tc.tool_name.replace("copilot_", "")
            desc = tc.invocation_message or tc.past_tense_message or ""
            desc_short = _truncate(desc, 80) if desc else ""
            status = f"{_C.GREEN}✓{_C.RESET}" if tc.success else f"{_C.RED}✗{_C.RESET}"

            lines.append(f"  {status} {tc.index}. {_C.MAGENTA}{short_name}{_C.RESET}")
            if desc_short:
                lines.append(f"     {_C.DIM}{desc_short}{_C.RESET}")
            if tc.output_preview:
                out_preview = _truncate(tc.output_preview, 100)
                lines.append(f"     → {out_preview}")

        lines.append("")

    if turn.files_touched:
        lines.append(f"{_C.BOLD}[Files Touched]{_C.RESET}")
        for fp in turn.files_touched:
            lines.append(f"  {fp}")
        lines.append("")

    if turn.commands_run:
        lines.append(f"{_C.BOLD}[Commands Run]{_C.RESET}")
        for cmd in turn.commands_run:
            lines.append(f"  $ {cmd}")
        lines.append("")

    if turn.assistant_response:
        lines.append(f"{_C.BOLD}{_C.GREEN}[Assistant Response]{_C.RESET}")
        # Show first 2000 chars for readability
        resp = turn.assistant_response
        if len(resp) > 2000:
            resp = resp[:2000] + f"\n\n{_C.DIM}[... truncated, {len(turn.assistant_response)} chars total]{_C.RESET}"
        lines.append(resp)

    return "\n".join(lines)


# ── Turns range (read <id> --turns N-M) ────────────────────────────────────

def format_turns_range(turns: list[TurnSummary], as_json: bool = False) -> str:
    if as_json:
        return _json_out(turns)

    if not turns:
        return "No turns in range."

    lines = [f"{_C.BOLD}Turns {turns[0].turn_number}-{turns[-1].turn_number}:{_C.RESET}", ""]
    for t in turns:
        preview = _truncate(t.user_message_preview, 80)
        lines.append(
            f"  {_C.GREEN}#{t.turn_number:<3}{_C.RESET} "
            f"[{t.tools_count} tools] {preview}"
        )
    return "\n".join(lines)


# ── Tool detail (read <id> --turn N --tool M) ─────────────────────────────

def format_tool_detail(tool: ToolCallDetail, as_json: bool = False) -> str:
    if as_json:
        return _json_out(tool)

    status = f"{_C.GREEN}✓ Complete{_C.RESET}" if tool.success else f"{_C.RED}✗ Failed{_C.RESET}"
    short_name = tool.tool_name.replace("copilot_", "")

    lines = [
        f"{_C.BOLD}=== Tool Call #{tool.index} ==={_C.RESET}",
        f"Tool: {_C.MAGENTA}{short_name}{_C.RESET} ({tool.tool_id})",
        f"Status: {status}",
    ]

    if tool.invocation_message:
        lines.append(f"Description: {tool.invocation_message}")

    lines.append("")
    lines.append(f"{_C.BOLD}[Input]{_C.RESET}")
    lines.append(tool.input_full or "(none)")
    lines.append("")
    lines.append(f"{_C.BOLD}[Output]{_C.RESET}")
    lines.append(tool.output_full or "(no output captured)")

    return "\n".join(lines)


# ── Diff (read <id> --diff A B) ────────────────────────────────────────────

def format_diff(diff: DiffResult, as_json: bool = False) -> str:
    if as_json:
        return _json_out(diff)

    lines = [
        f"{_C.BOLD}=== Diff: Turn {diff.turn_a} vs Turn {diff.turn_b} ==={_C.RESET}",
        f"Summary: {diff.summary}",
    ]

    if diff.tools_only_in_a:
        lines.append(f"\n{_C.RED}Tools only in turn {diff.turn_a}:{_C.RESET}")
        for t in diff.tools_only_in_a:
            lines.append(f"  - {t}")

    if diff.tools_only_in_b:
        lines.append(f"\n{_C.GREEN}Tools only in turn {diff.turn_b}:{_C.RESET}")
        for t in diff.tools_only_in_b:
            lines.append(f"  + {t}")

    if diff.files_only_in_a:
        lines.append(f"\n{_C.RED}Files only in turn {diff.turn_a}:{_C.RESET}")
        for fp in diff.files_only_in_a:
            lines.append(f"  - {fp}")

    if diff.files_only_in_b:
        lines.append(f"\n{_C.GREEN}Files only in turn {diff.turn_b}:{_C.RESET}")
        for fp in diff.files_only_in_b:
            lines.append(f"  + {fp}")

    return "\n".join(lines)


# ── Show artifacts ──────────────────────────────────────────────────────────

def format_artifacts(artifacts: list[ArtifactInfo], as_json: bool = False) -> str:
    if as_json:
        return _json_out(artifacts)

    if not artifacts:
        return f"{_C.DIM}No artifacts found in .flowcraft/{_C.RESET}"

    lines = [f"{_C.BOLD}Artifacts in .flowcraft/:{_C.RESET}", ""]
    for a in artifacts:
        mod = a.last_modified.strftime("%Y-%m-%d %H:%M") if a.last_modified else "?"
        size_kb = a.size_bytes / 1024
        lines.append(
            f"  {_C.CYAN}{a.path}{_C.RESET} "
            f"({a.type}, {size_kb:.1f}KB, modified {mod})"
        )
        if a.preview:
            lines.append(f"    {_C.DIM}{_truncate(a.preview, 100)}{_C.RESET}")
        lines.append("")

    return "\n".join(lines)


# ── Session Digest (extract/reflect data prep) ─────────────────────────────

def format_session_digest(digest: SessionDigest, as_json: bool = False) -> str:
    if as_json:
        return _json_out(digest)

    date_str = digest.date.strftime("%Y-%m-%d %H:%M") if digest.date else "?"

    lines = [
        f"{_C.BOLD}=== Session Digest: {digest.session_id[:12]} ==={_C.RESET}",
        f"Title: {digest.title} | Date: {date_str} | Model: {digest.model}",
        f"Total Turns: {digest.total_turns}",
        "",
    ]

    # Tools summary
    if digest.all_tools_used:
        lines.append(f"{_C.BOLD}Tools Used (top 10):{_C.RESET}")
        for t in sorted(digest.all_tools_used, key=lambda x: -x.call_count)[:10]:
            lines.append(f"  {t.tool_name}: {t.call_count}×")
        lines.append("")

    # Turn-by-turn digest
    lines.append(f"{_C.BOLD}Turn Digest:{_C.RESET}")
    for td in digest.turns:
        user_preview = _truncate(td.user_message, 100)
        tools_str = ", ".join(td.tools_used[:5])
        if len(td.tools_used) > 5:
            tools_str += f" +{len(td.tools_used)-5}"

        lines.append(f"  {_C.GREEN}#{td.turn_number:<3}{_C.RESET} {user_preview}")
        if tools_str:
            lines.append(f"       {_C.DIM}Tools: [{tools_str}]{_C.RESET}")
        if td.files_touched:
            files_str = ", ".join(td.files_touched[:3])
            if len(td.files_touched) > 3:
                files_str += f" +{len(td.files_touched)-3}"
            lines.append(f"       {_C.DIM}Files: {files_str}{_C.RESET}")
        if td.assistant_summary:
            lines.append(f"       {_C.DIM}→ {_truncate(td.assistant_summary, 80)}{_C.RESET}")
        lines.append("")

    return "\n".join(lines)


# ── Workflow DSL ────────────────────────────────────────────────────────────

def format_workflow_dsl(workflow: WorkflowDSL, as_json: bool = False) -> str:
    if as_json:
        return _json_out(workflow)

    lines = [
        f"{_C.BOLD}=== Workflow: {workflow.name} ==={_C.RESET}",
        f"Goal: {workflow.goal}",
        f"Source: {workflow.source_session_id[:12]}... ({workflow.source_title})",
        "",
    ]

    if workflow.inputs:
        lines.append(f"{_C.BOLD}Inputs:{_C.RESET}")
        for inp in workflow.inputs:
            lines.append(f"  • {inp}")
        lines.append("")

    if workflow.outputs:
        lines.append(f"{_C.BOLD}Outputs:{_C.RESET}")
        for out in workflow.outputs:
            lines.append(f"  • {out}")
        lines.append("")

    for phase in workflow.phases:
        lines.append(f"{_C.BOLD}{_C.CYAN}Phase {phase.phase_number}: {phase.name}{_C.RESET}")
        if phase.description:
            lines.append(f"  {phase.description}")
        if phase.entry_condition:
            lines.append(f"  {_C.DIM}Entry: {phase.entry_condition}{_C.RESET}")
        if phase.exit_condition:
            lines.append(f"  {_C.DIM}Exit: {phase.exit_condition}{_C.RESET}")

        for step in phase.steps:
            tools_str = ", ".join(t.tool_name for t in step.tools_used)
            lines.append(f"    {step.step_number}. {step.description}")
            if tools_str:
                lines.append(f"       {_C.DIM}Tools: {tools_str}{_C.RESET}")
            if step.decision_point:
                lines.append(f"       {_C.YELLOW}Decision: {step.decision_point}{_C.RESET}")
        lines.append("")

    if workflow.dependencies:
        lines.append(f"{_C.BOLD}Dependencies:{_C.RESET}")
        for dep in workflow.dependencies:
            lines.append(f"  → {dep}")
        lines.append("")

    return "\n".join(lines)


# ── Reflection ──────────────────────────────────────────────────────────────

def format_reflection(reflection: ReflectionResult, as_json: bool = False) -> str:
    if as_json:
        return _json_out(reflection)

    date_str = reflection.date.strftime("%Y-%m-%d") if reflection.date else "?"
    goal_icon = f"{_C.GREEN}✓{_C.RESET}" if reflection.goal_achieved else f"{_C.RED}✗{_C.RESET}"

    lines = [
        f"{_C.BOLD}=== Reflection: {reflection.title} ==={_C.RESET}",
        f"Session: {reflection.session_id[:12]} | Date: {date_str}",
        f"Goal: {goal_icon} {reflection.goal_summary}",
        "",
        f"{_C.BOLD}Workflow Summary:{_C.RESET}",
        f"  {reflection.workflow_summary}",
        "",
    ]

    categories = [
        ("🔴 Errors & Fixes", reflection.errors, _C.RED),
        ("🟡 Inefficiency Patterns", reflection.inefficiencies, _C.YELLOW),
        ("🟢 Effective Practices", reflection.good_practices, _C.GREEN),
        ("⚠️  Environment & Tool Traps", reflection.traps, _C.YELLOW),
    ]

    for cat_title, insights, color in categories:
        if not insights:
            continue
        lines.append(f"{_C.BOLD}{cat_title}{_C.RESET}")
        for ins in insights:
            lines.append(f"  {color}[{ins.severity}]{_C.RESET} {_C.BOLD}{ins.title}{_C.RESET}")
            lines.append(f"    {ins.description}")
            if ins.recommendation:
                lines.append(f"    {_C.DIM}→ {ins.recommendation}{_C.RESET}")
            if ins.source_turns:
                turns_str = ", ".join(str(t) for t in ins.source_turns)
                lines.append(f"    {_C.DIM}Turns: {turns_str}{_C.RESET}")
        lines.append("")

    if reflection.instructions:
        lines.append(f"{_C.BOLD}📋 Recommended Agent Instructions:{_C.RESET}")
        for inst in reflection.instructions:
            lines.append(f"  {inst}")
        lines.append("")

    return "\n".join(lines)


# ── Raw JSON ────────────────────────────────────────────────────────────────

def format_raw(data: dict, as_json: bool = True) -> str:
    """Format raw data — always JSON."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
