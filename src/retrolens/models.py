"""
Data models for RetroLens CLI.

Layered output models — each level returns just enough info for an agent
to decide whether to drill deeper.

    SessionInfo  →  SessionOverview  →  TurnDetail  →  ToolCallDetail
      (scan)         (read <id>)      (--turn N)     (--tool N)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Scan level ──────────────────────────────────────────────────────────────

class SessionInfo(BaseModel):
    """One row in the session list (scan output)."""

    session_id: str
    source_type: str  # "vscode" | "retrolens" | "claude"
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


# ── Workflow Extraction level ────────────────────────────────────────────────

class ToolUsage(BaseModel):
    """A tool used within a workflow step, with frequency and purpose."""

    tool_name: str = ""
    call_count: int = 0
    purpose: str = ""  # inferred from context


class WorkflowStep(BaseModel):
    """A single action/step within a workflow phase."""

    step_number: int = 0
    description: str = ""
    tools_used: list[ToolUsage] = Field(default_factory=list)
    input_summary: str = ""   # what was needed
    output_summary: str = ""  # what was produced
    decision_point: str = ""  # if this step involves a decision
    source_turns: list[int] = Field(default_factory=list)  # which turns this maps to


class WorkflowPhase(BaseModel):
    """A distinct phase in the workflow (e.g. research, implement, test)."""

    phase_number: int = 0
    name: str = ""
    description: str = ""
    entry_condition: str = ""
    exit_condition: str = ""
    steps: list[WorkflowStep] = Field(default_factory=list)
    source_turns: list[int] = Field(default_factory=list)  # turns range


class WorkflowDSL(BaseModel):
    """Complete workflow extracted from a session — the core output model.

    This is a structured representation that can be serialized to YAML DSL
    or used to generate LangGraph code.
    """

    name: str = ""
    description: str = ""
    goal: str = ""
    source_session_id: str = ""
    source_title: str = ""
    extracted_at: Optional[datetime] = None

    # Workflow structure
    phases: list[WorkflowPhase] = Field(default_factory=list)

    # Inputs & outputs
    inputs: list[str] = Field(default_factory=list)   # what the workflow needs
    outputs: list[str] = Field(default_factory=list)  # what it produces

    # Cross-cutting
    tools_summary: list[ToolUsage] = Field(default_factory=list)
    decision_points: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)  # e.g. "Phase 2 needs Phase 1 output"

    # Metadata for LangGraph generation
    state_variables: list[str] = Field(default_factory=list)
    human_checkpoints: list[str] = Field(default_factory=list)


class TurnDigest(BaseModel):
    """Condensed turn info for workflow analysis — enough for an agent to
    identify phases and patterns without reading full tool outputs."""

    turn_number: int = 0
    user_message: str = ""  # full user message (important for workflow)
    assistant_summary: str = ""  # first ~300 chars of response
    tools_used: list[str] = Field(default_factory=list)  # tool names
    tools_count: int = 0
    files_touched: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    has_error: bool = False
    timestamp: Optional[datetime] = None


class SessionDigest(BaseModel):
    """A condensed representation of a session for workflow/reflection analysis.

    This is the intermediate data that the CLI prepares for the agent
    to analyze. It's a structured summary, not raw data.
    """

    session_id: str = ""
    title: str = ""
    model: str = ""
    date: Optional[datetime] = None
    total_turns: int = 0

    # Per-turn condensed info
    turns: list[TurnDigest] = Field(default_factory=list)

    # Aggregated stats
    all_tools_used: list[ToolUsage] = Field(default_factory=list)
    all_files_touched: list[str] = Field(default_factory=list)
    all_commands_run: list[str] = Field(default_factory=list)


# ── Reflection level ────────────────────────────────────────────────────────

class ReflectionInsight(BaseModel):
    """A single insight from reflecting on a workflow/session."""

    category: str = ""  # "error", "inefficiency", "practice", "trap", "instruction"
    severity: str = ""  # "critical", "important", "minor", "info"
    title: str = ""
    description: str = ""
    evidence: str = ""  # what in the session supports this
    source_turns: list[int] = Field(default_factory=list)
    recommendation: str = ""


class ReflectionResult(BaseModel):
    """Complete reflection output for a session."""

    session_id: str = ""
    title: str = ""
    date: Optional[datetime] = None
    goal_achieved: bool = True
    goal_summary: str = ""
    workflow_summary: str = ""  # brief workflow description

    insights: list[ReflectionInsight] = Field(default_factory=list)

    # Specific categories for easy access
    errors: list[ReflectionInsight] = Field(default_factory=list)
    inefficiencies: list[ReflectionInsight] = Field(default_factory=list)
    good_practices: list[ReflectionInsight] = Field(default_factory=list)
    traps: list[ReflectionInsight] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)  # for AGENTS.md


# ── Show level ──────────────────────────────────────────────────────────────

class ArtifactInfo(BaseModel):
    """An existing output file in .retrolens/."""

    path: str
    type: str  # "lessons" | "workflow"
    last_modified: Optional[datetime] = None
    size_bytes: int = 0
    preview: str = ""  # first ~200 chars
