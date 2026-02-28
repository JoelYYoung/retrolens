#!/usr/bin/env python3
"""
Rev-Agent CLI - Session Analysis Command Line Tool
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from ..listener.storage import SessionStorage
    from .engine import analyze_session
except ImportError:
    # Import when running directly
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from listener.storage import SessionStorage
    from analyzer.engine import analyze_session


def list_sessions(args):
    """List all sessions"""
    storage = SessionStorage()
    sessions = storage.list_sessions()
    
    if not sessions:
        print("No sessions found.")
        return
    
    print(f"\nFound {len(sessions)} session(s):\n")
    print(f"{'Session ID':<12} {'Client':<15} {'Model':<30} {'Start Time'}")
    print("-" * 80)
    
    for s in sessions:
        print(f"{s['session_id']:<12} {s.get('client', 'N/A'):<15} {s.get('model', 'N/A'):<30} {s.get('start_time', 'N/A')}")


def show_session(args):
    """Show session details"""
    storage = SessionStorage()
    
    try:
        data = storage.get_session_data(args.session_id)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    metadata = data["metadata"]
    
    print(f"\n{'='*60}")
    print(f"Session: {args.session_id}")
    print(f"{'='*60}")
    print(f"Client: {metadata.get('client', 'N/A')}")
    print(f"Model: {metadata.get('model', 'N/A')}")
    print(f"Start Time: {metadata.get('start_time', 'N/A')}")
    print(f"Requests: {len(data['requests'])}")
    print(f"Responses: {len(data['responses'])}")
    
    if args.verbose:
        print(f"\n{'='*60}")
        print("Request Summary:")
        print(f"{'='*60}")
        for req in data["requests"]:
            ext = req.get("extracted", {})
            print(f"\n  #{req['sequence']} - {req['timestamp']}")
            print(f"    Messages: {ext.get('messages_count', 'N/A')}")
            print(f"    Tools: {ext.get('tools_count', 'N/A')}")
            print(f"    Tokens (est): {ext.get('messages_total_tokens_estimate', 'N/A')}")


def analyze(args):
    """Analyze session"""
    storage = SessionStorage()
    
    try:
        data = storage.get_session_data(args.session_id)
        analysis = analyze_session(data)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        return
    
    memory = analysis["memory_analysis"]
    planning = analysis["planning_analysis"]
    tools = analysis["tools_analysis"]
    
    print(f"\n{'='*60}")
    print(f"Analysis: {args.session_id}")
    print(f"{'='*60}")
    
    print(f"\n[Memory Analysis]")
    print(f"  Total Tokens (est): {memory['total_tokens_estimate']:,}")
    print(f"  File Reads: {len(memory['file_read_history'])}")
    print(f"  Repeated Files: {len(memory['repeated_files'])}")
    if memory['repeated_files']:
        for path, count in memory['repeated_files'].items():
            print(f"    - {path}: {count}x")
    
    print(f"\n[Planning Analysis]")
    print(f"  System Prompt Has Planning: {planning['system_prompt_has_planning_instruction']['has_planning_instructions']}")
    print(f"  Thinking Blocks: {len(planning['thinking_blocks'])}")
    print(f"  Task Decomposition: {planning['task_decomposition_detected']['detected']}")
    
    print(f"\n[Tools Analysis]")
    print(f"  Total Tools: {tools['total_tools_count']}")
    print(f"  Tools Tokens (est): {tools['total_tools_tokens']:,}")
    print(f"  Categories:")
    for cat, tool_list in tools['categorized_tools'].items():
        print(f"    - {cat}: {len(tool_list)} tools")


def export_tools(args):
    """Export tool definitions"""
    storage = SessionStorage()
    
    try:
        data = storage.get_session_data(args.session_id)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Extract tools
    all_tools = []
    for req in data.get("requests", []):
        tools = req.get("raw_request", {}).get("tools", [])
        if len(tools) > len(all_tools):
            all_tools = tools
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(all_tools, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(all_tools)} tools to: {args.output}")
    else:
        print(json.dumps(all_tools, indent=2, ensure_ascii=False))


def export_system_prompt(args):
    """Export system prompt"""
    storage = SessionStorage()
    
    try:
        data = storage.get_session_data(args.session_id)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Extract system prompt
    system_prompt = ""
    for req in data.get("requests", []):
        sp = req.get("raw_request", {}).get("system", "")
        if sp:
            system_prompt = sp
            break
    
    if isinstance(system_prompt, list):
        # Structured system prompt
        if args.json:
            output = json.dumps(system_prompt, indent=2, ensure_ascii=False)
        else:
            output = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in system_prompt
            )
    else:
        output = system_prompt if not args.json else json.dumps({"system": system_prompt}, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"System prompt exported to: {args.output}")
    else:
        print(output)


def raw_data(args):
    """Print raw request/response data"""
    storage = SessionStorage()
    
    try:
        data = storage.get_session_data(args.session_id)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    seq = args.seq
    data_type = args.type
    
    # Print request
    if data_type in ["request", "both"]:
        for req in data["requests"]:
            if req["sequence"] == seq:
                print("=" * 60)
                print(f"RAW REQUEST #{seq}")
                print("=" * 60)
                print(json.dumps(req["raw_request"], indent=2, ensure_ascii=False))
                break
        else:
            if data_type == "request":
                print(f"Request #{seq} not found")
                sys.exit(1)
    
    # Print response
    if data_type in ["response", "both"]:
        for resp in data["responses"]:
            if resp["sequence"] == seq:
                print("\n" + "=" * 60)
                print(f"RAW RESPONSE #{seq}")
                print("=" * 60)
                print(json.dumps(resp["raw_response"], indent=2, ensure_ascii=False))
                break
        else:
            if data_type == "response":
                print(f"Response #{seq} not found")
                sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="rev-cli",
        description="Rev-Agent CLI - Claude Code Reverse Analysis Tool"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # list command
    list_parser = subparsers.add_parser("list", help="List all sessions")
    list_parser.set_defaults(func=list_sessions)
    
    # show command
    show_parser = subparsers.add_parser("show", help="Show session details")
    show_parser.add_argument("session_id", help="Session ID")
    show_parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed info")
    show_parser.set_defaults(func=show_session)
    
    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a session")
    analyze_parser.add_argument("session_id", help="Session ID")
    analyze_parser.add_argument("--json", action="store_true", help="Output as JSON")
    analyze_parser.set_defaults(func=analyze)
    
    # tools command
    tools_parser = subparsers.add_parser("tools", help="Export tool definitions")
    tools_parser.add_argument("session_id", help="Session ID")
    tools_parser.add_argument("-o", "--output", help="Output file path")
    tools_parser.set_defaults(func=export_tools)
    
    # system-prompt command
    sp_parser = subparsers.add_parser("system-prompt", help="Export system prompt")
    sp_parser.add_argument("session_id", help="Session ID")
    sp_parser.add_argument("-o", "--output", help="Output file path")
    sp_parser.add_argument("--json", action="store_true", help="Output as JSON")
    sp_parser.set_defaults(func=export_system_prompt)
    
    # raw command
    raw_parser = subparsers.add_parser("raw", help="Print raw request/response data")
    raw_parser.add_argument("session_id", help="Session ID")
    raw_parser.add_argument("-n", "--seq", type=int, default=1, help="Request sequence number (default: 1)")
    raw_parser.add_argument("-t", "--type", choices=["request", "response", "both"], default="both", help="Data type to print")
    raw_parser.set_defaults(func=raw_data)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == "__main__":
    main()
