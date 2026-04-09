"""
Workflow DSL — serialize WorkflowDSL models to YAML and generate LangGraph code.

This module handles the "output" side: once an agent has analyzed a session
and filled in a WorkflowDSL model, this module serializes it to:
  1. YAML DSL (human-readable, editable)
  2. LangGraph Python code (executable agent)
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import WorkflowDSL, WorkflowPhase, WorkflowStep, ToolUsage


# ── YAML DSL Serialization ──────────────────────────────────────────────────

def workflow_to_yaml(workflow: WorkflowDSL) -> str:
    """Serialize a WorkflowDSL model to YAML string."""
    data = _workflow_to_dict(workflow)
    return yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )


def _workflow_to_dict(workflow: WorkflowDSL) -> dict[str, Any]:
    """Convert WorkflowDSL to a clean dict for YAML serialization."""
    return {
        "workflow": {
            "name": workflow.name,
            "description": workflow.description,
            "goal": workflow.goal,
            "version": "1.0",
            "source": {
                "session_id": workflow.source_session_id,
                "title": workflow.source_title,
                "extracted_at": (
                    workflow.extracted_at.isoformat()
                    if workflow.extracted_at
                    else datetime.now().isoformat()
                ),
            },
            "inputs": workflow.inputs,
            "outputs": workflow.outputs,
            "state_variables": workflow.state_variables,
            "phases": [_phase_to_dict(p) for p in workflow.phases],
            "dependencies": workflow.dependencies,
            "decision_points": workflow.decision_points,
            "human_checkpoints": workflow.human_checkpoints,
            "tools_summary": [
                {"name": t.tool_name, "count": t.call_count, "purpose": t.purpose}
                for t in workflow.tools_summary
            ],
        }
    }


def _phase_to_dict(phase: WorkflowPhase) -> dict[str, Any]:
    return {
        "name": phase.name,
        "description": phase.description,
        "entry_condition": phase.entry_condition,
        "exit_condition": phase.exit_condition,
        "source_turns": phase.source_turns,
        "steps": [_step_to_dict(s) for s in phase.steps],
    }


def _step_to_dict(step: WorkflowStep) -> dict[str, Any]:
    d: dict[str, Any] = {
        "description": step.description,
    }
    if step.tools_used:
        d["tools"] = [t.tool_name for t in step.tools_used]
    if step.input_summary:
        d["input"] = step.input_summary
    if step.output_summary:
        d["output"] = step.output_summary
    if step.decision_point:
        d["decision"] = step.decision_point
    if step.source_turns:
        d["source_turns"] = step.source_turns
    return d


def yaml_to_workflow(yaml_str: str) -> WorkflowDSL:
    """Parse a YAML DSL string back into a WorkflowDSL model."""
    data = yaml.safe_load(yaml_str)
    w = data.get("workflow", data)

    source = w.get("source", {})
    phases = []
    for p in w.get("phases", []):
        steps = []
        for i, s in enumerate(p.get("steps", []), 1):
            tools = [ToolUsage(tool_name=t) for t in s.get("tools", [])]
            steps.append(WorkflowStep(
                step_number=i,
                description=s.get("description", ""),
                tools_used=tools,
                input_summary=s.get("input", ""),
                output_summary=s.get("output", ""),
                decision_point=s.get("decision", ""),
                source_turns=s.get("source_turns", []),
            ))
        phases.append(WorkflowPhase(
            phase_number=len(phases) + 1,
            name=p.get("name", ""),
            description=p.get("description", ""),
            entry_condition=p.get("entry_condition", ""),
            exit_condition=p.get("exit_condition", ""),
            steps=steps,
            source_turns=p.get("source_turns", []),
        ))

    tools_summary = []
    for t in w.get("tools_summary", []):
        tools_summary.append(ToolUsage(
            tool_name=t.get("name", ""),
            call_count=t.get("count", 0),
            purpose=t.get("purpose", ""),
        ))

    return WorkflowDSL(
        name=w.get("name", ""),
        description=w.get("description", ""),
        goal=w.get("goal", ""),
        source_session_id=source.get("session_id", ""),
        source_title=source.get("title", ""),
        phases=phases,
        inputs=w.get("inputs", []),
        outputs=w.get("outputs", []),
        tools_summary=tools_summary,
        decision_points=w.get("decision_points", []),
        dependencies=w.get("dependencies", []),
        state_variables=w.get("state_variables", []),
        human_checkpoints=w.get("human_checkpoints", []),
    )


# ── LangGraph Code Generation ──────────────────────────────────────────────

def workflow_to_langgraph(workflow: WorkflowDSL) -> str:
    """Generate a LangGraph-based agent from a WorkflowDSL model.

    The generated code is a complete, runnable Python module that uses
    langgraph to orchestrate the workflow phases as a state machine.
    """
    safe_name = _safe_python_name(workflow.name)
    class_name = _to_class_name(workflow.name)

    sections = [
        _gen_header(workflow),
        _gen_imports(),
        _gen_state_class(workflow, class_name),
        _gen_tool_functions(workflow),
        _gen_phase_nodes(workflow, class_name),
        _gen_router(workflow),
        _gen_graph_builder(workflow, class_name, safe_name),
        _gen_main(safe_name, workflow),
    ]

    return "\n\n".join(s for s in sections if s)


def _safe_python_name(name: str) -> str:
    """Convert a workflow name to a safe Python identifier."""
    result = name.lower().replace(" ", "_").replace("-", "_")
    # Remove non-alphanumeric chars
    result = "".join(c for c in result if c.isalnum() or c == "_")
    if result and result[0].isdigit():
        result = "_" + result
    return result or "workflow"


def _to_class_name(name: str) -> str:
    """Convert a workflow name to PascalCase class name."""
    words = name.replace("-", " ").replace("_", " ").split()
    return "".join(w.capitalize() for w in words) + "State" if words else "WorkflowState"


def _gen_header(workflow: WorkflowDSL) -> str:
    return textwrap.dedent(f'''\
    """
    Auto-generated LangGraph workflow: {workflow.name}
    
    Goal: {workflow.goal}
    Source: Session {workflow.source_session_id[:12]}... ({workflow.source_title})
    Generated by FlowCraft Distill
    
    Usage:
        python {_safe_python_name(workflow.name)}_agent.py
    """''')


def _gen_imports() -> str:
    return textwrap.dedent('''\
    from __future__ import annotations

    import operator
    from typing import Annotated, Any, Literal, TypedDict

    from langgraph.graph import END, START, StateGraph
    from langgraph.prebuilt import ToolNode
    # Uncomment if using LLM-based nodes:
    # from langchain_openai import ChatOpenAI
    # from langchain_anthropic import ChatAnthropic''')


def _gen_state_class(workflow: WorkflowDSL, class_name: str) -> str:
    lines = [f"class {class_name}(TypedDict):"]
    lines.append(f'    """State for workflow: {workflow.name}"""')
    lines.append("")

    # Phase tracking
    phase_names = [p.name for p in workflow.phases]
    phase_literals = ", ".join(f'"{n}"' for n in phase_names + ["done"])
    lines.append(f"    phase: Literal[{phase_literals}]")

    # Standard fields
    lines.append('    messages: Annotated[list[dict], operator.add]')
    lines.append("    context: dict[str, Any]")

    # Custom state variables from DSL
    for var in workflow.state_variables:
        safe_var = _safe_python_name(var)
        lines.append(f"    {safe_var}: Any  # from DSL: {var}")

    return "\n".join(lines)


def _gen_tool_functions(workflow: WorkflowDSL) -> str:
    """Generate stub functions for each unique tool used."""
    tool_names = set()
    for phase in workflow.phases:
        for step in phase.steps:
            for t in step.tools_used:
                tool_names.add(t.tool_name)

    if not tool_names:
        return ""

    lines = ["# ── Tool stubs (implement these) ────────────────────────────────"]
    lines.append("")
    for name in sorted(tool_names):
        safe = _safe_python_name(name)
        lines.append(f"def tool_{safe}(**kwargs) -> str:")
        lines.append(f'    """Stub for tool: {name}"""')
        lines.append(f"    raise NotImplementedError('Implement tool_{safe}')")
        lines.append("")

    return "\n".join(lines)


def _gen_phase_nodes(workflow: WorkflowDSL, class_name: str) -> str:
    """Generate a node function for each phase."""
    lines = ["# ── Phase nodes ─────────────────────────────────────────────────"]

    for phase in workflow.phases:
        safe = _safe_python_name(phase.name)
        lines.append("")
        lines.append(f"def {safe}_node(state: {class_name}) -> dict:")
        lines.append(f'    """')
        lines.append(f"    Phase: {phase.name}")
        lines.append(f"    {phase.description}")
        if phase.entry_condition:
            lines.append(f"    Entry: {phase.entry_condition}")
        if phase.exit_condition:
            lines.append(f"    Exit: {phase.exit_condition}")
        lines.append(f'    """')

        # Add step comments
        for step in phase.steps:
            tools_str = ", ".join(t.tool_name for t in step.tools_used)
            lines.append(f"    # Step {step.step_number}: {step.description}")
            if tools_str:
                lines.append(f"    #   Tools: {tools_str}")
            if step.decision_point:
                lines.append(f"    #   Decision: {step.decision_point}")

        lines.append("")
        lines.append("    # TODO: Implement this phase")
        lines.append(f'    # Entry condition: {phase.entry_condition or "always"}')
        lines.append(f'    # Exit condition: {phase.exit_condition or "steps complete"}')
        lines.append("")
        lines.append("    return {")

        # Find next phase
        idx = next(
            (i for i, p in enumerate(workflow.phases) if p.name == phase.name), -1
        )
        if idx < len(workflow.phases) - 1:
            next_phase = workflow.phases[idx + 1].name
            lines.append(f'        "phase": "{next_phase}",')
        else:
            lines.append(f'        "phase": "done",')

        lines.append("    }")

    return "\n".join(lines)


def _gen_router(workflow: WorkflowDSL) -> str:
    """Generate router function that routes based on phase."""
    lines = ["# ── Phase router ────────────────────────────────────────────────"]
    lines.append("")
    lines.append(f"def route_by_phase(state) -> str:")
    lines.append(f'    """Route to the next phase based on state."""')
    lines.append(f'    phase = state.get("phase", "done")')

    for phase in workflow.phases:
        safe = _safe_python_name(phase.name)
        lines.append(f'    if phase == "{phase.name}":')
        lines.append(f'        return "{safe}"')

    lines.append(f'    return "end"')
    return "\n".join(lines)


def _gen_graph_builder(
    workflow: WorkflowDSL, class_name: str, safe_name: str
) -> str:
    """Generate the graph builder function."""
    lines = ["# ── Graph construction ───────────────────────────────────────────"]
    lines.append("")
    lines.append(f"def build_{safe_name}_graph() -> StateGraph:")
    lines.append(f'    """Build the LangGraph workflow."""')
    lines.append(f"    graph = StateGraph({class_name})")
    lines.append("")

    # Add nodes
    for phase in workflow.phases:
        safe = _safe_python_name(phase.name)
        lines.append(f'    graph.add_node("{safe}", {safe}_node)')

    lines.append("")

    # Entry point
    if workflow.phases:
        first_safe = _safe_python_name(workflow.phases[0].name)
        lines.append(f"    # Entry: start → first phase")
        lines.append(f'    graph.add_edge(START, "{first_safe}")')
        lines.append("")

        # Phase transitions
        lines.append(f"    # Phase transitions")
        for i, phase in enumerate(workflow.phases):
            safe = _safe_python_name(phase.name)
            if i < len(workflow.phases) - 1:
                next_safe = _safe_python_name(workflow.phases[i + 1].name)
                lines.append(f'    graph.add_edge("{safe}", "{next_safe}")')
            else:
                lines.append(f'    graph.add_edge("{safe}", END)')

    lines.append("")
    lines.append("    return graph.compile()")

    return "\n".join(lines)


def _gen_main(safe_name: str, workflow: WorkflowDSL) -> str:
    """Generate the main entry point."""
    first_phase = workflow.phases[0].name if workflow.phases else "done"

    return textwrap.dedent(f'''\
    # ── Main ────────────────────────────────────────────────────────────

    if __name__ == "__main__":
        graph = build_{safe_name}_graph()
        
        initial_state = {{
            "phase": "{first_phase}",
            "messages": [],
            "context": {{}},
        }}
        
        print(f"Running workflow: {workflow.name}")
        print(f"Goal: {workflow.goal}")
        print()
        
        result = graph.invoke(initial_state)
        
        print("\\nWorkflow complete!")
        print(f"Final phase: {{result.get('phase', 'unknown')}}")''')


# ── File I/O helpers ────────────────────────────────────────────────────────

def save_workflow_yaml(workflow: WorkflowDSL, output_dir: Path) -> Path:
    """Save workflow DSL to a YAML file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_python_name(workflow.name) or "workflow"
    path = output_dir / f"{safe}.workflow.yaml"
    path.write_text(workflow_to_yaml(workflow), encoding="utf-8")
    return path


def save_langgraph_code(workflow: WorkflowDSL, output_dir: Path) -> Path:
    """Save LangGraph code to a Python file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_python_name(workflow.name) or "workflow"
    path = output_dir / f"{safe}_agent.py"
    path.write_text(workflow_to_langgraph(workflow), encoding="utf-8")
    return path
