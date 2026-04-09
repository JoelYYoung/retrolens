"""
Content Compressor - 内容压缩器

实现段落级压缩，用于处理长对话：
- 自动检测需要压缩的长内容
- 保留关键信息（工具调用、决策点）
- 支持人工审核和编辑
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import tiktoken

from ..schemas import CompressedContent
from ..llm import LLMClient, get_analyzer_client


class ContentType(str, Enum):
    """内容类型"""
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM_PROMPT = "system_prompt"


@dataclass
class ContentSegment:
    """内容片段"""
    
    id: str
    """片段 ID"""
    
    content_type: ContentType
    """内容类型"""
    
    raw_content: str
    """原始内容"""
    
    token_count: int
    """Token 数量"""
    
    metadata: dict[str, Any] = field(default_factory=dict)
    """元数据（工具名、角色等）"""
    
    # 压缩相关
    compressed: Optional[CompressedContent] = None
    """压缩后的内容"""
    
    should_compress: bool = False
    """是否需要压缩"""
    
    user_edited: bool = False
    """用户是否编辑过"""
    
    @property
    def effective_content(self) -> str:
        """获取有效内容（压缩后或原始）"""
        if self.compressed and self.compressed.compressed_text:
            return self.compressed.compressed_text
        return self.raw_content
    
    @property
    def effective_tokens(self) -> int:
        """获取有效 token 数"""
        if self.compressed:
            return self.compressed.compressed_tokens
        return self.token_count
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content_type": self.content_type.value,
            "raw_content": self.raw_content,
            "token_count": self.token_count,
            "metadata": self.metadata,
            "compressed": self.compressed.model_dump() if self.compressed else None,
            "should_compress": self.should_compress,
            "user_edited": self.user_edited,
        }


class ContentCompressor:
    """内容压缩器
    
    策略：
    1. 短内容（<阈值）直接保留
    2. 工具调用保留关键信息（工具名、参数摘要、结果摘要）
    3. 长文本用 LLM 总结
    4. 支持人工审核和编辑
    
    Example:
        >>> compressor = ContentCompressor(threshold_tokens=500)
        >>> segments = compressor.segment_conversation(messages)
        >>> for seg in segments:
        ...     if seg.should_compress:
        ...         await compressor.compress_segment(seg)
    """
    
    # 压缩提示
    COMPRESS_PROMPT = """请总结以下内容，保留关键信息：

{content}

要求：
1. 保留所有重要的决策点和结论
2. 保留关键的技术细节和代码片段
3. 保留错误信息和解决方案
4. 用简洁的语言表达
5. 保持原文的逻辑结构

总结："""

    TOOL_COMPRESS_PROMPT = """请总结以下工具调用的关键信息：

工具名: {tool_name}
参数: {tool_args}
结果: {tool_result}

要求：
1. 说明工具的用途
2. 总结关键参数
3. 总结结果要点（如果结果很长，只保留关键部分）

总结："""
    
    def __init__(
        self,
        threshold_tokens: int = 500,
        target_ratio: float = 0.3,
        encoding_name: str = "cl100k_base",
        llm_client: Optional[LLMClient] = None,
    ):
        """初始化压缩器
        
        Args:
            threshold_tokens: 压缩阈值（超过此值才压缩）
            target_ratio: 目标压缩比（0.3 表示压缩到原来的 30%）
            encoding_name: tiktoken 编码名称
            llm_client: LLM 客户端
        """
        self.threshold_tokens = threshold_tokens
        self.target_ratio = target_ratio
        self.encoding = tiktoken.get_encoding(encoding_name)
        self.llm_client = llm_client
    
    def _get_llm(self) -> LLMClient:
        """获取 LLM 客户端"""
        if self.llm_client is None:
            self.llm_client = get_analyzer_client()
        return self.llm_client
    
    def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        return len(self.encoding.encode(text))
    
    def _generate_segment_id(self, content: str, index: int) -> str:
        """生成片段 ID"""
        hash_input = f"{index}:{content[:100]}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:8]
    
    def segment_conversation(
        self,
        messages: list[dict[str, Any]],
        include_system: bool = False,
    ) -> list[ContentSegment]:
        """将对话分割成片段
        
        Args:
            messages: 消息列表（OpenAI 或 Anthropic 格式）
            include_system: 是否包含系统提示
            
        Returns:
            内容片段列表
        """
        segments: list[ContentSegment] = []
        
        for idx, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # 跳过系统消息
            if role == "system" and not include_system:
                continue
            
            # 处理工具调用
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tc_content = self._format_tool_call(tc)
                    tokens = self.count_tokens(tc_content)
                    
                    segments.append(ContentSegment(
                        id=self._generate_segment_id(tc_content, len(segments)),
                        content_type=ContentType.TOOL_CALL,
                        raw_content=tc_content,
                        token_count=tokens,
                        metadata={
                            "tool_name": tc.get("function", {}).get("name", "unknown"),
                            "tool_id": tc.get("id", ""),
                        },
                        should_compress=tokens > self.threshold_tokens,
                    ))
                continue
            
            # 处理工具结果
            if role == "tool":
                tokens = self.count_tokens(str(content))
                segments.append(ContentSegment(
                    id=self._generate_segment_id(str(content), len(segments)),
                    content_type=ContentType.TOOL_RESULT,
                    raw_content=str(content),
                    token_count=tokens,
                    metadata={
                        "tool_call_id": msg.get("tool_call_id", ""),
                    },
                    should_compress=tokens > self.threshold_tokens,
                ))
                continue
            
            # 处理普通消息
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # 多模态内容，只提取文本
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                text = "\n".join(text_parts)
            else:
                text = str(content)
            
            if not text.strip():
                continue
            
            tokens = self.count_tokens(text)
            content_type = (
                ContentType.USER_MESSAGE if role == "user"
                else ContentType.ASSISTANT_MESSAGE if role == "assistant"
                else ContentType.SYSTEM_PROMPT
            )
            
            segments.append(ContentSegment(
                id=self._generate_segment_id(text, len(segments)),
                content_type=content_type,
                raw_content=text,
                token_count=tokens,
                metadata={"role": role},
                should_compress=tokens > self.threshold_tokens,
            ))
        
        return segments
    
    def _format_tool_call(self, tool_call: dict[str, Any]) -> str:
        """格式化工具调用"""
        func = tool_call.get("function", {})
        name = func.get("name", "unknown")
        args = func.get("arguments", "{}")
        
        return f"[Tool Call: {name}]\nArguments: {args}"
    
    async def compress_segment(
        self,
        segment: ContentSegment,
        custom_prompt: Optional[str] = None,
    ) -> CompressedContent:
        """压缩单个片段
        
        Args:
            segment: 内容片段
            custom_prompt: 自定义压缩提示
            
        Returns:
            压缩后的内容
        """
        llm = self._get_llm()
        
        # 选择压缩提示
        if custom_prompt:
            prompt = custom_prompt
        elif segment.content_type == ContentType.TOOL_CALL:
            prompt = self.TOOL_COMPRESS_PROMPT.format(
                tool_name=segment.metadata.get("tool_name", "unknown"),
                tool_args=segment.raw_content,
                tool_result="(见下一条工具结果)",
            )
        else:
            prompt = self.COMPRESS_PROMPT.format(content=segment.raw_content)
        
        # 计算目标长度
        target_tokens = int(segment.token_count * self.target_ratio)
        
        # 调用 LLM
        system_prompt = f"你是一个专业的文本总结助手。目标是将文本压缩到约 {target_tokens} tokens。"
        compressed_text = await llm.complete(
            prompt,
            system_prompt=system_prompt,
            temperature=0.3,
        )
        
        compressed_tokens = self.count_tokens(compressed_text)
        
        result = CompressedContent(
            original_tokens=segment.token_count,
            compressed_tokens=compressed_tokens,
            compression_ratio=compressed_tokens / segment.token_count if segment.token_count > 0 else 1.0,
            compressed_text=compressed_text,
        )
        
        segment.compressed = result
        return result
    
    async def compress_all(
        self,
        segments: list[ContentSegment],
        progress_callback: Optional[Callable[[int, int, ContentSegment], None]] = None,
    ) -> list[ContentSegment]:
        """压缩所有需要压缩的片段
        
        Args:
            segments: 片段列表
            progress_callback: 进度回调 (current, total, segment)
            
        Returns:
            处理后的片段列表
        """
        to_compress = [s for s in segments if s.should_compress and not s.user_edited]
        total = len(to_compress)
        
        for idx, segment in enumerate(to_compress):
            await self.compress_segment(segment)
            
            if progress_callback:
                progress_callback(idx + 1, total, segment)
        
        return segments
    
    def merge_segments(self, segments: list[ContentSegment]) -> str:
        """合并所有片段为单一文本
        
        Args:
            segments: 片段列表
            
        Returns:
            合并后的文本
        """
        parts = []
        for seg in segments:
            content = seg.effective_content
            if seg.content_type == ContentType.TOOL_CALL:
                parts.append(f"[Tool: {seg.metadata.get('tool_name', 'unknown')}]\n{content}")
            elif seg.content_type == ContentType.TOOL_RESULT:
                parts.append(f"[Tool Result]\n{content}")
            else:
                role = seg.metadata.get("role", "unknown")
                parts.append(f"[{role.capitalize()}]\n{content}")
        
        return "\n\n---\n\n".join(parts)
    
    def get_stats(self, segments: list[ContentSegment]) -> dict[str, Any]:
        """获取压缩统计
        
        Args:
            segments: 片段列表
            
        Returns:
            统计信息
        """
        total_original = sum(s.token_count for s in segments)
        total_effective = sum(s.effective_tokens for s in segments)
        
        compressed_count = sum(1 for s in segments if s.compressed)
        
        return {
            "total_segments": len(segments),
            "compressed_segments": compressed_count,
            "original_tokens": total_original,
            "effective_tokens": total_effective,
            "overall_ratio": total_effective / total_original if total_original > 0 else 1.0,
        }
