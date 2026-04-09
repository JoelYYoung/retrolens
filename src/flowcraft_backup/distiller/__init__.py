"""
Distiller - 工作流蒸馏模块

从 Agent 会话日志中提取可复用的工作流：
- 内容压缩：处理长对话
- 工作流提取：识别步骤、依赖、工具使用
- 交互式蒸馏：支持人工审核和编辑
"""

from .compressor import ContentCompressor, ContentSegment, ContentType
from .engine import DistillEngine, ExtractionResult

__all__ = [
    "ContentCompressor",
    "ContentSegment",
    "ContentType",
    "DistillEngine",
    "ExtractionResult",
]
