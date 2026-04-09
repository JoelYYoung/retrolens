"""
FlowCraft - 从 AI Agent 对话中提炼和优化工作流

功能模块：
- recorder: 多协议代理，记录 Agent 与 LLM 的交互
- inspector: 分析会话中的模式、工具使用、决策点  
- distiller: 从会话中提取可复用的工作流
- reflector: 分析工作流并提供改进建议
- codegen: 生成 LangGraph 可执行代码

CLI 命令: fc
"""

__version__ = "0.2.0"
__author__ = "Joel Yang"

from .config import get_config, Config

__all__ = ["__version__", "get_config", "Config"]
