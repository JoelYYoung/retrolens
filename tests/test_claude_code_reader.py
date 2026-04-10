"""
Tests for Claude Code native log reader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from retrolens.readers.claude_code import (
    ClaudeCodeReader,
    _parse_jsonl,
    _extract_tool_calls,
    _extract_assistant_text,
    _extract_files_touched,
    _extract_commands_run,
    _decode_project_path,
    _encode_project_path,
)


# ── Path encoding/decoding ──────────────────────────────────────────────────

class TestPathEncoding:
    def test_decode_project_path(self):
        assert _decode_project_path("-Users-joel-Projects-myapp") == "/Users/joel/Projects/myapp"

    def test_decode_project_path_no_leading_slash(self):
        result = _decode_project_path("home-user-app")
        assert result == "home/user/app"

    def test_encode_project_path(self):
        assert _encode_project_path("/Users/joel/Projects/myapp") == "-Users-joel-Projects-myapp"

    def test_roundtrip(self):
        original = "/Users/joel/Projects/myapp"
        assert _decode_project_path(_encode_project_path(original)) == original


# ── JSONL Parsing ───────────────────────────────────────────────────────────

class TestClaudeCodeJSONLParser:
    def test_parse_session_id(self, sample_claude_code_path: Path):
        session = _parse_jsonl(sample_claude_code_path)
        assert session.session_id == "cc-test-session-001"

    def test_parse_model(self, sample_claude_code_path: Path):
        session = _parse_jsonl(sample_claude_code_path)
        assert session.model == "anthropic/claude-sonnet-4"

    def test_parse_version(self, sample_claude_code_path: Path):
        session = _parse_jsonl(sample_claude_code_path)
        assert session.version == "2.1.37"

    def test_parse_cwd(self, sample_claude_code_path: Path):
        session = _parse_jsonl(sample_claude_code_path)
        assert session.cwd == "/Users/test/Projects/myapp"

    def test_parse_first_timestamp(self, sample_claude_code_path: Path):
        session = _parse_jsonl(sample_claude_code_path)
        assert session.first_timestamp is not None
        assert session.first_timestamp.tzinfo is not None

    def test_parse_turns_count(self, sample_claude_code_path: Path):
        session = _parse_jsonl(sample_claude_code_path)
        assert session.turns_count == 2  # two user messages

    def test_parse_turn_user_messages(self, sample_claude_code_path: Path):
        session = _parse_jsonl(sample_claude_code_path)
        assert session.turns[0].user_message == "Fix the authentication bug in login.py"
        assert session.turns[1].user_message == "Now add rate limiting to the login endpoint"


# ── Tool call extraction ────────────────────────────────────────────────────

class TestClaudeCodeToolExtraction:
    @pytest.fixture
    def session(self, sample_claude_code_path: Path):
        return _parse_jsonl(sample_claude_code_path)

    def test_turn1_tool_count(self, session):
        # Turn 1: Read + Edit + Bash = 3 tool calls
        assert len(session.turns[0].tool_calls) == 3

    def test_turn1_tool_names(self, session):
        names = [tc.tool_name for tc in session.turns[0].tool_calls]
        assert "Read" in names
        assert "Edit" in names
        assert "Bash" in names

    def test_turn1_tool_indices(self, session):
        indices = [tc.index for tc in session.turns[0].tool_calls]
        assert indices == [0, 1, 2]

    def test_turn1_tool_results_populated(self, session):
        """Tool results from the next user message should be back-filled."""
        read_tool = session.turns[0].tool_calls[0]
        assert "def login" in read_tool.output_full

        edit_tool = session.turns[0].tool_calls[1]
        assert "File updated" in edit_tool.output_full

        bash_tool = session.turns[0].tool_calls[2]
        assert "2 passed" in bash_tool.output_full

    def test_turn2_has_error(self, session):
        # Turn 2: Read (error) + Bash
        error_tool = None
        for tc in session.turns[1].tool_calls:
            if tc.tool_name == "Read":
                error_tool = tc
                break
        assert error_tool is not None
        assert not error_tool.success
        assert "[ERROR]" in error_tool.output_full

    def test_turn2_tool_count(self, session):
        # Turn 2: Read (error) + Bash = min 2 tool calls
        assert len(session.turns[1].tool_calls) >= 2

    def test_extract_assistant_text(self, session):
        assert "fix the authentication bug" in session.turns[0].assistant_response.lower()

    def test_extract_files_touched(self, session):
        files = _extract_files_touched(session.turns[0].tool_calls)
        assert "/Users/test/Projects/myapp/login.py" in files

    def test_extract_commands_run(self, session):
        commands = _extract_commands_run(session.turns[0].tool_calls)
        assert any("pytest" in cmd for cmd in commands)


# ── ClaudeCodeReader interface ──────────────────────────────────────────────

class TestClaudeCodeReader:
    @pytest.fixture
    def reader(self, sample_claude_code_path: Path) -> ClaudeCodeReader:
        return ClaudeCodeReader(paths=[sample_claude_code_path.parent])

    def test_scan(self, reader: ClaudeCodeReader, sample_claude_code_path: Path):
        sessions = reader.scan(sample_claude_code_path.parent)
        assert len(sessions) >= 1
        cc_session = next(
            (s for s in sessions if s.session_id == "cc-test-session-001"), None
        )
        assert cc_session is not None
        assert cc_session.source_type == "claude_code"
        assert cc_session.model == "anthropic/claude-sonnet-4"
        assert cc_session.turns_count == 2

    def test_scan_title_from_first_message(self, reader: ClaudeCodeReader, sample_claude_code_path: Path):
        sessions = reader.scan(sample_claude_code_path.parent)
        cc_session = next(
            (s for s in sessions if s.session_id == "cc-test-session-001"), None
        )
        assert cc_session is not None
        assert "authentication bug" in cc_session.title.lower()

    def test_get_overview(self, reader: ClaudeCodeReader):
        overview = reader.get_overview("cc-test-session-001")
        assert overview.info.session_id == "cc-test-session-001"
        assert len(overview.turns) == 2
        assert overview.turns[0].tools_count == 3

    def test_get_overview_turn_has_error(self, reader: ClaudeCodeReader):
        overview = reader.get_overview("cc-test-session-001")
        # Turn 2 has an error (file not found)
        assert overview.turns[1].has_error is True

    def test_get_turn_detail(self, reader: ClaudeCodeReader):
        turn = reader.get_turn("cc-test-session-001", 1)
        assert turn.turn_number == 1
        assert "authentication bug" in turn.user_message.lower()
        assert len(turn.tool_calls) == 3

    def test_get_turn_files_touched(self, reader: ClaudeCodeReader):
        turn = reader.get_turn("cc-test-session-001", 1)
        assert "/Users/test/Projects/myapp/login.py" in turn.files_touched

    def test_get_turn_commands_run(self, reader: ClaudeCodeReader):
        turn = reader.get_turn("cc-test-session-001", 1)
        assert any("pytest" in cmd for cmd in turn.commands_run)

    def test_get_turn_out_of_range(self, reader: ClaudeCodeReader):
        with pytest.raises(IndexError, match="out of range"):
            reader.get_turn("cc-test-session-001", 99)

    def test_get_turn_raw(self, reader: ClaudeCodeReader):
        raw = reader.get_turn_raw("cc-test-session-001", 1)
        assert isinstance(raw, dict)
        assert "user_message" in raw

    def test_get_turn_tool(self, reader: ClaudeCodeReader):
        tool = reader.get_turn_tool("cc-test-session-001", 1, 0)
        assert tool.tool_name == "Read"

    def test_get_turn_tool_out_of_range(self, reader: ClaudeCodeReader):
        with pytest.raises(IndexError, match="Tool index"):
            reader.get_turn_tool("cc-test-session-001", 1, 99)

    def test_diff_turns(self, reader: ClaudeCodeReader):
        diff = reader.diff_turns("cc-test-session-001", 1, 2)
        assert diff.turn_a == 1
        assert diff.turn_b == 2
        assert diff.summary  # non-empty

    def test_resolve_session_id_prefix(self, reader: ClaudeCodeReader, sample_claude_code_path: Path):
        full_id = reader.resolve_session_id("cc-test", sample_claude_code_path.parent)
        assert full_id == "cc-test-session-001"

    def test_resolve_session_id_not_found(self, reader: ClaudeCodeReader, sample_claude_code_path: Path):
        with pytest.raises(ValueError, match="No session matching"):
            reader.resolve_session_id("zzz-nonexistent", sample_claude_code_path.parent)


# ── Registry integration ────────────────────────────────────────────────────

class TestClaudeCodeRegistryIntegration:
    def test_registry_includes_claude_code(self):
        from retrolens.readers import create_default_registry
        registry = create_default_registry()
        assert "claude_code" in registry.source_types

    def test_registry_resolve_claude_code_session(self, sample_claude_code_path: Path):
        from retrolens.readers import ReaderRegistry
        registry = ReaderRegistry()
        reader = ClaudeCodeReader(paths=[sample_claude_code_path.parent])
        registry.register(reader)
        resolved_reader, full_id = registry.resolve("cc-test")
        assert full_id == "cc-test-session-001"
        assert resolved_reader.source_type == "claude_code"
