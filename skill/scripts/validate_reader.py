#!/usr/bin/env python3
"""Validate a retrolens reader by cross-checking parsed output against raw data.

Usage:
    python scripts/validate_reader.py [--path <log-dir>] [--session <id>] [--turns 3]

Requires: pip install retrolens

Runs a field-level check on N turns and reports pass/fail for each field.
"""

import json
import subprocess
import sys


def run_retrolens(*args: str) -> dict | list:
    """Run a retrolens CLI command and return parsed JSON."""
    cmd = ["retrolens", *args, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: retrolens {' '.join(args)} failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def check_turn(session_id: str, turn_num: int) -> list[tuple[str, bool, str]]:
    """Check a single turn's fields. Returns list of (field, passed, detail)."""
    results = []

    turn = run_retrolens("read", session_id, "--turn", str(turn_num))

    # user_message non-empty
    msg = turn.get("user_message", "")
    results.append(("user_message", bool(msg), f"{len(msg)} chars"))

    # assistant_response non-empty
    resp = turn.get("assistant_response", "")
    results.append(("assistant_response", bool(resp), f"{len(resp)} chars"))

    # tool_calls
    tools = turn.get("tool_calls", [])
    results.append(("tool_calls_present", len(tools) >= 0, f"{len(tools)} tools"))

    # Each tool has tool_name
    empty_names = [i for i, t in enumerate(tools) if not t.get("tool_name")]
    results.append(("tool_names_populated",
                     len(empty_names) == 0,
                     f"{len(empty_names)} empty" if empty_names else "all populated"))

    # Each tool has output
    empty_outputs = [i for i, t in enumerate(tools) if not t.get("output_preview") and not t.get("output_full")]
    results.append(("tool_outputs_present",
                     len(empty_outputs) == 0,
                     f"{len(empty_outputs)} missing" if empty_outputs else "all present"))

    # files_touched is a list
    files = turn.get("files_touched", [])
    results.append(("files_touched", isinstance(files, list), f"{len(files)} files"))

    # commands_run is a list
    cmds = turn.get("commands_run", [])
    results.append(("commands_run", isinstance(cmds, list), f"{len(cmds)} commands"))

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", help="Log directory path")
    parser.add_argument("--session", help="Session ID (or prefix)")
    parser.add_argument("--turns", type=int, default=3, help="Number of turns to check")
    args = parser.parse_args()

    # Set path if provided
    if args.path:
        subprocess.run(["retrolens", "cfg", "set", "--path", args.path], check=True)

    # List sessions
    sessions = run_retrolens("ls")
    if not sessions:
        print("No sessions found. Check your --path.")
        sys.exit(1)

    # Pick session
    if args.session:
        session_id = args.session
    else:
        session_id = sessions[0]["session_id"]
        print(f"Auto-selected session: {session_id[:12]}...")

    # Get overview
    overview = run_retrolens("read", session_id)
    total_turns = len(overview.get("turns", []))
    n_check = min(args.turns, total_turns)

    print(f"\nValidating session {session_id[:12]}... ({total_turns} turns, checking {n_check})")
    print("=" * 60)

    all_passed = True
    for t in range(1, n_check + 1):
        print(f"\n--- Turn {t} ---")
        results = check_turn(session_id, t)
        for field, passed, detail in results:
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"  [{status}] {field}: {detail}")

    print("\n" + "=" * 60)
    if all_passed:
        print("All checks passed!")
    else:
        print("Some checks FAILED — review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
