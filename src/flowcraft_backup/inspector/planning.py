"""
Planning Analyzer - 检测规划行为
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


class PlanningAnalyzer:
    """
    检测 Agent 的规划行为
    
    分析功能：
    - 检测系统提示中的规划指令
    - 查找响应中的显式规划
    - 提取 thinking 块
    - 检测任务分解
    """
    
    # 规划模式及其名称
    PLANNING_PATTERNS: List[Tuple[str, str]] = [
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
    
    # 规划关键词
    PLANNING_KEYWORDS = [
        "plan", "planning", "think step", "break down",
        "decompose", "outline", "strategy", "approach",
        "before coding", "before implementing",
    ]
    
    def analyze(
        self, 
        messages: List[Dict[str, Any]], 
        system_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        分析规划行为
        
        Args:
            messages: 消息列表
            system_prompt: 系统提示
            
        Returns:
            规划分析结果
        """
        return {
            "system_prompt_has_planning_instruction": self.check_system_planning(system_prompt),
            "explicit_planning_in_responses": self.find_planning_in_messages(messages),
            "thinking_blocks": self.extract_thinking_blocks(messages),
            "task_decomposition_detected": self.detect_task_decomposition(messages),
            "planning_patterns_found": self.find_all_planning_patterns(messages),
        }
    
    def check_system_planning(self, system_prompt: str) -> Dict[str, Any]:
        """
        检查系统提示中的规划指令
        
        Args:
            system_prompt: 系统提示文本
            
        Returns:
            检查结果
        """
        found = []
        system_lower = system_prompt.lower()
        
        for keyword in self.PLANNING_KEYWORDS:
            if keyword in system_lower:
                found.append(keyword)
        
        return {
            "has_planning_instructions": len(found) > 0,
            "keywords_found": found,
            "system_prompt_length": len(system_prompt),
        }
    
    def find_planning_in_messages(
        self, 
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        查找消息中的显式规划
        
        Args:
            messages: 消息列表
            
        Returns:
            规划实例列表
        """
        planning_instances: List[Dict[str, Any]] = []
        
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
            
            content = msg.get("content", "")
            text = self._extract_text_content(content)
            
            for pattern, pattern_name in self.PLANNING_PATTERNS:
                matches = list(re.finditer(pattern, text, re.DOTALL))
                if matches:
                    planning_instances.append({
                        "message_index": i,
                        "pattern_name": pattern_name,
                        "matches_count": len(matches),
                        "preview": text[:200] if len(text) > 200 else text,
                    })
        
        return planning_instances
    
    def extract_thinking_blocks(
        self, 
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        提取 thinking 块内容
        
        Args:
            messages: 消息列表
            
        Returns:
            thinking 块列表
        """
        thinking_blocks: List[Dict[str, Any]] = []
        
        for i, msg in enumerate(messages):
            content = msg.get("content", [])
            
            if not isinstance(content, list):
                continue
            
            for j, item in enumerate(content):
                if isinstance(item, dict) and item.get("type") == "thinking":
                    thinking_text = item.get("thinking", "")
                    thinking_blocks.append({
                        "message_index": i,
                        "block_index": j,
                        "thinking_text": thinking_text[:500],
                        "full_length": len(thinking_text),
                    })
        
        return thinking_blocks
    
    def detect_task_decomposition(
        self, 
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        检测任务分解
        
        Args:
            messages: 消息列表
            
        Returns:
            任务分解检测结果
        """
        indicators = {
            "numbered_lists": 0,
            "bullet_lists": 0,
            "subtask_mentions": 0,
        }
        
        numbered_pattern = r"^\s*\d+[\.\)]\s+"
        bullet_pattern = r"^\s*[-•*]\s+"
        subtask_pattern = r"(?i)(subtask|sub-task|step|phase)\s*\d*[:\s]"
        
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            
            text = self._extract_text_content(msg.get("content", ""))
            
            lines = text.split("\n")
            for line in lines:
                if re.match(numbered_pattern, line):
                    indicators["numbered_lists"] += 1
                if re.match(bullet_pattern, line):
                    indicators["bullet_lists"] += 1
            
            indicators["subtask_mentions"] += len(re.findall(subtask_pattern, text))
        
        return {
            "detected": sum(indicators.values()) > 3,
            "indicators": indicators,
        }
    
    def find_all_planning_patterns(
        self, 
        messages: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        统计所有规划模式的出现次数
        
        Args:
            messages: 消息列表
            
        Returns:
            模式名称到出现次数的映射
        """
        pattern_counts: Dict[str, int] = {}
        
        for msg in messages:
            text = self._extract_text_content(msg.get("content", ""))
            
            for pattern, pattern_name in self.PLANNING_PATTERNS:
                count = len(re.findall(pattern, text, re.DOTALL))
                if count > 0:
                    pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + count
        
        return pattern_counts
    
    def _extract_text_content(self, content: Any) -> str:
        """
        从内容中提取文本
        
        Args:
            content: 消息内容（字符串或列表）
            
        Returns:
            提取的文本
        """
        if isinstance(content, str):
            return content
        
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "\n".join(parts)
        
        return ""
