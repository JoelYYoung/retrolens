"""
Rev-Agent: Claude Code Reverse Analysis Proxy Layer
Used for intercepting and analyzing communication between Claude Code and API
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from openai import OpenAI
import httpx
import os
import json
import sys
import uuid
from typing import Optional, Generator
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
    version="0.1.0"
)

# Configuration - Read from environment variables
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
HTTP_PROXY = os.getenv("HTTP_PROXY", "")

# =============================================================================
# Anthropic API Proxy Endpoints
# =============================================================================

@app.post("/v1/messages")
async def anthropic_to_openai(request: Request):
    """
    Anthropic Messages API proxy endpoint
    Intercepts requests/responses and stores them, while forwarding to OpenAI compatible API
    """
    body = await request.json()
    headers_in = request.headers

    # Get API key from request headers (passed through from Claude Code)
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
    
    # Convert to OpenAI format
    system_prompt = body.get("system", "")
    if isinstance(system_prompt, list):
        # Structured system prompt, merge to string
        system_prompt = "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in system_prompt
        )
    
    messages = body.get("messages", [])
    openai_messages = []
    
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Handle structured content
        if isinstance(content, list):
            text_parts = []
            tool_calls = []  # Collect tool_use blocks
            tool_results = []  # Collect tool_result blocks
            
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        # Collect tool_result, convert to OpenAI tool message later
                        tool_result_content = item.get("content", "")
                        if isinstance(tool_result_content, list):
                            # Handle structured tool_result content
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
                    elif item.get("type") == "tool_use":
                        # Collect tool_use, convert to OpenAI tool_calls format
                        tool_input = item.get("input", {})
                        tool_calls.append({
                            "id": item.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": item.get("name", ""),
                                "arguments": json.dumps(tool_input, ensure_ascii=False)
                            }
                        })
            
            # Handle tool_use in assistant message
            if role == "assistant" and tool_calls:
                assistant_msg = {"role": "assistant"}
                if text_parts:
                    assistant_msg["content"] = "\n".join(text_parts)
                else:
                    assistant_msg["content"] = None
                assistant_msg["tool_calls"] = tool_calls
                openai_messages.append(assistant_msg)
                continue  # Already handled, skip default processing below
            
            # Handle tool_result in user message
            if role == "user" and tool_results:
                # First add tool messages (one for each tool_result)
                for tr in tool_results:
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": tr["content"]
                    })
                # If there's also text content, add separate user message
                if text_parts:
                    openai_messages.append({"role": "user", "content": "\n".join(text_parts)})
                continue  # Already handled, skip default processing below
            
            content = "\n".join(text_parts) if text_parts else ""
        
        openai_messages.append({"role": role, "content": content})

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
        
        # Streaming processing
        if is_streaming:
            print(f"  -> Streaming mode enabled")
            create_params["stream"] = True
            
            def generate_sse_stream() -> Generator[str, None, None]:
                """Generate Anthropic SSE format streaming response"""
                message_id = f"msg_{uuid.uuid4().hex[:24]}"
                collected_text = ""
                collected_tool_calls = {}  # id -> {name, arguments}
                input_tokens = 0
                output_tokens = 0
                
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
                
                content_block_started = False
                current_block_index = 0
                tool_block_indices = {}  # tool_call_id -> block_index
                
                try:
                    stream = client.chat.completions.create(**create_params)
                    
                    for chunk in stream:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        
                        if delta:
                            # Handle text content
                            if delta.content:
                                if not content_block_started:
                                    # Send content_block_start
                                    block_start = {
                                        "type": "content_block_start",
                                        "index": current_block_index,
                                        "content_block": {"type": "text", "text": ""}
                                    }
                                    yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n"
                                    content_block_started = True
                                
                                # Send content_block_delta
                                text_delta = {
                                    "type": "content_block_delta",
                                    "index": current_block_index,
                                    "delta": {"type": "text_delta", "text": delta.content}
                                }
                                yield f"event: content_block_delta\ndata: {json.dumps(text_delta)}\n\n"
                                collected_text += delta.content
                            
                            # Handle tool calls
                            if delta.tool_calls:
                                for tc in delta.tool_calls:
                                    tc_id = tc.id or list(collected_tool_calls.keys())[-1] if collected_tool_calls else None
                                    
                                    if tc.id:  # New tool call starts
                                        # If there was a text block before, end it first
                                        if content_block_started:
                                            block_stop = {"type": "content_block_stop", "index": current_block_index}
                                            yield f"event: content_block_stop\ndata: {json.dumps(block_stop)}\n\n"
                                            current_block_index += 1
                                            content_block_started = False
                                        
                                        tc_id = tc.id
                                        collected_tool_calls[tc_id] = {
                                            "name": tc.function.name if tc.function else "",
                                            "arguments": ""
                                        }
                                        tool_block_indices[tc_id] = current_block_index
                                        
                                        # Send tool_use content_block_start
                                        tool_start = {
                                            "type": "content_block_start",
                                            "index": current_block_index,
                                            "content_block": {
                                                "type": "tool_use",
                                                "id": tc_id,
                                                "name": tc.function.name if tc.function else "",
                                                "input": {}
                                            }
                                        }
                                        yield f"event: content_block_start\ndata: {json.dumps(tool_start)}\n\n"
                                        current_block_index += 1
                                    
                                    # Accumulate tool arguments
                                    if tc.function and tc.function.arguments:
                                        if tc_id and tc_id in collected_tool_calls:
                                            collected_tool_calls[tc_id]["arguments"] += tc.function.arguments
                                            # Send input_json_delta
                                            input_delta = {
                                                "type": "content_block_delta",
                                                "index": tool_block_indices.get(tc_id, 0),
                                                "delta": {
                                                    "type": "input_json_delta",
                                                    "partial_json": tc.function.arguments
                                                }
                                            }
                                            yield f"event: content_block_delta\ndata: {json.dumps(input_delta)}\n\n"
                        
                        # Check if finished
                        if chunk.choices and chunk.choices[0].finish_reason:
                            finish_reason = chunk.choices[0].finish_reason
                            
                            # End all unfinished content blocks
                            if content_block_started:
                                block_stop = {"type": "content_block_stop", "index": 0}
                                yield f"event: content_block_stop\ndata: {json.dumps(block_stop)}\n\n"
                            
                            for tc_id, idx in tool_block_indices.items():
                                block_stop = {"type": "content_block_stop", "index": idx}
                                yield f"event: content_block_stop\ndata: {json.dumps(block_stop)}\n\n"
                            
                            # Determine stop_reason
                            if finish_reason == "tool_calls":
                                stop_reason = "tool_use"
                            elif finish_reason == "stop":
                                stop_reason = "end_turn"
                            else:
                                stop_reason = finish_reason or "end_turn"
                            
                            # Send message_delta
                            message_delta = {
                                "type": "message_delta",
                                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                                "usage": {"output_tokens": output_tokens}
                            }
                            yield f"event: message_delta\ndata: {json.dumps(message_delta)}\n\n"
                            
                            # Send message_stop
                            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                
                except Exception as e:
                    print(f"  -> Streaming error: {e}")
                    error_event = {"type": "error", "error": {"type": "api_error", "message": str(e)}}
                    yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                
                # Build complete response for storage
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
                        "input": tool_input
                    })
                
                # Store complete response
                anthropic_response = {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
                    "model": model,
                    "stop_reason": stop_reason if 'stop_reason' in dir() else "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}
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
        raise HTTPException(status_code=500, detail=str(e))

    print(f"  <- Received response, finish_reason: {response.choices[0].finish_reason}")

    # Build Anthropic format response
    message = response.choices[0].message
    content_blocks = []
    
    # Handle text content
    if message.content:
        content_blocks.append({"type": "text", "text": message.content})
    
    # Handle tool calls
    if message.tool_calls:
        print(f"  -> Processing {len(message.tool_calls)} tool calls")
        for tool_call in message.tool_calls:
            try:
                tool_input = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_input = {"raw": tool_call.function.arguments}
            
            content_blocks.append({
                "type": "tool_use",
                "id": tool_call.id,
                "name": tool_call.function.name,
                "input": tool_input
            })
            print(f"     -> Tool: {tool_call.function.name}")
    
    # Determine stop_reason
    finish_reason = response.choices[0].finish_reason
    if finish_reason == "tool_calls":
        stop_reason = "tool_use"
    elif finish_reason == "stop":
        stop_reason = "end_turn"
    else:
        stop_reason = finish_reason or "end_turn"
    
    anthropic_response = {
        "id": response.id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0
        }
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

