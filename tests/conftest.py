"""
Shared fixtures for RetroLens tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def sample_jsonl_path(fixtures_dir: Path) -> Path:
    """Path to the sample VS Code Copilot session JSONL."""
    return fixtures_dir / "sample_vscode_session.jsonl"


@pytest.fixture
def sample_claude_code_path(fixtures_dir: Path) -> Path:
    """Path to the sample Claude Code session JSONL."""
    return fixtures_dir / "sample_claude_code_session.jsonl"



