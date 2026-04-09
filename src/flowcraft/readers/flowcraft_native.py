"""
FlowCraft native log reader.

Reads session logs stored in the FlowCraft format:
  logs/
  ├── index.json              ← session listing
  └── sessions/
      └── <session_id>/
          ├── metadata.json   ← session metadata
          ├── 001_request.json
          ├── 001_response.json
          ├── 002_request.json
          └── 002_response.json

Each request/response pair is one "sequence". Multiple sequences may
belong to the same logical "turn" (user message → assistant response).
Auxiliary requests (title generation, topic detection) are filtered out.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import models
from . import BaseReader


# ── Auxiliary request markers (requests to skip) ────────────────────────────

_AUXILIARY_MARKERS = [
    "write a 5-10 word title",
    "summarize this coding conversation",
    "extract any file paths",
    "is_displaying_contents",
    "analyze if this message indicates a new conversation topic",
    "isnewtopic",
    "suggestion mode",
    "suggest what the user might",
    "<policy_spec>",
    "your task is to process bash commands",
    "command prefix detection",
]

_SYSTEM_TAG_PREFIXES = [
    "<environment_info>",
    "<workspace_info>",
    "<conversation-summary>",
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _is_auxiliary(request: dict) -> bool:
    """Check if a request is auxiliary (title generation, etc.)."""
    raw = request.get("raw_request", {})

    # Token count probes
    if raw.get("max_tokens", 0) == 1:
        return True

    # Check system prompt + user messages for markers
    texts = []

    system = raw.get("system", [])
    if isinstance(system, str):
        texts.append(system)
    elif isinstance(system, list):
        for item in system:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)

    for msg in raw.get("messages", []):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(item.get("text", ""))

    combined = " ".join(texts).lower()
    return any(m in combined for m in _AUXILIARY_MARKERS)


def _extract_user_message(request: dict) -> str:
    """Extract new user message text from a request."""
    raw = request.get("raw_request", {})
    messages = raw.get("messages", [])

    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            stripped = content.strip()
            if stripped and not any(stripped.startswith(p) for p in _SYSTEM_TAG_PREFIXES):
                return content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "tool_result":
                        continue
                    if item.get("type") == "text":
                        text = item.get("text", "").strip()
                        if text and not any(text.startswith(p) for p in _SYSTEM_TAG_PREFIXES):
                            parts.append(text)
                elif isinstance(item, str):
                    if not any(item.strip().startswith(p) for p in _SYSTEM_TAG_PREFIXES):
                        parts.append(item)
            if parts:
                return "\n".join(parts)

    return ""


def _extract_response_text(response: dict) -> str:
    """Extract assistant text from a response."""
    raw = response.get("raw_response", {})
    content = raw.get("content", [])

    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            return item.get("text", "")

    return ""


def _extract_tool_calls_native(response: dict) -> list[models.ToolCallDetail]:
    """Extract tool calls from a FlowCraft native response."""
    raw = response.get("raw_response", {})
    content = raw.get("content", [])
    tools = []
    idx = 0

    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_use":
            continue

        name = item.get("name", "")
        input_data = item.get("input", {})
        input_str = json.dumps(input_data, ensure_ascii=False, indent=2)

        tools.append(models.ToolCallDetail(
            index=idx,
            tool_name=name,
            tool_id=item.get("id", ""),
            input_preview=input_str[:500] + ("..." if len(input_str) > 500 else ""),
            input_full=input_str,
            output_preview="",  # output is in tool_result of next request
            output_full="",
            success=True,
            invocation_message=f"Called {name}",
            past_tense_message=f"Called {name}",
        ))
        idx += 1

    return tools


# ── Turn assembly ───────────────────────────────────────────────────────────

def _user_hash(request: dict) -> str:
    """Hash the user message to detect new turns."""
    msg = _extract_user_message(request)
    return hashlib.md5(msg.encode()).hexdigest()[:16] if msg else ""


class _Turn:
    """Accumulates sequences belonging to one logical turn."""

    def __init__(self, number: int):
        self.number = number
        self.sequences: list[int] = []
        self.user_message: str = ""
        self.assistant_response: str = ""
        self.tool_calls: list[models.ToolCallDetail] = []
        self.timestamp: Optional[datetime] = None


def _assemble_turns(
    session_dir: Path, request_count: int
) -> list[_Turn]:
    """Divide sequences into logical turns."""
    turns: list[_Turn] = []
    current: Optional[_Turn] = None
    last_hash = ""

    for seq in range(1, request_count + 1):
        req_path = session_dir / f"{seq:03d}_request.json"
        resp_path = session_dir / f"{seq:03d}_response.json"

        if not req_path.exists():
            continue

        with open(req_path, "r", encoding="utf-8") as f:
            request = json.load(f)

        if _is_auxiliary(request):
            continue

        h = _user_hash(request)

        # New turn if hash changed
        if h != last_hash or current is None:
            if current:
                turns.append(current)
            current = _Turn(number=len(turns) + 1)
            current.user_message = _extract_user_message(request)
            current.timestamp = _parse_ts(request.get("timestamp"))
            last_hash = h

        current.sequences.append(seq)

        # Process response
        if resp_path.exists():
            with open(resp_path, "r", encoding="utf-8") as f:
                response = json.load(f)
            current.assistant_response = _extract_response_text(response)
            current.tool_calls.extend(_extract_tool_calls_native(response))

    if current:
        turns.append(current)

    return turns


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


# ── FlowCraftNativeReader ──────────────────────────────────────────────────

class FlowCraftNativeReader(BaseReader):
    """Read FlowCraft native session logs."""

    source_type = "flowcraft"

    def __init__(self, logs_dir: Path | str | None = None):
        if logs_dir:
            self._logs_dir = Path(logs_dir)
        else:
            # Default: ./logs in current working directory
            self._logs_dir = Path("logs")

    @property
    def _sessions_dir(self) -> Path:
        return self._logs_dir / "sessions"

    def _load_index(self) -> list[dict]:
        index_path = self._logs_dir / "index.json"
        if not index_path.exists():
            return []
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sessions", [])

    def _load_metadata(self, session_id: str) -> Optional[dict]:
        path = self._sessions_dir / session_id / "metadata.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── BaseReader interface ────────────────────────────────────────────────

    def scan(self, path: Path | None = None) -> list[models.SessionInfo]:
        if path:
            self._logs_dir = Path(path)

        sessions = []
        for entry in self._load_index():
            sid = entry.get("session_id", "")
            meta = self._load_metadata(sid)
            if not meta:
                continue

            sessions.append(models.SessionInfo(
                session_id=sid,
                source_type=self.source_type,
                date=_parse_ts(entry.get("start_time")),
                model=entry.get("model", meta.get("model", "")),
                title="",  # FlowCraft native doesn't have titles
                turns_count=meta.get("request_count", 0),
            ))

        _dt_min = datetime.min.replace(tzinfo=timezone.utc)
        sessions.sort(key=lambda s: s.date or _dt_min, reverse=True)
        return sessions

    def get_overview(self, session_id: str) -> models.SessionOverview:
        meta = self._load_metadata(session_id)
        if not meta:
            raise ValueError(f"Session '{session_id}' not found")

        request_count = meta.get("request_count", 0)
        session_dir = self._sessions_dir / session_id
        turns = _assemble_turns(session_dir, request_count)

        info = models.SessionInfo(
            session_id=session_id,
            source_type=self.source_type,
            date=_parse_ts(meta.get("start_time")),
            model=meta.get("model", ""),
            title="",
            turns_count=len(turns),
        )

        turn_summaries = []
        for t in turns:
            preview = t.user_message[:120]
            if len(t.user_message) > 120:
                preview += "..."
            tool_names = sorted(set(tc.tool_name for tc in t.tool_calls))

            turn_summaries.append(models.TurnSummary(
                turn_number=t.number,
                user_message_preview=preview,
                tools_count=len(t.tool_calls),
                tool_names=tool_names,
                has_error=False,
                timestamp=t.timestamp,
            ))

        return models.SessionOverview(info=info, turns=turn_summaries)

    def get_turn(self, session_id: str, turn_number: int) -> models.TurnDetail:
        meta = self._load_metadata(session_id)
        if not meta:
            raise ValueError(f"Session '{session_id}' not found")

        session_dir = self._sessions_dir / session_id
        turns = _assemble_turns(session_dir, meta.get("request_count", 0))

        target = None
        for t in turns:
            if t.number == turn_number:
                target = t
                break

        if not target:
            raise IndexError(
                f"Turn {turn_number} out of range (session has {len(turns)} turns)"
            )

        # Extract files and commands from tool calls
        files = set()
        commands = []
        for tc in target.tool_calls:
            name_lower = tc.tool_name.lower()
            try:
                data = json.loads(tc.input_full)
            except (json.JSONDecodeError, TypeError):
                data = {}

            if "read" in name_lower or "write" in name_lower or "edit" in name_lower:
                p = data.get("path") or data.get("file_path") or data.get("filePath")
                if p:
                    files.add(p)
            if "bash" in name_lower or "command" in name_lower or "terminal" in name_lower:
                cmd = data.get("command") or data.get("cmd")
                if cmd:
                    commands.append(cmd)

        return models.TurnDetail(
            turn_number=turn_number,
            user_message=target.user_message,
            assistant_response=target.assistant_response,
            tool_calls=target.tool_calls,
            files_touched=sorted(files),
            commands_run=commands,
            timestamp=target.timestamp,
            model=meta.get("model", ""),
            mode="",
        )
