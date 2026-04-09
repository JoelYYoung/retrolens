"""
Common utilities - 公共工具函数
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def ensure_dir(path: Path | str) -> Path:
    """确保目录存在，不存在则创建
    
    Args:
        path: 目录路径
        
    Returns:
        Path 对象
    """
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def format_timestamp(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳
    
    Args:
        dt: datetime 对象，None 则使用当前时间
        fmt: 格式字符串
        
    Returns:
        格式化的时间字符串
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断文本
    
    Args:
        text: 原文本
        max_length: 最大长度
        suffix: 截断后缀
        
    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_project_root() -> Path:
    """获取项目根目录（通过查找 pyproject.toml）"""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return current


def expand_path(path: str | Path) -> Path:
    """展开路径（环境变量和 ~）"""
    p = os.path.expandvars(str(path))
    return Path(p).expanduser()
