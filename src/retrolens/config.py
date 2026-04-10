"""
Persistent configuration for RetroLens working state.

Stores the current working log path, detected/overridden source type,
and optional custom reader path. Agents `retrolens cfg set --path <dir>`
once, then `ls`, `read`, `extract`, `reflect` all use it automatically.

Config is stored at `.retrolens/config.json` in the current working directory.

Config schema:
  {
    "path": "/absolute/path/to/log/directory",
    "source": "vscode",           # detected or overridden source type
    "reader": "/path/to/custom_reader.py"  # optional custom reader
  }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


_CONFIG_DIR = ".retrolens"
_CONFIG_FILE = "config.json"


def _config_path(base: Path | None = None) -> Path:
    """Return the path to the config file."""
    root = base or Path.cwd()
    return root / _CONFIG_DIR / _CONFIG_FILE


def load(base: Path | None = None) -> dict:
    """Load config from disk. Returns empty dict if no config exists."""
    path = _config_path(base)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict, base: Path | None = None) -> Path:
    """Save config to disk. Creates .retrolens/ directory if needed."""
    path = _config_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def get_path(base: Path | None = None) -> Optional[str]:
    """Return the configured log path, or None."""
    return load(base).get("path")


def get_source(base: Path | None = None) -> Optional[str]:
    """Return the configured source type, or None."""
    return load(base).get("source")


def get_reader(base: Path | None = None) -> Optional[str]:
    """Return the configured custom reader path, or None."""
    return load(base).get("reader")


def set_values(
    *,
    path: Optional[str] = None,
    source: Optional[str] = None,
    reader: Optional[str] = None,
    base: Path | None = None,
) -> dict:
    """Set one or more config values. Returns the updated config."""
    data = load(base)
    if path is not None:
        # Resolve to absolute path for clarity
        resolved = str(Path(path).resolve())
        data["path"] = resolved
    if source is not None:
        data["source"] = source
    if reader is not None:
        resolved_reader = str(Path(reader).resolve())
        data["reader"] = resolved_reader
    save(data, base)
    return data


def clear(base: Path | None = None) -> None:
    """Remove all config values."""
    path = _config_path(base)
    if path.exists():
        path.unlink()


def status(base: Path | None = None) -> dict:
    """Return current config with metadata for display."""
    data = load(base)
    path = _config_path(base)
    return {
        "config_file": str(path),
        "exists": path.exists(),
        **data,
    }
