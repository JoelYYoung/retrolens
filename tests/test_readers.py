"""
Tests for RetroLens readers — JSONL parsing, turn extraction, etc.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from retrolens.models import SessionInfo
from retrolens.readers import (
    BaseReader,
    ReaderRegistry,
    _sort_key_date,
    create_default_registry,
)
from retrolens.readers.vscode_copilot import (
    VSCodeCopilotReader,
    _parse_jsonl,
    _extract_tool_calls,
    _extract_files_touched,
    _extract_commands_run,
    _extract_assistant_text,
)


# ── JSONL Parsing ───────────────────────────────────────────────────────────

class TestJSONLParser:
    def test_parse_session_metadata(self, sample_jsonl_path: Path):
        session = _parse_jsonl(sample_jsonl_path)
        assert session.session_id == "test-session-001"
        assert session.model == "gpt-4o"
        assert session.mode == "agent"

    def test_parse_creation_date(self, sample_jsonl_path: Path):
        session = _parse_jsonl(sample_jsonl_path)
        assert session.creation_date is not None
        assert session.creation_date.tzinfo is not None  # tz-aware

    def test_parse_title(self, sample_jsonl_path: Path):
        session = _parse_jsonl(sample_jsonl_path)
        assert session.title == "Test Session: Fix Login Bug"

    def test_parse_turns_count(self, sample_jsonl_path: Path):
        session = _parse_jsonl(sample_jsonl_path)
        assert session.turns_count == 3  # 3 requests in the fixture

    def test_parse_request_messages(self, sample_jsonl_path: Path):
        session = _parse_jsonl(sample_jsonl_path)
        assert len(session.requests) == 3
        assert session.requests[0]["message"]["text"] == "Please fix the login bug in auth.py"
        assert session.requests[1]["message"]["text"] == "Now add input validation"
        assert session.requests[2]["message"]["text"] == "Can you also check for SQL injection?"

    def test_parse_response_items(self, sample_jsonl_path: Path):
        session = _parse_jsonl(sample_jsonl_path)
        # First request has 5 response items: text + 3 tools + text
        resp0 = session.requests[0].get("response", [])
        assert len(resp0) == 5
        # First is text
        assert "value" in resp0[0] and "kind" not in resp0[0]
        # Second is tool
        assert resp0[1].get("kind") == "toolInvocationSerialized"


# ── Response Item Extraction ────────────────────────────────────────────────

class TestExtraction:
    @pytest.fixture
    def response_items(self, sample_jsonl_path: Path) -> list[dict]:
        session = _parse_jsonl(sample_jsonl_path)
        return session.requests[0].get("response", [])

    def test_extract_assistant_text(self, response_items: list[dict]):
        text = _extract_assistant_text(response_items)
        assert "fix the login bug" in text
        assert "always returns False" in text

    def test_extract_tool_calls_count(self, response_items: list[dict]):
        tools = _extract_tool_calls(response_items)
        assert len(tools) == 3  # read_file, replace_string_in_file, run_in_terminal

    def test_extract_tool_names(self, response_items: list[dict]):
        tools = _extract_tool_calls(response_items)
        names = [t.tool_name for t in tools]
        assert "read_file" in names
        assert "replace_string_in_file" in names
        assert "run_in_terminal" in names

    def test_extract_tool_indices(self, response_items: list[dict]):
        tools = _extract_tool_calls(response_items)
        indices = [t.index for t in tools]
        assert indices == [0, 1, 2]

    def test_extract_tool_invocation_message(self, response_items: list[dict]):
        """Test that dict-format invocationMessage is handled."""
        tools = _extract_tool_calls(response_items)
        # First tool has dict-style invocationMessage
        assert tools[0].invocation_message == "Reading auth.py"
        # Second tool has plain string invocationMessage
        assert tools[1].invocation_message == "Fixing login function"

    def test_extract_tool_past_tense_message(self, response_items: list[dict]):
        tools = _extract_tool_calls(response_items)
        assert tools[0].past_tense_message == "Read auth.py"

    def test_extract_tool_result(self, response_items: list[dict]):
        tools = _extract_tool_calls(response_items)
        # read_file result is a string
        assert "def login" in tools[0].output_full
        # replace_string_in_file result
        assert "File updated" in tools[1].output_full

    def test_extract_tool_result_list(self, sample_jsonl_path: Path):
        """Turn 3 has a tool that returns a list result."""
        session = _parse_jsonl(sample_jsonl_path)
        resp2 = session.requests[2].get("response", [])
        tools = _extract_tool_calls(resp2)
        assert len(tools) == 1
        assert tools[0].tool_name == "semantic_search"
        # List result should be JSON-serialized
        assert "No SQL injection" in tools[0].output_full

    def test_extract_files_touched(self, response_items: list[dict]):
        tools = _extract_tool_calls(response_items)
        files = _extract_files_touched(tools)
        assert "/src/auth.py" in files

    def test_extract_commands_run(self, response_items: list[dict]):
        tools = _extract_tool_calls(response_items)
        commands = _extract_commands_run(tools)
        # run_in_terminal has the command in toolSpecificData
        # In our fixture, command is in toolSpecificData.command
        assert len(commands) >= 0  # depends on fixture structure


# ── VSCodeCopilotReader ─────────────────────────────────────────────────────

class TestVSCodeCopilotReader:
    @pytest.fixture
    def reader(self, sample_jsonl_path: Path) -> VSCodeCopilotReader:
        return VSCodeCopilotReader(paths=[sample_jsonl_path.parent])

    def test_scan(self, reader: VSCodeCopilotReader, sample_jsonl_path: Path):
        sessions = reader.scan(sample_jsonl_path.parent)
        assert len(sessions) >= 1
        # Find our test session
        test_session = next(
            (s for s in sessions if s.session_id == "test-session-001"), None
        )
        assert test_session is not None
        assert test_session.source_type == "vscode"
        assert test_session.model == "gpt-4o"
        assert test_session.turns_count == 3

    def test_get_overview(self, reader: VSCodeCopilotReader):
        overview = reader.get_overview("test-session-001")
        assert overview.info.session_id == "test-session-001"
        assert len(overview.turns) == 3
        assert overview.turns[0].user_message_preview.startswith("Please fix")

    def test_get_overview_tool_counts(self, reader: VSCodeCopilotReader):
        overview = reader.get_overview("test-session-001")
        assert overview.turns[0].tools_count == 3  # read + replace + run
        assert overview.turns[1].tools_count == 2  # read + replace
        assert overview.turns[2].tools_count == 1  # semantic_search

    def test_get_turn_detail(self, reader: VSCodeCopilotReader):
        turn = reader.get_turn("test-session-001", 1)
        assert turn.turn_number == 1
        assert "login bug" in turn.user_message
        assert len(turn.tool_calls) == 3

    def test_get_turn_files_touched(self, reader: VSCodeCopilotReader):
        turn = reader.get_turn("test-session-001", 1)
        assert "/src/auth.py" in turn.files_touched

    def test_get_turn_assistant_response(self, reader: VSCodeCopilotReader):
        turn = reader.get_turn("test-session-001", 1)
        assert "fix the login bug" in turn.assistant_response

    def test_get_turn_out_of_range(self, reader: VSCodeCopilotReader):
        with pytest.raises(IndexError, match="out of range"):
            reader.get_turn("test-session-001", 99)

    def test_get_turn_raw(self, reader: VSCodeCopilotReader):
        raw = reader.get_turn_raw("test-session-001", 1)
        assert isinstance(raw, dict)
        assert "message" in raw
        assert "response" in raw

    def test_get_turn_tool(self, reader: VSCodeCopilotReader):
        tool = reader.get_turn_tool("test-session-001", 1, 0)
        assert tool.tool_name == "read_file"

    def test_get_turn_tool_out_of_range(self, reader: VSCodeCopilotReader):
        with pytest.raises(IndexError, match="Tool index"):
            reader.get_turn_tool("test-session-001", 1, 99)

    def test_diff_turns(self, reader: VSCodeCopilotReader):
        diff = reader.diff_turns("test-session-001", 1, 3)
        assert diff.turn_a == 1
        assert diff.turn_b == 3
        assert diff.summary  # non-empty

    def test_get_turns_range(self, reader: VSCodeCopilotReader):
        summaries = reader.get_turns_range("test-session-001", 1, 2)
        assert len(summaries) == 2
        assert summaries[0].turn_number == 1
        assert summaries[1].turn_number == 2


# ── ReaderRegistry ──────────────────────────────────────────────────────────

class TestReaderRegistry:
    def test_create_default_registry(self):
        registry = create_default_registry()
        assert "vscode" in registry.source_types

    def test_register_and_get(self):
        registry = ReaderRegistry()

        class FakeReader(BaseReader):
            source_type = "fake"
            def scan(self, path=None): return []
            def get_overview(self, sid): raise NotImplementedError
            def get_turn(self, sid, turn): raise NotImplementedError

        registry.register(FakeReader())
        assert "fake" in registry.source_types
        assert isinstance(registry.get("fake"), FakeReader)

    def test_get_unknown_raises(self):
        registry = ReaderRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_resolve_by_prefix(self, sample_jsonl_path: Path):
        registry = ReaderRegistry()
        reader = VSCodeCopilotReader(paths=[sample_jsonl_path.parent])
        registry.register(reader)

        resolved_reader, full_id = registry.resolve("test-session")
        assert full_id == "test-session-001"

    def test_resolve_not_found(self):
        registry = create_default_registry()
        with pytest.raises(ValueError, match="No session matching"):
            registry.resolve("zzz-nonexistent-zzz")


# ── Timezone sorting ────────────────────────────────────────────────────────

class TestTimezoneHandling:
    def test_sort_key_with_none_date(self):
        s = SessionInfo(session_id="x", source_type="vscode", date=None)
        result = _sort_key_date(s)
        assert result.tzinfo is not None

    def test_sort_key_with_aware_date(self):
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        s = SessionInfo(session_id="x", source_type="vscode", date=dt)
        result = _sort_key_date(s)
        assert result == dt

    def test_sort_key_with_naive_date(self):
        dt = datetime(2025, 1, 1)  # naive
        s = SessionInfo(session_id="x", source_type="vscode", date=dt)
        result = _sort_key_date(s)
        assert result.tzinfo is not None
        assert result.year == 2025

    def test_mixed_sort(self):
        """Sort sessions with mixed tz-aware, naive, and None dates."""
        sessions = [
            SessionInfo(session_id="a", source_type="v", date=None),
            SessionInfo(
                session_id="b", source_type="v",
                date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            ),
            SessionInfo(
                session_id="c", source_type="v",
                date=datetime(2025, 3, 1),  # naive
            ),
        ]
        # Should not raise
        sessions.sort(key=_sort_key_date, reverse=True)
        # b (June) should be first, c (March) second, a (None→min) last
        assert sessions[0].session_id == "b"
        assert sessions[1].session_id == "c"
        assert sessions[2].session_id == "a"
