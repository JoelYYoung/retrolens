"""
LLM Client - 统一的 LLM 调用接口

轻量级多 provider 适配层，不依赖 litellm。
支持 OpenAI 兼容 API、Anthropic API 等。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional, Type

import httpx


# =============================================================================
# Provider 类型
# =============================================================================

class ProviderType(str, Enum):
    """LLM Provider 类型"""
    OPENAI = "openai"      # OpenAI 及兼容 API
    ANTHROPIC = "anthropic"  # Anthropic Claude API
    AUTO = "auto"          # 自动检测


# =============================================================================
# 配置
# =============================================================================

@dataclass
class LLMConfig:
    """LLM 配置"""
    
    model: str = "gpt-4o-mini"
    """模型名称，原样传递给 API"""
    
    api_base: Optional[str] = None
    """API 端点"""
    
    api_key: Optional[str] = None
    """API 密钥"""
    
    provider: ProviderType = ProviderType.AUTO
    """Provider 类型，auto 则根据 api_base 自动检测"""
    
    temperature: float = 0.7
    """生成温度"""
    
    max_tokens: int = 4096
    """最大输出 token 数"""
    
    timeout: float = 120.0
    """请求超时时间（秒）"""
    
    extra_params: dict[str, Any] = field(default_factory=dict)
    """额外参数"""
    
    @classmethod
    def from_analyzer_config(cls) -> "LLMConfig":
        """从全局配置加载 analyzer 配置"""
        from ..config import get_config
        
        config = get_config()
        return cls(
            model=config.analyzer.model,
            api_base=config.analyzer.api_base,
            api_key=config.analyzer.api_key,
            temperature=config.analyzer.temperature,
            max_tokens=config.analyzer.max_tokens,
            timeout=config.analyzer.timeout,
        )
    
    def detect_provider(self) -> ProviderType:
        """自动检测 provider 类型"""
        if self.provider != ProviderType.AUTO:
            return self.provider
        
        # 根据 api_base 检测
        if self.api_base:
            base = self.api_base.lower()
            if "anthropic" in base:
                return ProviderType.ANTHROPIC
            # 默认使用 OpenAI 兼容
            return ProviderType.OPENAI
        
        # 根据模型名检测
        model = self.model.lower()
        if "claude" in model:
            return ProviderType.ANTHROPIC
        
        return ProviderType.OPENAI


# =============================================================================
# Provider 基类
# =============================================================================

class BaseProvider(ABC):
    """Provider 基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client
    
    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """完成文本生成"""
        pass
    
    @abstractmethod
    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式生成"""
        pass


# =============================================================================
# OpenAI 兼容 Provider
# =============================================================================

class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 API Provider
    
    支持 OpenAI、Azure OpenAI、以及所有 OpenAI 兼容的 API。
    模型名称原样传递，不做任何转换。
    """
    
    @property
    def api_base(self) -> str:
        return self.config.api_base or "https://api.openai.com/v1"
    
    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers
    
    async def complete(
        self,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """完成文本生成"""
        url = f"{self.api_base}/chat/completions"
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            **self.config.extra_params,
            **kwargs,
        }
        
        response = await self.client.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""
    
    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式生成"""
        url = f"{self.api_base}/chat/completions"
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }
        
        async with self.client.stream("POST", url, json=payload, headers=self.headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue


# =============================================================================
# Anthropic Provider
# =============================================================================

class AnthropicProvider(BaseProvider):
    """Anthropic Claude API Provider"""
    
    @property
    def api_base(self) -> str:
        return self.config.api_base or "https://api.anthropic.com"
    
    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.config.api_key:
            headers["x-api-key"] = self.config.api_key
        return headers
    
    def _convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[Optional[str], list[dict[str, Any]]]:
        """转换消息格式，分离 system 消息"""
        system = None
        converted = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system = content
            else:
                converted.append({"role": role, "content": content})
        
        return system, converted
    
    async def complete(
        self,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """完成文本生成"""
        url = f"{self.api_base}/v1/messages"
        
        system, converted_messages = self._convert_messages(messages)
        
        payload = {
            "model": self.config.model,
            "messages": converted_messages,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            **self.config.extra_params,
            **kwargs,
        }
        
        if system:
            payload["system"] = system
        
        # Anthropic 不使用 temperature=0，使用 temperature=0.0001
        temp = temperature if temperature is not None else self.config.temperature
        if temp > 0:
            payload["temperature"] = temp
        
        response = await self.client.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        
        data = response.json()
        # Anthropic 返回 content 数组
        content = data.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return ""
    
    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式生成"""
        url = f"{self.api_base}/v1/messages"
        
        system, converted_messages = self._convert_messages(messages)
        
        payload = {
            "model": self.config.model,
            "messages": converted_messages,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "stream": True,
            **self.config.extra_params,
            **kwargs,
        }
        
        if system:
            payload["system"] = system
        
        temp = temperature if temperature is not None else self.config.temperature
        if temp > 0:
            payload["temperature"] = temp
        
        async with self.client.stream("POST", url, json=payload, headers=self.headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_type = data.get("type")
                        if event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            text = delta.get("text")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        continue


# =============================================================================
# Provider 工厂
# =============================================================================

PROVIDERS: dict[ProviderType, Type[BaseProvider]] = {
    ProviderType.OPENAI: OpenAIProvider,
    ProviderType.ANTHROPIC: AnthropicProvider,
}


def get_provider(config: LLMConfig) -> BaseProvider:
    """根据配置获取 Provider 实例"""
    provider_type = config.detect_provider()
    provider_class = PROVIDERS.get(provider_type, OpenAIProvider)
    return provider_class(config)


# =============================================================================
# 统一 LLM 客户端
# =============================================================================

class LLMClient:
    """统一的 LLM 客户端
    
    自动检测 provider 类型，支持 OpenAI 兼容 API 和 Anthropic API。
    模型名称原样传递给 API，不做任何转换。
    
    Example:
        >>> config = LLMConfig(
        ...     model="openai/gpt-4o-mini",
        ...     api_base="https://your-api.com/v1",
        ...     api_key="your-key",
        ... )
        >>> client = LLMClient(config)
        >>> response = await client.complete("Hello!")
        >>> print(response)
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """初始化 LLM 客户端
        
        Args:
            config: LLM 配置，None 则从全局 analyzer 配置加载
        """
        self.config = config or LLMConfig.from_analyzer_config()
        self._provider: Optional[BaseProvider] = None
    
    @property
    def provider(self) -> BaseProvider:
        """获取 provider 实例"""
        if self._provider is None:
            self._provider = get_provider(self.config)
        return self._provider
    
    async def close(self):
        """关闭客户端"""
        if self._provider:
            await self._provider.close()
            self._provider = None
    
    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
    ) -> list[dict[str, Any]]:
        """构建消息列表"""
        messages: list[dict[str, Any]] = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": prompt})
        
        return messages
    
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """异步完成文本生成
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            history: 历史消息
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大输出
            **kwargs: 传递给 API 的额外参数
            
        Returns:
            生成的文本
        """
        messages = self._build_messages(prompt, system_prompt, history)
        return await self.provider.complete(messages, temperature, max_tokens, **kwargs)
    
    async def complete_with_messages(
        self,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """使用消息列表完成生成
        
        Args:
            messages: 消息列表
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大输出
            **kwargs: 额外参数
            
        Returns:
            生成的文本
        """
        return await self.provider.complete(messages, temperature, max_tokens, **kwargs)
    
    async def complete_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式生成文本
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            history: 历史消息
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大输出
            **kwargs: 额外参数
            
        Yields:
            生成的文本片段
        """
        messages = self._build_messages(prompt, system_prompt, history)
        async for chunk in self.provider.complete_stream(
            messages, temperature, max_tokens, **kwargs
        ):
            yield chunk


# =============================================================================
# 全局客户端工厂
# =============================================================================

_analyzer_client: Optional[LLMClient] = None


def get_analyzer_client(config: Optional[LLMConfig] = None) -> LLMClient:
    """获取分析用 LLM 客户端（单例模式）
    
    用于 workflow 提取、反思等分析任务。
    
    Args:
        config: 配置，None 则从 analyzer 配置加载
        
    Returns:
        LLM 客户端实例
    """
    global _analyzer_client
    
    if _analyzer_client is None or config is not None:
        _analyzer_client = LLMClient(config)
    
    return _analyzer_client


def reset_clients():
    """重置全局客户端（主要用于测试）"""
    global _analyzer_client
    _analyzer_client = None
