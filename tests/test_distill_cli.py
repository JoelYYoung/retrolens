"""
CLI integration tests using Click's CliRunner.

These test the full command pipeline: CLI parsing → reader → formatter → output.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from retrolens.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def sample_jsonl_dir(sample_jsonl_path: Path) -> str:
    return str(sample_jsonl_path.parent)


@pytest.fixture(autouse=True)
def _mock_config(sample_jsonl_path: Path):
    """Patch config.load to return vscode/fixtures for all tests.

    Individual tests that don't need config (version, help, show, from-yaml)
    won't be affected because those code paths don't call config functions.
    """
    cfg_data = {
        "path": str(sample_jsonl_path.parent),
        "source": "vscode",
    }
    with patch("retrolens.config.load", return_value=cfg_data):
        yield


# ── Version / Help ──────────────────────────────────────────────────────────

class TestBasicCLI:
    def test_version(self, runner: CliRunner):
        from retrolens import __version__

        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help(self, runner: CliRunner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "ls" in result.output
        assert "cfg" in result.output
        assert "read" in result.output

    def test_no_args_shows_help(self, runner: CliRunner):
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "RetroLens" in result.output


# ── ls ──────────────────────────────────────────────────────────────────────

class TestLs:
    def test_ls_text(self, runner: CliRunner):
        result = runner.invoke(main, ["ls"])
        assert result.exit_code == 0
        assert "test-session" in result.output
        assert "gpt-4o" in result.output

    def test_ls_json(self, runner: CliRunner):
        result = runner.invoke(main, ["ls", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1
        session = data[0]
        assert session["session_id"] == "test-session-001"
        assert session["source_type"] == "vscode"
        assert session["turns_count"] == 3

    def test_ls_limit(self, runner: CliRunner):
        result = runner.invoke(main, ["ls", "-n", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) <= 1

    def test_ls_no_config(self, runner: CliRunner):
        """ls should error when no config is set."""
        with patch("retrolens.config.load", return_value={}):
            result = runner.invoke(main, ["ls"])
            assert result.exit_code != 0
            assert "cfg set" in result.output or "No log path" in (result.output + (result.stderr or ""))


# ── read ────────────────────────────────────────────────────────────────────

class TestRead:
    def test_read_overview_text(self, runner: CliRunner):
        result = runner.invoke(main, ["read", "test-session-001"])
        assert result.exit_code == 0
        assert "test-session" in result.output
        assert "gpt-4o" in result.output
        # Should show turn summaries
        assert "#1" in result.output or "Turn" in result.output

    def test_read_overview_json(self, runner: CliRunner):
        result = runner.invoke(main, ["read", "test-session-001", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["info"]["session_id"] == "test-session-001"
        assert len(data["turns"]) == 3

    def test_read_prefix_match(self, runner: CliRunner):
        """Should resolve session ID by prefix."""
        result = runner.invoke(main, ["read", "test-ses", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["info"]["session_id"] == "test-session-001"

    def test_read_turn_detail(self, runner: CliRunner):
        result = runner.invoke(main, [
            "read", "test-session-001", "--turn", "1",
        ])
        assert result.exit_code == 0
        assert "login bug" in result.output.lower() or "auth.py" in result.output

    def test_read_turn_detail_json(self, runner: CliRunner):
        result = runner.invoke(main, [
            "read", "test-session-001", "--turn", "1", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["turn_number"] == 1
        assert len(data["tool_calls"]) == 3

    def test_read_turn_tool(self, runner: CliRunner):
        result = runner.invoke(main, [
            "read", "test-session-001", "--turn", "1", "--tool", "0", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["tool_name"] == "read_file"

    def test_read_turns_range(self, runner: CliRunner):
        result = runner.invoke(main, [
            "read", "test-session-001", "--turns", "1-2", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_read_diff(self, runner: CliRunner):
        result = runner.invoke(main, [
            "read", "test-session-001", "--diff", "1,3", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["turn_a"] == 1
        assert data["turn_b"] == 3

    def test_read_raw(self, runner: CliRunner):
        result = runner.invoke(main, [
            "read", "test-session-001", "--turn", "1", "--raw",
        ])
        assert result.exit_code == 0
        # Raw should be JSON
        data = json.loads(result.output)
        assert "message" in data

    def test_read_not_found(self, runner: CliRunner):
        result = runner.invoke(main, ["read", "zzz-nonexistent"])
        assert result.exit_code != 0



