"""
Daemon Process Management - 后台守护进程管理

类似 CCR 的 start/stop/status 功能，使用 PID 文件跟踪进程。
"""

from __future__ import annotations

import os
import sys
import json
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import get_config


@dataclass
class ServiceInfo:
    """服务信息"""
    running: bool
    pid: Optional[int] = None
    host: str = "127.0.0.1"
    port: int = 8080
    endpoint: Optional[str] = None


def get_pid_file() -> Path:
    """获取 PID 文件路径"""
    config = get_config()
    config_dir = Path(config.storage.logs_dir).expanduser().parent
    return config_dir / ".flowcraft.pid"


def get_info_file() -> Path:
    """获取服务信息文件路径（存储运行时参数）"""
    config = get_config()
    config_dir = Path(config.storage.logs_dir).expanduser().parent
    return config_dir / ".flowcraft.info"


def get_log_file() -> Path:
    """获取日志文件路径"""
    config = get_config()
    config_dir = Path(config.storage.logs_dir).expanduser().parent
    return config_dir / "flowcraft.log"


def is_process_running(pid: int) -> bool:
    """检查进程是否运行中"""
    try:
        # 发送信号 0 检查进程是否存在
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid() -> Optional[int]:
    """从 PID 文件读取进程 ID"""
    pid_file = get_pid_file()
    if not pid_file.exists():
        return None
    
    try:
        content = pid_file.read_text().strip()
        return int(content) if content else None
    except (ValueError, IOError):
        return None


def save_pid(pid: int) -> None:
    """保存 PID 到文件"""
    pid_file = get_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid))


def save_service_info(host: str, port: int, protocol: str) -> None:
    """保存服务信息到文件"""
    info_file = get_info_file()
    info_file.parent.mkdir(parents=True, exist_ok=True)
    info_file.write_text(json.dumps({
        "host": host,
        "port": port,
        "protocol": protocol,
    }))


def load_service_info() -> Optional[dict]:
    """读取服务信息"""
    info_file = get_info_file()
    if not info_file.exists():
        return None
    try:
        return json.loads(info_file.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def cleanup_pid_file() -> None:
    """清理 PID 文件和服务信息文件"""
    pid_file = get_pid_file()
    if pid_file.exists():
        try:
            pid_file.unlink()
        except IOError:
            pass
    
    info_file = get_info_file()
    if info_file.exists():
        try:
            info_file.unlink()
        except IOError:
            pass


def is_service_running() -> bool:
    """检查服务是否运行中"""
    pid = read_pid()
    if pid is None:
        return False
    
    if is_process_running(pid):
        return True
    
    # PID 文件存在但进程已死，清理
    cleanup_pid_file()
    return False


def get_service_info() -> ServiceInfo:
    """获取服务信息"""
    pid = read_pid()
    config = get_config()
    
    # 尝试读取保存的服务信息
    saved_info = load_service_info()
    host = saved_info.get("host", config.recorder.host) if saved_info else config.recorder.host
    port = saved_info.get("port", config.recorder.port) if saved_info else config.recorder.port
    
    if pid is None or not is_process_running(pid):
        return ServiceInfo(
            running=False,
            host=host,
            port=port,
        )
    
    return ServiceInfo(
        running=True,
        pid=pid,
        host=host,
        port=port,
        endpoint=f"http://{host}:{port}",
    )


def start_daemon(host: str = "127.0.0.1", port: int = 8080, protocol: str = "auto") -> tuple[bool, str]:
    """
    启动守护进程
    
    Returns:
        (success, message)
    """
    # 检查是否已运行
    if is_service_running():
        info = get_service_info()
        return False, f"服务已在运行中 (PID: {info.pid}, 端口: {info.port})"
    
    # 构建启动命令
    # 使用当前 Python 解释器和 flowcraft 模块
    python_exe = sys.executable
    
    # 日志文件
    log_file = get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 启动子进程
    try:
        # 使用 flowcraft.cli.daemon_worker 作为后台进程入口
        cmd = [
            python_exe,
            "-m", "flowcraft.cli.daemon_worker",
            "--host", host,
            "--port", str(port),
            "--protocol", protocol,
        ]
        
        # 打开日志文件
        log_fd = open(log_file, "a")
        
        # 启动分离的子进程
        if sys.platform == "win32":
            # Windows 使用 CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                cmd,
                stdout=log_fd,
                stderr=log_fd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            )
        else:
            # Unix 使用 start_new_session
            process = subprocess.Popen(
                cmd,
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,
            )
        
        # 保存 PID 和服务信息
        save_pid(process.pid)
        save_service_info(host, port, protocol)
        
        # 等待一小会检查是否成功启动
        time.sleep(0.5)
        
        if is_process_running(process.pid):
            return True, f"服务已启动 (PID: {process.pid}, 端口: {port})"
        else:
            cleanup_pid_file()
            return False, f"服务启动失败，请查看日志: {log_file}"
    
    except Exception as e:
        cleanup_pid_file()
        return False, f"启动失败: {e}"


def stop_daemon() -> tuple[bool, str]:
    """
    停止守护进程
    
    Returns:
        (success, message)
    """
    pid = read_pid()
    
    if pid is None:
        return False, "服务未运行（无 PID 文件）"
    
    if not is_process_running(pid):
        cleanup_pid_file()
        return True, "服务未运行（PID 文件已清理）"
    
    try:
        # 发送 SIGTERM 信号
        if sys.platform == "win32":
            # Windows 使用 taskkill
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        
        # 等待进程退出
        for _ in range(10):
            time.sleep(0.3)
            if not is_process_running(pid):
                break
        
        # 如果还在运行，强制杀死
        if is_process_running(pid):
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGKILL)
            time.sleep(0.3)
        
        cleanup_pid_file()
        return True, f"服务已停止 (PID: {pid})"
    
    except OSError as e:
        cleanup_pid_file()
        return False, f"停止服务失败: {e}"


def restart_daemon(host: str = "127.0.0.1", port: int = 8080, protocol: str = "auto") -> tuple[bool, str]:
    """
    重启守护进程
    
    Returns:
        (success, message)
    """
    messages = []
    
    # 先停止
    if is_service_running():
        success, msg = stop_daemon()
        messages.append(msg)
        if not success:
            return False, "\n".join(messages)
        time.sleep(0.5)
    
    # 再启动
    success, msg = start_daemon(host, port, protocol)
    messages.append(msg)
    
    return success, "\n".join(messages)
