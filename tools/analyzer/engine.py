"""
Analysis Engine - Core Session Analysis Module

Contains:
- MemoryAnalyzer: Detect context duplication and redundancy
- PlanningAnalyzer: Detect planning behavior
- ToolsAnalyzer: Analyze tool definitions and usage
- RoundAnalyzer: Divide conversation rounds
"""

import re
import json
import hashlib
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional


# =============================================================================
# Memory Analyzer
# =============================================================================

class MemoryAnalyzer:
    """Detect duplication and redundancy in context"""
    
    def analyze(self, messages: list) -> dict:
        """Analyze memory usage patterns in message list"""
        return {
            "duplicate_content": self.find_duplicates(messages),
            "file_read_history": self.extract_file_reads(messages),
            "repeated_files": self.find_repeated_file_reads(messages),
            "total_tokens_estimate": self.estimate_tokens(messages),
            "compression_events": self.detect_compression(messages),
            "message_stats": self.get_message_stats(messages)
        }
    
    def find_duplicates(self, messages: list) -> List[dict]:
        """Find duplicate content blocks"""
        content_hashes = {}
        duplicates = []
        
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if isinstance(content, str):
                content_hash = hashlib.md5(content.encode()).hexdigest()
                if content_hash in content_hashes:
                    duplicates.append({
                        "hash": content_hash,
                        "first_occurrence": content_hashes[content_hash],
                        "duplicate_at": i,
                        "length": len(content)
                    })
                else:
                    content_hashes[content_hash] = i
            elif isinstance(content, list):
                for j, item in enumerate(content):
                    if isinstance(item, dict):
                        item_str = json.dumps(item, sort_keys=True)
                        item_hash = hashlib.md5(item_str.encode()).hexdigest()
                        key = f"{i}_{j}"
                        if item_hash in content_hashes:
                            duplicates.append({
                                "hash": item_hash,
                                "first_occurrence": content_hashes[item_hash],
                                "duplicate_at": key,
                                "type": item.get("type", "unknown"),
                                "length": len(item_str)
                            })
                        else:
                            content_hashes[item_hash] = key
        
        return duplicates
    
    def extract_file_reads(self, messages: list) -> List[dict]:
        """Extract all file read operations"""
        file_reads = []
        
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            tool_name = item.get("name", "").lower()
                            if any(kw in tool_name for kw in ["read", "file", "cat"]):
                                input_data = item.get("input", {})
                                file_reads.append({
                                    "message_index": i,
                                    "tool_name": item.get("name"),
                                    "tool_use_id": item.get("id"),
                                    "path": input_data.get("path") or input_data.get("file_path") or input_data.get("filePath"),
                                    "input": input_data
                                })
        
        return file_reads
    
    def find_repeated_file_reads(self, messages: list) -> Dict[str, int]:
        """Detect multiple reads of the same file"""
        file_reads = self.extract_file_reads(messages)
        paths = [fr["path"] for fr in file_reads if fr["path"]]
        return {path: count for path, count in Counter(paths).items() if count > 1}
    
    def estimate_tokens(self, messages: list) -> int:
        """Estimate total token count for messages"""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        total_chars += len(json.dumps(item))
                    elif isinstance(item, str):
                        total_chars += len(item)
        return int(total_chars / 3.5)
    
    def detect_compression(self, messages: list) -> List[dict]:
        """Detect possible compression events"""
        compression_patterns = [
            r"(?i)context.*truncat",
            r"(?i)message.*omit",
            r"(?i)previous.*summar",
            r"(?i)\[.*truncated.*\]",
            r"(?i)content.*compress"
        ]
        
        events = []
        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            for pattern in compression_patterns:
                if re.search(pattern, content):
                    events.append({
                        "message_index": i,
                        "pattern_matched": pattern,
                        "role": msg.get("role")
                    })
                    break
        
        return events
    
    def get_message_stats(self, messages: list) -> dict:
        """Get message statistics"""
        stats = {
            "total": len(messages),
            "by_role": Counter(msg.get("role", "unknown") for msg in messages),
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_results": 0
        }
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", [])
            
            if role == "user":
                stats["user_messages"] += 1
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            stats["tool_results"] += 1
            elif role == "assistant":
                stats["assistant_messages"] += 1
        
        return stats


# =============================================================================
# Planning Analyzer
# =============================================================================

class PlanningAnalyzer:
    """Detect planning behavior"""
    
    PLANNING_PATTERNS = [
        (r"(?i)step\s*\d+[:\s]", "step_numbered"),
        (r"(?i)first.*then.*finally", "sequence_words"),
        (r"(?i)^(plan|planning)[:\s]", "explicit_plan"),
        (r"(?i)i will[:\s]*\n\s*[-\d•]", "will_list"),
        (r"(?i)(todo|task list)[:\s]", "todo_list"),
        (r"<thinking>.*</thinking>", "thinking_block"),
        (r"(?i)let me (break down|decompose|outline)", "decomposition"),
        (r"(?i)my approach[:\s]", "approach_statement"),
        (r"(?i)here'?s (my|the) plan", "plan_statement"),
    ]
    
    def analyze(self, messages: list, system_prompt: str = "") -> dict:
        """Analyze planning behavior"""
        return {
            "system_prompt_has_planning_instruction": self.check_system_planning(system_prompt),
            "explicit_planning_in_responses": self.find_planning_in_messages(messages),
            "thinking_blocks": self.extract_thinking_blocks(messages),
            "task_decomposition_detected": self.detect_task_decomposition(messages),
            "planning_patterns_found": self.find_all_planning_patterns(messages)
        }
    
    def check_system_planning(self, system_prompt: str) -> dict:
        """Check planning instructions in system prompt"""
        planning_keywords = [
            "plan", "planning", "think step", "break down", 
            "decompose", "outline", "strategy", "approach",
            "before coding", "before implementing"
        ]
        
        found = []
        system_lower = system_prompt.lower()
        for keyword in planning_keywords:
            if keyword in system_lower:
                found.append(keyword)
        
        return {
            "has_planning_instructions": len(found) > 0,
            "keywords_found": found,
            "system_prompt_length": len(system_prompt)
        }
    
    def find_planning_in_messages(self, messages: list) -> List[dict]:
        """Find explicit planning in messages"""
        planning_instances = []
        
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
                
            content = msg.get("content", "")
            text = ""
            
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text += item.get("text", "") + "\n"
            
            for pattern, pattern_name in self.PLANNING_PATTERNS:
                matches = list(re.finditer(pattern, text, re.DOTALL))
                if matches:
                    planning_instances.append({
                        "message_index": i,
                        "pattern_name": pattern_name,
                        "matches_count": len(matches),
                        "preview": text[:200] if len(text) > 200 else text
                    })
        
        return planning_instances
    
    def extract_thinking_blocks(self, messages: list) -> List[dict]:
        """Extract thinking block content"""
        thinking_blocks = []
        
        for i, msg in enumerate(messages):
            content = msg.get("content", [])
            if isinstance(content, list):
                for j, item in enumerate(content):
                    if isinstance(item, dict) and item.get("type") == "thinking":
                        thinking_blocks.append({
                            "message_index": i,
                            "block_index": j,
                            "thinking_text": item.get("thinking", "")[:500],
                            "full_length": len(item.get("thinking", ""))
                        })
        
        return thinking_blocks
    
    def detect_task_decomposition(self, messages: list) -> dict:
        """Detect task decomposition"""
        decomposition_indicators = {
            "numbered_lists": 0,
            "bullet_lists": 0,
            "subtask_mentions": 0
        }
        
        numbered_pattern = r"^\s*\d+[\.\)]\s+"
        bullet_pattern = r"^\s*[-•*]\s+"
        subtask_pattern = r"(?i)(subtask|sub-task|step|phase)\s*\d*[:\s]"
        
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            
            content = msg.get("content", "")
            text = ""
            
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text += item.get("text", "") + "\n"
            
            lines = text.split("\n")
            for line in lines:
                if re.match(numbered_pattern, line):
                    decomposition_indicators["numbered_lists"] += 1
                if re.match(bullet_pattern, line):
                    decomposition_indicators["bullet_lists"] += 1
            
            decomposition_indicators["subtask_mentions"] += len(re.findall(subtask_pattern, text))
        
        return {
            "detected": sum(decomposition_indicators.values()) > 3,
            "indicators": decomposition_indicators
        }
    
    def find_all_planning_patterns(self, messages: list) -> Dict[str, int]:
        """Count occurrences of all planning patterns"""
        pattern_counts = {}
        
        for msg in messages:
            content = msg.get("content", "")
            text = ""
            
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text += item.get("text", "") + "\n"
            
            for pattern, pattern_name in self.PLANNING_PATTERNS:
                count = len(re.findall(pattern, text, re.DOTALL))
                if count > 0:
                    pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + count
        
        return pattern_counts


# =============================================================================
# Tools Analyzer
# =============================================================================

class ToolsAnalyzer:
    """Analyze tool definitions"""
    
    TOOL_CATEGORIES = {
        "file_system": ["file", "read", "write", "edit", "create", "delete", "directory", "path"],
        "search": ["grep", "glob", "search", "find", "query"],
        "execution": ["bash", "terminal", "run", "execute", "shell", "command"],
        "agent": ["agent", "subagent", "delegate"],
        "mcp_external": ["mcp_"],
        "web": ["fetch", "http", "url", "browser", "web"],
        "git": ["git", "commit", "branch", "merge"],
    }
    
    def analyze(self, tools: list) -> dict:
        """Analyze tool list"""
        return {
            "tools_summary": self.get_tools_summary(tools),
            "tools_full_definitions": tools,
            "total_tools_count": len(tools),
            "total_tools_tokens": self.estimate_tools_tokens(tools),
            "categorized_tools": self.categorize_tools(tools),
            "tools_by_description_length": self.sort_by_description_length(tools)
        }
    
    def get_tools_summary(self, tools: list) -> List[dict]:
        """Get tool summary"""
        summaries = []
        for t in tools:
            input_schema = t.get("input_schema", {})
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            summaries.append({
                "name": t.get("name", "unknown"),
                "description_preview": (t.get("description", "")[:200] + "...") 
                    if len(t.get("description", "")) > 200 else t.get("description", ""),
                "description_length": len(t.get("description", "")),
                "parameters": list(properties.keys()),
                "required_parameters": required,
                "parameter_count": len(properties)
            })
        
        return summaries
    
    def estimate_tools_tokens(self, tools: list) -> int:
        """Estimate token count for tool definitions"""
        total_chars = len(json.dumps(tools))
        return int(total_chars / 3.5)
    
    def categorize_tools(self, tools: list) -> Dict[str, List[str]]:
        """Categorize tools by type"""
        categories = {cat: [] for cat in self.TOOL_CATEGORIES}
        categories["other"] = []
        
        for t in tools:
            name = t.get("name", "").lower()
            description = t.get("description", "").lower()
            categorized = False
            
            for category, keywords in self.TOOL_CATEGORIES.items():
                for keyword in keywords:
                    if keyword in name or keyword in description:
                        categories[category].append(t.get("name"))
                        categorized = True
                        break
                if categorized:
                    break
            
            if not categorized:
                categories["other"].append(t.get("name"))
        
        return {k: v for k, v in categories.items() if v}
    
    def sort_by_description_length(self, tools: list) -> List[dict]:
        """Sort by description length"""
        sorted_tools = sorted(
            tools,
            key=lambda t: len(t.get("description", "")),
            reverse=True
        )
        return [
            {"name": t.get("name"), "description_length": len(t.get("description", ""))}
            for t in sorted_tools[:10]
        ]
    
    def compare_with_baseline(self, current_tools: list, baseline_tools: list) -> dict:
        """Compare with baseline tool list"""
        current_names = set(t.get("name") for t in current_tools)
        baseline_names = set(t.get("name") for t in baseline_tools)
        
        return {
            "added": list(current_names - baseline_names),
            "removed": list(baseline_names - current_names),
            "unchanged": list(current_names & baseline_names),
            "current_count": len(current_names),
            "baseline_count": len(baseline_names)
        }
    
    def extract_tool_details(self, tool_name: str, tools: list) -> Optional[dict]:
        """Extract detailed information for a specific tool"""
        for t in tools:
            if t.get("name") == tool_name:
                return {
                    "name": t.get("name"),
                    "description": t.get("description"),
                    "input_schema": t.get("input_schema"),
                    "cache_control": t.get("cache_control")
                }
        return None


# =============================================================================
# Round Analyzer
# =============================================================================

class RoundAnalyzer:
    """
    Round Analyzer - Divides Agent session request/response sequences into conversation rounds
    
    Round division rules:
    1. New round starts: Main model request has a new user message (not tool_result)
    2. Round content: Contains main request, tool calls, auxiliary requests (e.g., title generation)
    3. Round ends: stop_reason == "end_turn" and next request has new user message
    """
    
    AUXILIARY_MARKERS = [
        # Title/summary generation
        "write a 5-10 word title",
        "Summarize this coding conversation",
        # File path extraction
        "Extract any file paths",
        "is_displaying_contents",
        # Topic detection
        "Analyze if this message indicates a new conversation topic",
        "isNewTopic",
        # Suggestion mode
        "SUGGESTION MODE",
        "Suggest what the user might",
        # Command prefix detection (security check)
        "<policy_spec>",
        "Your task is to process Bash commands",
        "command prefix detection",
    ]
    
    def __init__(self, logs_path: str = "logs"):
        self.logs_path = Path(logs_path)
        self.sessions_path = self.logs_path / "sessions"
    
    def list_sessions(self) -> list[dict]:
        """List all sessions"""
        index_path = self.logs_path / "index.json"
        if not index_path.exists():
            return []
        
        with open(index_path, 'r', encoding='utf-8') as f:
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
                    "request_count": metadata.get("request_count", 0)
                })
        
        return sessions
    
    def _load_metadata(self, session_id: str) -> Optional[dict]:
        """Load session metadata"""
        metadata_path = self.sessions_path / session_id / "metadata.json"
        if not metadata_path.exists():
            return None
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_request(self, session_id: str, sequence: int) -> Optional[dict]:
        """Load request"""
        path = self.sessions_path / session_id / f"{sequence:03d}_request.json"
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_response(self, session_id: str, sequence: int) -> Optional[dict]:
        """Load response"""
        path = self.sessions_path / session_id / f"{sequence:03d}_response.json"
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _is_auxiliary_request(self, request: dict) -> bool:
        """Determine if this is an auxiliary request"""
        raw = request.get("raw_request", {})
        
        # Token counting request (max_tokens=1)
        max_tokens = raw.get("max_tokens", 0)
        if max_tokens == 1:
            return True
        
        tools = raw.get("tools", [])
        if not tools:
            system = raw.get("system", [])
            if isinstance(system, list):
                system_text = " ".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in system
                )
            else:
                system_text = str(system)
            
            for marker in self.AUXILIARY_MARKERS:
                if marker.lower() in system_text.lower():
                    return True
        
        messages = raw.get("messages", [])
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                content_text = ""
                if isinstance(content, str):
                    content_text = content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            content_text += item.get("text", "") + " "
                        elif isinstance(item, str):
                            content_text += item + " "
                
                for marker in self.AUXILIARY_MARKERS:
                    if marker.lower() in content_text.lower():
                        return True
        
        return False
    
    def _get_user_message_hash(self, request: dict) -> Optional[str]:
        """Get hash of user messages in request (excluding tool_result)"""
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
    
    def _extract_new_user_message(self, request: dict, prev_request: Optional[dict]) -> Optional[str]:
        """Extract new user message or first user message"""
        raw = request.get("raw_request", {})
        messages = raw.get("messages", [])
        
        # Get message count from previous request
        prev_msg_count = 0
        if prev_request:
            prev_raw = prev_request.get("raw_request", {})
            prev_msg_count = len(prev_raw.get("messages", []))
        
        # System tag prefixes to filter (skip when extracting user messages)
        system_tag_prefixes = [
            "<environment_info>",
            "<workspace_info>", 
            "<conversation-summary>",
        ]
        
        # Special tags to recognize but not filter (return simplified description as user message)
        special_tags = {
            "<task-notification>": "[Background task notification]",
        }
        
        def get_special_tag_label(text: str) -> Optional[str]:
            """Check if text is a special tag, return tag description"""
            stripped = text.strip()
            for prefix, label in special_tags.items():
                if stripped.startswith(prefix):
                    return label
            return None
        
        def is_system_tag(text: str) -> bool:
            """Check if text is a system tag (needs filtering)"""
            stripped = text.strip()
            # Short tags starting with < and ending with >
            if stripped.startswith("<") and stripped.endswith(">") and len(stripped) < 100:
                return True
            # Content starting with system tag prefixes
            for prefix in system_tag_prefixes:
                if stripped.startswith(prefix):
                    return True
            return False
        
        # First try to extract new messages
        new_messages = []
        special_label = None
        for i, msg in enumerate(messages):
            if i < prev_msg_count:
                continue
            
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    # Check for special tags
                    label = get_special_tag_label(content)
                    if label:
                        special_label = label
                    elif not is_system_tag(content):
                        new_messages.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                text = item.get("text", "")
                                # Check for special tags
                                label = get_special_tag_label(text)
                                if label:
                                    special_label = label
                                elif not is_system_tag(text):
                                    new_messages.append(text)
                        elif isinstance(item, str):
                            label = get_special_tag_label(item)
                            if label:
                                special_label = label
                            elif not is_system_tag(item):
                                new_messages.append(item)
        
        if new_messages:
            return "\n".join(new_messages)
        
        # If no new messages but has special tag, return special tag description
        if special_label:
            return special_label
        
        # If no new messages, extract first user message (new round scenario)
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    # Filter system tags starting with <
                    if content.strip().startswith("<"):
                        continue
                    return content[:500] if len(content) > 500 else content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            # Filter system tags starting with <
                            if text.strip().startswith("<"):
                                continue
                            return text[:500] if len(text) > 500 else text
        
        return None
    
    def analyze_rounds(self, session_id: str) -> list[dict]:
        """Analyze session and divide into rounds"""
        metadata = self._load_metadata(session_id)
        if not metadata:
            return []
        
        request_count = metadata.get("request_count", 0)
        if request_count == 0:
            return []
        
        rounds = []
        current_round = None
        last_user_hash = None
        last_main_request = None
        
        for seq in range(1, request_count + 1):
            request = self._load_request(session_id, seq)
            response = self._load_response(session_id, seq)
            
            if not request:
                continue
            
            is_aux = self._is_auxiliary_request(request)
            user_hash = self._get_user_message_hash(request)
            
            start_new_round = False
            if current_round is None:
                start_new_round = True
            elif not is_aux:
                if user_hash and user_hash != last_user_hash:
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
                        start_new_round = True
                    elif has_new_user_text and current_round:
                        last_seq = current_round["sequences"][-1] if current_round["sequences"] else 0
                        last_resp = self._load_response(session_id, last_seq)
                        if last_resp:
                            stop_reason = last_resp.get("raw_response", {}).get("stop_reason")
                            if stop_reason == "end_turn":
                                start_new_round = True
            
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
                    "end_time": None
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
                    raw_resp = response.get("raw_response", {})
                    content = raw_resp.get("content", [])
                    
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "tool_use":
                                current_round["tool_calls"].append({
                                    "name": item.get("name"),
                                    "id": item.get("id"),
                                    "input": item.get("input")
                                })
                            elif item.get("type") == "text" and not is_aux:
                                current_round["final_response"] = item.get("text", "")
        
        if current_round:
            rounds.append(current_round)
        
        return rounds
    
    def get_round_detail(self, session_id: str, round_number: int) -> Optional[dict]:
        """Get detailed information for a specific round"""
        rounds = self.analyze_rounds(session_id)
        for r in rounds:
            if r["round_number"] == round_number:
                return r
        return None
    
    def get_round_new_info(self, session_id: str, round_number: int) -> dict:
        """Get new information in a round"""
        rounds = self.analyze_rounds(session_id)
        
        target_round = None
        prev_round = None
        
        for r in rounds:
            if r["round_number"] == round_number:
                target_round = r
                break
            prev_round = r
        
        if not target_round:
            return {"error": f"Round {round_number} not found"}
        
        new_info = {
            "round_number": round_number,
            "user_message": target_round.get("user_message", ""),
            "new_tool_calls": target_round.get("tool_calls", []),
            "response": target_round.get("final_response", ""),
            "files_read": [],
            "files_written": [],
            "commands_executed": []
        }
        
        for tool in target_round.get("tool_calls", []):
            name = tool.get("name", "").lower()
            input_data = tool.get("input", {})
            
            if "read" in name or "cat" in name:
                path = input_data.get("path") or input_data.get("file_path") or input_data.get("filePath")
                if path:
                    new_info["files_read"].append(path)
            elif "write" in name or "edit" in name:
                path = input_data.get("path") or input_data.get("file_path") or input_data.get("filePath")
                if path:
                    new_info["files_written"].append(path)
            elif "bash" in name or "command" in name:
                cmd = input_data.get("command") or input_data.get("cmd")
                if cmd:
                    new_info["commands_executed"].append(cmd)
        
        return new_info
    
    def get_session_summary(self, session_id: str) -> dict:
        """Get session summary"""
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
                    "user_preview": r["user_message"][:100] + "..." if len(r.get("user_message", "")) > 100 else r.get("user_message", ""),
                    "tool_count": len(r.get("tool_calls", [])),
                    "sequences": r["sequences"]
                }
                for r in rounds
            ]
        }


# =============================================================================
# Convenience Functions
# =============================================================================

def analyze_session(session_data: dict) -> dict:
    """Analyze complete session data"""
    all_messages = []
    system_prompt = ""
    tools = []
    
    for req in session_data.get("requests", []):
        raw_req = req.get("raw_request", {})
        
        if not system_prompt:
            sp = raw_req.get("system", "")
            if isinstance(sp, str):
                system_prompt = sp
            elif isinstance(sp, list):
                system_prompt = json.dumps(sp)
        
        all_messages.extend(raw_req.get("messages", []))
        
        req_tools = raw_req.get("tools", [])
        if len(req_tools) > len(tools):
            tools = req_tools
    
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
            "unique_messages": len(all_messages)
        }
    }
