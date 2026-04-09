"""
Pydantic Models - 数据模型定义

使用 Pydantic v2 的数据模型。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
import yaml


# =============================================================================
# Enums
# =============================================================================

class DistillPhase(str, Enum):
    """蒸馏阶段"""
    SEGMENTING = "segmenting"
    COMPRESSING = "compressing"
    EXTRACTING = "extracting"
    REVIEWING = "reviewing"
    COMPLETED = "completed"


# =============================================================================
# Data Dependency
# =============================================================================

class DataDependency(BaseModel):
    """数据依赖"""
    
    source_round: int
    """来源步骤编号"""
    
    data_type: str
    """数据类型"""
    
    description: str = ""
    """依赖描述"""


# =============================================================================
# Workflow Step
# =============================================================================

class WorkflowStep(BaseModel):
    """工作流步骤
    
    对应 Agent 执行的一个逻辑步骤。
    """
    
    round_number: int
    """步骤编号"""
    
    goal: str
    """步骤目标"""
    
    action_summary: str = ""
    """动作摘要"""
    
    tools_used: list[str] = Field(default_factory=list)
    """使用的工具列表"""
    
    input_context: str = ""
    """输入上下文"""
    
    output_summary: str = ""
    """输出摘要"""
    
    data_dependencies: list[DataDependency] = Field(default_factory=list)
    """数据依赖"""
    
    decision_points: list[str] = Field(default_factory=list)
    """决策点"""
    
    success: bool = True
    """是否成功"""


# =============================================================================
# Workflow
# =============================================================================

class Workflow(BaseModel):
    """工作流定义
    
    完整的工作流结构，可导出为 YAML DSL 或生成 LangGraph 代码。
    """
    
    name: str
    """工作流名称"""
    
    description: str = ""
    """工作流描述"""
    
    goal: str
    """工作流目标"""
    
    steps: list[WorkflowStep] = Field(default_factory=list)
    """步骤列表"""
    
    tags: list[str] = Field(default_factory=list)
    """标签"""
    
    estimated_duration_minutes: Optional[int] = None
    """预计时长（分钟）"""
    
    session_id: Optional[str] = None
    """来源会话 ID"""
    
    metadata: Optional[dict[str, Any]] = None
    """元数据"""
    
    def to_yaml(self) -> str:
        """导出为 YAML"""
        return yaml.dump(
            self.model_dump(exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
        )
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Workflow":
        """从 YAML 加载"""
        data = yaml.safe_load(yaml_str)
        return cls(**data)


# =============================================================================
# Reflection Models
# =============================================================================

class PatternMatch(BaseModel):
    """模式匹配"""
    
    pattern_type: str
    """模式类型 (good_pattern, anti_pattern)"""
    
    name: str
    """模式名称"""
    
    description: str
    """模式描述"""
    
    occurrences: list[str] = Field(default_factory=list)
    """出现位置"""
    
    impact: str = "medium"
    """影响程度 (low, medium, high)"""
    
    recommendation: str = ""
    """改进建议"""


class Bottleneck(BaseModel):
    """瓶颈"""
    
    step_number: int
    """步骤编号"""
    
    description: str
    """描述"""
    
    severity: str = "medium"
    """严重程度"""
    
    cause: str = ""
    """原因"""
    
    suggestion: str = ""
    """改进建议"""


class LessonLearned(BaseModel):
    """经验教训"""
    
    category: str
    """分类"""
    
    title: str
    """标题"""
    
    description: str
    """描述"""
    
    applicability: str = ""
    """适用场景"""
    
    priority: str = "medium"
    """优先级"""


class Reflection(BaseModel):
    """工作流反思"""
    
    workflow_id: str
    """工作流 ID"""
    
    summary: str = ""
    """摘要"""
    
    efficiency_score: float = 0.5
    """效率评分 (0-1)"""
    
    patterns: list[PatternMatch] = Field(default_factory=list)
    """模式"""
    
    bottlenecks: list[Bottleneck] = Field(default_factory=list)
    """瓶颈"""
    
    lessons_learned: list[LessonLearned] = Field(default_factory=list)
    """经验教训"""
    
    improvement_suggestions: list[str] = Field(default_factory=list)
    """改进建议"""


# =============================================================================
# Distill State
# =============================================================================

class CompressedContent(BaseModel):
    """压缩后的内容"""
    
    original_tokens: int
    """原始 token 数"""
    
    compressed_tokens: int
    """压缩后 token 数"""
    
    compression_ratio: float
    """压缩比"""
    
    compressed_text: str
    """压缩后的文本"""


class DistillState(BaseModel):
    """蒸馏状态（用于交互式蒸馏）"""
    
    session_id: str
    """会话 ID"""
    
    phase: DistillPhase = DistillPhase.SEGMENTING
    """当前阶段"""
    
    segments: list[dict[str, Any]] = Field(default_factory=list)
    """所有片段"""
    
    current_segment_index: int = 0
    """当前处理的片段索引"""
    
    total_segments: int = 0
    """总片段数"""
    
    compressed_segments: list[dict[str, Any]] = Field(default_factory=list)
    """已压缩的片段"""
    
    extracted_workflow: Optional[dict[str, Any]] = None
    """提取的工作流"""
    
    user_edits: list[dict[str, Any]] = Field(default_factory=list)
    """用户编辑记录"""


class InteractiveEdit(BaseModel):
    """交互式编辑"""
    
    segment_id: str
    """片段 ID"""
    
    original: str
    """原始内容"""
    
    edited: str
    """编辑后内容"""
    
    timestamp: datetime = Field(default_factory=datetime.now)
    """编辑时间"""
