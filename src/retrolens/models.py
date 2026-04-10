"""
Data models for RetroLens CLI.

Layered output models — each level returns just enough info for an agent
to decide whether to drill deeper.

    SessionInfo  →  SessionOverview  →  TurnDetail  →  ToolCallDetail
      (scan)         (read <id>)      (--turn N)     (--tool N)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# ── Scan level ──────────────────────────────────────────────────────────────

class SessionInfo(BaseModel):
    """One row in the session list (scan output)."""

    session_id: str
    source_type: str  # "vscode" | "claude_code"
    date: Optional[datetime] = None
    model: str = ""
    title: str = ""
    turns_count: int = 0
    duration_seconds: Optional[float] = None


# ── Overview level ──────────────────────────────────────────────────────────

class TurnSummary(BaseModel):
    """One-line summary per turn (shown in session overview)."""

    turn_number: int
    user_message_preview: str = ""  # first ~120 chars
    tools_count: int = 0
    tool_names: list[str] = Field(default_factory=list)
    has_error: bool = False
    timestamp: Optional[datetime] = None


class SessionOverview(BaseModel):
    """Session overview: metadata + turn summaries."""

    info: SessionInfo
    turns: list[TurnSummary] = Field(default_factory=list)


# ── Turn detail level ───────────────────────────────────────────────────────

class ToolCallDetail(BaseModel):
    """Full detail of a single tool invocation."""

    index: int = 0
    tool_name: str = ""
    tool_id: str = ""
    input_preview: str = ""   # truncated to ~500 chars in overview
    input_full: str = ""      # complete input (only in --tool N)
    output_preview: str = ""  # truncated to ~500 chars in overview
    output_full: str = ""     # complete output (only in --tool N)
    success: bool = True
    invocation_message: str = ""  # human-readable description
    past_tense_message: str = ""  # e.g. "Read file src/main.py"


class TurnDetail(BaseModel):
    """Full detail of a single turn."""

    turn_number: int
    user_message: str = ""
    assistant_response: str = ""
    tool_calls: list[ToolCallDetail] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    timestamp: Optional[datetime] = None
    # Populated from response metadata
    model: str = ""
    mode: str = ""


# ── Diff level ──────────────────────────────────────────────────────────────

class DiffResult(BaseModel):
    """Comparison between two turns."""

    turn_a: int
    turn_b: int
    summary: str = ""
    tools_only_in_a: list[str] = Field(default_factory=list)
    tools_only_in_b: list[str] = Field(default_factory=list)
    files_only_in_a: list[str] = Field(default_factory=list)
    files_only_in_b: list[str] = Field(default_factory=list)
