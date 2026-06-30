#!/usr/bin/env python3
"""
Claude Code hook — block git commits/pushes that bypass verification hooks
via `--no-verify` (or its short form `-n`).

Pre-commit / pre-push hooks enforce quality gates (linting, type checks,
tests). Bypassing them with --no-verify defeats those gates and typically
causes avoidable CI failures. Fix the failing check instead.

Design notes:
- Only fires when `git commit` or `git push` is the actual command verb, so
  analysis commands that merely mention the flag (e.g. `grep -- --no-verify`)
  are NOT blocked.
- Segment-aware: the flag must appear in the same simple command segment as the
  git verb (not after a later `&&`/`;`/`|`), so chained commands like
  `git commit -m "msg" && echo -n hi` are not mistaken for a bypass.
- Also covers `git push --no-verify`, which has a separate pre-push hook bypass.
"""
import json
import re
import sys

COMMIT_BYPASS = re.compile(r"\bgit\s+commit\b[^&|;]*?(?:^|\s)(?:-n|--no-verify)\b")
PUSH_BYPASS   = re.compile(r"\bgit\s+push\b[^&|;]*?(?:^|\s)--no-verify\b")

ERROR_MSG = """
❌ BLOCKED: --no-verify bypasses pre-commit / pre-push quality gates.

Quality gates exist to catch issues before they reach CI. If a hook is failing:
1. Fix the failing check (the right path)
2. If the hook itself is broken, fix the hook
3. --no-verify is an absolute last resort — and even then, document why

Remove --no-verify from the command and resolve the underlying failure.
""".strip()


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    command = data.get("tool_input", {}).get("command", "")
    if _uses_no_verify(command):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


def _uses_no_verify(command: str) -> bool:
    cleaned = _sanitize(command)
    return bool(COMMIT_BYPASS.search(cleaned) or PUSH_BYPASS.search(cleaned))


def _sanitize(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    command = re.sub(r"#.*", "", command)
    return command


if __name__ == "__main__":
    main()
