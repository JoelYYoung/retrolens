"""
Daemon Worker - 后台守护进程的实际工作入口

这个模块被 daemon.py 的 start_daemon() 以子进程方式启动。
"""

from __future__ import annotations

import sys
import argparse
import signal
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def setup_signal_handlers():
    """设置信号处理"""
    def handle_shutdown(signum, frame):
        logger.info(f"收到信号 {signum}，正在关闭...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)


def main():
    """守护进程主入口"""
    parser = argparse.ArgumentParser(description="FlowCraft Daemon Worker")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8080, help="监听端口")
    parser.add_argument("--protocol", default="auto", help="协议模式")
    
    args = parser.parse_args()
    
    setup_signal_handlers()
    
    logger.info(f"FlowCraft 守护进程启动")
    logger.info(f"  地址: http://{args.host}:{args.port}")
    logger.info(f"  协议: {args.protocol}")
    
    try:
        import uvicorn
        from flowcraft.recorder import create_app
        
        app = create_app()
        
        # 使用 uvicorn 运行，但禁用一些交互功能
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
            access_log=True,
        )
    except Exception as e:
        logger.error(f"服务启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
