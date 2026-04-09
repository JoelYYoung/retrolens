"""
Workflow DSL - 工作流领域特定语言

支持格式：
- YAML DSL
- JSON DSL
- Mermaid 流程图
"""

from __future__ import annotations

import json
import yaml
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from ..schemas import Workflow, WorkflowStep


class DSLFormat(str, Enum):
    """DSL 输出格式"""
    
    YAML = "yaml"
    """YAML 格式"""
    
    JSON = "json"
    """JSON 格式"""
    
    MERMAID = "mermaid"
    """Mermaid 流程图"""
    
    MINIMAL = "minimal"
    """最小化格式（仅关键字段）"""


@dataclass
class DSLOutput:
    """DSL 输出结果"""
    
    content: str
    """生成的 DSL 内容"""
    
    format: DSLFormat
    """输出格式"""
    
    metadata: dict[str, Any]
    """元数据"""


class WorkflowDSL:
    """工作流 DSL 生成器
    
    将 Workflow 对象转换为各种 DSL 格式
    
    Example:
        >>> dsl = WorkflowDSL()
        >>> output = dsl.generate(workflow, DSLFormat.YAML)
        >>> print(output.content)
    """
    
    def __init__(self):
        """初始化 DSL 生成器"""
        self._formatters = {
            DSLFormat.YAML: self._to_yaml,
            DSLFormat.JSON: self._to_json,
            DSLFormat.MERMAID: self._to_mermaid,
            DSLFormat.MINIMAL: self._to_minimal,
        }
    
    def generate(
        self,
        workflow: Workflow,
        format: DSLFormat = DSLFormat.YAML,
        include_metadata: bool = True,
    ) -> DSLOutput:
        """生成 DSL
        
        Args:
            workflow: 工作流对象
            format: 输出格式
            include_metadata: 是否包含元数据
            
        Returns:
            DSL 输出结果
        """
        formatter = self._formatters.get(format)
        if formatter is None:
            raise ValueError(f"Unsupported format: {format}")
        
        content = formatter(workflow, include_metadata)
        
        return DSLOutput(
            content=content,
            format=format,
            metadata={
                "workflow_name": workflow.name,
                "steps_count": len(workflow.steps),
                "tools_used": self._collect_tools(workflow),
            }
        )
    
    def _to_yaml(self, workflow: Workflow, include_metadata: bool) -> str:
        """转换为 YAML 格式"""
        data = self._workflow_to_dict(workflow, include_metadata)
        return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def _to_json(self, workflow: Workflow, include_metadata: bool) -> str:
        """转换为 JSON 格式"""
        data = self._workflow_to_dict(workflow, include_metadata)
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _to_mermaid(self, workflow: Workflow, include_metadata: bool) -> str:
        """转换为 Mermaid 流程图"""
        lines = ["graph TD"]
        
        # 添加标题
        lines.append(f"    subgraph \"{workflow.name}\"")
        
        # 起始节点
        lines.append("    Start((Start))")
        
        prev_node = "Start"
        for i, step in enumerate(workflow.steps):
            node_id = f"Step{i+1}"
            # 截断过长的目标
            goal = step.goal[:30] + "..." if len(step.goal) > 30 else step.goal
            tools = ", ".join(step.tools_used[:2])  # 最多显示2个工具
            if tools:
                label = f"{goal}<br/>[{tools}]"
            else:
                label = goal
            
            # 节点形状：成功=圆角矩形，失败=菱形
            if step.success:
                lines.append(f"    {node_id}[\"{label}\"]")
            else:
                lines.append(f"    {node_id}{{\"{label}\"}}")
            
            # 连接线
            lines.append(f"    {prev_node} --> {node_id}")
            prev_node = node_id
        
        # 结束节点
        lines.append("    End((End))")
        lines.append(f"    {prev_node} --> End")
        lines.append("    end")
        
        # 添加数据依赖（虚线）
        for i, step in enumerate(workflow.steps):
            for dep in step.data_dependencies:
                if dep.source_round > 0 and dep.source_round <= len(workflow.steps):
                    source_node = f"Step{dep.source_round}"
                    target_node = f"Step{i+1}"
                    lines.append(f"    {source_node} -.->|{dep.data_type}| {target_node}")
        
        return "\n".join(lines)
    
    def _to_minimal(self, workflow: Workflow, include_metadata: bool) -> str:
        """转换为最小化格式"""
        lines = [f"# {workflow.name}", f"# Goal: {workflow.goal}", ""]
        
        for i, step in enumerate(workflow.steps):
            status = "✓" if step.success else "✗"
            tools = ", ".join(step.tools_used) if step.tools_used else "none"
            lines.append(f"{i+1}. [{status}] {step.goal}")
            lines.append(f"   Tools: {tools}")
            if step.data_dependencies:
                deps = ", ".join(f"Step{d.source_round}:{d.data_type}" for d in step.data_dependencies)
                lines.append(f"   Depends: {deps}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _workflow_to_dict(
        self,
        workflow: Workflow,
        include_metadata: bool,
    ) -> dict[str, Any]:
        """将工作流转换为字典"""
        steps = []
        for step in workflow.steps:
            step_dict: dict[str, Any] = {
                "round": step.round_number,
                "goal": step.goal,
                "action": step.action_summary,
                "tools": step.tools_used,
            }
            
            if step.data_dependencies:
                step_dict["dependencies"] = [
                    {
                        "from": dep.source_round,
                        "type": dep.data_type,
                        "desc": dep.description,
                    }
                    for dep in step.data_dependencies
                ]
            
            if step.decision_points:
                step_dict["decisions"] = step.decision_points
            
            if not step.success:
                step_dict["success"] = False
            
            steps.append(step_dict)
        
        result: dict[str, Any] = {
            "workflow": {
                "name": workflow.name,
                "goal": workflow.goal,
                "steps": steps,
            }
        }
        
        if include_metadata:
            result["workflow"]["description"] = workflow.description
            if workflow.tags:
                result["workflow"]["tags"] = workflow.tags
            if workflow.estimated_duration_minutes:
                result["workflow"]["duration_minutes"] = workflow.estimated_duration_minutes
        
        return result
    
    def _collect_tools(self, workflow: Workflow) -> list[str]:
        """收集所有使用的工具"""
        tools: set[str] = set()
        for step in workflow.steps:
            tools.update(step.tools_used)
        return sorted(tools)
    
    def parse(self, content: str, format: DSLFormat) -> Workflow:
        """从 DSL 解析为 Workflow
        
        Args:
            content: DSL 内容
            format: 格式
            
        Returns:
            Workflow 对象
        """
        if format == DSLFormat.YAML:
            data = yaml.safe_load(content)
        elif format == DSLFormat.JSON:
            data = json.loads(content)
        else:
            raise ValueError(f"Cannot parse format: {format}")
        
        workflow_data = data.get("workflow", data)
        
        from ..schemas import DataDependency
        
        steps = []
        for step_data in workflow_data.get("steps", []):
            deps = []
            for dep_data in step_data.get("dependencies", []):
                deps.append(DataDependency(
                    source_round=dep_data.get("from", 0),
                    data_type=dep_data.get("type", ""),
                    description=dep_data.get("desc", ""),
                ))
            
            steps.append(WorkflowStep(
                round_number=step_data.get("round", len(steps) + 1),
                goal=step_data.get("goal", ""),
                action_summary=step_data.get("action", ""),
                tools_used=step_data.get("tools", []),
                data_dependencies=deps,
                decision_points=step_data.get("decisions", []),
                success=step_data.get("success", True),
            ))
        
        return Workflow(
            name=workflow_data.get("name", "Parsed Workflow"),
            description=workflow_data.get("description", ""),
            goal=workflow_data.get("goal", ""),
            steps=steps,
            tags=workflow_data.get("tags", []),
            estimated_duration_minutes=workflow_data.get("duration_minutes"),
        )
