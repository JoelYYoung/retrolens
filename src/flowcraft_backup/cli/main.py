"""
CLI Main - 统一命令行入口

使用 Typer 构建现代化 CLI，命令 `flowcraft` (别名 `fc`)。

Commands:
    flowcraft config init/show/set   - 配置管理
    flowcraft record start/stop      - 会话记录
    flowcraft inspect list/show/analyze - 会话检查
    flowcraft distill <id>           - 工作流蒸馏
    flowcraft reflect <file>         - 工作流反思
    flowcraft generate <file>        - 代码生成
    flowcraft mcp serve              - MCP 服务
"""

from __future__ import annotations

import sys
import json
import asyncio
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import get_config, init_config, Config


# =============================================================================
# App Setup
# =============================================================================

app = typer.Typer(
    name="flowcraft",
    help="🔬 FlowCraft - 从 AI Agent 对话中提炼和优化工作流",
    no_args_is_help=True,
)

console = Console()


# =============================================================================
# Config Commands
# =============================================================================

config_app = typer.Typer(help="配置管理")
app.add_typer(config_app, name="config")


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", "-f", help="覆盖现有配置"),
):
    """初始化配置文件"""
    config_path = init_config(force=force)
    if config_path:
        console.print(f"[green]✓[/green] 配置文件已创建: {config_path}")
    else:
        console.print("[yellow]配置文件已存在，使用 --force 覆盖[/yellow]")


@config_app.command("show")
def config_show():
    """显示当前配置"""
    config = get_config()
    
    console.print(Panel.fit(
        f"""[bold]Listener (录制代理后端)[/bold]
  api_base: {config.listener.api_base or '(透明代理)'}
  api_key: {'***' + config.listener.api_key[-4:] if config.listener.api_key else '(透明代理)'}
  
[bold]Analyzer (分析任务 LLM)[/bold]
  model: {config.analyzer.model}
  api_base: {config.analyzer.api_base or '(默认)'}
  api_key: {'***' + config.analyzer.api_key[-4:] if config.analyzer.api_key else '(未配置)'}
  temperature: {config.analyzer.temperature}
  max_tokens: {config.analyzer.max_tokens}
  
[bold]Recorder (代理服务器)[/bold]
  host: {config.recorder.host}
  port: {config.recorder.port}
  protocol: {config.recorder.protocol}
  
[bold]Storage[/bold]
  logs_dir: {config.storage.logs_dir}
  
[bold]MCP[/bold]
  transport: {config.mcp.transport}""",
        title="FlowCraft Configuration",
    ))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="配置键 (如 llm.model)"),
    value: str = typer.Argument(..., help="配置值"),
):
    """设置配置项"""
    # TODO: 实现配置持久化
    console.print(f"[yellow]设置 {key} = {value}[/yellow]")
    console.print("[dim]注意: 配置持久化功能待实现，当前仅支持环境变量[/dim]")


# =============================================================================
# Record Commands
# =============================================================================

record_app = typer.Typer(help="会话记录")
app.add_typer(record_app, name="record")


@record_app.command("start")
def record_start(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8080, "--port", "-p", help="监听端口"),
    protocol: str = typer.Option("auto", "--protocol", help="协议: auto, anthropic, openai"),
    foreground: bool = typer.Option(False, "--foreground", "-f", help="前台运行（不作为守护进程）"),
):
    """启动代理服务器记录会话
    
    Examples:
        flowcraft record start              # 后台守护进程
        flowcraft record start -f           # 前台运行
        flowcraft record start -p 9000      # 指定端口
    """
    from .daemon import start_daemon, is_service_running, get_service_info
    
    if foreground:
        # 前台运行模式
        import uvicorn
        from ..recorder import create_app
        
        console.print(f"[bold]启动 FlowCraft 代理服务器（前台模式）[/bold]")
        console.print(f"  地址: http://{host}:{port}")
        console.print(f"  协议: {protocol}")
        console.print()
        console.print("[dim]按 Ctrl+C 停止[/dim]")
        
        app_instance = create_app()
        uvicorn.run(app_instance, host=host, port=port, log_level="info")
    else:
        # 守护进程模式
        if is_service_running():
            info = get_service_info()
            console.print(f"[yellow]⚠[/yellow] 服务已在运行中")
            console.print(f"  PID: {info.pid}")
            console.print(f"  端口: {info.port}")
            console.print(f"  端点: {info.endpoint}")
            console.print()
            console.print("[dim]使用 'flowcraft record stop' 停止服务[/dim]")
            raise typer.Exit(1)
        
        success, message = start_daemon(host=host, port=port, protocol=protocol)
        
        if success:
            console.print(f"[green]✓[/green] {message}")
            console.print()
            console.print(f"[dim]端点: http://{host}:{port}[/dim]")
            console.print(f"[dim]使用 'flowcraft record status' 查看状态[/dim]")
            console.print(f"[dim]使用 'flowcraft record stop' 停止服务[/dim]")
        else:
            console.print(f"[red]✗[/red] {message}")
            raise typer.Exit(1)


@record_app.command("stop")
def record_stop():
    """停止代理服务器"""
    from .daemon import stop_daemon, is_service_running
    
    if not is_service_running():
        console.print("[yellow]服务未运行[/yellow]")
        return
    
    success, message = stop_daemon()
    
    if success:
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")
        raise typer.Exit(1)


@record_app.command("restart")
def record_restart(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8080, "--port", "-p", help="监听端口"),
    protocol: str = typer.Option("auto", "--protocol", help="协议: auto, anthropic, openai"),
):
    """重启代理服务器"""
    from .daemon import restart_daemon
    
    console.print("[bold]重启 FlowCraft 服务...[/bold]")
    
    success, message = restart_daemon(host=host, port=port, protocol=protocol)
    
    if success:
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")
        raise typer.Exit(1)


@record_app.command("status")
def record_status():
    """查看记录服务状态"""
    from .daemon import get_service_info, get_pid_file, get_log_file
    
    info = get_service_info()
    
    if info.running:
        console.print(Panel.fit(
            f"""[green]● 运行中[/green]

[bold]进程信息[/bold]
  PID:    {info.pid}
  端点:   {info.endpoint}
  主机:   {info.host}
  端口:   {info.port}

[bold]文件位置[/bold]
  PID 文件: {get_pid_file()}
  日志文件: {get_log_file()}""",
            title="FlowCraft 服务状态",
        ))
    else:
        console.print(Panel.fit(
            f"""[red]○ 未运行[/red]

[dim]使用 'flowcraft record start' 启动服务[/dim]""",
            title="FlowCraft 服务状态",
        ))


# =============================================================================
# Inspect Commands
# =============================================================================

inspect_app = typer.Typer(help="会话检查")
app.add_typer(inspect_app, name="inspect")


@inspect_app.command("list")
def inspect_list(
    limit: int = typer.Option(20, "-n", "--limit", help="显示的最大会话数"),
):
    """列出已记录的会话"""
    config = get_config()
    logs_dir = Path(config.storage.logs_dir).expanduser()
    sessions_dir = logs_dir / "sessions"
    
    if not sessions_dir.exists():
        console.print("[yellow]没有找到会话记录[/yellow]")
        return
    
    table = Table(title="会话列表")
    table.add_column("ID", style="cyan")
    table.add_column("开始时间")
    table.add_column("客户端")
    table.add_column("模型")
    table.add_column("请求数")
    
    count = 0
    for session_dir in sorted(sessions_dir.iterdir(), reverse=True):
        if count >= limit:
            break
        
        if session_dir.is_dir():
            metadata_file = session_dir / "metadata.json"
            if metadata_file.exists():
                try:
                    data = json.loads(metadata_file.read_text())
                    table.add_row(
                        session_dir.name,
                        data.get("start_time", "N/A")[:19],
                        data.get("client", "N/A"),
                        data.get("model", "N/A").split("/")[-1],
                        str(data.get("request_count", "N/A")),
                    )
                    count += 1
                except Exception:
                    table.add_row(session_dir.name, "N/A", "N/A", "N/A", "N/A")
                    count += 1
    
    console.print(table)


@inspect_app.command("show")
def inspect_show(
    session_id: str = typer.Argument(..., help="会话 ID"),
):
    """显示会话详情"""
    config = get_config()
    logs_dir = Path(config.storage.logs_dir).expanduser()
    session_dir = logs_dir / "sessions" / session_id
    
    if not session_dir.exists():
        console.print(f"[red]会话 {session_id} 不存在[/red]")
        raise typer.Exit(1)
    
    # 读取 metadata
    metadata_file = session_dir / "metadata.json"
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())
        console.print(Panel.fit(
            f"""Session ID: {session_id}
Start Time: {metadata.get('start_time', 'N/A')}
Client: {metadata.get('client', 'N/A')}
Model: {metadata.get('model', 'N/A')}
Requests: {metadata.get('request_count', 'N/A')}""",
            title="会话信息",
        ))
    
    # 列出轮次
    rounds = []
    i = 1
    while True:
        req_file = session_dir / f"{i:03d}_request.json"
        if not req_file.exists():
            break
        rounds.append(i)
        i += 1
    
    console.print(f"\n共 {len(rounds)} 轮交互")


@inspect_app.command("analyze")
def inspect_analyze(
    session_id: str = typer.Argument(..., help="会话 ID"),
    aspects: List[str] = typer.Option(
        ["memory", "tools", "rounds"],
        "--aspect", "-a",
        help="分析方面",
    ),
):
    """分析会话"""
    from ..inspector import InspectorEngine
    
    config = get_config()
    logs_dir = Path(config.storage.logs_dir).expanduser()
    session_dir = logs_dir / "sessions" / session_id
    
    if not session_dir.exists():
        console.print(f"[red]会话 {session_id} 不存在[/red]")
        raise typer.Exit(1)
    
    # 加载消息
    messages = []
    i = 1
    while True:
        req_file = session_dir / f"{i:03d}_request.json"
        if not req_file.exists():
            break
        req_data = json.loads(req_file.read_text())
        raw_req = req_data.get("raw_request", {})
        messages.extend(raw_req.get("messages", []))
        i += 1
    
    console.print(f"[green]✓[/green] 加载 {len(messages)} 条消息")
    
    # 分析
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("分析中...", total=None)
        
        engine = InspectorEngine()
        result = engine.analyze(messages, aspects=aspects)
        
        progress.remove_task(task)
    
    # 显示结果
    console.print(Panel(
        json.dumps(result, ensure_ascii=False, indent=2)[:2000],
        title="分析结果",
    ))


@inspect_app.command("delete")
def inspect_delete(
    session_ids: List[str] = typer.Argument(..., help="要删除的会话 ID（可多个）"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """删除指定的会话
    
    Examples:
        flowcraft inspect delete abc123
        flowcraft inspect delete abc123 def456 --force
    """
    import shutil
    
    config = get_config()
    logs_dir = Path(config.storage.logs_dir).expanduser()
    sessions_dir = logs_dir / "sessions"
    
    # 验证会话存在
    valid_sessions = []
    for sid in session_ids:
        session_dir = sessions_dir / sid
        if session_dir.exists():
            valid_sessions.append(sid)
        else:
            console.print(f"[yellow]会话 {sid} 不存在，跳过[/yellow]")
    
    if not valid_sessions:
        console.print("[yellow]没有有效的会话可删除[/yellow]")
        return
    
    # 确认删除
    if not force:
        console.print(f"[bold]即将删除以下 {len(valid_sessions)} 个会话:[/bold]")
        for sid in valid_sessions:
            console.print(f"  • {sid}")
        
        confirm = typer.confirm("确认删除？")
        if not confirm:
            console.print("[dim]已取消[/dim]")
            return
    
    # 执行删除
    deleted = 0
    for sid in valid_sessions:
        session_dir = sessions_dir / sid
        try:
            shutil.rmtree(session_dir)
            console.print(f"[green]✓[/green] 已删除 {sid}")
            deleted += 1
        except Exception as e:
            console.print(f"[red]✗[/red] 删除 {sid} 失败: {e}")
    
    console.print(f"\n共删除 {deleted} 个会话")


@inspect_app.command("clean")
def inspect_clean(
    days: int = typer.Option(30, "--days", "-d", help="删除多少天前的会话"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="仅显示将被删除的会话，不实际删除"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """清理旧会话
    
    Examples:
        flowcraft inspect clean --days 7           # 删除 7 天前的会话
        flowcraft inspect clean --days 30 --dry-run  # 预览将被删除的会话
    """
    import shutil
    from datetime import datetime, timedelta
    
    config = get_config()
    logs_dir = Path(config.storage.logs_dir).expanduser()
    sessions_dir = logs_dir / "sessions"
    
    if not sessions_dir.exists():
        console.print("[yellow]没有找到会话记录[/yellow]")
        return
    
    cutoff_date = datetime.now() - timedelta(days=days)
    old_sessions = []
    
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        
        metadata_file = session_dir / "metadata.json"
        if metadata_file.exists():
            try:
                data = json.loads(metadata_file.read_text())
                start_time_str = data.get("start_time", "")
                if start_time_str:
                    # 解析时间 (格式: 2026-04-01T00:08:34.123456)
                    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    if start_time.replace(tzinfo=None) < cutoff_date:
                        old_sessions.append((session_dir.name, start_time_str[:19]))
            except Exception:
                pass
    
    if not old_sessions:
        console.print(f"[green]没有 {days} 天前的会话需要清理[/green]")
        return
    
    # 显示将被删除的会话
    table = Table(title=f"{days} 天前的会话 ({len(old_sessions)} 个)")
    table.add_column("ID", style="cyan")
    table.add_column("开始时间")
    
    for sid, start_time in sorted(old_sessions, key=lambda x: x[1]):
        table.add_row(sid, start_time)
    
    console.print(table)
    
    if dry_run:
        console.print("\n[dim]--dry-run 模式，未实际删除[/dim]")
        return
    
    # 确认删除
    if not force:
        confirm = typer.confirm(f"确认删除这 {len(old_sessions)} 个会话？")
        if not confirm:
            console.print("[dim]已取消[/dim]")
            return
    
    # 执行删除
    deleted = 0
    for sid, _ in old_sessions:
        session_dir = sessions_dir / sid
        try:
            shutil.rmtree(session_dir)
            deleted += 1
        except Exception as e:
            console.print(f"[red]✗[/red] 删除 {sid} 失败: {e}")
    
    console.print(f"[green]✓[/green] 已清理 {deleted} 个旧会话")


@inspect_app.command("stats")
def inspect_stats():
    """显示会话统计信息"""
    from datetime import datetime
    
    config = get_config()
    logs_dir = Path(config.storage.logs_dir).expanduser()
    sessions_dir = logs_dir / "sessions"
    
    if not sessions_dir.exists():
        console.print("[yellow]没有找到会话记录[/yellow]")
        return
    
    total_sessions = 0
    total_requests = 0
    total_size = 0
    models = {}
    clients = {}
    
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        
        total_sessions += 1
        
        # 计算目录大小
        for f in session_dir.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size
        
        # 读取 metadata
        metadata_file = session_dir / "metadata.json"
        if metadata_file.exists():
            try:
                data = json.loads(metadata_file.read_text())
                total_requests += data.get("request_count", 0)
                
                model = data.get("model", "unknown")
                models[model] = models.get(model, 0) + 1
                
                client = data.get("client", "unknown")
                clients[client] = clients.get(client, 0) + 1
            except Exception:
                pass
    
    # 格式化大小
    if total_size < 1024:
        size_str = f"{total_size} B"
    elif total_size < 1024 * 1024:
        size_str = f"{total_size / 1024:.1f} KB"
    else:
        size_str = f"{total_size / 1024 / 1024:.1f} MB"
    
    console.print(Panel.fit(
        f"""[bold]总计[/bold]
  会话数: {total_sessions}
  请求数: {total_requests}
  存储大小: {size_str}
  存储路径: {sessions_dir}

[bold]模型分布[/bold]
{chr(10).join(f'  {m}: {c}' for m, c in sorted(models.items(), key=lambda x: -x[1])[:5])}

[bold]客户端分布[/bold]
{chr(10).join(f'  {c}: {n}' for c, n in sorted(clients.items(), key=lambda x: -x[1])[:5])}""",
        title="会话统计",
    ))


# =============================================================================
# Distill Command
# =============================================================================

@app.command()
def distill(
    session_id: str = typer.Argument(..., help="会话 ID"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="输出文件"),
    format: str = typer.Option("yaml", "-f", "--format", help="输出格式: yaml, json"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="交互式模式"),
):
    """从会话中蒸馏工作流
    
    Examples:
        flowcraft distill abc123 -o workflow.yaml
        flowcraft distill abc123 --interactive
    """
    from ..distiller import DistillEngine
    from ..codegen import WorkflowDSL, DSLFormat
    
    config = get_config()
    logs_dir = Path(config.storage.logs_dir).expanduser()
    session_dir = logs_dir / "sessions" / session_id
    
    if not session_dir.exists():
        console.print(f"[red]会话 {session_id} 不存在[/red]")
        raise typer.Exit(1)
    
    # 加载消息
    messages = []
    i = 1
    while True:
        req_file = session_dir / f"{i:03d}_request.json"
        if not req_file.exists():
            break
        req_data = json.loads(req_file.read_text())
        raw_req = req_data.get("raw_request", {})
        for msg in raw_req.get("messages", []):
            messages.append({
                "role": msg.get("role"),
                "content": msg.get("content"),
            })
        i += 1
    
    console.print(f"[green]✓[/green] 加载 {len(messages)} 条消息")
    
    # 蒸馏
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("蒸馏工作流...", total=None)
        
        engine = DistillEngine()
        result = asyncio.run(engine.distill(messages, session_id=session_id))
        
        progress.remove_task(task)
    
    # 格式化输出
    dsl = WorkflowDSL()
    fmt = DSLFormat.YAML if format == "yaml" else DSLFormat.JSON
    dsl_output = dsl.generate(result.workflow, format=fmt)
    
    if output:
        output.write_text(dsl_output.content)
        console.print(f"[green]✓[/green] 已保存到 {output}")
    else:
        console.print(Syntax(dsl_output.content, "yaml" if format == "yaml" else "json"))


# =============================================================================
# Reflect Command
# =============================================================================

@app.command()
def reflect(
    workflow_file: Path = typer.Argument(..., help="工作流文件", exists=True),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="输出文件"),
):
    """分析工作流并提供改进建议
    
    Examples:
        flowcraft reflect workflow.yaml
        flowcraft reflect workflow.yaml -o reflection.json
    """
    import yaml
    from ..schemas import Workflow
    from ..reflector import WorkflowReflector
    
    # 读取工作流
    content = workflow_file.read_text()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = yaml.safe_load(content)
    
    workflow = Workflow.model_validate(data)
    console.print(f"[green]✓[/green] 加载工作流: {workflow.name}")
    
    # 反思
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("分析中...", total=None)
        
        reflector = WorkflowReflector()
        result = asyncio.run(reflector.reflect(workflow))
        
        progress.remove_task(task)
    
    # 显示结果
    console.print(Panel(
        f"效率评分: {result.efficiency_score:.2f}\n\n{result.summary}",
        title="反思结果",
    ))
    
    if result.patterns:
        console.print("\n[bold cyan]识别的模式:[/bold cyan]")
        for p in result.patterns:
            console.print(f"  • {p.name}: {p.description}")
    
    if result.improvements:
        console.print("\n[bold yellow]改进建议:[/bold yellow]")
        for imp in result.improvements:
            console.print(f"  • {imp}")
    
    if output:
        output.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        console.print(f"\n[green]✓[/green] 已保存到 {output}")


# =============================================================================
# Generate Command
# =============================================================================

@app.command()
def generate(
    workflow_file: Path = typer.Argument(..., help="工作流文件", exists=True),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="输出文件"),
    with_tests: bool = typer.Option(False, "--with-tests", help="生成测试代码"),
):
    """从工作流生成 LangGraph 代码
    
    Examples:
        flowcraft generate workflow.yaml -o agent.py
        flowcraft generate workflow.yaml --with-tests
    """
    import yaml
    from ..schemas import Workflow
    from ..codegen import LangGraphGenerator
    
    # 读取工作流
    content = workflow_file.read_text()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = yaml.safe_load(content)
    
    workflow = Workflow.model_validate(data)
    console.print(f"[green]✓[/green] 加载工作流: {workflow.name}")
    
    # 生成
    generator = LangGraphGenerator()
    code = generator.generate(workflow, include_tests=with_tests)
    
    if output:
        output.write_text(code.main_code)
        console.print(f"[green]✓[/green] 代码已保存到 {output}")
        
        if code.test_code:
            test_output = output.with_name(f"test_{output.name}")
            test_output.write_text(code.test_code)
            console.print(f"[green]✓[/green] 测试代码已保存到 {test_output}")
    else:
        console.print(Syntax(code.main_code, "python"))
    
    console.print(f"\n[dim]依赖: {', '.join(code.requirements)}[/dim]")


# =============================================================================
# MCP Commands
# =============================================================================

mcp_app = typer.Typer(help="MCP 服务")
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("serve")
def mcp_serve():
    """启动 MCP 服务（通过 stdio）"""
    console.print("[bold]启动 MCP 服务...[/bold]")
    console.print("[dim]通过 stdio 通信[/dim]")
    
    from ..mcp import run_mcp_server
    asyncio.run(run_mcp_server())


# =============================================================================
# Version Command
# =============================================================================

@app.command()
def version():
    """显示版本信息"""
    from .. import __version__
    console.print(f"FlowCraft v{__version__}")


# =============================================================================
# Main Entry
# =============================================================================

def main():
    """CLI 入口"""
    app()


if __name__ == "__main__":
    main()
