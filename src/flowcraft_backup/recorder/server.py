"""
Recording Proxy Server - 记录 Agent 会话的代理服务器

这是一个 FastAPI 服务器，作为 LLM API 的代理，记录所有请求和响应。
支持 Anthropic 和 OpenAI 协议，并能透明转发到后端 API。

Usage:
    agi record start --port 8080 --backend openai
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, AsyncIterator, Dict, Generator, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx

from ..config import get_config, Config

# Lazy imports to avoid startup overhead
_openai_client = None
_storage = None
_transformer_registry = None


def get_storage():
    """Lazy load storage"""
    global _storage
    if _storage is None:
        from .storage import SessionStorage
        config = get_config()
        _storage = SessionStorage(base_path=config.storage.logs_dir)
    return _storage


def get_transformer_registry():
    """Lazy load transformer registry"""
    global _transformer_registry
    if _transformer_registry is None:
        from .transformers import get_registry
        _transformer_registry = get_registry()
    return _transformer_registry


def get_openai_client(api_key: str, base_url: Optional[str] = None):
    """Get or create OpenAI client
    
    Args:
        api_key: API key from request headers (preferred for transparent proxy)
        base_url: Override base URL
        
    Note:
        In transparent proxy mode, we always use the request's api_key.
        Config api_key is only used as fallback when request has no key.
    """
    from openai import OpenAI
    
    config = get_config()
    
    # Use provided base_url or config default
    actual_base_url = base_url or config.listener.api_base or "https://api.openai.com/v1"
    
    # Transparent proxy: prefer request's API key, fallback to config
    actual_api_key = api_key or config.listener.api_key or ""
    
    return OpenAI(
        api_key=actual_api_key,
        base_url=actual_base_url,
    )


def get_api_base_url() -> str:
    """Get the API base URL from config"""
    config = get_config()
    return config.listener.api_base or "https://api.openai.com/v1"


async def forward_openai_request(
    api_key: str,
    body: Dict[str, Any],
    stream: bool = False
) -> httpx.Response:
    """Forward request to OpenAI-compatible API using httpx
    
    This gives us full control over headers, avoiding any SDK transformations.
    """
    base_url = get_api_base_url()
    url = f"{base_url}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            url,
            json=body,
            headers=headers,
        )
        return response


def _mask_api_key(api_key: str) -> str:
    """Mask API key for display, showing only prefix and suffix"""
    if len(api_key) <= 12:
        return api_key[:4] + "***"
    return api_key[:8] + "***" + api_key[-6:]


def _get_auth_error_message(api_key: str, base_url: str) -> str:
    """Generate a detailed error message for authentication failures"""
    masked_key = _mask_api_key(api_key)
    
    lines = [
        "=" * 60,
        "Authentication Failed (401)",
        "=" * 60,
        "",
        "Current Configuration:",
        f"  API Base URL : {base_url}",
        f"  API Key      : {masked_key}",
        "",
    ]
    
    # Provider-specific hints
    if "openrouter.ai" in base_url:
        lines.extend([
            "Expected Key Format: sk-or-v1-...",
            "",
            "Your key doesn't appear to be an OpenRouter key.",
            "Either:",
            "  1. Get an OpenRouter key at: https://openrouter.ai/keys",
            "  2. Or change the API base URL to match your key's provider:",
            "",
            "     flowcraft config set llm.api_base \"YOUR_API_BASE_URL\"",
            "",
            "Common providers:",
            "  - OpenAI:      https://api.openai.com/v1",
            "  - Anthropic:   https://api.anthropic.com/v1",
            "  - Azure:       https://YOUR_RESOURCE.openai.azure.com",
            "  - Custom:      Your own API endpoint",
        ])
    elif "openai.com" in base_url:
        lines.extend([
            "Expected Key Format: sk-...",
            "",
            "Get a valid OpenAI key at: https://platform.openai.com/api-keys",
        ])
    elif "anthropic.com" in base_url:
        lines.extend([
            "Expected Key Format: sk-ant-...",
            "",
            "Get a valid Anthropic key at: https://console.anthropic.com/",
        ])
    else:
        lines.extend([
            "The API key may not be valid for this endpoint.",
            "",
            "To change the API base URL:",
            "  flowcraft config set llm.api_base \"YOUR_API_BASE_URL\"",
        ])
    
    lines.extend([
        "",
        "Config file location: ~/.flowcraft/config.yaml",
        "=" * 60,
    ])
    
    return "\n".join(lines)


async def forward_openai_stream(
    api_key: str,
    body: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Forward streaming request to OpenAI-compatible API"""
    base_url = get_api_base_url()
    url = f"{base_url}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=body, headers=headers) as response:
            if response.status_code == 401:
                error_body = await response.aread()
                error_text = error_body.decode()
                
                # Print detailed error message to console
                error_msg = _get_auth_error_message(api_key, base_url)
                print(f"\n{error_msg}")
                print(f"Backend response: {error_text[:200]}\n")
                
                raise HTTPException(
                    status_code=401,
                    detail=error_msg + f"\n\nBackend response: {error_text}"
                )
            elif response.status_code != 200:
                error_body = await response.aread()
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_body.decode()
                )
            async for line in response.aiter_lines():
                if line:
                    yield line + "\n"


# =============================================================================
# Session Management
# =============================================================================

_current_session_id: Optional[str] = None
_last_request_time: Optional[datetime] = None


def _detect_client_type(user_agent: str, headers: Dict[str, str]) -> str:
    """Detect client type from User-Agent and other headers
    
    Returns a descriptive client name based on known patterns.
    """
    user_agent_lower = user_agent.lower()
    
    # Check common AI coding assistants
    if "claude-code" in user_agent_lower or "claude code" in user_agent_lower:
        return "claude-code"
    if "claude" in user_agent_lower:
        return "claude"
    if "cursor" in user_agent_lower:
        return "cursor"
    if "copilot" in user_agent_lower:
        return "github-copilot"
    if "vscode" in user_agent_lower or "visual studio code" in user_agent_lower:
        return "vscode"
    if "windsurf" in user_agent_lower:
        return "windsurf"
    if "continue" in user_agent_lower:
        return "continue"
    if "aider" in user_agent_lower:
        return "aider"
    
    # Check for common HTTP clients / proxies
    if "httpx" in user_agent_lower or "python" in user_agent_lower:
        return "python-client"
    if "node" in user_agent_lower or "axios" in user_agent_lower:
        return "node-client"
    if "curl" in user_agent_lower:
        return "curl"
    
    # Check custom headers that might indicate the client
    if "x-client-name" in headers:
        return headers["x-client-name"]
    
    # Extract first part of user-agent if available
    if user_agent and "/" in user_agent:
        return user_agent.split("/")[0].lower()[:20]
    
    return "api-client"


def get_or_create_session(
    client: str = "api-client", 
    model: str = "unknown",
    protocol: str = "openai"
) -> str:
    """Get current session or create a new one
    
    Creates a new session if:
    - No current session exists
    - Current session doesn't exist in storage
    - More than 30 minutes since last request
    
    Args:
        client: Client type (claude-code, cursor, etc.)
        model: Model being used
        protocol: API protocol (anthropic, openai)
    """
    global _current_session_id, _last_request_time
    
    storage = get_storage()
    should_create_new = False
    
    if _current_session_id is None:
        # No current session
        should_create_new = True
    else:
        # Check if session still exists
        session = storage.get_session(_current_session_id)
        if session is None:
            should_create_new = True
        elif _last_request_time is not None:
            # Check if 30 minutes have passed since last request
            elapsed = (datetime.now() - _last_request_time).total_seconds()
            if elapsed > 1800:  # 30 minutes
                should_create_new = True
    
    if should_create_new:
        _current_session_id = storage.create_session(
            client=client,
            model=model,
            protocol=protocol,
        )
    
    # Update last request time
    _last_request_time = datetime.now()
    
    return _current_session_id


# =============================================================================
# Format Conversion Helpers
# =============================================================================

def convert_anthropic_to_openai_tools(anthropic_tools: List[Dict]) -> List[Dict]:
    """Convert Anthropic tool definitions to OpenAI format"""
    openai_tools = []
    for tool in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            }
        })
    return openai_tools


def convert_anthropic_to_openai_messages(
    messages: List[Dict], 
    system_prompt: str = ""
) -> List[Dict]:
    """Convert Anthropic message format to OpenAI format"""
    openai_messages = []
    
    # Add system message if present
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # String content
        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue
        
        # Structured content
        if isinstance(content, list):
            if role == "user":
                _process_user_message(content, openai_messages)
            elif role == "assistant":
                _process_assistant_message(content, openai_messages)
    
    return openai_messages


def _process_user_message(content: List[Dict], openai_messages: List[Dict]):
    """Process user message with structured content"""
    tool_results = []
    text_and_media_parts = []
    
    for item in content:
        if not isinstance(item, dict):
            continue
        
        item_type = item.get("type")
        
        if item_type == "tool_result":
            # Tool result
            result_content = item.get("content", "")
            if isinstance(result_content, list):
                parts = []
                for part in result_content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        parts.append(part)
                result_content = "\n".join(parts)
            
            tool_results.append({
                "tool_call_id": item.get("tool_use_id", ""),
                "content": str(result_content),
            })
        
        elif item_type == "text":
            text_and_media_parts.append({
                "type": "text",
                "text": item.get("text", ""),
            })
        
        elif item_type == "image":
            # Handle image content
            source = item.get("source", {})
            if source.get("type") == "base64":
                image_url = f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
            else:
                image_url = source.get("url", "")
            
            text_and_media_parts.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })
    
    # Add tool messages first
    for tr in tool_results:
        openai_messages.append({
            "role": "tool",
            "tool_call_id": tr["tool_call_id"],
            "content": tr["content"],
        })
    
    # Add text/media content as user message
    if text_and_media_parts:
        if len(text_and_media_parts) == 1 and text_and_media_parts[0].get("type") == "text":
            openai_messages.append({
                "role": "user",
                "content": text_and_media_parts[0].get("text", ""),
            })
        else:
            openai_messages.append({
                "role": "user",
                "content": text_and_media_parts,
            })


def _process_assistant_message(content: List[Dict], openai_messages: List[Dict]):
    """Process assistant message with structured content"""
    assistant_msg: Dict[str, Any] = {"role": "assistant"}
    text_parts = []
    tool_calls = []
    
    for item in content:
        if not isinstance(item, dict):
            continue
        
        item_type = item.get("type")
        
        if item_type == "text":
            text_parts.append(item.get("text", ""))
        
        elif item_type == "tool_use":
            tool_input = item.get("input", {})
            tool_calls.append({
                "id": item.get("id", ""),
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": json.dumps(tool_input, ensure_ascii=False),
                }
            })
    
    # Set content
    if text_parts:
        assistant_msg["content"] = "\n".join(text_parts)
    else:
        assistant_msg["content"] = None
    
    # Set tool calls
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    
    openai_messages.append(assistant_msg)


def map_finish_reason_to_stop_reason(finish_reason: str) -> str:
    """Map OpenAI finish_reason to Anthropic stop_reason"""
    mapping = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "stop_sequence",
        "function_call": "tool_use",
    }
    return mapping.get(finish_reason, "end_turn")


def build_anthropic_usage(openai_usage: Optional[Dict]) -> Dict:
    """Build Anthropic usage object from OpenAI usage"""
    if not openai_usage:
        return {"input_tokens": 0, "output_tokens": 0}
    
    prompt_tokens = openai_usage.get("prompt_tokens", 0)
    cached_tokens = 0
    
    prompt_details = openai_usage.get("prompt_tokens_details", {})
    if prompt_details:
        cached_tokens = prompt_details.get("cached_tokens", 0)
    
    return {
        "input_tokens": prompt_tokens - cached_tokens,
        "output_tokens": openai_usage.get("completion_tokens", 0),
        "cache_read_input_tokens": cached_tokens,
    }


def estimate_token_count(text: str) -> int:
    """Rough token count estimation (~4 chars per token)"""
    if not text:
        return 0
    return max(1, len(text) // 4)


def count_message_tokens(
    messages: List[Dict], 
    system: Any = None, 
    tools: List[Dict] = None
) -> int:
    """Estimate total tokens for a message request"""
    total = 0
    
    # Count system prompt
    if system:
        if isinstance(system, str):
            total += estimate_token_count(system)
        elif isinstance(system, list):
            for item in system:
                if isinstance(item, dict) and item.get("type") == "text":
                    total += estimate_token_count(item.get("text", ""))
    
    # Count messages
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_token_count(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        total += estimate_token_count(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        result = item.get("content", "")
                        if isinstance(result, str):
                            total += estimate_token_count(result)
                    elif item.get("type") == "tool_use":
                        total += estimate_token_count(json.dumps(item.get("input", {})))
        total += 4  # Overhead for role/structure
    
    # Count tools
    if tools:
        for tool in tools:
            total += estimate_token_count(tool.get("name", ""))
            total += estimate_token_count(tool.get("description", ""))
            total += estimate_token_count(json.dumps(tool.get("input_schema", {})))
    
    return total


# =============================================================================
# FastAPI Application
# =============================================================================

def create_app() -> FastAPI:
    """Create FastAPI application"""
    app = FastAPI(
        title="Agent Inspector Recorder",
        description="Recording proxy for LLM API calls",
        version="0.2.0",
    )
    
    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request):
        """Token counting endpoint (Anthropic API)"""
        body = await request.json()
        
        messages = body.get("messages", [])
        system = body.get("system")
        tools = body.get("tools", [])
        
        input_tokens = count_message_tokens(messages, system, tools)
        
        return {"input_tokens": input_tokens}
    
    @app.post("/v1/messages")
    async def anthropic_messages_proxy(request: Request):
        """Anthropic Messages API proxy endpoint"""
        body = await request.json()
        headers_in = dict(request.headers)
        
        # Get API key from headers
        auth_header = headers_in.get("authorization", "")
        x_api_key = headers_in.get("x-api-key", "")
        # Try Authorization header first (Bearer token)
        api_key = ""
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                api_key = auth_header[7:]  # Remove "Bearer " prefix
            else:
                api_key = auth_header
        
        # Try x-api-key header (Anthropic style)
        if not api_key and x_api_key:
            api_key = x_api_key
        
        # Fallback to config (not recommended for proxy mode)
        if not api_key:
            config = get_config()
            api_key = config.listener.api_key or ""
        
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required. Please provide Authorization header or x-api-key header.")
        
        # Detect client type from User-Agent and other headers
        user_agent = headers_in.get("user-agent", "").lower()
        client_type = _detect_client_type(user_agent, headers_in)
        
        model = body.get("model", "unknown")
        
        # Get or create session (Anthropic protocol)
        session_id = get_or_create_session(client=client_type, model=model, protocol="anthropic")
        storage = get_storage()
        
        # Store request
        print(f"[{datetime.now().isoformat()}] Session {session_id}: Request from {client_type}")
        sequence = storage.save_request(session_id, body)
        print(f"  -> Request #{sequence}, Model: {model}, Messages: {len(body.get('messages', []))}")
        
        # Convert system prompt
        system_prompt = body.get("system", "")
        if isinstance(system_prompt, list):
            parts = []
            for item in system_prompt:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            system_prompt = "\n".join(parts)
        
        # Convert to OpenAI format
        messages = body.get("messages", [])
        openai_messages = convert_anthropic_to_openai_messages(messages, system_prompt)
        
        # Get OpenAI client
        client = get_openai_client(api_key)
        
        # Convert tools
        openai_tools = None
        anthropic_tools = body.get("tools", [])
        if anthropic_tools:
            openai_tools = convert_anthropic_to_openai_tools(anthropic_tools)
        
        # Build request params
        create_params = {
            "model": body.get("model", "gpt-4"),
            "messages": openai_messages,
            "max_tokens": body.get("max_tokens", 4096),
        }
        
        if openai_tools:
            create_params["tools"] = openai_tools
        
        # Handle tool_choice
        tool_choice = body.get("tool_choice")
        if tool_choice:
            if isinstance(tool_choice, dict):
                if tool_choice.get("type") == "tool":
                    create_params["tool_choice"] = {
                        "type": "function",
                        "function": {"name": tool_choice.get("name", "")},
                    }
                else:
                    create_params["tool_choice"] = tool_choice.get("type", "auto")
            else:
                create_params["tool_choice"] = tool_choice
        
        is_streaming = body.get("stream", False)
        
        try:
            if is_streaming:
                create_params["stream"] = True
                create_params["stream_options"] = {"include_usage": True}
                
                return StreamingResponse(
                    _generate_anthropic_stream(
                        client, create_params, model, session_id, sequence, storage
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    }
                )
            
            # Non-streaming
            response = client.chat.completions.create(**create_params)
            
            # Convert response to Anthropic format
            anthropic_response = _convert_openai_response_to_anthropic(response, model)
            
            # Store response
            storage.save_response(session_id, sequence, anthropic_response)
            print(f"  <- Response #{sequence}, stop_reason: {anthropic_response['stop_reason']}")
            
            return anthropic_response
            
        except Exception as e:
            print(f"  -> API Error: {e}")
            # Extract status code from OpenAI error if available
            status_code = 500
            error_detail = str(e)
            if hasattr(e, 'status_code'):
                status_code = e.status_code
            if hasattr(e, 'body'):
                error_detail = e.body
            elif hasattr(e, 'message'):
                error_detail = e.message
            raise HTTPException(status_code=status_code, detail=error_detail)
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "0.2.0",
        }
    
    @app.get("/")
    async def root():
        """API root"""
        return {
            "name": "FlowCraft Recorder",
            "description": "Recording proxy for LLM API calls",
            "endpoints": {
                "openai_proxy": "POST /v1/chat/completions - OpenAI API proxy (transparent)",
                "anthropic_proxy": "POST /v1/messages - Anthropic API proxy (with conversion)",
                "health": "GET /health - Health check",
            }
        }
    
    @app.post("/v1/chat/completions")
    async def openai_chat_completions_proxy(request: Request):
        """OpenAI Chat Completions API proxy - transparent forwarding"""
        body = await request.json()
        headers_in = dict(request.headers)
        
        # Get API key - try multiple header names
        auth_header = headers_in.get("authorization", "")
        x_api_key = headers_in.get("x-api-key", "")
        
        api_key = ""
        key_source = "none"
        
        # Try Authorization header first (Bearer token)
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                api_key = auth_header[7:]
                key_source = "authorization (bearer)"
            else:
                api_key = auth_header
                key_source = "authorization (raw)"
        
        # Try x-api-key header
        if not api_key and x_api_key:
            api_key = x_api_key
            key_source = "x-api-key"
        
        # Fallback to config
        if not api_key:
            config = get_config()
            api_key = config.listener.api_key or ""
            key_source = "config"
        
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # Detect client type from User-Agent and other headers
        user_agent = headers_in.get("user-agent", "").lower()
        client_type = _detect_client_type(user_agent, headers_in)
        
        model = body.get("model", "unknown")
        
        # Get or create session (OpenAI protocol)
        session_id = get_or_create_session(client=client_type, model=model, protocol="openai")
        storage = get_storage()
        
        # Store request
        print(f"[{datetime.now().isoformat()}] Session {session_id}: OpenAI format request from {client_type}")
        sequence = storage.save_request(session_id, body)
        print(f"  -> Request #{sequence}, Model: {model}, Messages: {len(body.get('messages', []))}")
        
        is_streaming = body.get("stream", False)
        
        try:
            if is_streaming:
                # Streaming mode - use httpx for full control
                body["stream_options"] = {"include_usage": True}
                
                async def generate_stream():
                    """Forward streaming response"""
                    collected_response = {"choices": [], "usage": {}}
                    async for line in forward_openai_stream(api_key, body):
                        yield line
                        # Parse SSE data for storage
                        if line.startswith("data: ") and not line.strip().endswith("[DONE]"):
                            try:
                                chunk = json.loads(line[6:])
                                if chunk.get("usage"):
                                    collected_response["usage"] = chunk["usage"]
                            except:
                                pass
                    # Store response summary
                    storage.save_response(session_id, sequence, {"type": "stream", **collected_response})
                
                return StreamingResponse(
                    generate_stream(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    }
                )
            
            # Non-streaming - use httpx for full control
            response = await forward_openai_request(api_key, body)
            
            if response.status_code == 401:
                error_msg = _get_auth_error_message(api_key, get_api_base_url())
                print(f"\n{error_msg}")
                print(f"Backend response: {response.text[:200]}\n")
                raise HTTPException(status_code=401, detail=error_msg + f"\n\nBackend response: {response.text}")
            elif response.status_code != 200:
                print(f"  -> API Error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            response_dict = response.json()
            
            # Store response
            storage.save_response(session_id, sequence, response_dict)
            finish_reason = response_dict.get("choices", [{}])[0].get("finish_reason", "N/A")
            print(f"  <- Response #{sequence}, finish_reason: {finish_reason}")
            
            return response_dict
            
        except Exception as e:
            print(f"  -> API Error: {e}")
            status_code = getattr(e, 'status_code', 500)
            error_detail = getattr(e, 'body', None) or getattr(e, 'message', None) or str(e)
            raise HTTPException(status_code=status_code, detail=error_detail)
    
    @app.post("/")
    async def root_post(request: Request):
        """Handle POST to root - detect format and forward to appropriate endpoint
        
        Format Detection Logic:
        - Anthropic format indicators:
          - Has "system" at top level (string or list, not in messages)
          - Content blocks with Anthropic-specific types: "tool_use", "tool_result", "image" (with source.data)
        - OpenAI format indicators:
          - No top-level "system" (system is a message with role="system")
          - Content uses OpenAI types: "text", "image_url" (with image_url.url)
          
        Note: Both formats can have structured content as list of dicts with "type",
        but the types differ. CCR (Claude Code Router) sends OpenAI format with
        {"type": "text"} and {"type": "image_url"} structures.
        """
        body_bytes = await request.body()
        body = json.loads(body_bytes)
        
        # Key indicator 1: Anthropic has "system" at top level (not in messages)
        has_top_level_system = "system" in body and body["system"] is not None
        
        # Key indicator 2: Anthropic-specific content block types
        # Anthropic uses: "tool_use", "tool_result", "image" (with source.data field)
        # OpenAI uses: "text", "image_url" (with image_url.url field)
        has_anthropic_content = False
        anthropic_only_types = {"tool_use", "tool_result"}  # These are Anthropic-only
        
        messages = body.get("messages", [])
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type")
                        # Anthropic-only types
                        if item_type in anthropic_only_types:
                            has_anthropic_content = True
                            break
                        # Anthropic image format has "source" with "data" field
                        # OpenAI image format has "image_url" with "url" field
                        if item_type == "image":
                            source = item.get("source", {})
                            if source.get("type") == "base64" or "data" in source:
                                has_anthropic_content = True
                                break
                if has_anthropic_content:
                    break
        
        is_anthropic = has_top_level_system or has_anthropic_content
        
        # Create new request
        scope = request.scope.copy()
        if is_anthropic:
            scope["path"] = "/v1/messages"
            scope["raw_path"] = b"/v1/messages"
        else:
            scope["path"] = "/v1/chat/completions"
            scope["raw_path"] = b"/v1/chat/completions"
        
        async def receive():
            return {"type": "http.request", "body": body_bytes}
        
        new_request = Request(scope, receive)
        
        if is_anthropic:
            return await anthropic_messages_proxy(new_request)
        else:
            return await openai_chat_completions_proxy(new_request)
    
    return app


def _generate_anthropic_stream(
    client,
    create_params: Dict[str, Any],
    model: str,
    session_id: str,
    sequence: int,
    storage,
) -> Generator[str, None, None]:
    """Generate Anthropic SSE format streaming response"""
    message_id = f"msg_{uuid.uuid4().hex[:24]}"
    collected_text = ""
    collected_tool_calls: Dict[str, Dict] = {}
    usage_stats = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
    
    # State tracking
    has_text_started = False
    has_finished = False
    content_index = 0
    current_block_index = -1
    tool_index_to_block: Dict[int, int] = {}
    stop_reason = "end_turn"
    
    def next_block_index() -> int:
        nonlocal content_index
        idx = content_index
        content_index += 1
        return idx
    
    # Send message_start
    message_start = {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    }
    yield f"event: message_start\ndata: {json.dumps(message_start)}\n\n"
    
    try:
        stream = client.chat.completions.create(**create_params)
        
        for chunk in stream:
            if has_finished:
                break
            
            # Handle usage stats
            if hasattr(chunk, "usage") and chunk.usage:
                usage_data = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else vars(chunk.usage)
                usage_stats = build_anthropic_usage(usage_data)
            
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            
            delta = choice.delta
            if not delta:
                continue
            
            # Handle text content
            if delta.content:
                if not has_text_started:
                    block_idx = next_block_index()
                    block_start = {
                        "type": "content_block_start",
                        "index": block_idx,
                        "content_block": {"type": "text", "text": ""},
                    }
                    yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n"
                    current_block_index = block_idx
                    has_text_started = True
                
                text_delta = {
                    "type": "content_block_delta",
                    "index": current_block_index,
                    "delta": {"type": "text_delta", "text": delta.content},
                }
                yield f"event: content_block_delta\ndata: {json.dumps(text_delta)}\n\n"
                collected_text += delta.content
            
            # Handle tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    tc_index = tc.index if hasattr(tc, "index") else 0
                    
                    if tc.id:
                        # Close previous block
                        if current_block_index >= 0:
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                            has_text_started = False
                        
                        block_idx = next_block_index()
                        tool_index_to_block[tc_index] = block_idx
                        
                        tc_name = tc.function.name if tc.function else f"tool_{tc_index}"
                        collected_tool_calls[tc.id] = {
                            "name": tc_name,
                            "arguments": "",
                            "block_index": block_idx,
                        }
                        
                        tool_start = {
                            "type": "content_block_start",
                            "index": block_idx,
                            "content_block": {
                                "type": "tool_use",
                                "id": tc.id,
                                "name": tc_name,
                                "input": {},
                            }
                        }
                        yield f"event: content_block_start\ndata: {json.dumps(tool_start)}\n\n"
                        current_block_index = block_idx
                    
                    if tc.function and tc.function.arguments:
                        block_idx = tool_index_to_block.get(tc_index)
                        if block_idx is not None:
                            for tc_id, tc_data in collected_tool_calls.items():
                                if tc_data["block_index"] == block_idx:
                                    tc_data["arguments"] += tc.function.arguments
                                    break
                            
                            input_delta = {
                                "type": "content_block_delta",
                                "index": block_idx,
                                "delta": {
                                    "type": "input_json_delta",
                                    "partial_json": tc.function.arguments,
                                }
                            }
                            yield f"event: content_block_delta\ndata: {json.dumps(input_delta)}\n\n"
            
            # Handle finish
            if choice.finish_reason:
                has_finished = True
                stop_reason = map_finish_reason_to_stop_reason(choice.finish_reason)
                
                if current_block_index >= 0:
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n"
                
                message_delta = {
                    "type": "message_delta",
                    "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                    "usage": usage_stats,
                }
                yield f"event: message_delta\ndata: {json.dumps(message_delta)}\n\n"
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
    
    except Exception as e:
        error_msg = str(e)
        is_connection_error = any(x in error_msg.lower() for x in ["connection", "closed", "reset", "timeout"])
        
        if not is_connection_error:
            print(f"  -> Streaming error: {error_msg}")
            error_event = {
                "type": "error",
                "error": {"type": "api_error", "message": error_msg},
            }
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
    
    # Build and store response
    content_blocks = []
    if collected_text:
        content_blocks.append({"type": "text", "text": collected_text})
    
    for tc_id, tc_data in collected_tool_calls.items():
        try:
            tool_input = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
        except json.JSONDecodeError:
            tool_input = {"raw": tc_data["arguments"]}
        
        content_blocks.append({
            "type": "tool_use",
            "id": tc_id,
            "name": tc_data["name"],
            "input": tool_input,
        })
    
    anthropic_response = {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage_stats,
    }
    storage.save_response(session_id, sequence, anthropic_response)
    print(f"  <- Response #{sequence} (streaming), stop_reason: {stop_reason}")


def _generate_openai_stream(
    client,
    create_params: Dict[str, Any],
    session_id: str,
    sequence: int,
    storage,
) -> Generator[str, None, None]:
    """Generate OpenAI SSE format streaming response - transparent forwarding"""
    collected_content = ""
    collected_tool_calls = []
    finish_reason = None
    usage_stats = None
    response_id = None
    model = create_params.get("model", "unknown")
    
    try:
        stream = client.chat.completions.create(**create_params)
        
        for chunk in stream:
            # Store response ID
            if chunk.id and not response_id:
                response_id = chunk.id
            
            # Forward the chunk as-is
            chunk_dict = chunk.model_dump()
            yield f"data: {json.dumps(chunk_dict)}\n\n"
            
            # Collect data for storage
            if chunk.choices:
                choice = chunk.choices[0]
                if choice.delta:
                    if choice.delta.content:
                        collected_content += choice.delta.content
                    if choice.delta.tool_calls:
                        for tc in choice.delta.tool_calls:
                            tc_dict = tc.model_dump() if hasattr(tc, 'model_dump') else vars(tc)
                            collected_tool_calls.append(tc_dict)
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
            
            # Collect usage
            if hasattr(chunk, 'usage') and chunk.usage:
                usage_stats = chunk.usage.model_dump() if hasattr(chunk.usage, 'model_dump') else vars(chunk.usage)
        
        # Send done marker
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        error_msg = {"error": {"message": str(e), "type": "api_error"}}
        yield f"data: {json.dumps(error_msg)}\n\n"
        print(f"  -> Streaming error: {e}")
        return
    
    # Store the complete response
    openai_response = {
        "id": response_id or f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": collected_content or None,
                "tool_calls": collected_tool_calls if collected_tool_calls else None,
            },
            "finish_reason": finish_reason or "stop",
        }],
        "usage": usage_stats,
    }
    storage.save_response(session_id, sequence, openai_response)
    print(f"  <- Response #{sequence} (streaming), finish_reason: {finish_reason}")


def _convert_openai_response_to_anthropic(response, model: str) -> Dict[str, Any]:
    """Convert OpenAI response to Anthropic format"""
    choice = response.choices[0]
    message = choice.message
    content_blocks = []
    
    # Handle text content
    if message.content:
        content_blocks.append({"type": "text", "text": message.content})
    
    # Handle tool calls
    if message.tool_calls:
        for tool_call in message.tool_calls:
            try:
                args_str = tool_call.function.arguments or "{}"
                tool_input = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                tool_input = {"text": tool_call.function.arguments or ""}
            
            content_blocks.append({
                "type": "tool_use",
                "id": tool_call.id,
                "name": tool_call.function.name,
                "input": tool_input,
            })
    
    stop_reason = map_finish_reason_to_stop_reason(choice.finish_reason or "stop")
    
    usage_data = (
        response.usage.model_dump() if hasattr(response.usage, "model_dump")
        else (vars(response.usage) if response.usage else None)
    )
    usage_stats = build_anthropic_usage(usage_data)
    
    return {
        "id": response.id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage_stats,
    }


# Create app instance
app = create_app()


def run_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    reload: bool = False,
):
    """Run the recording proxy server"""
    import uvicorn
    
    config = get_config()
    
    print("=" * 60)
    print("Agent Inspector - Recording Proxy Server")
    print("=" * 60)
    print(f"Server: http://{host}:{port}")
    print(f"Backend: {config.listener.api_base or 'https://api.openai.com/v1'}")
    print(f"Logs: {config.storage.logs_dir}")
    if config.recorder.http_proxy:
        print(f"Proxy: {config.recorder.http_proxy}")
    print("=" * 60)
    
    uvicorn.run(
        "agent_inspector.recorder.server:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run_server()
