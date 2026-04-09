"""
Tools Analyzer - 分析工具定义和使用
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class ToolsAnalyzer:
    """
    分析工具定义
    
    分析功能：
    - 获取工具摘要
    - 估算工具定义的 Token 数
    - 按类型分类工具
    - 按描述长度排序
    - 与基线对比
    """
    
    # 工具类别及其关键词
    TOOL_CATEGORIES: Dict[str, List[str]] = {
        "file_system": ["file", "read", "write", "edit", "create", "delete", "directory", "path"],
        "search": ["grep", "glob", "search", "find", "query"],
        "execution": ["bash", "terminal", "run", "execute", "shell", "command"],
        "agent": ["agent", "subagent", "delegate"],
        "mcp_external": ["mcp_"],
        "web": ["fetch", "http", "url", "browser", "web"],
        "git": ["git", "commit", "branch", "merge"],
    }
    
    def analyze(self, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析工具列表
        
        Args:
            tools: 工具定义列表
            
        Returns:
            工具分析结果
        """
        return {
            "tools_summary": self.get_tools_summary(tools),
            "tools_full_definitions": tools,
            "total_tools_count": len(tools),
            "total_tools_tokens": self.estimate_tools_tokens(tools),
            "categorized_tools": self.categorize_tools(tools),
            "tools_by_description_length": self.sort_by_description_length(tools),
        }
    
    def get_tools_summary(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        获取工具摘要
        
        Args:
            tools: 工具定义列表
            
        Returns:
            工具摘要列表
        """
        summaries: List[Dict[str, Any]] = []
        
        for t in tools:
            input_schema = t.get("input_schema", {})
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            description = t.get("description", "")
            preview = (description[:200] + "...") if len(description) > 200 else description
            
            summaries.append({
                "name": t.get("name", "unknown"),
                "description_preview": preview,
                "description_length": len(description),
                "parameters": list(properties.keys()),
                "required_parameters": required,
                "parameter_count": len(properties),
            })
        
        return summaries
    
    def estimate_tools_tokens(self, tools: List[Dict[str, Any]]) -> int:
        """
        估算工具定义的 Token 数
        
        Args:
            tools: 工具定义列表
            
        Returns:
            估算的 Token 数
        """
        total_chars = len(json.dumps(tools))
        return int(total_chars / 3.5)
    
    def categorize_tools(self, tools: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        按类型分类工具
        
        Args:
            tools: 工具定义列表
            
        Returns:
            类别到工具名称列表的映射
        """
        categories: Dict[str, List[str]] = {cat: [] for cat in self.TOOL_CATEGORIES}
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
        
        # 只返回非空的类别
        return {k: v for k, v in categories.items() if v}
    
    def sort_by_description_length(
        self, 
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        按描述长度排序（降序）
        
        Args:
            tools: 工具定义列表
            
        Returns:
            前 10 个最长描述的工具
        """
        sorted_tools = sorted(
            tools,
            key=lambda t: len(t.get("description", "")),
            reverse=True
        )
        
        return [
            {
                "name": t.get("name"),
                "description_length": len(t.get("description", "")),
            }
            for t in sorted_tools[:10]
        ]
    
    def compare_with_baseline(
        self, 
        current_tools: List[Dict[str, Any]], 
        baseline_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        与基线工具列表对比
        
        Args:
            current_tools: 当前工具列表
            baseline_tools: 基线工具列表
            
        Returns:
            对比结果
        """
        current_names = set(t.get("name") for t in current_tools)
        baseline_names = set(t.get("name") for t in baseline_tools)
        
        return {
            "added": list(current_names - baseline_names),
            "removed": list(baseline_names - current_names),
            "unchanged": list(current_names & baseline_names),
            "current_count": len(current_names),
            "baseline_count": len(baseline_names),
        }
    
    def extract_tool_details(
        self, 
        tool_name: str, 
        tools: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        提取特定工具的详细信息
        
        Args:
            tool_name: 工具名称
            tools: 工具定义列表
            
        Returns:
            工具详细信息，如未找到返回 None
        """
        for t in tools:
            if t.get("name") == tool_name:
                return {
                    "name": t.get("name"),
                    "description": t.get("description"),
                    "input_schema": t.get("input_schema"),
                    "cache_control": t.get("cache_control"),
                }
        return None
    
    def analyze_tool_usage(
        self, 
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        分析工具使用情况
        
        Args:
            messages: 消息列表
            
        Returns:
            工具使用统计
        """
        tool_calls: Dict[str, int] = {}
        tool_errors: Dict[str, int] = {}
        
        for msg in messages:
            content = msg.get("content", [])
            
            if not isinstance(content, list):
                continue
            
            for item in content:
                if not isinstance(item, dict):
                    continue
                
                if item.get("type") == "tool_use":
                    name = item.get("name", "unknown")
                    tool_calls[name] = tool_calls.get(name, 0) + 1
                
                elif item.get("type") == "tool_result":
                    # 检查是否有错误
                    is_error = item.get("is_error", False)
                    if is_error:
                        # 尝试从相邻的 tool_use 获取名称
                        tool_use_id = item.get("tool_use_id", "unknown")
                        tool_errors[tool_use_id] = tool_errors.get(tool_use_id, 0) + 1
        
        return {
            "call_counts": tool_calls,
            "total_calls": sum(tool_calls.values()),
            "unique_tools_used": len(tool_calls),
            "most_used": sorted(tool_calls.items(), key=lambda x: x[1], reverse=True)[:5],
            "error_count": sum(tool_errors.values()),
        }
