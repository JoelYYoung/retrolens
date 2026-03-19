"""
Rev-Agent: Claude Code Reverse Analysis Proxy Layer
Used for intercepting and analyzing communication between Claude Code and API

Conversion logic referenced from claude-code-router project:
https://github.com/musistudio/claude-code-router
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from openai import OpenAI
import httpx
import os
import json
import sys
import uuid
import base64
from typing import Optional, Generator, Dict, List, Any, Union
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent.parent / ".env")

try:
    from .storage import SessionStorage, get_storage, get_or_create_session
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from listener.storage import SessionStorage, get_storage, get_or_create_session

app = FastAPI(
    title="Rev-Agent",
    description="Claude Code reverse analysis proxy layer",
    version="0.2.0"
)

# Configuration - Read from environment variables
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
HTTP_PROXY = os.getenv("HTTP_PROXY", "")


# =============================================================================
# Helper Functions for Format Conversion
# =============================================================================

def format_base64_image(data: str, media_type: str) -> str:
    """Format base64 image data to data URL"""
    return f"data:{media_type};base64,{data}"


def convert_anthropic_tools_to_openai(anthropic_tools: List[Dict]) -> List[Dict]:
    """Convert Anthropic tool definitions to OpenAI format"""
    openai_tools = []
    for tool in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {})
            }
        })
    return openai_tools


def convert_anthropic_messages_to_openai(
    messages: List[Dict], 
    system_prompt: str = ""
) -> List[Dict]:
    """
    Convert Anthropic message format to OpenAI format
    
    Handles:
    - System prompts (string or structured)
    - Text content
    - Image content (base64 and URL)
    - Tool use blocks
    - Tool result blocks
    - Thinking blocks
    """
    openai_messages = []
    
    # Add system message if present
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Handle string content directly
        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue
        
        # Handle structured content (list)
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
            # Collect tool results
            tool_result_content = item.get("content", "")
            if isinstance(tool_result_content, list):
                parts = []
                for part in tool_result_content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        parts.append(part)
                tool_result_content = "\n".join(parts)
            
            tool_results.append({
                "tool_call_id": item.get("tool_use_id", ""),
                "content": str(tool_result_content)
            })
        
        elif item_type == "text":
            text_and_media_parts.append({
                "type": "text",
                "text": item.get("text", "")
            })
        
        elif item_type == "image":
            # Handle image content
            source = item.get("source", {})
            if source.get("type") == "base64":
                image_url = format_base64_image(
                    source.get("data", ""),
                    source.get("media_type", "image/png")
                )
            else:
                image_url = source.get("url", "")
            
            text_and_media_parts.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
    
    # Add tool messages first (one for each tool_result)
    for tr in tool_results:
        openai_messages.append({
            "role": "tool",
            "tool_call_id": tr["tool_call_id"],
            "content": tr["content"]
        })
    
    # Add text/media content as user message
    if text_and_media_parts:
        if len(text_and_media_parts) == 1 and text_and_media_parts[0].get("type") == "text":
            # Single text, use string format
            openai_messages.append({
                "role": "user",
                "content": text_and_media_parts[0].get("text", "")
            })
        else:
            # Multiple parts or has images, use structured format
            openai_messages.append({
                "role": "user",
                "content": text_and_media_parts
            })


def _process_assistant_message(content: List[Dict], openai_messages: List[Dict]):
    """Process assistant message with structured content"""
    assistant_msg: Dict[str, Any] = {"role": "assistant"}
    text_parts = []
    tool_calls = []
    thinking_content = None
    
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
                    "arguments": json.dumps(tool_input, ensure_ascii=False)
                }
            })
        
        elif item_type == "thinking":
            # Preserve thinking blocks for models that support it
            thinking_content = {
                "content": item.get("thinking", ""),
                "signature": item.get("signature", "")
            }
    
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
        "function_call": "tool_use",  # Legacy
    }
    return mapping.get(finish_reason, "end_turn")


def build_anthropic_usage(openai_usage: Optional[Dict]) -> Dict:
    """Build Anthropic usage object from OpenAI usage"""
    if not openai_usage:
        return {"input_tokens": 0, "output_tokens": 0}
    
    prompt_tokens = openai_usage.get("prompt_tokens", 0)
    cached_tokens = 0
    
    # Handle cached tokens if present
    prompt_details = openai_usage.get("prompt_tokens_details", {})
    if prompt_details:
        cached_tokens = prompt_details.get("cached_tokens", 0)
    
    return {
        "input_tokens": prompt_tokens - cached_tokens,
        "output_tokens": openai_usage.get("completion_tokens", 0),
        "cache_read_input_tokens": cached_tokens
    }

# =============================================================================
# Anthropic API Proxy Endpoints
# =============================================================================

@app.post("/v1/messages")
async def anthropic_to_openai(request: Request):
    """
    Anthropic Messages API proxy endpoint
    Intercepts requests/responses and stores them, while forwarding to OpenAI compatible API
    
    Conversion logic follows claude-code-router/packages/core/src/transformer/anthropic.transformer.ts
    """
    body = await request.json()
    headers_in = request.headers

    # Get API key from request headers (passed through from Claude Code)
    # Support both Bearer token and x-api-key header
    api_key = headers_in.get("authorization", "").replace("Bearer ", "")
    if not api_key:
        api_key = headers_in.get("x-api-key", "")

    # Detect client type
    user_agent = headers_in.get("user-agent", "").lower()
    if "claude-code" in user_agent or "claude" in user_agent:
        client_type = "claude-code"
    elif "vscode" in user_agent or "copilot" in user_agent:
        client_type = "vscode-copilot"
    else:
        client_type = "unknown"

    model = body.get("model", "unknown")
    
    # Get or create session
    session_id = get_or_create_session(client=client_type, model=model)
    storage = get_storage()
    
    # Store request
    print(f"[{datetime.now().isoformat()}] Session {session_id}: Received request from {client_type}")
    sequence = storage.save_request(session_id, body)
    print(f"  -> Saved as request #{sequence}")
    print(f"  -> Model: {model}")
    print(f"  -> Messages: {len(body.get('messages', []))}")
    print(f"  -> Tools: {len(body.get('tools', []))}")
    if body.get("thinking"):
        print(f"  -> Thinking: enabled (budget: {body['thinking'].get('budget_tokens', 'N/A')})")
    
    # Convert system prompt
    system_prompt = body.get("system", "")
    if isinstance(system_prompt, list):
        # Structured system prompt - extract text parts
        system_parts = []
        for item in system_prompt:
            if isinstance(item, dict) and item.get("type") == "text":
                system_parts.append(item.get("text", ""))
            elif isinstance(item, str):
                system_parts.append(item)
        system_prompt = "\n".join(system_parts)
    
    # Convert messages using helper function
    messages = body.get("messages", [])
    openai_messages = convert_anthropic_messages_to_openai(messages, system_prompt)

    # Configure HTTP client
    http_client = httpx.Client(proxy=HTTP_PROXY) if HTTP_PROXY else None

    client = OpenAI(
        api_key=api_key,
        base_url=OPENAI_BASE_URL,
        http_client=http_client
    )

    # Convert tool definitions to OpenAI format
    openai_tools = None
    anthropic_tools = body.get("tools", [])
    if anthropic_tools:
        openai_tools = convert_anthropic_tools_to_openai(anthropic_tools)
        print(f"  -> Converted {len(openai_tools)} tools to OpenAI format")

    # Call API
    model_name = body.get("model", "openai/gpt-4o")
    is_streaming = body.get("stream", False)
    
    try:
        create_params = {
            "model": model_name,
            "messages": openai_messages,
            "max_tokens": body.get("max_tokens", 4096)
        }
        if openai_tools:
            create_params["tools"] = openai_tools
        
        # Handle tool_choice conversion
        tool_choice = body.get("tool_choice")
        if tool_choice:
            if isinstance(tool_choice, dict):
                if tool_choice.get("type") == "tool":
                    create_params["tool_choice"] = {
                        "type": "function",
                        "function": {"name": tool_choice.get("name", "")}
                    }
                else:
                    create_params["tool_choice"] = tool_choice.get("type", "auto")
            else:
                create_params["tool_choice"] = tool_choice
        
        # Streaming processing
        if is_streaming:
            print(f"  -> Streaming mode enabled")
            create_params["stream"] = True
            # Request usage stats in stream if supported
            create_params["stream_options"] = {"include_usage": True}
            
            def generate_sse_stream() -> Generator[str, None, None]:
                """
                Generate Anthropic SSE format streaming response
                
                Event sequence follows Anthropic spec:
                1. message_start
                2. content_block_start (for each block)
                3. content_block_delta (streaming content)
                4. content_block_stop (end each block)
                5. message_delta (final stats)
                6. message_stop
                """
                message_id = f"msg_{uuid.uuid4().hex[:24]}"
                collected_text = ""
                collected_tool_calls: Dict[str, Dict] = {}  # tool_call_id -> {name, arguments, index}
                collected_thinking = ""
                usage_stats = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
                
                # State tracking - following claude-code-router pattern
                has_started = False
                has_text_started = False
                has_thinking_started = False
                has_finished = False
                content_index = 0  # Atomic content block index counter
                current_content_block_index = -1
                tool_call_index_to_block_index: Dict[int, int] = {}
                stop_reason = "end_turn"
                
                def assign_content_block_index() -> int:
                    nonlocal content_index
                    idx = content_index
                    content_index += 1
                    return idx
                
                # Send message_start event
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
                        "usage": {"input_tokens": 0, "output_tokens": 0}
                    }
                }
                yield f"event: message_start\ndata: {json.dumps(message_start)}\n\n"
                has_started = True
                
                try:
                    stream = client.chat.completions.create(**create_params)
                    
                    for chunk in stream:
                        if has_finished:
                            break
                            
                        # Handle usage stats (may come in final chunk)
                        if hasattr(chunk, 'usage') and chunk.usage:
                            usage_stats = build_anthropic_usage(chunk.usage.model_dump() if hasattr(chunk.usage, 'model_dump') else vars(chunk.usage))
                        
                        choice = chunk.choices[0] if chunk.choices else None
                        if not choice:
                            continue
                        
                        delta = choice.delta
                        if not delta:
                            continue
                        
                        # Handle thinking content (for models that support it)
                        if hasattr(delta, 'thinking') and delta.thinking:
                            thinking_data = delta.thinking
                            if not has_thinking_started:
                                thinking_block_index = assign_content_block_index()
                                block_start = {
                                    "type": "content_block_start",
                                    "index": thinking_block_index,
                                    "content_block": {"type": "thinking", "thinking": ""}
                                }
                                yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n"
                                current_content_block_index = thinking_block_index
                                has_thinking_started = True
                            
                            # Handle thinking signature (end of thinking)
                            if hasattr(thinking_data, 'signature') and thinking_data.signature:
                                sig_delta = {
                                    "type": "content_block_delta",
                                    "index": current_content_block_index,
                                    "delta": {"type": "signature_delta", "signature": thinking_data.signature}
                                }
                                yield f"event: content_block_delta\ndata: {json.dumps(sig_delta)}\n\n"
                                # Close thinking block
                                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_content_block_index})}\n\n"
                                current_content_block_index = -1
                            elif hasattr(thinking_data, 'content') and thinking_data.content:
                                collected_thinking += thinking_data.content
                                thinking_delta = {
                                    "type": "content_block_delta",
                                    "index": current_content_block_index,
                                    "delta": {"type": "thinking_delta", "thinking": thinking_data.content}
                                }
                                yield f"event: content_block_delta\ndata: {json.dumps(thinking_delta)}\n\n"
                        
                        # Handle text content
                        if delta.content:
                            # Close previous non-text block if needed
                            if current_content_block_index >= 0 and not has_text_started:
                                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_content_block_index})}\n\n"
                                current_content_block_index = -1
                            
                            if not has_text_started:
                                text_block_index = assign_content_block_index()
                                block_start = {
                                    "type": "content_block_start",
                                    "index": text_block_index,
                                    "content_block": {"type": "text", "text": ""}
                                }
                                yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n"
                                current_content_block_index = text_block_index
                                has_text_started = True
                            
                            text_delta = {
                                "type": "content_block_delta",
                                "index": current_content_block_index,
                                "delta": {"type": "text_delta", "text": delta.content}
                            }
                            yield f"event: content_block_delta\ndata: {json.dumps(text_delta)}\n\n"
                            collected_text += delta.content
                        
                        # Handle tool calls
                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                tc_index = tc.index if hasattr(tc, 'index') else 0
                                
                                # New tool call starting
                                if tc.id:
                                    # Close previous content block
                                    if current_content_block_index >= 0:
                                        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_content_block_index})}\n\n"
                                        current_content_block_index = -1
                                        has_text_started = False
                                    
                                    tool_block_index = assign_content_block_index()
                                    tool_call_index_to_block_index[tc_index] = tool_block_index
                                    
                                    tc_id = tc.id
                                    tc_name = tc.function.name if tc.function else f"tool_{tc_index}"
                                    
                                    collected_tool_calls[tc_id] = {
                                        "name": tc_name,
                                        "arguments": "",
                                        "block_index": tool_block_index
                                    }
                                    
                                    tool_start = {
                                        "type": "content_block_start",
                                        "index": tool_block_index,
                                        "content_block": {
                                            "type": "tool_use",
                                            "id": tc_id,
                                            "name": tc_name,
                                            "input": {}
                                        }
                                    }
                                    yield f"event: content_block_start\ndata: {json.dumps(tool_start)}\n\n"
                                    current_content_block_index = tool_block_index
                                
                                # Accumulate tool arguments
                                if tc.function and tc.function.arguments:
                                    block_idx = tool_call_index_to_block_index.get(tc_index)
                                    if block_idx is not None:
                                        # Find the tool call by block index
                                        for tc_id, tc_data in collected_tool_calls.items():
                                            if tc_data["block_index"] == block_idx:
                                                tc_data["arguments"] += tc.function.arguments
                                                break
                                        
                                        input_delta = {
                                            "type": "content_block_delta",
                                            "index": block_idx,
                                            "delta": {
                                                "type": "input_json_delta",
                                                "partial_json": tc.function.arguments
                                            }
                                        }
                                        yield f"event: content_block_delta\ndata: {json.dumps(input_delta)}\n\n"
                        
                        # Handle finish
                        if choice.finish_reason:
                            has_finished = True
                            stop_reason = map_finish_reason_to_stop_reason(choice.finish_reason)
                            
                            # Close any remaining open content block
                            if current_content_block_index >= 0:
                                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_content_block_index})}\n\n"
                            
                            # Send message_delta with final stats
                            message_delta = {
                                "type": "message_delta",
                                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                "usage": usage_stats
                            }
                            yield f"event: message_delta\ndata: {json.dumps(message_delta)}\n\n"
                            
                            # Send message_stop
                            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                
                except Exception as e:
                    print(f"  -> Streaming error: {e}")
                    import traceback
                    traceback.print_exc()
                    error_event = {
                        "type": "error",
                        "error": {"type": "api_error", "message": str(e)}
                    }
                    yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                
                # Build complete response for storage
                content_blocks = []
                if collected_thinking:
                    content_blocks.append({"type": "thinking", "thinking": collected_thinking})
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
                        "input": tool_input
                    })
                
                # Store complete response
                anthropic_response = {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
                    "model": model,
                    "stop_reason": stop_reason,
                    "stop_sequence": None,
                    "usage": usage_stats
                }
                storage.save_response(session_id, sequence, anthropic_response)
                print(f"  -> Saved streaming response #{sequence}")
            
            return StreamingResponse(
                generate_sse_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        
        # Non-streaming processing
        response = client.chat.completions.create(**create_params)
    except Exception as e:
        print(f"  -> API Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    print(f"  <- Received response, finish_reason: {response.choices[0].finish_reason}")

    # Build Anthropic format response - following claude-code-router pattern
    choice = response.choices[0]
    message = choice.message
    content_blocks = []
    
    # Handle annotations (web search results) - if present
    if hasattr(message, 'annotations') and message.annotations:
        tool_use_id = f"srvtoolu_{uuid.uuid4().hex[:24]}"
        content_blocks.append({
            "type": "server_tool_use",
            "id": tool_use_id,
            "name": "web_search",
            "input": {"query": ""}
        })
        web_results = []
        for annotation in message.annotations:
            if hasattr(annotation, 'url_citation'):
                web_results.append({
                    "type": "web_search_result",
                    "url": annotation.url_citation.url,
                    "title": annotation.url_citation.title
                })
        if web_results:
            content_blocks.append({
                "type": "web_search_tool_result",
                "tool_use_id": tool_use_id,
                "content": web_results
            })
    
    # Handle thinking content (for models that support it)
    if hasattr(message, 'thinking') and message.thinking:
        content_blocks.append({
            "type": "thinking",
            "thinking": message.thinking.get("content", ""),
            "signature": message.thinking.get("signature", "")
        })
    
    # Handle text content
    if message.content:
        content_blocks.append({"type": "text", "text": message.content})
    
    # Handle tool calls
    if message.tool_calls:
        print(f"  -> Processing {len(message.tool_calls)} tool calls")
        for tool_call in message.tool_calls:
            try:
                args_str = tool_call.function.arguments or "{}"
                if isinstance(args_str, dict):
                    tool_input = args_str
                elif isinstance(args_str, str):
                    tool_input = json.loads(args_str)
                else:
                    tool_input = {"raw": str(args_str)}
            except json.JSONDecodeError:
                tool_input = {"text": tool_call.function.arguments or ""}
            
            content_blocks.append({
                "type": "tool_use",
                "id": tool_call.id,
                "name": tool_call.function.name,
                "input": tool_input
            })
            print(f"     -> Tool: {tool_call.function.name}")
    
    # Determine stop_reason using helper function
    stop_reason = map_finish_reason_to_stop_reason(choice.finish_reason or "stop")
    
    # Build usage stats using helper function
    usage_stats = build_anthropic_usage(
        response.usage.model_dump() if hasattr(response.usage, 'model_dump') else 
        (vars(response.usage) if response.usage else None)
    )
    
    anthropic_response = {
        "id": response.id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage_stats
    }
    
    # Store response
    storage.save_response(session_id, sequence, anthropic_response)
    print(f"  -> Saved response #{sequence}")
    
    return anthropic_response


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0"
    }


@app.get("/")
async def root():
    """API root path"""
    return {
        "name": "Rev-Agent",
        "description": "Claude Code reverse analysis proxy layer",
        "endpoints": {
            "proxy": "POST /v1/messages - Anthropic API proxy",
            "health": "GET /health - Health check"
        }
    }


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """Start server"""
    import uvicorn
    
    host = os.getenv("REV_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("REV_AGENT_PORT", "8080"))
    
    print("=" * 60)
    print("Rev-Agent: Claude Code Reverse Analysis Proxy Layer")
    print("=" * 60)
    print(f"Server: http://{host}:{port}")
    print(f"API Base URL: {OPENAI_BASE_URL}")
    print(f"HTTP Proxy: {HTTP_PROXY or 'None'}")
    print("=" * 60)
    
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

