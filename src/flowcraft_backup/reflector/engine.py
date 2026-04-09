"""
Workflow Reflector - 工作流反思引擎

核心功能：
- 模式识别 (Pattern Recognition)
- 瓶颈分析 (Bottleneck Analysis)
- 经验提取 (Lesson Learning)
- 优化建议 (Optimization Suggestions)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from ..schemas import (
    Workflow,
    WorkflowStep,
    Reflection,
    PatternMatch,
    Bottleneck,
    LessonLearned,
)
from ..llm import LLMClient, get_analyzer_client


class PatternType(str, Enum):
    """模式类型"""
    
    RETRY_LOOP = "retry_loop"
    """重试循环模式"""
    
    EXPLORATION = "exploration"
    """探索模式"""
    
    SEQUENTIAL = "sequential"
    """顺序执行模式"""
    
    PARALLEL = "parallel"
    """并行执行模式"""
    
    BACKTRACK = "backtrack"
    """回溯模式"""
    
    ITERATIVE_REFINEMENT = "iterative_refinement"
    """迭代优化模式"""


class BottleneckType(str, Enum):
    """瓶颈类型"""
    
    TOOL_LIMITATION = "tool_limitation"
    """工具限制"""
    
    CONTEXT_LOSS = "context_loss"
    """上下文丢失"""
    
    UNNECESSARY_STEP = "unnecessary_step"
    """不必要步骤"""
    
    MISSING_INFORMATION = "missing_information"
    """信息缺失"""
    
    INEFFICIENT_APPROACH = "inefficient_approach"
    """低效方法"""


# 反思系统提示
REFLECTION_SYSTEM = """你是一个专业的 AI Agent 工作流分析师。你的任务是分析工作流并提取有价值的经验教训。

你需要识别：
1. **模式 (Patterns)**: 工作流中的常见模式和反模式
2. **瓶颈 (Bottlenecks)**: 效率低下的地方
3. **经验 (Lessons)**: 可以复用的经验教训
4. **优化 (Optimizations)**: 具体的改进建议

分析时请注意：
- 关注失败尝试中的学习价值
- 识别可以合并或消除的步骤
- 找出工具使用的最佳实践
- 提取可泛化的策略"""

REFLECTION_PROMPT = """分析以下工作流并提供反思：

{workflow_yaml}

请以 JSON 格式输出：
```json
{{
  "patterns": [
    {{
      "pattern_type": "retry_loop|exploration|sequential|parallel|backtrack|iterative_refinement",
      "description": "模式描述",
      "steps_involved": [1, 2, 3],
      "is_antipattern": false,
      "suggestion": "改进建议（如果是反模式）"
    }}
  ],
  "bottlenecks": [
    {{
      "step_number": 1,
      "bottleneck_type": "tool_limitation|context_loss|unnecessary_step|missing_information|inefficient_approach",
      "description": "瓶颈描述",
      "impact": "high|medium|low",
      "suggestion": "优化建议"
    }}
  ],
  "lessons": [
    {{
      "title": "经验标题",
      "description": "详细描述",
      "applicable_scenarios": ["场景1", "场景2"],
      "tags": ["tag1", "tag2"]
    }}
  ],
  "overall_efficiency_score": 0.75,
  "summary": "整体总结"
}}
```"""


@dataclass
class ReflectionResult:
    """反思结果"""
    
    reflection: Reflection
    """结构化反思"""
    
    raw_response: str
    """LLM 原始响应"""
    
    workflow: Workflow
    """输入的工作流"""
    
    suggestions_priority: list[str] = field(default_factory=list)
    """按优先级排序的建议列表"""


class WorkflowReflector:
    """工作流反思引擎
    
    功能：
    - 分析工作流模式
    - 识别瓶颈
    - 提取经验
    - 生成优化建议
    
    Example:
        >>> reflector = WorkflowReflector()
        >>> result = await reflector.reflect(workflow)
        >>> for lesson in result.reflection.lessons:
        ...     print(f"- {lesson.title}")
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
    ):
        """初始化反思引擎
        
        Args:
            llm_client: LLM 客户端
        """
        self.llm_client = llm_client
    
    def _get_llm(self) -> LLMClient:
        """获取 LLM 客户端"""
        if self.llm_client is None:
            self.llm_client = get_analyzer_client()
        return self.llm_client
    
    async def reflect(
        self,
        workflow: Workflow,
        context: Optional[str] = None,
    ) -> ReflectionResult:
        """执行工作流反思
        
        Args:
            workflow: 待分析的工作流
            context: 额外上下文
            
        Returns:
            反思结果
        """
        llm = self._get_llm()
        
        # 生成工作流 YAML
        workflow_yaml = workflow.to_yaml()
        
        prompt = REFLECTION_PROMPT.format(workflow_yaml=workflow_yaml)
        if context:
            prompt += f"\n\n额外上下文:\n{context}"
        
        response = await llm.complete(
            prompt,
            system_prompt=REFLECTION_SYSTEM,
            temperature=0.3,
        )
        
        # 解析响应
        reflection = self._parse_reflection_response(response)
        
        # 生成优先级建议
        suggestions = self._prioritize_suggestions(reflection)
        
        return ReflectionResult(
            reflection=reflection,
            raw_response=response,
            workflow=workflow,
            suggestions_priority=suggestions,
        )
    
    def _parse_reflection_response(self, response: str) -> Reflection:
        """解析反思响应
        
        Args:
            response: LLM 响应
            
        Returns:
            Reflection 对象
        """
        # 提取 JSON
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response.strip()
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # 返回空反思
            return Reflection(
                patterns=[],
                bottlenecks=[],
                lessons=[],
                summary="Failed to parse reflection response",
            )
        
        # 转换模式
        patterns: list[PatternMatch] = []
        for p in data.get("patterns", []):
            patterns.append(PatternMatch(
                pattern_type=p.get("pattern_type", "sequential"),
                description=p.get("description", ""),
                steps_involved=p.get("steps_involved", []),
                is_antipattern=p.get("is_antipattern", False),
                suggestion=p.get("suggestion"),
            ))
        
        # 转换瓶颈
        bottlenecks: list[Bottleneck] = []
        for b in data.get("bottlenecks", []):
            bottlenecks.append(Bottleneck(
                step_number=b.get("step_number", 0),
                bottleneck_type=b.get("bottleneck_type", "inefficient_approach"),
                description=b.get("description", ""),
                impact=b.get("impact", "medium"),
                suggestion=b.get("suggestion", ""),
            ))
        
        # 转换经验
        lessons: list[LessonLearned] = []
        for l in data.get("lessons", []):
            lessons.append(LessonLearned(
                title=l.get("title", ""),
                description=l.get("description", ""),
                applicable_scenarios=l.get("applicable_scenarios", []),
                tags=l.get("tags", []),
            ))
        
        return Reflection(
            patterns=patterns,
            bottlenecks=bottlenecks,
            lessons=lessons,
            overall_efficiency_score=data.get("overall_efficiency_score"),
            summary=data.get("summary", ""),
        )
    
    def _prioritize_suggestions(
        self,
        reflection: Reflection,
    ) -> list[str]:
        """按优先级排序建议
        
        Args:
            reflection: 反思结果
            
        Returns:
            排序后的建议列表
        """
        suggestions: list[tuple[str, int]] = []
        
        # 高优先级：反模式
        for pattern in reflection.patterns:
            if pattern.is_antipattern and pattern.suggestion:
                suggestions.append((
                    f"[反模式] {pattern.suggestion}",
                    3  # 高优先级
                ))
        
        # 中高优先级：高影响瓶颈
        for bottleneck in reflection.bottlenecks:
            priority = {"high": 3, "medium": 2, "low": 1}.get(bottleneck.impact, 1)
            if bottleneck.suggestion:
                suggestions.append((
                    f"[{bottleneck.bottleneck_type}] {bottleneck.suggestion}",
                    priority
                ))
        
        # 排序并返回
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in suggestions]
    
    def reflect_sync(
        self,
        workflow: Workflow,
        context: Optional[str] = None,
    ) -> ReflectionResult:
        """同步反思
        
        Args:
            workflow: 工作流
            context: 上下文
            
        Returns:
            反思结果
        """
        import asyncio
        return asyncio.run(self.reflect(workflow, context))
    
    async def batch_reflect(
        self,
        workflows: list[Workflow],
    ) -> list[ReflectionResult]:
        """批量反思
        
        Args:
            workflows: 工作流列表
            
        Returns:
            反思结果列表
        """
        import asyncio
        tasks = [self.reflect(w) for w in workflows]
        return await asyncio.gather(*tasks)
    
    def aggregate_lessons(
        self,
        results: list[ReflectionResult],
    ) -> list[LessonLearned]:
        """聚合多个反思结果的经验
        
        Args:
            results: 反思结果列表
            
        Returns:
            去重并聚合的经验列表
        """
        # 按标题去重
        lessons_map: dict[str, LessonLearned] = {}
        
        for result in results:
            for lesson in result.reflection.lessons:
                key = lesson.title.lower().strip()
                if key not in lessons_map:
                    lessons_map[key] = lesson
                else:
                    # 合并场景和标签
                    existing = lessons_map[key]
                    existing.applicable_scenarios = list(set(
                        existing.applicable_scenarios + lesson.applicable_scenarios
                    ))
                    existing.tags = list(set(existing.tags + lesson.tags))
        
        return list(lessons_map.values())
