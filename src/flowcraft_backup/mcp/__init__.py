"""
MCP Module - Model Context Protocol 服务

提供 MCP 工具接口，让 LLM Agent 可以使用检查、蒸馏和反思功能。
"""

from .server import create_mcp_server, run_mcp_server, main

__all__ = ["create_mcp_server", "run_mcp_server", "main"]
