"""
MCP Server - Model Context Protocol 服务器实现

提供以下工具：
- list_sessions: 列出所有会话
- get_session: 获取会话详情
- analyze_session: 分析会话
- distill_workflow: 蒸馏工作流
- reflect_workflow: 反思工作流
- generate_code: 生成 LangGraph 代码
"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any, Sequence

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ..config import get_config


def create_mcp_server(name: str = "agent-inspector") -> Server:
    """创建 MCP 服务器
    
    Args:
        name: 服务器名称
        
    Returns:
        配置好的 MCP Server 实例
    """
    server = Server(name)
    config = get_config()
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """列出所有可用工具"""
        return [
            Tool(
                name="list_sessions",
                description="列出所有已记录的 Agent 会话",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "number",
                            "description": "返回的最大会话数",
                            "default": 20,
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="get_session",
                description="获取指定会话的详细信息",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "会话 ID",
                        },
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="analyze_session",
                description="分析会话中的模式、工具使用和决策点",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "会话 ID",
                        },
                        "aspects": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "分析方面: memory, planning, tools, rounds",
                            "default": ["memory", "planning", "tools", "rounds"],
                        },
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="distill_workflow",
                description="从会话中蒸馏出结构化工作流",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "会话 ID",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["yaml", "json"],
                            "description": "输出格式",
                            "default": "yaml",
                        },
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="reflect_workflow",
                description="分析工作流并提供改进建议",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "string",
                            "description": "工作流内容 (YAML 或 JSON)",
                        },
                    },
                    "required": ["workflow"],
                },
            ),
            Tool(
                name="generate_langgraph",
                description="从工作流生成 LangGraph Agent 代码",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "string",
                            "description": "工作流内容 (YAML 或 JSON)",
                        },
                        "include_tests": {
                            "type": "boolean",
                            "description": "是否生成测试代码",
                            "default": False,
                        },
                    },
                    "required": ["workflow"],
                },
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        """处理工具调用"""
        try:
            if name == "list_sessions":
                return await _handle_list_sessions(arguments, config)
            elif name == "get_session":
                return await _handle_get_session(arguments, config)
            elif name == "analyze_session":
                return await _handle_analyze_session(arguments, config)
            elif name == "distill_workflow":
                return await _handle_distill_workflow(arguments, config)
            elif name == "reflect_workflow":
                return await _handle_reflect_workflow(arguments)
            elif name == "generate_langgraph":
                return await _handle_generate_langgraph(arguments)
            else:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False),
                )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, ensure_ascii=False),
            )]
    
    return server


async def _handle_list_sessions(arguments: dict[str, Any], config) -> Sequence[TextContent]:
    """处理列出会话请求"""
    logs_dir = Path(config.storage.logs_dir).expanduser()
    
    if not logs_dir.exists():
        return [TextContent(
            type="text",
            text=json.dumps({"sessions": [], "message": "No sessions found"}, ensure_ascii=False),
        )]
    
    sessions = []
    limit = arguments.get("limit", 20)
    
    for session_dir in sorted(logs_dir.iterdir(), reverse=True):
        if len(sessions) >= limit:
            break
        
        if session_dir.is_dir():
            metadata_file = session_dir / "metadata.json"
            if metadata_file.exists():
                try:
                    data = json.loads(metadata_file.read_text())
                    sessions.append({
                        "session_id": session_dir.name,
                        "start_time": data.get("start_time"),
                        "client": data.get("client"),
                        "model": data.get("model"),
                        "request_count": data.get("request_count", 0),
                    })
                except Exception:
                    sessions.append({"session_id": session_dir.name})
    
    return [TextContent(
        type="text",
        text=json.dumps({"sessions": sessions}, ensure_ascii=False, indent=2),
    )]


async def _handle_get_session(arguments: dict[str, Any], config) -> Sequence[TextContent]:
    """处理获取会话请求"""
    session_id = arguments.get("session_id")
    if not session_id:
        return [TextContent(
            type="text",
            text=json.dumps({"error": "Missing session_id"}, ensure_ascii=False),
        )]
    
    logs_dir = Path(config.storage.logs_dir).expanduser()
    session_dir = logs_dir / session_id
    
    if not session_dir.exists():
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Session {session_id} not found"}, ensure_ascii=False),
        )]
    
    # 读取 metadata
    metadata_file = session_dir / "metadata.json"
    metadata = json.loads(metadata_file.read_text()) if metadata_file.exists() else {}
    
    # 收集消息
    messages = []
    i = 1
    while True:
        req_file = session_dir / f"{i:03d}_request.json"
        if not req_file.exists():
            break
        
        req_data = json.loads(req_file.read_text())
        messages.append({"sequence": i, "type": "request", "data": req_data})
        
        res_file = session_dir / f"{i:03d}_response.json"
        if res_file.exists():
            res_data = json.loads(res_file.read_text())
            messages.append({"sequence": i, "type": "response", "data": res_data})
        
        i += 1
    
    return [TextContent(
        type="text",
        text=json.dumps({
            "session_id": session_id,
            "metadata": metadata,
            "messages": messages,
        }, ensure_ascii=False, indent=2),
    )]


async def _handle_analyze_session(arguments: dict[str, Any], config) -> Sequence[TextContent]:
    """处理分析会话请求"""
    from ..inspector import InspectorEngine
    
    session_id = arguments.get("session_id")
    aspects = arguments.get("aspects", ["memory", "planning", "tools", "rounds"])
    
    # 获取会话数据
    logs_dir = Path(config.storage.logs_dir).expanduser()
    session_dir = logs_dir / session_id
    
    if not session_dir.exists():
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Session {session_id} not found"}, ensure_ascii=False),
        )]
    
    # 加载消息
    messages = []
    i = 1
    while True:
        req_file = session_dir / f"{i:03d}_request.json"
        if not req_file.exists():
            break
        req_data = json.loads(req_file.read_text())
        raw_req = req_data.get("raw_request", {})
        messages.extend(raw_req.get("messages", []))
        i += 1
    
    # 分析
    engine = InspectorEngine()
    result = engine.analyze(messages, aspects=aspects)
    
    return [TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2),
    )]


async def _handle_distill_workflow(arguments: dict[str, Any], config) -> Sequence[TextContent]:
    """处理蒸馏工作流请求"""
    from ..distiller import DistillEngine
    from ..codegen import WorkflowDSL, DSLFormat
    
    session_id = arguments.get("session_id")
    output_format = arguments.get("format", "yaml")
    
    # 获取会话数据
    logs_dir = Path(config.storage.logs_dir).expanduser()
    session_dir = logs_dir / session_id
    
    if not session_dir.exists():
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Session {session_id} not found"}, ensure_ascii=False),
        )]
    
    # 加载消息
    messages = []
    i = 1
    while True:
        req_file = session_dir / f"{i:03d}_request.json"
        if not req_file.exists():
            break
        req_data = json.loads(req_file.read_text())
        raw_req = req_data.get("raw_request", {})
        for msg in raw_req.get("messages", []):
            messages.append({
                "role": msg.get("role"),
                "content": msg.get("content"),
            })
        i += 1
    
    # 蒸馏
    engine = DistillEngine()
    result = await engine.distill(messages, session_id=session_id)
    
    # 格式化输出
    dsl = WorkflowDSL()
    fmt = DSLFormat.YAML if output_format == "yaml" else DSLFormat.JSON
    output = dsl.generate(result.workflow, format=fmt)
    
    return [TextContent(
        type="text",
        text=output.content,
    )]


async def _handle_reflect_workflow(arguments: dict[str, Any]) -> Sequence[TextContent]:
    """处理反思工作流请求"""
    import yaml
    from ..schemas import Workflow
    from ..reflector import ReflectorEngine
    
    workflow_str = arguments.get("workflow", "")
    
    # 解析工作流
    try:
        data = json.loads(workflow_str)
    except json.JSONDecodeError:
        data = yaml.safe_load(workflow_str)
    
    workflow = Workflow.model_validate(data)
    
    # 反思
    engine = ReflectorEngine()
    result = await engine.reflect(workflow)
    
    return [TextContent(
        type="text",
        text=json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
    )]


async def _handle_generate_langgraph(arguments: dict[str, Any]) -> Sequence[TextContent]:
    """处理生成 LangGraph 代码请求"""
    import yaml
    from ..schemas import Workflow
    from ..codegen import LangGraphGenerator
    
    workflow_str = arguments.get("workflow", "")
    include_tests = arguments.get("include_tests", False)
    
    # 解析工作流
    try:
        data = json.loads(workflow_str)
    except json.JSONDecodeError:
        data = yaml.safe_load(workflow_str)
    
    workflow = Workflow.model_validate(data)
    
    # 生成代码
    generator = LangGraphGenerator()
    code = generator.generate(workflow, include_tests=include_tests)
    
    result = {"main_code": code.main_code}
    if code.test_code:
        result["test_code"] = code.test_code
    result["requirements"] = code.requirements
    
    return [TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2),
    )]


async def run_mcp_server():
    """运行 MCP 服务器"""
    server = create_mcp_server()
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    """入口函数"""
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
