"""
Log readers — parse different AI conversation log formats.

BaseReader: Abstract interface every reader must implement.
ReaderRegistry: Auto-discover sessions across all known sources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from ..models import (
    DiffResult,
    SessionInfo,
    SessionOverview,
    ToolCallDetail,
    TurnDetail,
    TurnSummary,
)


class BaseReader(ABC):
    """Abstract base for all log format readers."""

    source_type: str = "unknown"

    @abstractmethod
    def scan(self, path: Path | None = None) -> list[SessionInfo]:
        """Discover available sessions. Optionally narrow to a specific path."""
        ...

    @abstractmethod
    def get_overview(self, session_id: str) -> SessionOverview:
        """Return session metadata + one-line summary per turn."""
        ...

    @abstractmethod
    def get_turn(self, session_id: str, turn_number: int) -> TurnDetail:
        """Return full detail for a single turn."""
        ...

    def get_turns_range(
        self, session_id: str, start: int, end: int
    ) -> list[TurnSummary]:
        """Return summaries for turns [start, end] inclusive."""
        overview = self.get_overview(session_id)
        return [t for t in overview.turns if start <= t.turn_number <= end]

    def get_turn_tool(
        self, session_id: str, turn_number: int, tool_index: int
    ) -> ToolCallDetail:
        """Return full detail for a specific tool call within a turn."""
        turn = self.get_turn(session_id, turn_number)
        if tool_index < 0 or tool_index >= len(turn.tool_calls):
            raise IndexError(
                f"Tool index {tool_index} out of range "
                f"(turn {turn_number} has {len(turn.tool_calls)} tool calls)"
            )
        return turn.tool_calls[tool_index]

    def get_turn_raw(self, session_id: str, turn_number: int) -> dict[str, Any]:
        """Return the raw underlying data for a turn (format-specific)."""
        turn = self.get_turn(session_id, turn_number)
        return turn.model_dump()

    def diff_turns(
        self, session_id: str, a: int, b: int
    ) -> DiffResult:
        """Compare two turns and highlight differences."""
        turn_a = self.get_turn(session_id, a)
        turn_b = self.get_turn(session_id, b)

        tools_a = {tc.tool_name for tc in turn_a.tool_calls}
        tools_b = {tc.tool_name for tc in turn_b.tool_calls}
        files_a = set(turn_a.files_touched)
        files_b = set(turn_b.files_touched)

        summary_parts = []
        if turn_a.user_message[:80] != turn_b.user_message[:80]:
            summary_parts.append("Different user messages")
        if tools_a != tools_b:
            summary_parts.append(
                f"Tools: {len(tools_a)} in turn {a}, {len(tools_b)} in turn {b}"
            )
        if files_a != files_b:
            summary_parts.append(
                f"Files: {len(files_a)} in turn {a}, {len(files_b)} in turn {b}"
            )

        return DiffResult(
            turn_a=a,
            turn_b=b,
            summary="; ".join(summary_parts) if summary_parts else "Turns are similar",
            tools_only_in_a=sorted(tools_a - tools_b),
            tools_only_in_b=sorted(tools_b - tools_a),
            files_only_in_a=sorted(files_a - files_b),
            files_only_in_b=sorted(files_b - files_a),
        )

    # ── Session ID prefix matching ──────────────────────────────────────────

    def resolve_session_id(self, prefix: str, path: Path | None = None) -> str:
        """Resolve a session ID prefix to the full ID. Raises ValueError if ambiguous."""
        if prefix == "latest":
            sessions = self.scan(path)
            if not sessions:
                raise ValueError("No sessions found")
            # Sort by date descending, pick newest
            sessions.sort(key=_sort_key_date, reverse=True)
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


from datetime import datetime, timezone  # noqa: E402 — needed by resolve_session_id

_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _sort_key_date(s: SessionInfo) -> datetime:
    """Normalize session date for sorting — handles mixed tz-aware/naive."""
    d = s.date
    if d is None:
        return _DT_MIN
    if d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    return d


class ReaderRegistry:
    """Registry of all available readers + cross-source operations."""

    def __init__(self) -> None:
        self._readers: dict[str, BaseReader] = {}

    def register(self, reader: BaseReader) -> None:
        self._readers[reader.source_type] = reader

    def get(self, source_type: str) -> BaseReader:
        if source_type not in self._readers:
            raise KeyError(f"Unknown source type: {source_type}")
        return self._readers[source_type]

    @property
    def source_types(self) -> list[str]:
        return list(self._readers.keys())

    def auto_discover(self, path: Path | None = None) -> list[SessionInfo]:
        """Scan all registered readers and merge results."""
        all_sessions: list[SessionInfo] = []
        for reader in self._readers.values():
            try:
                all_sessions.extend(reader.scan(path))
            except Exception:
                continue  # skip broken readers
        # Sort by date descending
        all_sessions.sort(key=_sort_key_date, reverse=True)
        return all_sessions

    def resolve(self, session_id_prefix: str) -> tuple[BaseReader, str]:
        """Find which reader owns a session ID prefix, return (reader, full_id)."""
        for reader in self._readers.values():
            try:
                full_id = reader.resolve_session_id(session_id_prefix)
                return reader, full_id
            except ValueError:
                continue
        raise ValueError(f"No session matching '{session_id_prefix}' in any source")


def create_default_registry() -> ReaderRegistry:
    """Create a registry with all built-in readers."""
    registry = ReaderRegistry()

    # VS Code Copilot reader
    try:
        from .vscode_copilot import VSCodeCopilotReader
        registry.register(VSCodeCopilotReader())
    except Exception:
        pass

    # RetroLens native reader
    try:
        from .retrolens_native import RetroLensNativeReader
        registry.register(RetroLensNativeReader())
    except Exception:
        pass

    return registry
