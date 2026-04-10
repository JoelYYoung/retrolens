"""
Claude Code native log reader.

Parses the JSONL format used by Claude Code (the CLI).
Each .jsonl file represents one session, stored per-project.

Format:
  type:"system"    → System events (local_command, api_error, turn_duration)
  type:"user"      → User messages (may contain tool_result blocks)
  type:"assistant"  → Assistant responses (may contain tool_use blocks)
  type:"file-history-snapshot" → File change snapshots (skipped)

Log location (macOS):
  ~/.claude/projects/<encoded-path>/<session-id>.jsonl

Project path encoding: / → -
  e.g. /Users/joel/Projects/myapp → -Users-joel-Projects-myapp
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import models
from . import BaseReader


# ── Default log paths per OS ────────────────────────────────────────────────

def _default_claude_code_paths() -> list[Path]:
    """Return candidate Claude Code project directories for this OS."""
    home = Path.home()
    projects_dir = home / ".claude" / "projects"
    if not projects_dir.exists():
        return []

    paths = []
    try:
        for proj_dir in projects_dir.iterdir():
            if proj_dir.is_dir() and list(proj_dir.glob("*.jsonl")):
                paths.append(proj_dir)
    except PermissionError:
        pass
    return paths


def _decode_project_path(encoded: str) -> str:
    """Decode Claude Code directory name back to project path.

    e.g. -Users-joel-Projects-myapp → /Users/joel/Projects/myapp
    """
    # The encoding replaces / with -
    # Leading - represents the root /
    if encoded.startswith("-"):
        return "/" + encoded[1:].replace("-", "/")
    return encoded.replace("-", "/")


def _encode_project_path(path: str) -> str:
    """Encode a project path to Claude Code directory name.

    e.g. /Users/joel/Projects/myapp → -Users-joel-Projects-myapp
    """
    return path.replace("/", "-")


# ── JSONL Parser ────────────────────────────────────────────────────────────

class _ParsedSession:
    """In-memory representation of a parsed Claude Code session."""

    def __init__(self) -> None:
        self.session_id: str = ""
        self.model: str = ""
        self.version: str = ""
        self.cwd: str = ""
        self.git_branch: str = ""
        self.first_timestamp: Optional[datetime] = None
        self.turns: list[_Turn] = []
        self.source_path: Optional[Path] = None

    @property
    def turns_count(self) -> int:
        return len(self.turns)


class _Turn:
    """A single user→assistant exchange."""

    def __init__(self, number: int):
        self.number = number
        self.user_message: str = ""
        self.user_uuid: str = ""
        self.assistant_response: str = ""
        self.tool_calls: list[models.ToolCallDetail] = []
        self.tool_results: dict[str, str] = {}  # tool_use_id → result
        self.timestamp: Optional[datetime] = None
        self.duration_ms: Optional[int] = None


def _parse_timestamp(ts: Any) -> Optional[datetime]:
    """Parse a timestamp from Claude Code format (ISO string)."""
    if not ts:
        return None
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return None


def _extract_user_text(message: dict) -> str:
    """Extract user-visible text from a user message."""
    content = message.get("content", "")
    if isinstance(content, str):
        # Skip system/command messages
        if content.startswith("<") and ">" in content:
            return ""
        return content

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if not (text.startswith("<") and ">" in text):
                        text_parts.append(text)
                # Skip tool_result blocks — they're handled separately
            elif isinstance(item, str):
                if not (item.startswith("<") and ">" in item):
                    text_parts.append(item)
        return "\n".join(text_parts)

    return ""


def _extract_tool_results(message: dict) -> dict[str, str]:
    """Extract tool results from a user message content array."""
    results = {}
    content = message.get("content", [])
    if not isinstance(content, list):
        return results

    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            tool_use_id = item.get("tool_use_id", "")
            result_content = item.get("content", "")
            is_error = item.get("is_error", False)

            if isinstance(result_content, str):
                result_text = result_content
            elif isinstance(result_content, list):
                parts = []
                for part in result_content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        parts.append(part)
                result_text = "\n".join(parts)
            else:
                result_text = json.dumps(result_content, ensure_ascii=False)

            if is_error:
                result_text = f"[ERROR] {result_text}"

            results[tool_use_id] = result_text

    return results


def _extract_assistant_text(content: list) -> str:
    """Extract text blocks from assistant content array."""
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "\n".join(parts)


def _extract_tool_calls(content: list) -> list[models.ToolCallDetail]:
    """Extract tool_use blocks from assistant content array."""
    tools = []
    idx = 0
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_use":
            continue

        name = item.get("name", "")
        tool_id = item.get("id", "")
        input_data = item.get("input", {})

        if isinstance(input_data, dict):
            input_str = json.dumps(input_data, ensure_ascii=False, indent=2)
        else:
            input_str = str(input_data)

        input_preview = input_str[:500] + ("..." if len(input_str) > 500 else "")

        tools.append(models.ToolCallDetail(
            index=idx,
            tool_name=name,
            tool_id=tool_id,
            input_preview=input_preview,
            input_full=input_str,
            output_preview="",  # filled in later from tool_result
            output_full="",
            success=True,
            invocation_message=f"Called {name}",
            past_tense_message=f"Called {name}",
        ))
        idx += 1

    return tools


def _extract_files_touched(tool_calls: list[models.ToolCallDetail]) -> list[str]:
    """Infer files touched from tool calls."""
    files = set()
    file_tool_names = {
        "Read", "Write", "Edit", "MultiEdit",
        "read_file", "write_file", "edit_file",
        "ReadFile", "WriteFile", "CreateFile",
    }
    for tc in tool_calls:
        if tc.tool_name in file_tool_names:
            try:
                data = json.loads(tc.input_full)
                path = (
                    data.get("file_path")
                    or data.get("filePath")
                    or data.get("path")
                    or data.get("file")
                    or ""
                )
                if path:
                    files.add(path)
            except (json.JSONDecodeError, AttributeError):
                pass
    return sorted(files)


def _extract_commands_run(tool_calls: list[models.ToolCallDetail]) -> list[str]:
    """Infer commands run from tool calls."""
    commands = []
    cmd_tool_names = {"Bash", "bash", "run_command", "Terminal", "execute"}
    for tc in tool_calls:
        if tc.tool_name in cmd_tool_names:
            try:
                data = json.loads(tc.input_full)
                cmd = data.get("command") or data.get("cmd") or ""
                if cmd:
                    commands.append(cmd)
            except (json.JSONDecodeError, AttributeError):
                pass
    return commands


def _parse_jsonl(path: Path) -> _ParsedSession:
    """Parse a Claude Code JSONL file into a _ParsedSession."""
    session = _ParsedSession()
    session.source_path = path

    events: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not events:
        return session

    # Extract session metadata from first event
    first = events[0]
    session.session_id = first.get("sessionId", path.stem)
    session.version = first.get("version", "")
    session.cwd = first.get("cwd", "")
    session.git_branch = first.get("gitBranch", "")
    session.first_timestamp = _parse_timestamp(first.get("timestamp"))

    # Build turns by grouping user→assistant exchanges
    current_turn: Optional[_Turn] = None
    turn_number = 0
    pending_tool_results: dict[str, str] = {}

    for event in events:
        etype = event.get("type", "")
        is_meta = event.get("isMeta", False)

        if etype == "user" and not is_meta:
            msg = event.get("message", {})
            user_text = _extract_user_text(msg)

            # Collect tool results from this user message
            tool_results = _extract_tool_results(msg)
            if tool_results:
                pending_tool_results.update(tool_results)

            # Only start a new turn if there's actual user text
            if user_text:
                # Save previous turn
                if current_turn:
                    _finalize_turn(current_turn, pending_tool_results)
                    session.turns.append(current_turn)
                    pending_tool_results = {}

                turn_number += 1
                current_turn = _Turn(number=turn_number)
                current_turn.user_message = user_text
                current_turn.user_uuid = event.get("uuid", "")
                current_turn.timestamp = _parse_timestamp(event.get("timestamp"))

        elif etype == "user" and is_meta:
            # Meta user messages may contain tool results
            msg = event.get("message", {})
            tool_results = _extract_tool_results(msg)
            if tool_results:
                pending_tool_results.update(tool_results)

        elif etype == "assistant":
            if current_turn is None:
                # Assistant without a user turn — create one
                turn_number += 1
                current_turn = _Turn(number=turn_number)
                current_turn.timestamp = _parse_timestamp(event.get("timestamp"))

            msg = event.get("message", {})
            content = msg.get("content", [])

            # Extract model from first assistant message
            if not session.model:
                session.model = msg.get("model", "")

            if isinstance(content, list):
                # Append text
                text = _extract_assistant_text(content)
                if text:
                    if current_turn.assistant_response:
                        current_turn.assistant_response += "\n" + text
                    else:
                        current_turn.assistant_response = text

                # Append tool calls
                tools = _extract_tool_calls(content)
                for tc in tools:
                    tc.index = len(current_turn.tool_calls)
                    current_turn.tool_calls.append(tc)

        elif etype == "system":
            subtype = event.get("subtype", "")
            if subtype == "turn_duration" and current_turn:
                current_turn.duration_ms = event.get("durationMs")

    # Don't forget the last turn
    if current_turn:
        _finalize_turn(current_turn, pending_tool_results)
        session.turns.append(current_turn)

    return session


def _finalize_turn(turn: _Turn, tool_results: dict[str, str]) -> None:
    """Fill in tool call outputs from collected tool results."""
    for tc in turn.tool_calls:
        if tc.tool_id in tool_results:
            result = tool_results[tc.tool_id]
            tc.output_full = result
            tc.output_preview = result[:500] + ("..." if len(result) > 500 else "")
            if result.startswith("[ERROR]"):
                tc.success = False


# ── ClaudeCodeReader ────────────────────────────────────────────────────────

class ClaudeCodeReader(BaseReader):
    """Read Claude Code native session logs."""

    source_type = "claude_code"

    def __init__(self, paths: list[Path] | None = None):
        self._custom_paths = paths
        self._cache: dict[str, _ParsedSession] = {}

    def _get_search_paths(self, path: Path | None = None) -> list[Path]:
        """Return directories to search for .jsonl files."""
        if path:
            p = Path(path)
            if p.is_file():
                return [p.parent]
            return [p]
        if self._custom_paths:
            return self._custom_paths
        return _default_claude_code_paths()

    def _find_jsonl_files(self, path: Path | None = None) -> list[Path]:
        """Find all .jsonl session files."""
        files = []
        for search_dir in self._get_search_paths(path):
            if search_dir.is_dir():
                files.extend(search_dir.glob("*.jsonl"))
            elif search_dir.is_file() and search_dir.suffix == ".jsonl":
                files.append(search_dir)
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def _load_session(self, session_id: str, path: Path | None = None) -> _ParsedSession:
        """Load and cache a parsed session."""
        if session_id in self._cache:
            return self._cache[session_id]

        for jsonl_path in self._find_jsonl_files(path):
            if jsonl_path.stem == session_id:
                parsed = _parse_jsonl(jsonl_path)
                self._cache[session_id] = parsed
                return parsed

        # Try parsing to find by sessionId in content
        for jsonl_path in self._find_jsonl_files(path):
            stem = jsonl_path.stem
            if stem in self._cache:
                parsed = self._cache[stem]
            else:
                parsed = _parse_jsonl(jsonl_path)
                self._cache[parsed.session_id or stem] = parsed
            if parsed.session_id == session_id:
                return parsed

        raise ValueError(f"Session '{session_id}' not found")

    def _infer_project_path(self, jsonl_path: Path) -> str:
        """Infer the project path from the JSONL file's parent directory."""
        parent_name = jsonl_path.parent.name
        return _decode_project_path(parent_name)

    # ── BaseReader interface ────────────────────────────────────────────────

    def scan(self, path: Path | None = None) -> list[models.SessionInfo]:
        sessions = []
        for jsonl_path in self._find_jsonl_files(path):
            try:
                parsed = _parse_jsonl(jsonl_path)
                sid = parsed.session_id or jsonl_path.stem
                self._cache[sid] = parsed

                # Use first user message as title if available
                title = ""
                if parsed.turns:
                    title = parsed.turns[0].user_message[:80]
                    if len(parsed.turns[0].user_message) > 80:
                        title += "..."

                sessions.append(models.SessionInfo(
                    session_id=sid,
                    source_type=self.source_type,
                    date=parsed.first_timestamp,
                    model=parsed.model,
                    title=title,
                    turns_count=parsed.turns_count,
                ))
            except Exception:
                continue

        _dt_min = datetime.min.replace(tzinfo=timezone.utc)
        sessions.sort(
            key=lambda s: s.date.replace(tzinfo=timezone.utc)
            if s.date and s.date.tzinfo is None
            else (s.date or _dt_min),
            reverse=True,
        )
        return sessions

    def get_overview(self, session_id: str) -> models.SessionOverview:
        parsed = self._load_session(session_id)

        info = models.SessionInfo(
            session_id=parsed.session_id,
            source_type=self.source_type,
            date=parsed.first_timestamp,
            model=parsed.model,
            title="",
            turns_count=parsed.turns_count,
        )

        turns = []
        for turn in parsed.turns:
            preview = turn.user_message[:120]
            if len(turn.user_message) > 120:
                preview += "..."
            tool_names = sorted(set(tc.tool_name for tc in turn.tool_calls))

            turns.append(models.TurnSummary(
                turn_number=turn.number,
                user_message_preview=preview,
                tools_count=len(turn.tool_calls),
                tool_names=tool_names,
                has_error=any(not tc.success for tc in turn.tool_calls),
                timestamp=turn.timestamp,
            ))

        return models.SessionOverview(info=info, turns=turns)

    def get_turn(self, session_id: str, turn_number: int) -> models.TurnDetail:
        parsed = self._load_session(session_id)

        target = None
        for turn in parsed.turns:
            if turn.number == turn_number:
                target = turn
                break

        if not target:
            raise IndexError(
                f"Turn {turn_number} out of range "
                f"(session has {parsed.turns_count} turns)"
            )

        files = _extract_files_touched(target.tool_calls)
        commands = _extract_commands_run(target.tool_calls)

        return models.TurnDetail(
            turn_number=target.number,
            user_message=target.user_message,
            assistant_response=target.assistant_response,
            tool_calls=target.tool_calls,
            files_touched=files,
            commands_run=commands,
            timestamp=target.timestamp,
            model=parsed.model,
        )

    def get_turn_raw(self, session_id: str, turn_number: int) -> dict[str, Any]:
        """Return raw data for a turn (reconstructed from parsed events)."""
        turn_detail = self.get_turn(session_id, turn_number)
        return turn_detail.model_dump()

    # ── Session ID resolution ───────────────────────────────────────────────

    def resolve_session_id(self, prefix: str, path: Path | None = None) -> str:
        if prefix == "latest":
            sessions = self.scan(path)
            if not sessions:
                raise ValueError("No sessions found")
            return sessions[0].session_id

        sessions = self.scan(path)
        matches = [s for s in sessions if s.session_id.startswith(prefix)]
        if len(matches) == 0:
            raise ValueError(f"No session matching prefix '{prefix}'")
        if len(matches) > 1:
            ids = ", ".join(m.session_id[:12] for m in matches[:5])
            raise ValueError(
                f"Ambiguous prefix '{prefix}' matches {len(matches)} sessions: {ids}"
            )
        return matches[0].session_id
