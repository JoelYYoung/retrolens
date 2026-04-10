"""Tests for retrolens.config — persistent working state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from retrolens import config


# ── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg_dir(tmp_path: Path) -> Path:
    """Return a temporary base directory for config tests."""
    return tmp_path


# ── load / save ─────────────────────────────────────────────────────────────

class TestLoadSave:
    def test_load_returns_empty_when_no_config(self, cfg_dir: Path):
        assert config.load(cfg_dir) == {}

    def test_save_creates_directory(self, cfg_dir: Path):
        path = config.save({"path": "/tmp/logs"}, cfg_dir)
        assert path.exists()
        assert path.parent.name == ".retrolens"

    def test_roundtrip(self, cfg_dir: Path):
        config.save({"path": "/tmp/logs", "source": "vscode"}, cfg_dir)
        data = config.load(cfg_dir)
        assert data["path"] == "/tmp/logs"
        assert data["source"] == "vscode"

    def test_load_ignores_corrupt_json(self, cfg_dir: Path):
        path = cfg_dir / ".retrolens" / "config.json"
        path.parent.mkdir(parents=True)
        path.write_text("not json!!!", encoding="utf-8")
        assert config.load(cfg_dir) == {}


# ── get_path / get_source ───────────────────────────────────────────────────

class TestGetters:
    def test_get_path_none_when_no_config(self, cfg_dir: Path):
        assert config.get_path(cfg_dir) is None

    def test_get_source_none_when_no_config(self, cfg_dir: Path):
        assert config.get_source(cfg_dir) is None

    def test_get_path_returns_value(self, cfg_dir: Path):
        config.save({"path": "/tmp/logs"}, cfg_dir)
        assert config.get_path(cfg_dir) == "/tmp/logs"

    def test_get_source_returns_value(self, cfg_dir: Path):
        config.save({"source": "claude_code"}, cfg_dir)
        assert config.get_source(cfg_dir) == "claude_code"


# ── set_values ──────────────────────────────────────────────────────────────

class TestSetValues:
    def test_set_path(self, cfg_dir: Path):
        result = config.set_values(path="/tmp/logs", base=cfg_dir)
        assert "/tmp/logs" in result["path"]  # resolved to absolute
        assert config.get_path(cfg_dir) is not None

    def test_set_source(self, cfg_dir: Path):
        result = config.set_values(source="vscode", base=cfg_dir)
        assert result["source"] == "vscode"

    def test_set_preserves_existing(self, cfg_dir: Path):
        config.set_values(path="/tmp/a", base=cfg_dir)
        config.set_values(source="vscode", base=cfg_dir)
        data = config.load(cfg_dir)
        assert "path" in data
        assert data["source"] == "vscode"

    def test_set_resolves_path_to_absolute(self, cfg_dir: Path):
        config.set_values(path="relative/dir", base=cfg_dir)
        stored = config.get_path(cfg_dir)
        assert Path(stored).is_absolute()


# ── clear ───────────────────────────────────────────────────────────────────

class TestClear:
    def test_clear_removes_config(self, cfg_dir: Path):
        config.set_values(path="/tmp/logs", base=cfg_dir)
        config.clear(cfg_dir)
        assert config.load(cfg_dir) == {}

    def test_clear_noop_when_no_config(self, cfg_dir: Path):
        # Should not raise
        config.clear(cfg_dir)


# ── status ──────────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_when_no_config(self, cfg_dir: Path):
        st = config.status(cfg_dir)
        assert st["exists"] is False
        assert "config_file" in st

    def test_status_when_config_set(self, cfg_dir: Path):
        config.set_values(path="/tmp/logs", source="vscode", base=cfg_dir)
        st = config.status(cfg_dir)
        assert st["exists"] is True
        assert st["source"] == "vscode"
        assert "/tmp/logs" in st["path"]


# ── CLI integration (via click testing) ─────────────────────────────────────

class TestCLI:
    """Test cfg subcommands via click.testing."""

    @pytest.fixture(autouse=True)
    def _setup(self, cfg_dir: Path, monkeypatch: pytest.MonkeyPatch):
        """Make config use the temp directory."""
        monkeypatch.chdir(cfg_dir)

    def _invoke(self, args: list[str]):
        from click.testing import CliRunner
        from retrolens.cli import main
        runner = CliRunner()
        return runner.invoke(main, args, catch_exceptions=False)

    def test_cfg_show_no_config(self):
        result = self._invoke(["cfg", "show"])
        assert result.exit_code == 0
        assert "No config set" in result.output

    def test_cfg_set_path(self, cfg_dir: Path):
        result = self._invoke(["cfg", "set", "--path", str(cfg_dir)])
        assert result.exit_code == 0
        assert "Config updated" in result.output

    def test_cfg_set_source(self):
        result = self._invoke(["cfg", "set", "--source", "vscode"])
        assert result.exit_code == 0
        assert "vscode" in result.output

    def test_cfg_show_after_set(self, cfg_dir: Path):
        self._invoke(["cfg", "set", "--path", str(cfg_dir)])
        result = self._invoke(["cfg", "show"])
        assert result.exit_code == 0
        assert str(cfg_dir) in result.output

    def test_cfg_show_json(self, cfg_dir: Path):
        self._invoke(["cfg", "set", "--path", str(cfg_dir), "--source", "vscode"])
        result = self._invoke(["cfg", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["source"] == "vscode"
        assert data["exists"] is True

    def test_cfg_clear(self, cfg_dir: Path):
        self._invoke(["cfg", "set", "--path", str(cfg_dir)])
        result = self._invoke(["cfg", "clear"])
        assert result.exit_code == 0
        assert "cleared" in result.output.lower()
        # Verify config is gone
        result = self._invoke(["cfg", "show"])
        assert "No config set" in result.output

    def test_cfg_set_nothing_fails(self):
        result = self._invoke(["cfg", "set"])
        assert result.exit_code != 0

    def test_cfg_default_shows_status(self, cfg_dir: Path):
        """Running `retrolens cfg` without subcommand shows status."""
        self._invoke(["cfg", "set", "--path", str(cfg_dir)])
        result = self._invoke(["cfg"])
        assert result.exit_code == 0
        assert str(cfg_dir) in result.output
