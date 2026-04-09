"""
Distill Engine - 工作流蒸馏引擎

核心功能：
- 从压缩后的对话中提取工作流
- 识别步骤、依赖关系、工具使用
- 生成结构化的 Workflow 对象
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from ..schemas import (
    Workflow,
    WorkflowStep,
    DataDependency,
)
from ..llm import LLMClient, get_analyzer_client
from .compressor import ContentCompressor


# 工作流提取的系统提示
WORKFLOW_EXTRACTION_SYSTEM = """你是一个专业的工作流分析师。你的任务是从 Agent 的对话日志中提取结构化的工作流。

工作流应该包含：
1. **步骤 (Steps)**: Agent 完成任务的每个关键步骤
2. **目标 (Goals)**: 每个步骤要达成的目标
3. **工具使用 (Tools)**: 每个步骤使用的工具
4. **数据依赖 (Dependencies)**: 步骤之间的数据流动

注意：
- 合并相似的重复步骤
- 忽略失败的尝试（除非它们提供了重要信息）
- 关注最终成功的路径
- 识别可以并行执行的步骤"""

WORKFLOW_EXTRACTION_PROMPT = """分析以下 Agent 对话日志，提取工作流：

{compressed_log}

请以 JSON 格式输出，包含以下字段：
```json
{{
  "name": "工作流名称",
  "description": "工作流描述",
  "goal": "最终目标",
  "steps": [
    {{
      "round_number": 1,
      "goal": "步骤目标",
      "action_summary": "执行动作摘要",
      "tools_used": ["tool1", "tool2"],
      "input_context": "输入上下文",
      "output_summary": "输出摘要",
      "data_dependencies": [
        {{
          "source_round": 0,
          "data_type": "数据类型",
          "description": "依赖描述"
        }}
      ],
      "decision_points": ["决策点1"],
      "success": true
    }}
  ],
  "tags": ["tag1", "tag2"],
  "estimated_duration_minutes": 10
}}
```"""


@dataclass
class ExtractionResult:
    """提取结果"""
    
    workflow: Workflow
    """提取的工作流"""
    
    confidence: float
    """置信度 (0-1)"""
    
    raw_response: str
    """LLM 原始响应"""
    
    warnings: list[str]
    """警告信息"""


class DistillEngine:
    """工作流蒸馏引擎
    
    核心流程：
    1. 对话分段 (segment)
    2. 内容压缩 (compress)
    3. 工作流提取 (extract)
    4. 结构验证 (validate)
    
    Example:
        >>> engine = DistillEngine()
        >>> result = await engine.distill(messages)
        >>> print(result.workflow.to_yaml())
    """
    
    def __init__(
        self,
        compressor: Optional[ContentCompressor] = None,
        llm_client: Optional[LLMClient] = None,
        compression_threshold: int = 500,
    ):
        """初始化引擎
        
        Args:
            compressor: 内容压缩器
            llm_client: LLM 客户端
            compression_threshold: 压缩阈值
        """
        self.compressor = compressor or ContentCompressor(
            threshold_tokens=compression_threshold
        )
        self.llm_client = llm_client
    
    def _get_llm(self) -> LLMClient:
        """获取 LLM 客户端（使用 analyzer 配置）"""
        if self.llm_client is None:
            self.llm_client = get_analyzer_client()
        return self.llm_client
    
    async def distill(
        self,
        messages: list[dict[str, Any]],
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        skip_compression: bool = False,
    ) -> ExtractionResult:
        """完整蒸馏流程
        
        Args:
            messages: 原始消息列表
            session_id: 会话 ID
            metadata: 额外元数据
            skip_compression: 跳过压缩步骤
            
        Returns:
            提取结果
        """
        # Step 1: 分段
        segments = self.compressor.segment_conversation(messages)
        
        # Step 2: 压缩
        if not skip_compression:
            segments = await self.compressor.compress_all(segments)
        
        # Step 3: 合并
        compressed_log = self.compressor.merge_segments(segments)
        
        # Step 4: 提取
        result = await self._extract_workflow(
            compressed_log,
            session_id=session_id,
            metadata=metadata,
        )
        
        # 添加压缩统计
        stats = self.compressor.get_stats(segments)
        result.workflow.metadata = result.workflow.metadata or {}
        result.workflow.metadata["compression_stats"] = stats
        
        return result
    
    async def _extract_workflow(
        self,
        compressed_log: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExtractionResult:
        """从压缩日志提取工作流
        
        Args:
            compressed_log: 压缩后的日志
            session_id: 会话 ID
            metadata: 元数据
            
        Returns:
            提取结果
        """
        llm = self._get_llm()
        
        prompt = WORKFLOW_EXTRACTION_PROMPT.format(compressed_log=compressed_log)
        
        response = await llm.complete(
            prompt,
            system_prompt=WORKFLOW_EXTRACTION_SYSTEM,
            temperature=0.2,
        )
        
        # 解析响应
        workflow, warnings = self._parse_workflow_response(response)
        
        # 设置元数据
        if session_id:
            workflow.session_id = session_id
        if metadata:
            workflow.metadata = {**(workflow.metadata or {}), **metadata}
        
        # 计算置信度
        confidence = self._calculate_confidence(workflow, warnings)
        
        return ExtractionResult(
            workflow=workflow,
            confidence=confidence,
            raw_response=response,
            warnings=warnings,
        )
    
    def _parse_workflow_response(
        self,
        response: str,
    ) -> tuple[Workflow, list[str]]:
        """解析 LLM 响应为 Workflow
        
        Args:
            response: LLM 响应文本
            
        Returns:
            (Workflow, 警告列表)
        """
        warnings: list[str] = []
        
        # 提取 JSON
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = response.strip()
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            warnings.append(f"JSON 解析失败: {e}")
            return Workflow(
                name="Unknown",
                description="Failed to parse",
                goal="Unknown",
                steps=[],
            ), warnings
        
        # 转换步骤
        steps: list[WorkflowStep] = []
        for step_data in data.get("steps", []):
            # 转换数据依赖
            deps: list[DataDependency] = []
            for dep_data in step_data.get("data_dependencies", []):
                deps.append(DataDependency(
                    source_round=dep_data.get("source_round", 0),
                    data_type=dep_data.get("data_type", "unknown"),
                    description=dep_data.get("description", ""),
                ))
            
            steps.append(WorkflowStep(
                round_number=step_data.get("round_number", len(steps) + 1),
                goal=step_data.get("goal", ""),
                action_summary=step_data.get("action_summary", ""),
                tools_used=step_data.get("tools_used", []),
                input_context=step_data.get("input_context", ""),
                output_summary=step_data.get("output_summary", ""),
                data_dependencies=deps,
                decision_points=step_data.get("decision_points", []),
                success=step_data.get("success", True),
            ))
        
        workflow = Workflow(
            name=data.get("name", "Extracted Workflow"),
            description=data.get("description", ""),
            goal=data.get("goal", ""),
            steps=steps,
            tags=data.get("tags", []),
            estimated_duration_minutes=data.get("estimated_duration_minutes"),
        )
        
        return workflow, warnings
    
    def _calculate_confidence(
        self,
        workflow: Workflow,
        warnings: list[str],
    ) -> float:
        """计算提取置信度
        
        Args:
            workflow: 工作流
            warnings: 警告列表
            
        Returns:
            置信度 (0-1)
        """
        confidence = 1.0
        
        # 警告扣分
        confidence -= 0.1 * len(warnings)
        
        # 步骤数检查
        if len(workflow.steps) == 0:
            confidence -= 0.5
        elif len(workflow.steps) < 2:
            confidence -= 0.2
        
        # 字段完整性检查
        if not workflow.name or workflow.name == "Unknown":
            confidence -= 0.1
        if not workflow.goal:
            confidence -= 0.1
        
        # 步骤质量检查
        for step in workflow.steps:
            if not step.goal:
                confidence -= 0.05
            if not step.tools_used:
                confidence -= 0.02
        
        return max(0.0, min(1.0, confidence))
    
    def distill_sync(
        self,
        messages: list[dict[str, Any]],
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExtractionResult:
        """同步蒸馏（简化版，不压缩）
        
        Args:
            messages: 原始消息列表
            session_id: 会话 ID
            metadata: 元数据
            
        Returns:
            提取结果
        """
        import asyncio
        return asyncio.run(self.distill(
            messages,
            session_id=session_id,
            metadata=metadata,
            skip_compression=True,
        ))
