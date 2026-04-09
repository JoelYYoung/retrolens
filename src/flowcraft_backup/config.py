"""
Config - 统一配置管理

配置结构：
- listener: 录制代理的后端 LLM 配置
- analyzer: 分析任务（distill/reflect）的 LLM 配置  
- recorder: 代理服务器配置
- storage: 存储配置
- mcp: MCP 服务配置
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

import yaml

DEFAULT_CONFIG = {
    "listener": {
        "api_base": None,
        "api_key": None,
    },
    "analyzer": {
        "model": "gpt-4o-mini",
        "api_base": None,
        "api_key": None,
        "temperature": 0.3,
        "max_tokens": 8192,
        "timeout": 120.0,
    },
    "recorder": {
        "host": "127.0.0.1",
        "port": 8080,
        "protocol": "auto",
    },
    "storage": {
        "logs_dir": "~/.flowcraft/logs",
        "format": "json",
    },
    "mcp": {
        "transport": "stdio",
    },
}

ENV_VAR_MAP = {
    "FLOWCRAFT_LISTENER_API_BASE": "listener.api_base",
    "FLOWCRAFT_LISTENER_API_KEY": "listener.api_key",
    "FLOWCRAFT_ANALYZER_MODEL": "analyzer.model",
    "FLOWCRAFT_ANALYZER_API_BASE": "analyzer.api_base",
    "FLOWCRAFT_ANALYZER_API_KEY": "analyzer.api_key",
    "FLOWCRAFT_ANALYZER_TEMPERATURE": "analyzer.temperature",
    "FLOWCRAFT_ANALYZER_MAX_TOKENS": "analyzer.max_tokens",
    "FLOWCRAFT_ANALYZER_TIMEOUT": "analyzer.timeout",
    "FLOWCRAFT_RECORDER_HOST": "recorder.host",
    "FLOWCRAFT_RECORDER_PORT": "recorder.port",
    "FLOWCRAFT_RECORDER_PROTOCOL": "recorder.protocol",
    "FLOWCRAFT_LOGS_DIR": "storage.logs_dir",
    "FLOWCRAFT_STORAGE_FORMAT": "storage.format",
    "FLOWCRAFT_MCP_TRANSPORT": "mcp.transport",
}


@dataclass
class ListenerConfig:
    """录制代理后端配置"""
    api_base: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class AnalyzerConfig:
    """分析器 LLM 配置（使用 litellm）"""
    model: str = "gpt-4o-mini"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 8192
    timeout: float = 120.0


@dataclass
class RecorderConfig:
    """代理服务器配置"""
    host: str = "127.0.0.1"
    port: int = 8080
    protocol: str = "auto"


@dataclass
class StorageConfig:
    """存储配置"""
    logs_dir: str = "~/.flowcraft/logs"
    format: str = "json"
    
    @property
    def logs_path(self) -> Path:
        return Path(self.logs_dir).expanduser()


@dataclass
class MCPConfig:
    """MCP 配置"""
    transport: str = "stdio"


@dataclass
class Config:
    """主配置类"""
    listener: ListenerConfig = field(default_factory=ListenerConfig)
    analyzer: AnalyzerConfig = field(default_factory=AnalyzerConfig)
    recorder: RecorderConfig = field(default_factory=RecorderConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return cls(
            listener=ListenerConfig(**data.get("listener", {})),
            analyzer=AnalyzerConfig(**data.get("analyzer", {})),
            recorder=RecorderConfig(**data.get("recorder", {})),
            storage=StorageConfig(**data.get("storage", {})),
            mcp=MCPConfig(**data.get("mcp", {})),
        )
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "listener": {"api_base": self.listener.api_base, "api_key": self.listener.api_key},
            "analyzer": {
                "model": self.analyzer.model,
                "api_base": self.analyzer.api_base,
                "api_key": self.analyzer.api_key,
                "temperature": self.analyzer.temperature,
                "max_tokens": self.analyzer.max_tokens,
                "timeout": self.analyzer.timeout,
            },
            "recorder": {"host": self.recorder.host, "port": self.recorder.port, "protocol": self.recorder.protocol},
            "storage": {"logs_dir": self.storage.logs_dir, "format": self.storage.format},
            "mcp": {"transport": self.mcp.transport},
        }


def _expand_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        pattern = r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)'
        def replacer(match):
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, "")
        return re.sub(pattern, replacer, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _set_nested(data: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    final_key = keys[-1]
    if final_key in ("port", "max_tokens"):
        value = int(value)
    elif final_key in ("temperature", "timeout"):
        value = float(value)
    current[final_key] = value


def _get_config_file_path() -> Path:
    env_path = os.environ.get("FLOWCRAFT_CONFIG_FILE")
    if env_path:
        return Path(env_path).expanduser()
    return Path("~/.flowcraft/config.yaml").expanduser()


def load_config(config_file: Optional[Path] = None, cli_overrides: Optional[dict[str, Any]] = None) -> Config:
    config_data = _deep_merge({}, DEFAULT_CONFIG)
    
    file_path = config_file or _get_config_file_path()
    if file_path.exists():
        with open(file_path) as f:
            file_config = yaml.safe_load(f) or {}
            file_config = _expand_env_vars(file_config)
            config_data = _deep_merge(config_data, file_config)
    
    for env_var, config_path in ENV_VAR_MAP.items():
        value = os.environ.get(env_var)
        if value:
            _set_nested(config_data, config_path, value)
    
    if cli_overrides:
        config_data = _deep_merge(config_data, cli_overrides)
    
    return Config.from_dict(config_data)


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    global _config
    _config = config


def reset_config() -> None:
    global _config
    _config = None


def init_config(force: bool = False) -> Optional[Path]:
    config_path = _get_config_file_path()
    if config_path.exists() and not force:
        return None
    config_path.parent.mkdir(parents=True, exist_ok=True)
    default_content = '''# FlowCraft 配置文件

# Listener - 录制代理的后端配置
listener:
  api_base: null
  api_key: null

# Analyzer - 分析任务的 LLM 配置 (使用 litellm)
analyzer:
  model: "gpt-4o-mini"
  api_base: null
  api_key: null
  temperature: 0.3
  max_tokens: 8192
  timeout: 120.0

# Recorder - 代理服务器配置
recorder:
  host: "127.0.0.1"
  port: 8080
  protocol: "auto"

# Storage - 存储配置
storage:
  logs_dir: "~/.flowcraft/logs"
  format: "json"

# MCP - MCP 服务配置
mcp:
  transport: "stdio"
'''
    config_path.write_text(default_content)
    return config_path
