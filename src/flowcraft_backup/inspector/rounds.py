"""
Round Analyzer - 划分会话轮次

将 Agent 会话的请求/响应序列划分为会话轮次，便于理解会话结构。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import get_config


class RoundAnalyzer:
    """
    轮次分析器 - 将 Agent 会话划分为会话轮次
    
    轮次划分规则：
    1. 新轮次开始：主模型请求有新的用户消息（非 tool_result）
    2. 轮次内容：包含主请求、工具调用、辅助请求（如标题生成）
    3. 轮次结束：stop_reason == "end_turn" 且下一请求有新用户消息
    """
    
    # 辅助请求的标记
    AUXILIARY_MARKERS = [
        # 标题/摘要生成
        "write a 5-10 word title",
        "Summarize this coding conversation",
        # 文件路径提取
        "Extract any file paths",
        "is_displaying_contents",
        # 话题检测
        "Analyze if this message indicates a new conversation topic",
        "isNewTopic",
        # 建议模式
        "SUGGESTION MODE",
        "Suggest what the user might",
        # 命令前缀检测
        "<policy_spec>",
        "Your task is to process Bash commands",
        "command prefix detection",
    ]
    
    # 系统标签前缀（需要过滤）
    SYSTEM_TAG_PREFIXES = [
        "<environment_info>",
        "<workspace_info>",
        "<conversation-summary>",
    ]
    
    # 特殊标签（返回简化描述）
    SPECIAL_TAGS = {
        "<task-notification>": "[Background task notification]",
    }
    
    def __init__(self, logs_path: Optional[str] = None):
        """
        初始化轮次分析器
        
        Args:
            logs_path: 日志目录路径，如不指定则使用配置
        """
        if logs_path:
            self.logs_path = Path(logs_path)
        else:
            config = get_config()
            self.logs_path = Path(config.storage.logs_dir)
        
        self.sessions_path = self.logs_path / "sessions"
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话
        
        Returns:
            会话信息列表
        """
        index_path = self.logs_path / "index.json"
        if not index_path.exists():
            return []
        
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        
        sessions = []
        for sess in index.get("sessions", []):
            session_id = sess["session_id"]
            metadata = self._load_metadata(session_id)
            
            if metadata:
                sessions.append({
                    "session_id": session_id,
                    "start_time": sess.get("start_time"),
                    "client": sess.get("client"),
                    "model": sess.get("model"),
                    "request_count": metadata.get("request_count", 0),
                })
        
        return sessions
    
    def analyze_rounds(self, session_id: str) -> List[Dict[str, Any]]:
        """
        分析会话并划分为轮次
        
        Args:
            session_id: 会话 ID
            
        Returns:
            轮次列表
        """
        metadata = self._load_metadata(session_id)
        if not metadata:
            return []
        
        request_count = metadata.get("request_count", 0)
        if request_count == 0:
            return []
        
        rounds: List[Dict[str, Any]] = []
        current_round: Optional[Dict[str, Any]] = None
        last_user_hash: Optional[str] = None
        last_main_request: Optional[Dict[str, Any]] = None
        
        for seq in range(1, request_count + 1):
            request = self._load_request(session_id, seq)
            response = self._load_response(session_id, seq)
            
            if not request:
                continue
            
            is_aux = self._is_auxiliary_request(request)
            user_hash = self._get_user_message_hash(request)
            
            # 判断是否开始新轮次
            start_new_round = self._should_start_new_round(
                current_round, is_aux, user_hash, last_user_hash,
                request, session_id
            )
            
            if start_new_round:
                if current_round:
                    rounds.append(current_round)
                
                user_msg = self._extract_new_user_message(request, last_main_request)
                current_round = {
                    "round_number": len(rounds) + 1,
                    "sequences": [],
                    "main_sequences": [],
                    "auxiliary_sequences": [],
                    "user_message": user_msg or "",
                    "final_response": "",
                    "tool_calls": [],
                    "start_time": request.get("timestamp"),
                    "end_time": None,
                }
            
            if current_round:
                current_round["sequences"].append(seq)
                
                if is_aux:
                    current_round["auxiliary_sequences"].append(seq)
                else:
                    current_round["main_sequences"].append(seq)
                    last_main_request = request
                    last_user_hash = user_hash
                
                if response:
                    current_round["end_time"] = response.get("timestamp")
                    self._process_response(response, current_round, is_aux)
        
        if current_round:
            rounds.append(current_round)
        
        return rounds
    
    def get_round_detail(
        self, 
        session_id: str, 
        round_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        获取特定轮次的详细信息
        
        Args:
            session_id: 会话 ID
            round_number: 轮次编号
            
        Returns:
            轮次详情，如未找到返回 None
        """
        rounds = self.analyze_rounds(session_id)
        for r in rounds:
            if r["round_number"] == round_number:
                return r
        return None
    
    def get_round_new_info(
        self, 
        session_id: str, 
        round_number: int
    ) -> Dict[str, Any]:
        """
        获取轮次中的新信息
        
        Args:
            session_id: 会话 ID
            round_number: 轮次编号
            
        Returns:
            新信息摘要
        """
        rounds = self.analyze_rounds(session_id)
        
        target_round = None
        for r in rounds:
            if r["round_number"] == round_number:
                target_round = r
                break
        
        if not target_round:
            return {"error": f"Round {round_number} not found"}
        
        new_info = {
            "round_number": round_number,
            "user_message": target_round.get("user_message", ""),
            "new_tool_calls": target_round.get("tool_calls", []),
            "response": target_round.get("final_response", ""),
            "files_read": [],
            "files_written": [],
            "commands_executed": [],
        }
        
        # 分析工具调用
        for tool in target_round.get("tool_calls", []):
            name = tool.get("name", "").lower()
            input_data = tool.get("input", {})
            
            if "read" in name or "cat" in name:
                path = self._extract_path(input_data)
                if path:
                    new_info["files_read"].append(path)
            
            elif "write" in name or "edit" in name:
                path = self._extract_path(input_data)
                if path:
                    new_info["files_written"].append(path)
            
            elif "bash" in name or "command" in name or "terminal" in name:
                cmd = input_data.get("command") or input_data.get("cmd")
                if cmd:
                    new_info["commands_executed"].append(cmd)
        
        return new_info
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话摘要
        """
        metadata = self._load_metadata(session_id)
        if not metadata:
            return {"error": "Session not found"}
        
        rounds = self.analyze_rounds(session_id)
        
        total_tool_calls = sum(len(r.get("tool_calls", [])) for r in rounds)
        total_aux = sum(len(r.get("auxiliary_sequences", [])) for r in rounds)
        
        return {
            "session_id": session_id,
            "start_time": metadata.get("start_time"),
            "client": metadata.get("client"),
            "model": metadata.get("model"),
            "total_requests": metadata.get("request_count", 0),
            "total_rounds": len(rounds),
            "total_tool_calls": total_tool_calls,
            "auxiliary_requests": total_aux,
            "rounds_summary": [
                {
                    "round": r["round_number"],
                    "user_preview": (r["user_message"][:100] + "...") 
                        if len(r.get("user_message", "")) > 100 
                        else r.get("user_message", ""),
                    "tool_count": len(r.get("tool_calls", [])),
                    "sequences": r["sequences"],
                }
                for r in rounds
            ],
        }
    
    # =========================================================================
    # 私有方法
    # =========================================================================
    
    def _load_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载会话元数据"""
        path = self.sessions_path / session_id / "metadata.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _load_request(self, session_id: str, sequence: int) -> Optional[Dict[str, Any]]:
        """加载请求"""
        path = self.sessions_path / session_id / f"{sequence:03d}_request.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _load_response(self, session_id: str, sequence: int) -> Optional[Dict[str, Any]]:
        """加载响应"""
        path = self.sessions_path / session_id / f"{sequence:03d}_response.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _is_auxiliary_request(self, request: Dict[str, Any]) -> bool:
        """判断是否为辅助请求"""
        raw = request.get("raw_request", {})
        
        # Token 计数请求
        if raw.get("max_tokens", 0) == 1:
            return True
        
        # 无工具时检查系统提示
        tools = raw.get("tools", [])
        if not tools:
            system = raw.get("system", [])
            system_text = self._extract_system_text(system)
            
            for marker in self.AUXILIARY_MARKERS:
                if marker.lower() in system_text.lower():
                    return True
        
        # 检查用户消息
        messages = raw.get("messages", [])
        for msg in messages:
            if msg.get("role") == "user":
                content_text = self._extract_message_text(msg.get("content", ""))
                
                for marker in self.AUXILIARY_MARKERS:
                    if marker.lower() in content_text.lower():
                        return True
        
        return False
    
    def _get_user_message_hash(self, request: Dict[str, Any]) -> Optional[str]:
        """获取请求中用户消息的哈希（排除 tool_result）"""
        raw = request.get("raw_request", {})
        messages = raw.get("messages", [])
        
        user_content = []
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_content.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "tool_result":
                                continue
                            if item.get("type") == "text":
                                user_content.append(item.get("text", ""))
                        elif isinstance(item, str):
                            user_content.append(item)
        
        if user_content:
            combined = "|||".join(user_content)
            return hashlib.md5(combined.encode()).hexdigest()[:16]
        return None
    
    def _should_start_new_round(
        self,
        current_round: Optional[Dict[str, Any]],
        is_aux: bool,
        user_hash: Optional[str],
        last_user_hash: Optional[str],
        request: Dict[str, Any],
        session_id: str,
    ) -> bool:
        """判断是否应开始新轮次"""
        if current_round is None:
            return True
        
        if is_aux:
            return False
        
        if not user_hash or user_hash == last_user_hash:
            return False
        
        raw = request.get("raw_request", {})
        messages = raw.get("messages", [])
        
        has_tool_result = False
        has_new_user_text = False
        
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "tool_result":
                                has_tool_result = True
                            elif item.get("type") == "text":
                                has_new_user_text = True
        
        if has_new_user_text and not has_tool_result:
            return True
        
        if has_new_user_text and current_round:
            last_seq = current_round["sequences"][-1] if current_round["sequences"] else 0
            last_resp = self._load_response(session_id, last_seq)
            if last_resp:
                stop_reason = last_resp.get("raw_response", {}).get("stop_reason")
                if stop_reason == "end_turn":
                    return True
        
        return False
    
    def _extract_new_user_message(
        self,
        request: Dict[str, Any],
        prev_request: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """提取新的用户消息"""
        raw = request.get("raw_request", {})
        messages = raw.get("messages", [])
        
        prev_msg_count = 0
        if prev_request:
            prev_raw = prev_request.get("raw_request", {})
            prev_msg_count = len(prev_raw.get("messages", []))
        
        # 提取新消息
        new_messages = []
        special_label = None
        
        for i, msg in enumerate(messages):
            if i < prev_msg_count:
                continue
            
            if msg.get("role") == "user":
                content = msg.get("content", "")
                
                if isinstance(content, str):
                    label = self._get_special_tag_label(content)
                    if label:
                        special_label = label
                    elif not self._is_system_tag(content):
                        new_messages.append(content)
                
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            label = self._get_special_tag_label(text)
                            if label:
                                special_label = label
                            elif not self._is_system_tag(text):
                                new_messages.append(text)
                        elif isinstance(item, str):
                            label = self._get_special_tag_label(item)
                            if label:
                                special_label = label
                            elif not self._is_system_tag(item):
                                new_messages.append(item)
        
        if new_messages:
            return "\n".join(new_messages)
        
        if special_label:
            return special_label
        
        # 无新消息时提取第一条用户消息
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                
                if isinstance(content, str):
                    if content.strip().startswith("<"):
                        continue
                    return content[:500] if len(content) > 500 else content
                
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            if text.strip().startswith("<"):
                                continue
                            return text[:500] if len(text) > 500 else text
        
        return None
    
    def _process_response(
        self,
        response: Dict[str, Any],
        current_round: Dict[str, Any],
        is_aux: bool,
    ):
        """处理响应，提取工具调用和最终响应"""
        raw_resp = response.get("raw_response", {})
        content = raw_resp.get("content", [])
        
        for item in content:
            if not isinstance(item, dict):
                continue
            
            if item.get("type") == "tool_use":
                current_round["tool_calls"].append({
                    "name": item.get("name"),
                    "id": item.get("id"),
                    "input": item.get("input"),
                })
            
            elif item.get("type") == "text" and not is_aux:
                current_round["final_response"] = item.get("text", "")
    
    def _extract_system_text(self, system: Any) -> str:
        """提取系统提示文本"""
        if isinstance(system, str):
            return system
        
        if isinstance(system, list):
            parts = []
            for item in system:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return " ".join(parts)
        
        return ""
    
    def _extract_message_text(self, content: Any) -> str:
        """提取消息文本"""
        if isinstance(content, str):
            return content
        
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return " ".join(parts)
        
        return ""
    
    def _extract_path(self, input_data: Dict[str, Any]) -> Optional[str]:
        """从工具输入中提取文件路径"""
        return (
            input_data.get("path") or
            input_data.get("file_path") or
            input_data.get("filePath")
        )
    
    def _get_special_tag_label(self, text: str) -> Optional[str]:
        """检查是否为特殊标签，返回标签描述"""
        stripped = text.strip()
        for prefix, label in self.SPECIAL_TAGS.items():
            if stripped.startswith(prefix):
                return label
        return None
    
    def _is_system_tag(self, text: str) -> bool:
        """检查是否为系统标签"""
        stripped = text.strip()
        
        # 短标签
        if stripped.startswith("<") and stripped.endswith(">") and len(stripped) < 100:
            return True
        
        # 系统标签前缀
        for prefix in self.SYSTEM_TAG_PREFIXES:
            if stripped.startswith(prefix):
                return True
        
        return False
