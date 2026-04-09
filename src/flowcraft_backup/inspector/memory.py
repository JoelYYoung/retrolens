"""
Memory Analyzer - 检测上下文中的重复和冗余
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Dict, List


class MemoryAnalyzer:
    """
    检测会话中的重复和冗余内容
    
    分析功能：
    - 查找重复的内容块
    - 提取文件读取操作历史
    - 检测重复的文件读取
    - 估算 Token 使用量
    - 检测可能的压缩事件
    """
    
    def analyze(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析消息列表中的内存使用模式
        
        Args:
            messages: 消息列表
            
        Returns:
            包含各种分析结果的字典
        """
        return {
            "duplicate_content": self.find_duplicates(messages),
            "file_read_history": self.extract_file_reads(messages),
            "repeated_files": self.find_repeated_file_reads(messages),
            "total_tokens_estimate": self.estimate_tokens(messages),
            "compression_events": self.detect_compression(messages),
            "message_stats": self.get_message_stats(messages),
        }
    
    def find_duplicates(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        查找重复的内容块
        
        Args:
            messages: 消息列表
            
        Returns:
            重复内容的列表，包含哈希值、首次出现位置、重复位置等信息
        """
        content_hashes: Dict[str, Any] = {}
        duplicates: List[Dict[str, Any]] = []
        
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            
            if isinstance(content, str):
                content_hash = hashlib.md5(content.encode()).hexdigest()
                if content_hash in content_hashes:
                    duplicates.append({
                        "hash": content_hash,
                        "first_occurrence": content_hashes[content_hash],
                        "duplicate_at": i,
                        "length": len(content),
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
                                "length": len(item_str),
                            })
                        else:
                            content_hashes[item_hash] = key
        
        return duplicates
    
    def extract_file_reads(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        提取所有文件读取操作
        
        Args:
            messages: 消息列表
            
        Returns:
            文件读取操作列表
        """
        file_reads: List[Dict[str, Any]] = []
        
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue
            
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            
            for item in content:
                if not isinstance(item, dict):
                    continue
                
                if item.get("type") != "tool_use":
                    continue
                
                tool_name = item.get("name", "").lower()
                if not any(kw in tool_name for kw in ["read", "file", "cat"]):
                    continue
                
                input_data = item.get("input", {})
                path = (
                    input_data.get("path") or 
                    input_data.get("file_path") or 
                    input_data.get("filePath")
                )
                
                file_reads.append({
                    "message_index": i,
                    "tool_name": item.get("name"),
                    "tool_use_id": item.get("id"),
                    "path": path,
                    "input": input_data,
                })
        
        return file_reads
    
    def find_repeated_file_reads(
        self, 
        messages: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        检测对同一文件的多次读取
        
        Args:
            messages: 消息列表
            
        Returns:
            文件路径到读取次数的映射（仅包含读取次数 > 1 的）
        """
        file_reads = self.extract_file_reads(messages)
        paths = [fr["path"] for fr in file_reads if fr["path"]]
        return {
            path: count 
            for path, count in Counter(paths).items() 
            if count > 1
        }
    
    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        估算消息的总 Token 数
        
        使用简单的字符计数估算（约 3.5 字符/token）
        
        Args:
            messages: 消息列表
            
        Returns:
            估算的 Token 数
        """
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
    
    def detect_compression(
        self, 
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        检测可能的压缩/截断事件
        
        Args:
            messages: 消息列表
            
        Returns:
            检测到的压缩事件列表
        """
        compression_patterns = [
            r"(?i)context.*truncat",
            r"(?i)message.*omit",
            r"(?i)previous.*summar",
            r"(?i)\[.*truncated.*\]",
            r"(?i)content.*compress",
        ]
        
        events: List[Dict[str, Any]] = []
        
        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            
            for pattern in compression_patterns:
                if re.search(pattern, content):
                    events.append({
                        "message_index": i,
                        "pattern_matched": pattern,
                        "role": msg.get("role"),
                    })
                    break
        
        return events
    
    def get_message_stats(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取消息统计信息
        
        Args:
            messages: 消息列表
            
        Returns:
            统计信息字典
        """
        stats: Dict[str, Any] = {
            "total": len(messages),
            "by_role": dict(Counter(msg.get("role", "unknown") for msg in messages)),
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_results": 0,
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
