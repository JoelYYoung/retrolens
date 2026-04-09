"""
Anthropic Transformer - Convert Anthropic Messages API format

支持 Claude Code 等客户端使用的 Anthropic Messages API 格式。
"""

from typing import Any, Dict, List
import uuid

from .base import Transformer
from .unified import (
    ContentBlock,
    TextBlock,
    ToolDefinition,
    ToolResultBlock,
    UnifiedMessage,
    UnifiedRequest,
    UnifiedResponse,
    content_block_from_dict,
)


class AnthropicTransformer(Transformer):
    """
    Transformer for Anthropic Messages API
    
    处理 Claude Code 等客户端使用的 Anthropic API 格式。
    
    Anthropic 格式特点：
    - system 是独立字段（可以是字符串或结构化数组）
    - messages 使用 content 数组（支持 text, image, tool_use, tool_result）
    - tools 使用 input_schema
    - 支持 thinking 块
    
    Example request format:
    
    .. code-block:: json
    
        {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "system": "You are a helpful assistant.",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
            ],
            "tools": [
                {"name": "read_file", "input_schema": {...}}
            ],
            "thinking": {"type": "enabled", "budget_tokens": 10000}
        }
    """
    
    name = "anthropic"
    
    def detect(self, request: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Detect Anthropic API format
        
        检测特征：
        1. 有 system 字段（通常是字符串或数组）
        2. messages 中的 content 是数组且包含 type 字段
        3. User-Agent 包含 claude 相关
        4. tools 使用 input_schema 而非 function
        5. 有 thinking 配置字段
        
        Args:
            request: 原始请求字典
            headers: HTTP 请求头
            
        Returns:
            True 如果检测到 Anthropic 格式
        """
        # Check User-Agent for strong indicators
        user_agent = headers.get("user-agent", "").lower()
        if "claude" in user_agent or "anthropic" in user_agent:
            return True
        
        # Check x-api-key header (Anthropic uses this pattern)
        if "x-api-key" in headers:
            return True
        
        # Check for Anthropic-specific fields
        if "system" in request:
            system = request.get("system")
            # Anthropic system can be string or structured array
            if isinstance(system, str):
                return True
            if isinstance(system, list) and any(
                isinstance(item, dict) and "type" in item 
                for item in system
            ):
                return True
        
        # Check message content structure
        messages = request.get("messages", [])
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") in [
                        "text", "image", "tool_use", "tool_result", "thinking"
                    ]:
                        return True
        
        # Check tools format (input_schema is Anthropic-specific)
        tools = request.get("tools", [])
        for tool in tools:
            if isinstance(tool, dict) and "input_schema" in tool:
                return True
        
        # Check for thinking config
        if "thinking" in request:
            return True
        
        return False
    
    def transform_request(
        self, 
        request: Dict[str, Any], 
        headers: Dict[str, str]
    ) -> UnifiedRequest:
        """
        Transform Anthropic request to unified format
        
        Args:
            request: 原始 Anthropic 格式请求
            headers: HTTP 请求头
            
        Returns:
            统一格式的请求对象
        """
        # Extract system prompt
        system_prompt = self._extract_system_prompt(request.get("system"))
        
        # Transform messages
        messages = self._transform_messages(request.get("messages", []))
        
        # Transform tools
        tools = [
            ToolDefinition.from_anthropic(tool) 
            for tool in request.get("tools", [])
        ]
        
        # Extract thinking config
        thinking = request.get("thinking", {})
        thinking_enabled = thinking.get("type") == "enabled" if thinking else False
        thinking_budget = thinking.get("budget_tokens") if thinking else None
        
        return UnifiedRequest(
            messages=messages,
            system=system_prompt,
            tools=tools,
            model=request.get("model", ""),
            stream=request.get("stream", False),
            max_tokens=request.get("max_tokens", 4096),
            temperature=request.get("temperature", 1.0),
            thinking_enabled=thinking_enabled,
            thinking_budget_tokens=thinking_budget,
            protocol="anthropic",
            metadata={
                "original_request": request,
                "client_type": self.get_client_type(headers),
            }
        )
    
    def transform_response(
        self,
        response: UnifiedResponse,
        original_request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transform unified response back to Anthropic format
        
        Args:
            response: 统一格式的响应对象
            original_request: 原始请求（用于获取 model 等信息）
            
        Returns:
            Anthropic 格式的响应字典
        """
        # Build content array
        content = []
        for block in response.content:
            content.append(block.to_dict())
        
        return {
            "id": response.id or f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "content": content,
            "model": response.model or original_request.get("model", ""),
            "stop_reason": response.stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_read_input_tokens": response.usage.cache_read_input_tokens,
                "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
            }
        }
    
    def _extract_system_prompt(self, system: Any) -> str:
        """
        Extract system prompt from Anthropic format
        
        Anthropic 支持两种 system 格式：
        1. 字符串: "You are a helpful assistant."
        2. 结构化数组: [{"type": "text", "text": "..."}, ...]
        
        Args:
            system: 原始 system 字段值
            
        Returns:
            提取的系统提示文本
        """
        if not system:
            return ""
        
        if isinstance(system, str):
            return system
        
        if isinstance(system, list):
            parts = []
            for item in system:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        
        return str(system)
    
    def _transform_messages(
        self, 
        messages: List[Dict[str, Any]]
    ) -> List[UnifiedMessage]:
        """
        Transform Anthropic messages to unified format
        
        Args:
            messages: Anthropic 格式的消息列表
            
        Returns:
            统一格式的消息列表
        """
        result = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Handle string content (simple text message)
            if isinstance(content, str):
                result.append(UnifiedMessage(
                    role=role,
                    content=[TextBlock(text=content)]
                ))
                continue
            
            # Handle structured content (array of content blocks)
            if isinstance(content, list):
                blocks: List[ContentBlock] = []
                for item in content:
                    if isinstance(item, dict):
                        blocks.append(content_block_from_dict(item))
                    elif isinstance(item, str):
                        blocks.append(TextBlock(text=item))
                
                result.append(UnifiedMessage(
                    role=role,
                    content=blocks
                ))
        
        return result
