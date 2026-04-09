"""
OpenAI Transformer - Convert OpenAI Chat Completions API format

支持 VS Code Copilot、Cursor、ChatGPT 等客户端使用的 OpenAI API 格式。
"""

from typing import Any, Dict, List, Optional
import json
import time
import uuid

from .base import Transformer
from .unified import (
    ContentBlock,
    ImageBlock,
    TextBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
    UnifiedMessage,
    UnifiedRequest,
    UnifiedResponse,
)


class OpenAITransformer(Transformer):
    """
    Transformer for OpenAI Chat Completions API
    
    处理 VS Code Copilot、Cursor 等客户端使用的 OpenAI API 格式。
    
    OpenAI 格式特点：
    - system 消息是 messages 数组的一部分（role="system"）
    - messages 使用 content 字符串或结构化数组
    - tools 使用 function.parameters（而非 input_schema）
    - tool_calls 在 assistant message 中
    - tool 角色用于返回工具结果
    
    Example request format:
    
    .. code-block:: json
    
        {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"}
            ],
            "tools": [
                {"type": "function", "function": {"name": "...", "parameters": {...}}}
            ]
        }
    """
    
    name = "openai"
    
    def detect(self, request: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Detect OpenAI API format
        
        检测特征：
        1. 没有独立的 system 字段
        2. messages 中有 role="system" 的消息
        3. tools 使用 function 结构
        4. User-Agent 包含 openai/copilot/cursor 相关
        5. 使用 Authorization: Bearer 头
        
        Args:
            request: 原始请求字典
            headers: HTTP 请求头
            
        Returns:
            True 如果检测到 OpenAI 格式
        """
        # Check User-Agent for strong indicators
        user_agent = headers.get("user-agent", "").lower()
        if any(kw in user_agent for kw in ["openai", "copilot", "cursor", "vscode"]):
            return True
        
        # Check Authorization header pattern
        auth = headers.get("authorization", "")
        if auth.startswith("Bearer ") and "x-api-key" not in headers:
            # OpenAI uses Bearer token, Anthropic uses x-api-key
            pass  # Weak signal, continue checking
        
        # No separate system field is a strong indicator
        if "system" not in request:
            messages = request.get("messages", [])
            
            # Check for system message in messages array (OpenAI-style)
            for msg in messages:
                if msg.get("role") == "system":
                    return True
            
            # Check for tool message role (OpenAI-specific)
            for msg in messages:
                if msg.get("role") == "tool":
                    return True
            
            # Check for tool_calls in assistant messages
            for msg in messages:
                if msg.get("role") == "assistant" and "tool_calls" in msg:
                    return True
        
        # Check tools format (function wrapper is OpenAI-specific)
        tools = request.get("tools", [])
        if tools and isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict) and "function" in tool:
                    return True
        
        return False
    
    def transform_request(
        self, 
        request: Dict[str, Any], 
        headers: Dict[str, str]
    ) -> UnifiedRequest:
        """
        Transform OpenAI request to unified format
        
        Args:
            request: 原始 OpenAI 格式请求
            headers: HTTP 请求头
            
        Returns:
            统一格式的请求对象
        """
        messages = request.get("messages", [])
        
        # Extract system prompt and transform messages
        system_prompt: Optional[str] = None
        unified_messages: List[UnifiedMessage] = []
        
        for msg in messages:
            role = msg.get("role", "user")
            
            if role == "system":
                # Extract system prompt from system message
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_prompt = content
                elif isinstance(content, list):
                    parts = [
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    ]
                    system_prompt = "\n".join(parts)
                continue
            
            # Transform other messages
            unified_msg = self._transform_message(msg)
            if unified_msg:
                unified_messages.append(unified_msg)
        
        # Transform tools
        tools = [
            ToolDefinition.from_openai(tool)
            for tool in request.get("tools", [])
            if isinstance(tool, dict) and "function" in tool
        ]
        
        # OpenAI uses max_tokens or max_completion_tokens
        max_tokens = (
            request.get("max_tokens") or 
            request.get("max_completion_tokens") or 
            4096
        )
        
        return UnifiedRequest(
            messages=unified_messages,
            system=system_prompt,
            tools=tools,
            model=request.get("model", ""),
            stream=request.get("stream", False),
            max_tokens=max_tokens,
            temperature=request.get("temperature", 1.0),
            protocol="openai",
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
        Transform unified response back to OpenAI format
        
        Args:
            response: 统一格式的响应对象
            original_request: 原始请求（用于获取 model 等信息）
            
        Returns:
            OpenAI 格式的响应字典
        """
        # Build message content
        message: Dict[str, Any] = {
            "role": "assistant",
        }
        
        # Extract text content and tool calls
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        
        for block in response.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input, ensure_ascii=False)
                    }
                })
        
        # Set content (None if no text, to match OpenAI behavior)
        message["content"] = "\n".join(text_parts) if text_parts else None
        
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        # Map stop reason to OpenAI finish_reason
        finish_reason = self._map_stop_reason(response.stop_reason)
        
        return {
            "id": response.id or f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.model or original_request.get("model", ""),
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        }
    
    def _transform_message(self, msg: Dict[str, Any]) -> Optional[UnifiedMessage]:
        """
        Transform a single OpenAI message to unified format
        
        Args:
            msg: OpenAI 格式的单条消息
            
        Returns:
            统一格式的消息，如果消息为空则返回 None
        """
        role = msg.get("role", "user")
        content = msg.get("content")
        
        # Handle tool messages (tool result)
        if role == "tool":
            return UnifiedMessage(
                role="user",  # Convert to user with tool_result block
                content=[ToolResultBlock(
                    tool_use_id=msg.get("tool_call_id", ""),
                    content=str(content) if content else "",
                )],
                tool_call_id=msg.get("tool_call_id"),
            )
        
        blocks: List[ContentBlock] = []
        
        # Handle string content
        if isinstance(content, str):
            blocks.append(TextBlock(text=content))
        
        # Handle structured content array
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "text")
                    if item_type == "text":
                        blocks.append(TextBlock(text=item.get("text", "")))
                    elif item_type == "image_url":
                        # OpenAI uses image_url format
                        image_url = item.get("image_url", {})
                        url = image_url.get("url", "")
                        if url.startswith("data:"):
                            # Parse data URL: data:image/png;base64,xxx
                            parts = url.split(",", 1)
                            if len(parts) == 2:
                                header = parts[0]
                                data = parts[1]
                                # Extract media type from header
                                media_type = header.split(";")[0].replace("data:", "")
                                blocks.append(ImageBlock(
                                    source_type="base64",
                                    media_type=media_type,
                                    data=data
                                ))
                        else:
                            # Direct URL
                            blocks.append(ImageBlock(
                                source_type="url",
                                data=url
                            ))
                elif isinstance(item, str):
                    blocks.append(TextBlock(text=item))
        
        # Handle None content for assistant messages (may have only tool_calls)
        elif content is None and role == "assistant":
            pass  # Will handle tool_calls below
        
        # Handle tool_calls in assistant messages
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            if tc.get("type") == "function":
                func = tc.get("function", {})
                arguments = func.get("arguments", "{}")
                
                # Parse arguments JSON
                try:
                    input_data = json.loads(arguments)
                except json.JSONDecodeError:
                    input_data = {"raw": arguments}
                
                blocks.append(ToolUseBlock(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    input=input_data
                ))
        
        # Return None for empty assistant messages without tool_calls
        if not blocks and role == "assistant" and not tool_calls:
            return None
        
        return UnifiedMessage(role=role, content=blocks)
    
    def _map_stop_reason(self, stop_reason: str) -> str:
        """
        Map unified stop reason to OpenAI finish_reason
        
        Args:
            stop_reason: 统一格式的停止原因
            
        Returns:
            OpenAI 格式的 finish_reason
        """
        mapping = {
            "end_turn": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
            "stop_sequence": "stop",
            "error": "stop",
        }
        return mapping.get(stop_reason, "stop")
