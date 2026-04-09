"""
Transformers - 协议转换器模块

支持多种 LLM API 协议的双向转换：
- Anthropic Messages API
- OpenAI Chat Completions API

转换流程：
1. detect: 自动检测请求协议
2. transform_request: 原始请求 → UnifiedRequest
3. transform_response: UnifiedResponse → 原始响应
"""

from .unified import (
    TextBlock,
    ImageBlock,
    ToolUseBlock,
    ToolResultBlock,
    ThinkingBlock,
    ContentBlock,
    content_block_from_dict,
    ToolDefinition,
    TokenUsage,
    UnifiedMessage,
    UnifiedRequest,
    UnifiedResponse,
)
from .base import (
    Transformer,
    TransformerRegistry,
    get_registry,
    register_transformer,
)
from .anthropic import AnthropicTransformer
from .openai import OpenAITransformer

__all__ = [
    # Content blocks
    "TextBlock",
    "ImageBlock", 
    "ToolUseBlock",
    "ToolResultBlock",
    "ThinkingBlock",
    "ContentBlock",
    "content_block_from_dict",
    # Definitions
    "ToolDefinition",
    "TokenUsage",
    # Unified formats
    "UnifiedMessage",
    "UnifiedRequest",
    "UnifiedResponse",
    # Transformers
    "Transformer",
    "TransformerRegistry",
    "get_registry",
    "register_transformer",
    "AnthropicTransformer",
    "OpenAITransformer",
]


# 自动注册内置转换器
def _register_builtin_transformers():
    registry = get_registry()
    registry.register(AnthropicTransformer())
    registry.register(OpenAITransformer())


_register_builtin_transformers()
