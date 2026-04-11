#!/usr/bin/env python3
"""Sample the first N lines of a JSONL log file to identify its format.

Usage:
    python scripts/sample_log.py <file.jsonl> [--lines 5]

Output: prints each line as pretty-printed JSON with a format guess.
"""

import json
import sys
from pathlib import Path


FORMAT_SIGNATURES = {
    "vscode": lambda d: d.get("kind") is not None and "v" in d,
    "claude_code": lambda d: d.get("type") in ("user", "assistant", "system") or d.get("parentUuid") is not None,
    "openai_style": lambda d: d.get("role") in ("user", "assistant", "system") and "content" in d,
}


def guess_format(obj: dict) -> str:
    for name, check in FORMAT_SIGNATURES.items():
        try:
            if check(obj):
                return name
        except Exception:
            continue
    return "unknown"


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    path = Path(sys.argv[1])
    n_lines = 5
    if "--lines" in sys.argv:
        idx = sys.argv.index("--lines")
        n_lines = int(sys.argv[idx + 1])

    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    guesses = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= n_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                fmt = guess_format(obj)
                guesses.append(fmt)
                print(f"--- Line {i + 1} [format: {fmt}] ---")
                print(json.dumps(obj, indent=2, ensure_ascii=False)[:2000])
                print()
            except json.JSONDecodeError:
                print(f"--- Line {i + 1} [not valid JSON] ---")
                print(line[:200])
                print()

    if guesses:
        from collections import Counter
        most_common = Counter(guesses).most_common(1)[0][0]
        print(f"Best guess: {most_common}")
    else:
        print("No JSON lines found in file.")


if __name__ == "__main__":
    main()
