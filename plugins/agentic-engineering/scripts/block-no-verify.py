#!/usr/bin/env python3
"""
Claude Code hook to block git commits/pushes that bypass verification hooks
via `--no-verify` (or its short form `-n`).

Pre-commit / pre-push hooks exist to catch issues before they reach CI. If
checks fail, fix the root cause — don't bypass them.

Design notes (why this is more than a substring check):
- It only fires when `git commit` or `git push` is the actual command verb,
  so analysis/meta commands that merely *mention* the flag (e.g.
  `echo 'never use --no-verify'`, `grep -- --no-verify`, a `# git commit
  --no-verify` comment) are NOT blocked. The previous naive
  `"git commit" in command` check produced these false positives and even
  blocked legitimate transcript-analysis commands.
- It is segment-aware: the flag must appear in the same simple command
  segment as the git verb (not after a later `&&`/`;`/`|`), so a chained
  `git commit -m x && echo -n hi` is not mistaken for a bypass.
- It also covers `git push --no-verify`, which the previous version missed
  entirely (push has a pre-push hook bypass too).
"""
import json
import re
import sys

# Within a single command segment, `git commit ... (-n | --no-verify)`.
COMMIT_BYPASS = re.compile(r"\bgit\s+commit\b[^&|;]*?(?:^|\s)(?:-n|--no-verify)\b")
# `git push ... --no-verify` (push has no `-n` short form for this).
PUSH_BYPASS = re.compile(r"\bgit\s+push\b[^&|;]*?(?:^|\s)--no-verify\b")

ERROR_MSG = """
❌ BLOCKED: Using --no-verify bypasses pre-commit / pre-push hooks!

Verification hooks exist to catch issues before they reach CI. If hooks are failing:
1. Fix the failing tests/checks (don't bypass them)
2. If the hooks themselves are broken, fix the hooks
3. Only use --no-verify as an absolute last resort

Bypassing hooks defeats the quality guardrails this plugin is designed to enforce.
""".strip()


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)  # Allow other tools

    command = input_data.get("tool_input", {}).get("command", "")

    if uses_no_verify_bypass(command):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)  # Exit code 2 blocks the command

    sys.exit(0)


def uses_no_verify_bypass(command: str) -> bool:
    """True only when an actual git commit/push is bypassing verification."""
    cleaned = sanitize(command)
    return bool(COMMIT_BYPASS.search(cleaned) or PUSH_BYPASS.search(cleaned))


def sanitize(command: str) -> str:
    """Drop quoted strings and shell comments so prose/paths that merely
    mention the flag can't trigger a false positive."""
    command = re.sub(r"'[^']*'", "", command)   # single-quoted strings
    command = re.sub(r'"[^"]*"', "", command)   # double-quoted strings
    command = re.sub(r"#.*", "", command)        # trailing comments
    return command


if __name__ == "__main__":
    main()
