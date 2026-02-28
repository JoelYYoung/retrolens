#!/usr/bin/env python3
"""
MCP Server for Agent Session Analysis

Analyzes Agent session logs, automatically divides requests/responses into rounds,
and provides convenient tools to view new information and responses for each round.

Usage:
1. Configure Claude Code MCP:
   Add to ~/.claude/settings.json:
   {
     "mcpServers": {
       "agent-session": {
         "command": "python",
         "args": ["-m", "tools.analyzer.mcp_server"],
         "cwd": "/path/to/rev-agent"
       }
     }
   }

2. Or run with uv:
   uv run python -m tools.analyzer.mcp_server
"""

import json
import sys
import asyncio
from pathlib import Path
from typing import Optional

try:
    from .engine import RoundAnalyzer
except ImportError:
    from engine import RoundAnalyzer

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


# =============================================================================
# Logs Path Resolution
# =============================================================================

def find_logs_path() -> Optional[Path]:
    """
    Auto-detect logs path using multiple strategies:
    1. Relative to script location (rev-agent/tools/analyzer/mcp_server.py -> rev-agent/logs)
    2. Current working directory
    3. Common project structures
    """
    candidates = []
    
    # Strategy 1: Relative to script
    script_dir = Path(__file__).parent.absolute()
    candidates.append(script_dir.parent.parent / "logs")
    
    # Strategy 2: Current working directory
    cwd = Path.cwd()
    candidates.append(cwd / "logs")
    
    # Strategy 3: Parent of cwd (if running from subdirectory)
    candidates.append(cwd.parent / "logs")
    
    # Find first valid path
    for path in candidates:
        if path.exists() and (path / "sessions").exists():
            return path.absolute()
    
    return None


# Global state
_current_logs_path: Optional[Path] = find_logs_path()
_analyzer: Optional[RoundAnalyzer] = None


def get_analyzer() -> RoundAnalyzer:
    """Get or create analyzer with current logs path"""
    global _analyzer, _current_logs_path
    
    if _analyzer is None:
        if _current_logs_path is None:
            raise ValueError("Logs path not set. Use set_logs_path tool first.")
        _analyzer = RoundAnalyzer(logs_path=str(_current_logs_path))
    
    return _analyzer


def set_logs_path(path: str) -> dict:
    """Set logs path and recreate analyzer"""
    global _analyzer, _current_logs_path
    
    new_path = Path(path).absolute()
    
    if not new_path.exists():
        return {"error": f"Path does not exist: {new_path}"}
    
    sessions_path = new_path / "sessions"
    if not sessions_path.exists():
        return {"error": f"No sessions directory found at: {sessions_path}"}
    
    _current_logs_path = new_path
    _analyzer = RoundAnalyzer(logs_path=str(_current_logs_path))
    
    return {
        "success": True,
        "logs_path": str(_current_logs_path),
        "sessions_count": len(list(sessions_path.iterdir()))
    }


server = Server("agent-session")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="set_logs_path",
            description="Set the path to the logs directory. Use this if auto-detection fails or you want to analyze logs from a different location.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the logs directory (should contain a 'sessions' subdirectory)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="get_logs_path",
            description="Get the current logs directory path being used for analysis",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="list_sessions",
            description="List all recorded Agent sessions",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_session_summary",
            description="Get summary information for a specified session, including round count, tool call statistics, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="list_rounds",
            description="List all rounds in a session and their summaries",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_round_detail",
            description="Get complete details for a specific round, including all tool calls and responses",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "round_number": {
                        "type": "integer",
                        "description": "Round number (starting from 1)"
                    }
                },
                "required": ["session_id", "round_number"]
            }
        ),
        Tool(
            name="get_round_new_info",
            description="Get new information in a round, including user messages, tool calls, file operations, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "round_number": {
                        "type": "integer",
                        "description": "Round number"
                    }
                },
                "required": ["session_id", "round_number"]
            }
        ),
        Tool(
            name="get_round_response",
            description="Get the final response text of a round",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "round_number": {
                        "type": "integer",
                        "description": "Round number"
                    }
                },
                "required": ["session_id", "round_number"]
            }
        ),
        Tool(
            name="get_request_detail",
            description="Get detailed content of a raw request (for in-depth analysis)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "sequence": {
                        "type": "integer",
                        "description": "Request sequence number"
                    }
                },
                "required": ["session_id", "sequence"]
            }
        ),
        Tool(
            name="get_response_detail",
            description="Get detailed content of a raw response (for in-depth analysis)",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "sequence": {
                        "type": "integer",
                        "description": "Response sequence number"
                    }
                },
                "required": ["session_id", "sequence"]
            }
        ),
        Tool(
            name="compare_rounds",
            description="Compare differences between two rounds",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "round1": {
                        "type": "integer",
                        "description": "First round number"
                    },
                    "round2": {
                        "type": "integer",
                        "description": "Second round number"
                    }
                },
                "required": ["session_id", "round1", "round2"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    try:
        # Path management tools (don't need analyzer)
        if name == "set_logs_path":
            result = set_logs_path(arguments["path"])
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
        
        elif name == "get_logs_path":
            result = {
                "logs_path": str(_current_logs_path) if _current_logs_path else None,
                "status": "configured" if _current_logs_path else "not_set",
                "hint": "Use set_logs_path to configure if needed"
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
        
        # All other tools need analyzer
        analyzer = get_analyzer()
        
        if name == "list_sessions":
            result = analyzer.list_sessions()
        
        elif name == "get_session_summary":
            result = analyzer.get_session_summary(arguments["session_id"])
        
        elif name == "list_rounds":
            rounds = analyzer.analyze_rounds(arguments["session_id"])
            result = [
                {
                    "round": r["round_number"],
                    "sequences": r["sequences"],
                    "user_message": r["user_message"][:200] + "..." if len(r.get("user_message", "")) > 200 else r.get("user_message", ""),
                    "tool_calls": [t["name"] for t in r.get("tool_calls", [])],
                    "time_range": f"{r.get('start_time', '')} - {r.get('end_time', '')}"
                }
                for r in rounds
            ]
        
        elif name == "get_round_detail":
            result = analyzer.get_round_detail(
                arguments["session_id"],
                arguments["round_number"]
            )
            if not result:
                result = {"error": f"Round {arguments['round_number']} not found"}
        
        elif name == "get_round_new_info":
            result = analyzer.get_round_new_info(
                arguments["session_id"],
                arguments["round_number"]
            )
        
        elif name == "get_round_response":
            detail = analyzer.get_round_detail(
                arguments["session_id"],
                arguments["round_number"]
            )
            if detail:
                result = {
                    "round_number": arguments["round_number"],
                    "response": detail.get("final_response", "")
                }
            else:
                result = {"error": f"Round {arguments['round_number']} not found"}
        
        elif name == "get_request_detail":
            request = analyzer._load_request(
                arguments["session_id"],
                arguments["sequence"]
            )
            if request:
                # Simplify output to avoid excessive length
                result = {
                    "sequence": arguments["sequence"],
                    "timestamp": request.get("timestamp"),
                    "model": request.get("raw_request", {}).get("model"),
                    "messages_count": len(request.get("raw_request", {}).get("messages", [])),
                    "tools_count": len(request.get("raw_request", {}).get("tools", [])),
                    "extracted": request.get("extracted"),
                    "messages_preview": request.get("raw_request", {}).get("messages", [])[:3]
                }
            else:
                result = {"error": f"Request {arguments['sequence']} not found"}
        
        elif name == "get_response_detail":
            response = analyzer._load_response(
                arguments["session_id"],
                arguments["sequence"]
            )
            if response:
                result = {
                    "sequence": arguments["sequence"],
                    "timestamp": response.get("timestamp"),
                    "raw_response": response.get("raw_response"),
                    "extracted": response.get("extracted")
                }
            else:
                result = {"error": f"Response {arguments['sequence']} not found"}
        
        elif name == "compare_rounds":
            r1 = analyzer.get_round_new_info(arguments["session_id"], arguments["round1"])
            r2 = analyzer.get_round_new_info(arguments["session_id"], arguments["round2"])
            
            result = {
                "round1": r1,
                "round2": r2,
                "diff": {
                    "tools_diff": {
                        "round1_only": [t["name"] for t in r1.get("new_tool_calls", [])],
                        "round2_only": [t["name"] for t in r2.get("new_tool_calls", [])]
                    }
                }
            }
        
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def main():
    """Run MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
