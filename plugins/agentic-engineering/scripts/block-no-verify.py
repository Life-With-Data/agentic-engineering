#!/usr/bin/env python3
"""
Claude Code hook to block git commits with --no-verify flag.

This hook prevents bypassing pre-commit checks, which are there for a reason.
If tests or checks fail, fix them - don't bypass them!
"""
import json
import re
import sys

def main():
    # Read the tool use input from stdin
    input_data = json.load(sys.stdin)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only check Bash tool commands
    if tool_name != "Bash":
        sys.exit(0)  # Allow other tools

    # Check for git commit with --no-verify as a flag (not in quoted strings)
    if "git commit" in command and is_no_verify_flag(command):
        error_msg = """
❌ BLOCKED: Using --no-verify bypasses pre-commit hooks!

Pre-commit hooks exist to catch issues before they reach CI. If hooks are failing:
1. Fix the failing tests/checks (don't bypass them)
2. If the hooks themselves are broken, fix the hooks
3. Only use --no-verify as an absolute last resort with explicit user permission

Bypassing hooks defeats the purpose of quality gates that protect the codebase.
""".strip()
        print(error_msg, file=sys.stderr)
        sys.exit(2)  # Exit code 2 blocks the command

    # Allow the command
    sys.exit(0)

def is_no_verify_flag(command):
    """
    Check if --no-verify appears as a flag (not inside quoted strings).
    This is a simple heuristic that looks for --no-verify outside of quotes.
    """
    # Remove single-quoted strings
    command = re.sub(r"'[^']*'", "", command)
    # Remove double-quoted strings
    command = re.sub(r'"[^"]*"', "", command)
    # Now check if --no-verify appears in what's left
    return "--no-verify" in command

if __name__ == "__main__":
    main()
