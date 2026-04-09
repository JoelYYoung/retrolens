"""
LLM Integration - 多后端 LLM 客户端

轻量级多 provider 适配层，支持 OpenAI 兼容 API 和 Anthropic API。
"""

from .client import (
    LLMClient,
    LLMConfig,
    ProviderType,
    get_analyzer_client,
    get_provider,
    reset_clients,
)

__all__ = [
    "LLMClient",
    "LLMConfig",
    "ProviderType",
    "get_analyzer_client",
    "get_provider",
    "reset_clients",
]
