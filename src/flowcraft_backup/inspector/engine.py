"""
Session Inspector Engine - 统一会话分析接口
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory import MemoryAnalyzer
from .planning import PlanningAnalyzer
from .tools import ToolsAnalyzer
from .rounds import RoundAnalyzer
from ..config import get_config


class SessionInspector:
    """
    会话检查器 - 提供统一的会话分析接口
    
    整合 Memory、Planning、Tools 和 Round 分析器，
    提供完整的会话分析能力。
    
    Example:
        >>> inspector = SessionInspector()
        >>> summary = inspector.get_session_summary("abc123")
        >>> rounds = inspector.get_rounds("abc123")
    """
    
    def __init__(self, logs_path: Optional[str] = None):
        """
        初始化会话检查器
        
        Args:
            logs_path: 日志目录路径，如不指定则使用配置
        """
        if logs_path:
            self.logs_path = Path(logs_path)
        else:
            config = get_config()
            self.logs_path = Path(config.storage.logs_dir)
        
        self.sessions_path = self.logs_path / "sessions"
        
        # 初始化分析器
        self.memory_analyzer = MemoryAnalyzer()
        self.planning_analyzer = PlanningAnalyzer()
        self.tools_analyzer = ToolsAnalyzer()
        self.round_analyzer = RoundAnalyzer(str(self.logs_path))
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话
        
        Returns:
            会话信息列表
        """
        return self.round_analyzer.list_sessions()
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话摘要
        """
        return self.round_analyzer.get_session_summary(session_id)
    
    def get_rounds(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取会话轮次
        
        Args:
            session_id: 会话 ID
            
        Returns:
            轮次列表
        """
        return self.round_analyzer.analyze_rounds(session_id)
    
    def get_round_detail(
        self, 
        session_id: str, 
        round_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        获取轮次详情
        
        Args:
            session_id: 会话 ID
            round_number: 轮次编号
            
        Returns:
            轮次详情
        """
        return self.round_analyzer.get_round_detail(session_id, round_number)
    
    def get_round_new_info(
        self, 
        session_id: str, 
        round_number: int
    ) -> Dict[str, Any]:
        """
        获取轮次新信息
        
        Args:
            session_id: 会话 ID
            round_number: 轮次编号
            
        Returns:
            轮次新信息
        """
        return self.round_analyzer.get_round_new_info(session_id, round_number)
    
    def analyze_session(self, session_id: str) -> Dict[str, Any]:
        """
        完整分析会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            完整分析结果
        """
        session_data = self._load_session_data(session_id)
        if not session_data:
            return {"error": "Session not found"}
        
        return analyze_session(session_data)
    
    def analyze_memory(self, session_id: str) -> Dict[str, Any]:
        """
        分析内存使用
        
        Args:
            session_id: 会话 ID
            
        Returns:
            内存分析结果
        """
        messages = self._extract_all_messages(session_id)
        return self.memory_analyzer.analyze(messages)
    
    def analyze_planning(self, session_id: str) -> Dict[str, Any]:
        """
        分析规划行为
        
        Args:
            session_id: 会话 ID
            
        Returns:
            规划分析结果
        """
        messages = self._extract_all_messages(session_id)
        system_prompt = self._extract_system_prompt(session_id)
        return self.planning_analyzer.analyze(messages, system_prompt)
    
    def analyze_tools(self, session_id: str) -> Dict[str, Any]:
        """
        分析工具定义
        
        Args:
            session_id: 会话 ID
            
        Returns:
            工具分析结果
        """
        tools = self._extract_tools(session_id)
        return self.tools_analyzer.analyze(tools)
    
    def analyze_tool_usage(self, session_id: str) -> Dict[str, Any]:
        """
        分析工具使用情况
        
        Args:
            session_id: 会话 ID
            
        Returns:
            工具使用统计
        """
        messages = self._extract_all_messages(session_id)
        return self.tools_analyzer.analyze_tool_usage(messages)
    
    def diff_rounds(
        self, 
        session_id: str, 
        round_a: int, 
        round_b: int
    ) -> Dict[str, Any]:
        """
        比较两个轮次的差异
        
        Args:
            session_id: 会话 ID
            round_a: 第一个轮次编号
            round_b: 第二个轮次编号
            
        Returns:
            差异信息
        """
        info_a = self.get_round_new_info(session_id, round_a)
        info_b = self.get_round_new_info(session_id, round_b)
        
        if "error" in info_a or "error" in info_b:
            return {"error": "One or both rounds not found"}
        
        return {
            "round_a": round_a,
            "round_b": round_b,
            "diff": {
                "user_message_a": info_a.get("user_message", ""),
                "user_message_b": info_b.get("user_message", ""),
                "tool_calls_a": len(info_a.get("new_tool_calls", [])),
                "tool_calls_b": len(info_b.get("new_tool_calls", [])),
                "files_read_a": info_a.get("files_read", []),
                "files_read_b": info_b.get("files_read", []),
                "files_written_a": info_a.get("files_written", []),
                "files_written_b": info_b.get("files_written", []),
            }
        }
    
    # =========================================================================
    # 私有方法
    # =========================================================================
    
    def _load_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载会话数据"""
        session_dir = self.sessions_path / session_id
        if not session_dir.exists():
            return None
        
        metadata_path = session_dir / "metadata.json"
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        requests = []
        responses = []
        
        request_count = metadata.get("request_count", 0)
        for seq in range(1, request_count + 1):
            req_path = session_dir / f"{seq:03d}_request.json"
            if req_path.exists():
                with open(req_path, "r", encoding="utf-8") as f:
                    requests.append(json.load(f))
            
            resp_path = session_dir / f"{seq:03d}_response.json"
            if resp_path.exists():
                with open(resp_path, "r", encoding="utf-8") as f:
                    responses.append(json.load(f))
        
        return {
            "metadata": metadata,
            "requests": requests,
            "responses": responses,
        }
    
    def _extract_all_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """提取所有消息"""
        session_data = self._load_session_data(session_id)
        if not session_data:
            return []
        
        all_messages = []
        for req in session_data.get("requests", []):
            raw_req = req.get("raw_request", {})
            all_messages.extend(raw_req.get("messages", []))
        
        return all_messages
    
    def _extract_system_prompt(self, session_id: str) -> str:
        """提取系统提示"""
        session_data = self._load_session_data(session_id)
        if not session_data:
            return ""
        
        for req in session_data.get("requests", []):
            raw_req = req.get("raw_request", {})
            sp = raw_req.get("system", "")
            
            if sp:
                if isinstance(sp, str):
                    return sp
                elif isinstance(sp, list):
                    return json.dumps(sp)
        
        return ""
    
    def _extract_tools(self, session_id: str) -> List[Dict[str, Any]]:
        """提取工具定义"""
        session_data = self._load_session_data(session_id)
        if not session_data:
            return []
        
        tools: List[Dict[str, Any]] = []
        for req in session_data.get("requests", []):
            raw_req = req.get("raw_request", {})
            req_tools = raw_req.get("tools", [])
            if len(req_tools) > len(tools):
                tools = req_tools
        
        return tools


def analyze_session(session_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析完整的会话数据
    
    Args:
        session_data: 会话数据字典，包含 requests 和 responses
        
    Returns:
        完整的分析结果
    """
    all_messages: List[Dict[str, Any]] = []
    system_prompt = ""
    tools: List[Dict[str, Any]] = []
    
    for req in session_data.get("requests", []):
        raw_req = req.get("raw_request", {})
        
        # 提取系统提示
        if not system_prompt:
            sp = raw_req.get("system", "")
            if isinstance(sp, str):
                system_prompt = sp
            elif isinstance(sp, list):
                system_prompt = json.dumps(sp)
        
        # 收集消息
        all_messages.extend(raw_req.get("messages", []))
        
        # 提取工具（取最大的集合）
        req_tools = raw_req.get("tools", [])
        if len(req_tools) > len(tools):
            tools = req_tools
    
    # 创建分析器
    memory_analyzer = MemoryAnalyzer()
    planning_analyzer = PlanningAnalyzer()
    tools_analyzer = ToolsAnalyzer()
    
    return {
        "memory_analysis": memory_analyzer.analyze(all_messages),
        "planning_analysis": planning_analyzer.analyze(all_messages, system_prompt),
        "tools_analysis": tools_analyzer.analyze(tools),
        "session_stats": {
            "total_requests": len(session_data.get("requests", [])),
            "total_responses": len(session_data.get("responses", [])),
            "unique_messages": len(all_messages),
        },
    }
