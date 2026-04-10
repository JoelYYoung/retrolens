"""
Tests for RetroLens data models.
"""

from __future__ import annotations

from datetime import datetime, timezone

from retrolens.models import (
    DiffResult,
    SessionInfo,
    SessionOverview,
    ToolCallDetail,
    TurnDetail,
    TurnSummary,
)


# ── SessionInfo ─────────────────────────────────────────────────────────────

class TestSessionInfo:
    def test_minimal(self):
        info = SessionInfo(session_id="abc-123", source_type="vscode")
        assert info.session_id == "abc-123"
        assert info.source_type == "vscode"
        assert info.date is None
        assert info.model == ""
        assert info.turns_count == 0

    def test_full(self):
        dt = datetime(2025, 4, 10, 12, 0, tzinfo=timezone.utc)
        info = SessionInfo(
            session_id="abc-123",
            source_type="vscode",
            date=dt,
            model="gpt-4o",
            title="Test Session",
            turns_count=5,
            duration_seconds=120.0,
        )
        assert info.model == "gpt-4o"
        assert info.turns_count == 5
        assert info.duration_seconds == 120.0

    def test_json_roundtrip(self):
        info = SessionInfo(
            session_id="abc-123",
            source_type="vscode",
            date=datetime(2025, 4, 10, tzinfo=timezone.utc),
            model="gpt-4o",
        )
        data = info.model_dump(mode="json")
        restored = SessionInfo.model_validate(data)
        assert restored.session_id == info.session_id
        assert restored.model == info.model


# ── TurnSummary / SessionOverview ───────────────────────────────────────────

class TestSessionOverview:
    def test_overview_structure(self):
        turns = [
            TurnSummary(
                turn_number=1,
                user_message_preview="Fix the bug",
                tools_count=3,
                tool_names=["read_file", "replace_string_in_file"],
                has_error=False,
            ),
            TurnSummary(
                turn_number=2,
                user_message_preview="Add tests",
                tools_count=1,
                tool_names=["run_in_terminal"],
            ),
        ]
        overview = SessionOverview(
            info=SessionInfo(session_id="x", source_type="vscode", turns_count=2),
            turns=turns,
        )
        assert len(overview.turns) == 2
        assert overview.turns[0].tools_count == 3
        assert overview.turns[1].tool_names == ["run_in_terminal"]

    def test_json_roundtrip(self):
        overview = SessionOverview(
            info=SessionInfo(session_id="x", source_type="vscode"),
            turns=[TurnSummary(turn_number=1, user_message_preview="hi")],
        )
        data = overview.model_dump(mode="json")
        restored = SessionOverview.model_validate(data)
        assert len(restored.turns) == 1


# ── ToolCallDetail / TurnDetail ─────────────────────────────────────────────

class TestTurnDetail:
    def test_turn_with_tools(self):
        tools = [
            ToolCallDetail(
                index=0,
                tool_name="read_file",
                tool_id="read_file",
                input_preview="/src/auth.py",
                input_full='{"filePath": "/src/auth.py"}',
                output_preview="def login()...",
                output_full="def login(user, pw):\n    return False",
                success=True,
            ),
            ToolCallDetail(
                index=1,
                tool_name="replace_string_in_file",
                tool_id="replace_string_in_file",
                success=True,
            ),
        ]
        turn = TurnDetail(
            turn_number=1,
            user_message="Fix the login",
            assistant_response="I'll fix it",
            tool_calls=tools,
            files_touched=["/src/auth.py"],
            commands_run=["pytest"],
        )
        assert len(turn.tool_calls) == 2
        assert turn.tool_calls[0].tool_name == "read_file"
        assert "/src/auth.py" in turn.files_touched

    def test_empty_turn(self):
        turn = TurnDetail(turn_number=1)
        assert turn.user_message == ""
        assert turn.tool_calls == []
        assert turn.files_touched == []


# ── DiffResult ──────────────────────────────────────────────────────────────

class TestDiffResult:
    def test_diff(self):
        diff = DiffResult(
            turn_a=1,
            turn_b=3,
            summary="Different user messages",
            tools_only_in_a=["read_file"],
            tools_only_in_b=["semantic_search"],
        )
        assert diff.turn_a == 1
        assert len(diff.tools_only_in_a) == 1
