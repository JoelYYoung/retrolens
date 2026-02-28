"""
Data Storage Module - Persist API interaction data
"""
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import uuid


class SessionStorage:
    """Session storage manager"""
    
    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = os.getenv("REV_AGENT_LOGS_DIR", "logs")
        self.base_path = Path(base_path)
        self.sessions_path = self.base_path / "sessions"
        self.index_path = self.base_path / "index.json"
        self._ensure_dirs()
        
    def _ensure_dirs(self):
        """Ensure directory structure exists"""
        self.sessions_path.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._save_index({"sessions": []})
    
    def _save_index(self, index: dict):
        """Save index file"""
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def _load_index(self) -> dict:
        """Load index file"""
        if self.index_path.exists():
            with open(self.index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"sessions": []}
    
    def create_session(self, client: str = "unknown", model: str = "unknown", 
                       tags: List[str] = None, notes: str = "") -> str:
        """Create a new session"""
        session_id = str(uuid.uuid4())[:8]
        session_path = self.sessions_path / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "session_id": session_id,
            "start_time": datetime.now().isoformat(),
            "client": client,
            "model": model,
            "tags": tags or [],
            "notes": notes,
            "request_count": 0
        }
        
        # Save metadata
        with open(session_path / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Update index
        index = self._load_index()
        index["sessions"].append({
            "session_id": session_id,
            "start_time": metadata["start_time"],
            "client": client,
            "model": model
        })
        self._save_index(index)
        
        return session_id
    
    def save_request(self, session_id: str, request_data: dict, 
                     extracted: Optional[dict] = None) -> int:
        """Save request data, return sequence number"""
        session_path = self.sessions_path / session_id
        
        # Get current sequence number
        metadata = self._load_metadata(session_id)
        sequence = metadata["request_count"] + 1
        
        # Build storage structure
        request_record = {
            "timestamp": datetime.now().isoformat(),
            "sequence": sequence,
            "raw_request": request_data,
            "extracted": extracted or self._extract_request_fields(request_data)
        }
        
        # Save request
        filename = f"{sequence:03d}_request.json"
        with open(session_path / filename, 'w', encoding='utf-8') as f:
            json.dump(request_record, f, indent=2, ensure_ascii=False)
        
        # Update metadata
        metadata["request_count"] = sequence
        with open(session_path / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        return sequence
    
    def save_response(self, session_id: str, sequence: int, response_data: dict,
                      extracted: Optional[dict] = None):
        """Save response data"""
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
        """Load session metadata"""
        session_path = self.sessions_path / session_id
        metadata_path = session_path / "metadata.json"
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _extract_request_fields(self, request_data: dict) -> dict:
        """Extract key fields from request"""
        system_prompt = request_data.get("system", "")
        if isinstance(system_prompt, list):
            # Handle structured system prompt
            system_prompt = json.dumps(system_prompt)
        
        messages = request_data.get("messages", [])
        tools = request_data.get("tools", [])
        
        return {
            "model": request_data.get("model", "unknown"),
            "system_prompt_length": len(system_prompt),
            "system_prompt_hash": hashlib.sha256(system_prompt.encode()).hexdigest()[:16],
            "messages_count": len(messages),
            "messages_total_tokens_estimate": self._estimate_tokens(messages),
            "tools_count": len(tools),
            "tools_names": [t.get("name", "unknown") for t in tools],
            "has_thinking": request_data.get("thinking", {}).get("type") == "enabled",
            "max_tokens": request_data.get("max_tokens", 0)
        }
    
    def _extract_response_fields(self, response_data: dict) -> dict:
        """Extract key fields from response"""
        content = response_data.get("content", [])
        
        tool_uses = []
        text_length = 0
        has_thinking = False
        
        for item in content:
            item_type = item.get("type", "")
            if item_type == "tool_use":
                tool_uses.append(item.get("name", "unknown"))
            elif item_type == "text":
                text_length += len(item.get("text", ""))
            elif item_type == "thinking":
                has_thinking = True
        
        return {
            "stop_reason": response_data.get("stop_reason", "unknown"),
            "tool_uses": tool_uses,
            "text_length": text_length,
            "has_thinking": has_thinking,
            "content_blocks_count": len(content)
        }
    
    def _estimate_tokens(self, messages: list) -> int:
        """Estimate token count for messages (rough estimate: ~1 token per 4 characters)"""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            total_chars += len(item.get("text", ""))
                        elif item.get("type") == "tool_result":
                            total_chars += len(str(item.get("content", "")))
        return total_chars // 4
    
    def get_session_data(self, session_id: str) -> Dict[str, Any]:
        """Get complete session data"""
        session_path = self.sessions_path / session_id
        
        if not session_path.exists():
            raise ValueError(f"Session {session_id} not found")
        
        metadata = self._load_metadata(session_id)
        
        requests = []
        responses = []
        
        for file in sorted(session_path.glob("*_request.json")):
            with open(file, 'r', encoding='utf-8') as f:
                requests.append(json.load(f))
        
        for file in sorted(session_path.glob("*_response.json")):
            with open(file, 'r', encoding='utf-8') as f:
                responses.append(json.load(f))
        
        return {
            "metadata": metadata,
            "requests": requests,
            "responses": responses
        }
    
    def list_sessions(self) -> List[dict]:
        """List all sessions"""
        index = self._load_index()
        return index.get("sessions", [])


# Global storage instance
_storage: Optional[SessionStorage] = None
_current_session: Optional[str] = None


def get_storage() -> SessionStorage:
    """Get global storage instance"""
    global _storage
    if _storage is None:
        _storage = SessionStorage()
    return _storage


def get_or_create_session(client: str = "claude-code", model: str = "unknown") -> str:
    """Get or create current session"""
    global _current_session
    if _current_session is None:
        _current_session = get_storage().create_session(client=client, model=model)
    return _current_session


def reset_session():
    """Reset session (start a new session)"""
    global _current_session
    _current_session = None
