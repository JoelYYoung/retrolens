"""
VS Code Copilot Chat JSONL reader.

Parses the incremental state-machine format used by GitHub Copilot Chat
in VS Code. Each .jsonl file represents one chat session.

Format:
  kind:0  → Session initialization (metadata, model, mode)
  kind:1  → UI state incremental updates (customTitle is useful, rest skipped)
  kind:2  → Core data patches
    k: ["requests"]              → Append new request objects
    k: ["requests", N, "response"] → Append response items to request N
    k: ["customTitle"]           → Session title update

Log location (macOS):
  ~/Library/Application Support/Code/User/workspaceStorage/*/chatSessions/*.jsonl
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

def _default_vscode_paths() -> list[Path]:
    """Return candidate VS Code chatSession directories for this OS."""
    system = platform.system()
    home = Path.home()

    if system == "Darwin":
        base = home / "Library" / "Application Support" / "Code" / "User"
    elif system == "Linux":
        base = home / ".config" / "Code" / "User"
    elif system == "Windows":
        base = home / "AppData" / "Roaming" / "Code" / "User"
    else:
        return []

    ws_storage = base / "workspaceStorage"
    if not ws_storage.exists():
        return []

    # Each workspace folder may have a chatSessions/ subfolder
    paths = []
    try:
        for ws_dir in ws_storage.iterdir():
            cs_dir = ws_dir / "chatSessions"
            if cs_dir.is_dir():
                paths.append(cs_dir)
    except PermissionError:
        pass
    return paths


# ── JSONL Parser ────────────────────────────────────────────────────────────

class _ParsedSession:
    """In-memory representation of a replayed JSONL session."""

    def __init__(self) -> None:
        self.session_id: str = ""
        self.model: str = ""
        self.mode: str = ""
        self.creation_date: Optional[datetime] = None
        self.title: str = ""
        self.requests: list[dict[str, Any]] = []  # fully assembled request objects
        self.source_path: Optional[Path] = None

    @property
    def turns_count(self) -> int:
        return len(self.requests)


def _parse_jsonl(path: Path) -> _ParsedSession:
    """Replay a VS Code Copilot Chat JSONL file into a _ParsedSession."""
    session = _ParsedSession()
    session.source_path = path

    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            kind = obj.get("kind")

            if kind == 0:
                _handle_kind0(obj, session)
            elif kind == 1:
                _handle_kind1(obj, session)
            elif kind == 2:
                _handle_kind2(obj, session)

    return session


def _handle_kind0(obj: dict, session: _ParsedSession) -> None:
    """Process session initialization."""
    v = obj.get("v", {})
    session.session_id = v.get("sessionId", "")

    # Extract model from inputState.selectedModel.metadata.id
    input_state = v.get("inputState", {})
    sel_model = input_state.get("selectedModel", {})
    metadata = sel_model.get("metadata", {})
    session.model = metadata.get("id", metadata.get("name", ""))

    # Mode
    mode_info = input_state.get("mode", {})
    session.mode = mode_info.get("kind", mode_info.get("id", ""))

    # Creation date (epoch ms)
    creation_ms = v.get("creationDate")
    if creation_ms and isinstance(creation_ms, (int, float)):
        session.creation_date = datetime.fromtimestamp(
            creation_ms / 1000, tz=timezone.utc
        )

    # Initial requests (usually empty but handle if present)
    for req in v.get("requests", []):
        if isinstance(req, dict) and req.get("requestId"):
            session.requests.append(req)


def _handle_kind1(obj: dict, session: _ParsedSession) -> None:
    """Process UI state updates. Only extract customTitle."""
    k = obj.get("k", [])
    v = obj.get("v")

    if k == ["customTitle"] and isinstance(v, str):
        session.title = v


def _handle_kind2(obj: dict, session: _ParsedSession) -> None:
    """Process core data patches (requests + responses)."""
    k = obj.get("k", [])
    v = obj.get("v")

    if not k:
        return

    # ── Append new requests ──
    if k == ["requests"] and isinstance(v, list):
        for req in v:
            if isinstance(req, dict):
                session.requests.append(req)
        return

    # ── Append response items to request N ──
    if (
        len(k) == 3
        and k[0] == "requests"
        and isinstance(k[1], int)
        and k[2] == "response"
        and isinstance(v, list)
    ):
        req_idx = k[1]
        if 0 <= req_idx < len(session.requests):
            req = session.requests[req_idx]
            if "response" not in req:
                req["response"] = []
            req["response"].extend(v)
        return

    # ── Replace specific response item ──
    if (
        len(k) == 4
        and k[0] == "requests"
        and isinstance(k[1], int)
        and k[2] == "response"
        and isinstance(k[3], int)
    ):
        req_idx = k[1]
        resp_idx = k[3]
        if 0 <= req_idx < len(session.requests):
            resp = session.requests[req_idx].get("response", [])
            if 0 <= resp_idx < len(resp):
                resp[resp_idx] = v
        return

    # ── Custom title via kind:2 ──
    if k == ["customTitle"] and isinstance(v, str):
        session.title = v


# ── Response item extraction helpers ────────────────────────────────────────

def _extract_assistant_text(response_items: list[dict]) -> str:
    """Extract concatenated assistant text from response items."""
    parts = []
    for item in response_items:
        if not isinstance(item, dict):
            continue
        # Text response items have a "value" key and no "kind"
        if "value" in item and "kind" not in item:
            parts.append(item["value"])
    return "\n".join(parts)


def _extract_tool_calls(response_items: list[dict]) -> list[models.ToolCallDetail]:
    """Extract tool call details from response items."""
    tools = []
    idx = 0
    for item in response_items:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "toolInvocationSerialized":
            continue

        tool_id = item.get("toolId", "")
        invocation_msg_raw = item.get("invocationMessage", "")
        past_tense_msg_raw = item.get("pastTenseMessage", "")
        # These can be dicts like {value: "...", ...} instead of plain strings
        invocation_msg = invocation_msg_raw.get("value", str(invocation_msg_raw)) if isinstance(invocation_msg_raw, dict) else str(invocation_msg_raw) if invocation_msg_raw else ""
        past_tense_msg = past_tense_msg_raw.get("value", str(past_tense_msg_raw)) if isinstance(past_tense_msg_raw, dict) else str(past_tense_msg_raw) if past_tense_msg_raw else ""

        # Extract input from toolSpecificData or invocationMessage
        tsd = item.get("toolSpecificData", {})
        input_text = ""
        if isinstance(tsd, dict):
            # For subagent calls, show the prompt
            if tsd.get("kind") == "subagent":
                input_text = tsd.get("inputDescription", invocation_msg)
            else:
                # Generic: serialize toolSpecificData
                input_text = json.dumps(tsd, ensure_ascii=False, indent=2)
                if input_text == "{}":
                    input_text = invocation_msg
        if not input_text:
            input_text = invocation_msg
        # Ensure input_text is a string
        if not isinstance(input_text, str):
            input_text = json.dumps(input_text, ensure_ascii=False, indent=2) if input_text else ""

        # Extract output/result
        result = item.get("result", "")
        if isinstance(result, dict):
            result_content = result.get("content", result)
            if isinstance(result_content, list):
                # Flatten content parts
                result_parts = []
                for part in result_content:
                    if isinstance(part, dict) and "value" in part:
                        result_parts.append(part["value"])
                    elif isinstance(part, str):
                        result_parts.append(part)
                result = "\n".join(result_parts)
            elif isinstance(result_content, str):
                result = result_content
            else:
                result = json.dumps(result_content, ensure_ascii=False)
        elif isinstance(result, (list, tuple)):
            result = json.dumps(result, ensure_ascii=False, indent=2)
        elif not isinstance(result, str):
            result = str(result) if result else ""

        # Truncation for preview
        input_preview = input_text[:500] + ("..." if len(input_text) > 500 else "")
        output_preview = result[:500] + ("..." if len(str(result)) > 500 else "")

        tools.append(models.ToolCallDetail(
            index=idx,
            tool_name=tool_id,
            tool_id=tool_id,
            input_preview=input_preview,
            input_full=input_text,
            output_preview=output_preview,
            output_full=str(result),
            success=True,  # VS Code doesn't expose error state clearly
            invocation_message=invocation_msg,
            past_tense_message=past_tense_msg,
        ))
        idx += 1

    return tools


def _extract_files_touched(tool_calls: list[models.ToolCallDetail]) -> list[str]:
    """Infer files touched from tool call names and inputs."""
    files = set()
    file_tool_ids = {
        "copilot_readFile", "copilot_editFile", "copilot_createFile",
        "read_file", "insert_edit_into_file", "replace_string_in_file",
        "create_file",
    }
    for tc in tool_calls:
        if tc.tool_name in file_tool_ids:
            # Try to extract path from input
            try:
                data = json.loads(tc.input_full)
                path = (
                    data.get("filePath")
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
    """Infer commands run from tool call names and inputs."""
    commands = []
    cmd_tool_ids = {
        "run_in_terminal", "copilot_runCommand", "runCommand",
    }
    for tc in tool_calls:
        if tc.tool_name in cmd_tool_ids:
            try:
                data = json.loads(tc.input_full)
                cmd = data.get("command", "")
                if cmd:
                    commands.append(cmd)
            except (json.JSONDecodeError, AttributeError):
                pass
    return commands


# ── VSCodeCopilotReader ─────────────────────────────────────────────────────

class VSCodeCopilotReader(BaseReader):
    """Read VS Code Copilot Chat session logs."""

    source_type = "vscode"

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
        return _default_vscode_paths()

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

        # Find the file
        for jsonl_path in self._find_jsonl_files(path):
            if jsonl_path.stem == session_id:
                parsed = _parse_jsonl(jsonl_path)
                self._cache[session_id] = parsed
                return parsed

        # Try parsing all files to find by session_id in content
        for jsonl_path in self._find_jsonl_files(path):
            if jsonl_path.stem in self._cache:
                parsed = self._cache[jsonl_path.stem]
            else:
                parsed = _parse_jsonl(jsonl_path)
                self._cache[parsed.session_id or jsonl_path.stem] = parsed

            if parsed.session_id == session_id:
                return parsed

        raise ValueError(f"Session '{session_id}' not found")

    # ── BaseReader interface ────────────────────────────────────────────────

    def scan(self, path: Path | None = None) -> list[models.SessionInfo]:
        sessions = []
        for jsonl_path in self._find_jsonl_files(path):
            try:
                parsed = _parse_jsonl(jsonl_path)
                sid = parsed.session_id or jsonl_path.stem
                self._cache[sid] = parsed

                sessions.append(models.SessionInfo(
                    session_id=sid,
                    source_type=self.source_type,
                    date=parsed.creation_date,
                    model=parsed.model,
                    title=parsed.title,
                    turns_count=parsed.turns_count,
                ))
            except Exception:
                continue

        _dt_min = datetime.min.replace(tzinfo=timezone.utc)
        sessions.sort(key=lambda s: s.date or _dt_min, reverse=True)
        return sessions

    def get_overview(self, session_id: str) -> models.SessionOverview:
        parsed = self._load_session(session_id)
        info = models.SessionInfo(
            session_id=parsed.session_id,
            source_type=self.source_type,
            date=parsed.creation_date,
            model=parsed.model,
            title=parsed.title,
            turns_count=parsed.turns_count,
        )

        turns = []
        for i, req in enumerate(parsed.requests):
            msg_text = req.get("message", {}).get("text", "")
            preview = msg_text[:120] + ("..." if len(msg_text) > 120 else "")

            response_items = req.get("response", [])
            tool_calls = _extract_tool_calls(response_items)
            tool_names = sorted(set(tc.tool_name for tc in tool_calls))

            # Extract timestamp
            ts = None
            ts_raw = req.get("timestamp")
            if ts_raw and isinstance(ts_raw, (int, float)):
                ts = datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)

            turns.append(models.TurnSummary(
                turn_number=i + 1,
                user_message_preview=preview,
                tools_count=len(tool_calls),
                tool_names=tool_names,
                has_error=False,
                timestamp=ts,
            ))

        return models.SessionOverview(info=info, turns=turns)

    def get_turn(self, session_id: str, turn_number: int) -> models.TurnDetail:
        parsed = self._load_session(session_id)
        idx = turn_number - 1  # 1-based → 0-based
        if idx < 0 or idx >= len(parsed.requests):
            raise IndexError(
                f"Turn {turn_number} out of range "
                f"(session has {len(parsed.requests)} turns)"
            )

        req = parsed.requests[idx]
        msg_text = req.get("message", {}).get("text", "")
        response_items = req.get("response", [])

        assistant_text = _extract_assistant_text(response_items)
        tool_calls = _extract_tool_calls(response_items)
        files = _extract_files_touched(tool_calls)
        commands = _extract_commands_run(tool_calls)

        ts = None
        ts_raw = req.get("timestamp")
        if ts_raw and isinstance(ts_raw, (int, float)):
            ts = datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)

        return models.TurnDetail(
            turn_number=turn_number,
            user_message=msg_text,
            assistant_response=assistant_text,
            tool_calls=tool_calls,
            files_touched=files,
            commands_run=commands,
            timestamp=ts,
            model=parsed.model,
            mode=parsed.mode,
        )

    def get_turn_raw(self, session_id: str, turn_number: int) -> dict[str, Any]:
        """Return the raw request dict for a turn."""
        parsed = self._load_session(session_id)
        idx = turn_number - 1
        if idx < 0 or idx >= len(parsed.requests):
            raise IndexError(f"Turn {turn_number} out of range")
        return parsed.requests[idx]
