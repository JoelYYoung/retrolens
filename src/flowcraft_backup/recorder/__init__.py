"""
Recorder - 会话记录模块

多协议代理服务器，记录 AI Agent 与 LLM 的交互：
- 支持 Anthropic Messages API
- 支持 OpenAI Chat Completions API
- 自动协议检测
- 统一格式存储
"""

from .storage import SessionStorage, get_storage
from .transformers import (
    UnifiedMessage,
    UnifiedRequest,
    UnifiedResponse,
    Transformer,
    TransformerRegistry,
    get_registry,
)
from .server import run_server, create_app

__all__ = [
    # Storage
    "SessionStorage",
    "get_storage",
    # Unified formats
    "UnifiedMessage",
    "UnifiedRequest",
    "UnifiedResponse",
    # Transformers
    "Transformer",
    "TransformerRegistry",
    "get_registry",
    # Server
    "run_server",
    "create_app",
]
