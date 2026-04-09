"""
Session Storage - 会话存储管理

负责持久化 API 交互数据：
- 会话创建和管理
- 请求/响应保存
- 元数据提取
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import uuid

from ..config import get_config


class SessionStorage:
    """会话存储管理器"""
    
    def __init__(self, base_path: Optional[str] = None):
        """初始化存储管理器
        
        Args:
            base_path: 存储根路径，None 则从配置读取
        """
        if base_path is None:
            config = get_config()
            base_path = str(config.storage.logs_path)
        
        self.base_path = Path(base_path).expanduser()
        self.sessions_path = self.base_path / "sessions"
        self.index_path = self.base_path / "index.json"
        self._ensure_dirs()
        
    def _ensure_dirs(self):
        """确保目录结构存在"""
        self.sessions_path.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._save_index({"sessions": []})
    
    def _save_index(self, index: dict):
        """保存索引文件"""
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def _load_index(self) -> dict:
        """加载索引文件"""
        if self.index_path.exists():
            with open(self.index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"sessions": []}
    
    def create_session(
        self, 
        client: str = "unknown", 
        model: str = "unknown", 
        protocol: str = "unknown",
        tags: Optional[List[str]] = None, 
        notes: str = ""
    ) -> str:
        """创建新会话
        
        Args:
            client: 客户端类型 (claude-code, vscode-copilot, etc.)
            model: 使用的模型
            protocol: 协议类型 (anthropic, openai)
            tags: 标签
            notes: 备注
            
        Returns:
            会话 ID
        """
        session_id = str(uuid.uuid4())[:8]
        session_path = self.sessions_path / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "session_id": session_id,
            "start_time": datetime.now().isoformat(),
            "client": client,
            "model": model,
            "protocol": protocol,
            "tags": tags or [],
            "notes": notes,
            "request_count": 0
        }
        
        # 保存元数据
        with open(session_path / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # 更新索引
        index = self._load_index()
        index["sessions"].append({
            "session_id": session_id,
            "start_time": metadata["start_time"],
            "client": client,
            "model": model,
            "protocol": protocol
        })
        self._save_index(index)
        
        return session_id
    
    def save_request(
        self, 
        session_id: str, 
        request_data: dict, 
        extracted: Optional[dict] = None
    ) -> int:
        """保存请求数据
        
        Args:
            session_id: 会话 ID
            request_data: 原始请求数据
            extracted: 提取的关键字段
            
        Returns:
            序列号
        """
        session_path = self.sessions_path / session_id
        
        # 获取当前序列号
        metadata = self._load_metadata(session_id)
        sequence = metadata["request_count"] + 1
        
        # 构建存储结构
        request_record = {
            "timestamp": datetime.now().isoformat(),
            "sequence": sequence,
            "raw_request": request_data,
            "extracted": extracted or self._extract_request_fields(request_data)
        }
        
        # 保存请求
        filename = f"{sequence:03d}_request.json"
        with open(session_path / filename, 'w', encoding='utf-8') as f:
            json.dump(request_record, f, indent=2, ensure_ascii=False)
        
        # 更新元数据
        metadata["request_count"] = sequence
        with open(session_path / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        return sequence
    
    def save_response(
        self, 
        session_id: str, 
        sequence: int, 
        response_data: dict,
        extracted: Optional[dict] = None
    ):
        """保存响应数据
        
        Args:
            session_id: 会话 ID
            sequence: 序列号
            response_data: 原始响应数据
            extracted: 提取的关键字段
        """
        session_path = self.sessions_path / session_id
        
        response_record = {
            "timestamp": datetime.now().isoformat(),
            "sequence": sequence,
            "raw_response": response_data,
            "extracted": extracted or self._extract_response_fields(response_data)
        }
        
        filename = f"{sequence:03d}_response.json"
        with open(session_path / filename, 'w', encoding='utf-8') as f:
            json.dump(response_record, f, indent=2, ensure_ascii=False)
    
    def _load_metadata(self, session_id: str) -> dict:
        """加载会话元数据"""
        session_path = self.sessions_path / session_id
        metadata_path = session_path / "metadata.json"
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话信息
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话元数据，不存在则返回 None
        """
        try:
            return self._load_metadata(session_id)
        except FileNotFoundError:
            return None
    
    def list_sessions(self, limit: int = 50) -> List[dict]:
        """列出会话
        
        Args:
            limit: 最大返回数量
            
        Returns:
            会话列表
        """
        sessions = []
        
        if not self.sessions_path.exists():
            return sessions
        
        for session_dir in sorted(self.sessions_path.iterdir(), reverse=True):
            if len(sessions) >= limit:
                break
            
            if session_dir.is_dir():
                metadata_file = session_dir / "metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file) as f:
                            sessions.append(json.load(f))
                    except Exception:
                        pass
        
        return sessions
    
    def get_session_messages(self, session_id: str) -> List[dict]:
        """获取会话的所有消息
        
        Args:
            session_id: 会话 ID
            
        Returns:
            消息列表
        """
        session_path = self.sessions_path / session_id
        messages = []
        
        i = 1
        while True:
            req_file = session_path / f"{i:03d}_request.json"
            res_file = session_path / f"{i:03d}_response.json"
            
            if not req_file.exists():
                break
            
            # 读取请求
            with open(req_file) as f:
                req_data = json.load(f)
                messages.append({
                    "type": "request",
                    "sequence": i,
                    "data": req_data
                })
            
            # 读取响应（如果存在）
            if res_file.exists():
                with open(res_file) as f:
                    res_data = json.load(f)
                    messages.append({
                        "type": "response", 
                        "sequence": i,
                        "data": res_data
                    })
            
            i += 1
        
        return messages
    
    def _extract_request_fields(self, request_data: dict) -> dict:
        """从请求中提取关键字段"""
        system_prompt = request_data.get("system", "")
        if isinstance(system_prompt, list):
            system_prompt = json.dumps(system_prompt)
        
        messages = request_data.get("messages", [])
        tools = request_data.get("tools", [])
        
        return {
            "model": request_data.get("model", "unknown"),
            "system_prompt_length": len(str(system_prompt)),
            "system_prompt_hash": hashlib.sha256(str(system_prompt).encode()).hexdigest()[:16],
            "messages_count": len(messages),
            "tools_count": len(tools),
            "tools_names": [t.get("name", "unknown") for t in tools],
            "has_thinking": request_data.get("thinking", {}).get("type") == "enabled",
            "max_tokens": request_data.get("max_tokens", 0),
            "stream": request_data.get("stream", False)
        }
    
    def _extract_response_fields(self, response_data: dict) -> dict:
        """从响应中提取关键字段"""
        content = response_data.get("content", [])
        usage = response_data.get("usage", {})
        
        # 计算工具调用数
        tool_calls = 0
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_calls += 1
        
        return {
            "model": response_data.get("model", "unknown"),
            "stop_reason": response_data.get("stop_reason", "unknown"),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "tool_calls_count": tool_calls,
            "has_error": "error" in response_data
        }


# =============================================================================
# 全局存储实例
# =============================================================================

_storage: Optional[SessionStorage] = None


def get_storage() -> SessionStorage:
    """获取全局存储实例"""
    global _storage
    if _storage is None:
        _storage = SessionStorage()
    return _storage


def get_or_create_session(
    client: str = "unknown",
    model: str = "unknown",
    protocol: str = "unknown"
) -> str:
    """获取或创建会话（用于代理服务器）"""
    storage = get_storage()
    return storage.create_session(client=client, model=model, protocol=protocol)
