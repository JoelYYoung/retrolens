"""
Unified Message Format - 统一消息格式

所有协议的内部表示，用于：
- 存储和分析
- 协议之间的转换
- 工作流提取

参考 claude-code-router 的设计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal, Union
from datetime import datetime
import json


# =============================================================================
# Content Block Types
# =============================================================================

@dataclass
class TextBlock:
    """文本内容块"""
    type: Literal["text"] = "text"
    text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "text": self.text}


@dataclass
class ImageBlock:
    """图片内容块"""
    type: Literal["image"] = "image"
    source_type: Literal["base64", "url"] = "base64"
    media_type: str = "image/png"
    data: str = ""  # base64 data or URL
    
    def to_dict(self) -> Dict[str, Any]:
        if self.source_type == "base64":
            return {
                "type": self.type,
                "source": {
                    "type": "base64",
                    "media_type": self.media_type,
                    "data": self.data
                }
            }
        else:
            return {
                "type": self.type,
                "source": {
                    "type": "url",
                    "url": self.data
                }
            }


@dataclass
class ToolUseBlock:
    """工具调用块"""
    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "input": self.input
        }


@dataclass
class ToolResultBlock:
    """工具结果块"""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "tool_use_id": self.tool_use_id,
            "content": self.content,
            "is_error": self.is_error
        }


@dataclass
class ThinkingBlock:
    """思维/推理块（用于支持 thinking 的模型）"""
    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type, "thinking": self.thinking}
        if self.signature:
            result["signature"] = self.signature
        return result


# 所有内容块的联合类型
ContentBlock = Union[TextBlock, ImageBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock]


def content_block_from_dict(data: Dict[str, Any]) -> ContentBlock:
    """从字典创建 ContentBlock"""
    block_type = data.get("type", "text")
    
    if block_type == "text":
        return TextBlock(text=data.get("text", ""))
    
    elif block_type == "image":
        source = data.get("source", {})
        return ImageBlock(
            source_type=source.get("type", "base64"),
            media_type=source.get("media_type", "image/png"),
            data=source.get("data", "") or source.get("url", "")
        )
    
    elif block_type == "tool_use":
        return ToolUseBlock(
            id=data.get("id", ""),
            name=data.get("name", ""),
            input=data.get("input", {})
        )
    
    elif block_type == "tool_result":
        content = data.get("content", "")
        if isinstance(content, list):
            # 从结构化内容中提取文本
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
            content = "\n".join(parts)
        return ToolResultBlock(
            tool_use_id=data.get("tool_use_id", ""),
            content=str(content),
            is_error=data.get("is_error", False)
        )
    
    elif block_type == "thinking":
        return ThinkingBlock(
            thinking=data.get("thinking", ""),
            signature=data.get("signature", "")
        )
    
    else:
        # 默认为文本
        return TextBlock(text=str(data))


# =============================================================================
# Tool Definition
# =============================================================================

@dataclass
class ToolDefinition:
    """工具/函数定义"""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }
    
    @classmethod
    def from_anthropic(cls, data: Dict[str, Any]) -> "ToolDefinition":
        """从 Anthropic 工具格式创建"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            input_schema=data.get("input_schema", {})
        )
    
    @classmethod
    def from_openai(cls, data: Dict[str, Any]) -> "ToolDefinition":
        """从 OpenAI 工具格式创建"""
        func = data.get("function", {})
        return cls(
            name=func.get("name", ""),
            description=func.get("description", ""),
            input_schema=func.get("parameters", {})
        )


# =============================================================================
# Token Usage
# =============================================================================

@dataclass
class TokenUsage:
    """Token 使用统计"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens
        }
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# =============================================================================
# Unified Message
# =============================================================================

@dataclass
class UnifiedMessage:
    """统一消息格式
    
    支持的角色：
    - user: 用户消息（可包含文本、图片、工具结果）
    - assistant: 助手消息（可包含文本、工具调用、思维）
    - system: 系统消息
    - tool: 工具结果消息（OpenAI 风格）
    """
    role: Literal["user", "assistant", "system", "tool"]
    content: List[ContentBlock] = field(default_factory=list)
    
    # For tool messages (OpenAI style)
    tool_call_id: Optional[str] = None
    
    # Metadata
    name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"role": self.role}
        
        if self.content:
            if len(self.content) == 1 and isinstance(self.content[0], TextBlock):
                # 单个文本块 - 使用字符串格式
                result["content"] = self.content[0].text
            else:
                result["content"] = [block.to_dict() for block in self.content]
        
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        
        if self.name:
            result["name"] = self.name
        
        return result
    
    def get_text(self) -> str:
        """提取消息中的所有文本内容"""
        texts = []
        for block in self.content:
            if isinstance(block, TextBlock):
                texts.append(block.text)
            elif isinstance(block, ThinkingBlock):
                texts.append(f"[Thinking: {block.thinking}]")
        return "\n".join(texts)
    
    def get_tool_calls(self) -> List[ToolUseBlock]:
        """提取消息中的所有工具调用"""
        return [block for block in self.content if isinstance(block, ToolUseBlock)]
    
    def get_tool_results(self) -> List[ToolResultBlock]:
        """提取消息中的所有工具结果"""
        return [block for block in self.content if isinstance(block, ToolResultBlock)]


# =============================================================================
# Unified Request
# =============================================================================

@dataclass
class UnifiedRequest:
    """统一 API 请求格式"""
    messages: List[UnifiedMessage] = field(default_factory=list)
    system: Optional[str] = None
    tools: List[ToolDefinition] = field(default_factory=list)
    model: str = ""
    stream: bool = False
    max_tokens: int = 4096
    temperature: float = 1.0
    
    # Thinking 配置（用于 Claude）
    thinking_enabled: bool = False
    thinking_budget_tokens: Optional[int] = None
    
    # 原始协议信息
    protocol: Literal["anthropic", "openai", "unknown"] = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 时间戳
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "messages": [msg.to_dict() for msg in self.messages],
            "model": self.model,
            "stream": self.stream,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "protocol": self.protocol,
            "timestamp": self.timestamp,
        }
        
        if self.system:
            result["system"] = self.system
        
        if self.tools:
            result["tools"] = [tool.to_dict() for tool in self.tools]
        
        if self.thinking_enabled:
            result["thinking"] = {
                "enabled": True,
                "budget_tokens": self.thinking_budget_tokens
            }
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        return result
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# =============================================================================
# Unified Response
# =============================================================================

@dataclass
class UnifiedResponse:
    """统一 API 响应格式"""
    id: str = ""
    content: List[ContentBlock] = field(default_factory=list)
    stop_reason: Literal["end_turn", "max_tokens", "tool_use", "stop_sequence", "error"] = "end_turn"
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    
    # 原始协议信息
    protocol: Literal["anthropic", "openai", "unknown"] = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 时间戳
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 错误信息
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "content": [block.to_dict() for block in self.content],
            "stop_reason": self.stop_reason,
            "usage": self.usage.to_dict(),
            "model": self.model,
            "protocol": self.protocol,
            "timestamp": self.timestamp,
        }
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        if self.error:
            result["error"] = self.error
        
        return result
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    def get_text(self) -> str:
        """提取响应中的所有文本内容"""
        texts = []
        for block in self.content:
            if isinstance(block, TextBlock):
                texts.append(block.text)
        return "\n".join(texts)
    
    def get_tool_calls(self) -> List[ToolUseBlock]:
        """提取响应中的所有工具调用"""
        return [block for block in self.content if isinstance(block, ToolUseBlock)]
