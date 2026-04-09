"""
Base Transformer - 协议转换器基类

参考 claude-code-router 的 Transformer 设计模式。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from .unified import UnifiedRequest, UnifiedResponse


class Transformer(ABC):
    """协议转换器抽象基类
    
    每个 Transformer 负责一种协议的双向转换：
    - transform_request: 原始请求 → UnifiedRequest
    - transform_response: UnifiedResponse → 原始响应格式
    - detect: 检测请求是否属于该协议
    """
    
    name: str = "base"
    
    @abstractmethod
    def detect(self, request: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """检测请求是否属于该协议
        
        Args:
            request: 原始请求体
            headers: HTTP 头
            
        Returns:
            如果该转换器应处理此请求则返回 True
        """
        pass
    
    @abstractmethod
    def transform_request(
        self, 
        request: Dict[str, Any], 
        headers: Dict[str, str]
    ) -> UnifiedRequest:
        """将原始请求转换为统一格式
        
        Args:
            request: 原始请求体
            headers: HTTP 头
            
        Returns:
            UnifiedRequest 对象
        """
        pass
    
    @abstractmethod
    def transform_response(
        self,
        response: UnifiedResponse,
        original_request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """将统一响应转换回原始协议格式
        
        Args:
            response: UnifiedResponse 对象
            original_request: 原始请求（用于上下文）
            
        Returns:
            原始协议格式的响应
        """
        pass
    
    def get_client_type(self, headers: Dict[str, str]) -> str:
        """从 headers 检测客户端类型
        
        Args:
            headers: HTTP 头
            
        Returns:
            客户端类型字符串
        """
        user_agent = headers.get("user-agent", "").lower()
        
        if "claude-code" in user_agent or "claude" in user_agent:
            return "claude-code"
        elif "vscode" in user_agent or "copilot" in user_agent:
            return "vscode-copilot"
        elif "cursor" in user_agent:
            return "cursor"
        else:
            return "unknown"


class TransformerRegistry:
    """转换器注册表
    
    管理所有已注册的 Transformer，并根据请求自动选择合适的转换器。
    """
    
    def __init__(self):
        self._transformers: List[Transformer] = []
        self._transformer_map: Dict[str, Transformer] = {}
    
    def register(self, transformer: Transformer):
        """注册转换器
        
        Args:
            transformer: Transformer 实例
        """
        self._transformers.append(transformer)
        self._transformer_map[transformer.name] = transformer
    
    def get_transformer(
        self, 
        request: Dict[str, Any], 
        headers: Dict[str, str]
    ) -> Optional[Transformer]:
        """获取适合该请求的转换器
        
        Args:
            request: 原始请求体
            headers: HTTP 头
            
        Returns:
            Transformer 实例或 None
        """
        for transformer in self._transformers:
            if transformer.detect(request, headers):
                return transformer
        return None
    
    def get_by_name(self, name: str) -> Optional[Transformer]:
        """按名称获取转换器
        
        Args:
            name: 转换器名称
            
        Returns:
            Transformer 实例或 None
        """
        return self._transformer_map.get(name)
    
    def list_transformers(self) -> List[str]:
        """列出所有已注册的转换器名称"""
        return list(self._transformer_map.keys())


# =============================================================================
# 全局注册表
# =============================================================================

_registry = TransformerRegistry()


def get_registry() -> TransformerRegistry:
    """获取全局转换器注册表"""
    return _registry


def register_transformer(transformer: Transformer):
    """在全局注册表中注册转换器"""
    _registry.register(transformer)
