"""
Auto-detect log format by sampling file content.

Provides a `detect_format()` function that reads the first few lines of a
JSONL file (or inspects a directory structure) and returns the best-matching
source_type string, or None if no built-in reader matches.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def detect_format(path: Path) -> Optional[str]:
    """Detect the log format at the given path.

    Args:
        path: A file (.jsonl) or directory to inspect.

    Returns:
        A source_type string ('vscode', 'claude_code') or None.
    """
    path = Path(path)

    if path.is_dir():
        return _detect_dir(path)
    elif path.is_file():
        return _detect_file(path)
    return None


def detect_format_for_dir(path: Path) -> Optional[str]:
    """Detect the log format for a directory by sampling its contents.

    Tries directory-level detection first, then samples individual files.

    Returns:
        A source_type string or None.
    """
    path = Path(path)
    if not path.is_dir():
        return None

    result = _detect_dir(path)
    if result:
        return result

    # Sample first .jsonl file
    jsonl_files = sorted(path.glob("*.jsonl"))
    if not jsonl_files:
        # Also check one level deeper
        jsonl_files = sorted(path.rglob("*.jsonl"))[:1]
    if jsonl_files:
        return _detect_file(jsonl_files[0])

    return None


def _detect_dir(path: Path) -> Optional[str]:
    """Detect format from directory structure."""
    return None


def _detect_file(path: Path) -> Optional[str]:
    """Detect format by sampling the first few lines of a file."""
    if path.suffix != ".jsonl":
        return None

    try:
        lines = _read_sample_lines(path, max_lines=5)
    except Exception:
        return None

    if not lines:
        return None

    # Try each detector
    for detector, source_type in [
        (_is_vscode_format, "vscode"),
        (_is_claude_code_format, "claude_code"),
    ]:
        if detector(lines):
            return source_type

    return None


def _read_sample_lines(path: Path, max_lines: int = 5) -> list[dict]:
    """Read and parse the first N lines of a JSONL file."""
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def _is_vscode_format(lines: list[dict]) -> bool:
    """Check if lines match VS Code Copilot Chat format.

    Indicators:
    - First line has {"kind": 0, "v": {"sessionId": ...}}
    - Subsequent lines have "kind" and "k" or "v" fields
    """
    if not lines:
        return False

    first = lines[0]
    if "kind" in first and first.get("kind") == 0:
        v = first.get("v", {})
        if isinstance(v, dict) and ("sessionId" in v or "inputState" in v):
            return True

    # Fallback: check if multiple lines have "kind" field
    kind_count = sum(1 for l in lines if "kind" in l)
    return kind_count >= len(lines) * 0.5 and len(lines) >= 2


def _is_claude_code_format(lines: list[dict]) -> bool:
    """Check if lines match Claude Code format.

    Indicators:
    - Lines have "type" field with values like "user", "assistant", "system"
    - Lines have "parentUuid" or "sessionId" field
    """
    if not lines:
        return False

    type_values = {"user", "assistant", "system", "file-history-snapshot"}
    matches = 0
    for line in lines:
        if "type" in line and line["type"] in type_values:
            matches += 1
        elif "parentUuid" in line or ("sessionId" in line and "type" in line):
            matches += 1

    return matches >= len(lines) * 0.5 and len(lines) >= 1


def describe_detection(path: Path) -> dict:
    """Return a detailed detection result for display.

    Returns:
        dict with keys: path, format, sample_files, confidence, details
    """
    path = Path(path)
    result = {
        "path": str(path),
        "format": None,
        "sample_files": 0,
        "details": "",
    }

    if not path.exists():
        result["details"] = "Path does not exist"
        return result

    if path.is_file():
        fmt = _detect_file(path)
        result["format"] = fmt
        result["sample_files"] = 1
        result["details"] = f"Single file: {path.name}"
        return result

    # Directory
    fmt = _detect_dir(path)
    if fmt:
        result["format"] = fmt
        if fmt == "retrolens":
            try:
                with open(path / "index.json") as f:
                    idx = json.load(f)
                result["sample_files"] = len(idx.get("sessions", []))
            except Exception:
                result["sample_files"] = sum(1 for _ in (path / "sessions").iterdir()) if (path / "sessions").is_dir() else 0
        result["details"] = f"Directory structure matches {fmt}"
        return result

    # Try sampling files
    jsonl_files = sorted(path.glob("*.jsonl"))
    result["sample_files"] = len(jsonl_files)

    if jsonl_files:
        fmt = _detect_file(jsonl_files[0])
        result["format"] = fmt
        result["details"] = f"Sampled {jsonl_files[0].name} → {fmt or 'unknown'}"
    else:
        # Check subdirectories
        sub_jsonl = list(path.rglob("*.jsonl"))[:1]
        if sub_jsonl:
            fmt = _detect_file(sub_jsonl[0])
            result["format"] = fmt
            result["sample_files"] = len(list(path.rglob("*.jsonl")))
            result["details"] = f"Found .jsonl in subdirectory → {fmt or 'unknown'}"
        else:
            result["details"] = "No .jsonl files found"

    return result
