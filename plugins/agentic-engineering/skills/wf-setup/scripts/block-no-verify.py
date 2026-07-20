#!/usr/bin/env python3
"""
Claude Code hook to block git commits/pushes that bypass verification hooks
via `--no-verify` (or its short form `-n`).

Pre-commit / pre-push hooks exist to catch issues before they reach CI. If
checks fail, fix the root cause — don't bypass them.

Design notes:
- Only fires when `git commit` or `git push` is the actual command verb, so
  analysis commands that merely *mention* the flag (e.g. `grep -- --no-verify`)
  are NOT blocked.
- Segment-aware: the flag must appear in the same simple command segment as the
  git verb (not after a later `&&`/`;`/`|`).
- Covers `git push --no-verify`, which has its own pre-push hook bypass.
- Ignores `--no-verify` that only appears inside a here-document body (e.g. a
  PR/issue body describing the flag, passed via
  `gh pr create --body-file - <<'EOF' … EOF`). Heredoc bodies are data, not
  commands, so prose mentioning the flag there must not block; inline
  `--body "…"` bodies are already covered by the quoted-string stripping.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import emit_allow, normalize

COMMIT_BYPASS = re.compile(r"\bgit\s+commit\b[^&|;]*?(?:^|\s)(?:-n|--no-verify)\b")
PUSH_BYPASS = re.compile(r"\bgit\s+push\b[^&|;]*?(?:^|\s)--no-verify\b")

ERROR_MSG = """
❌ BLOCKED: Using --no-verify bypasses pre-commit / pre-push hooks!

Verification hooks exist to catch issues before they reach CI. If hooks fail:
1. Fix the failing tests/checks — don't bypass them
2. If the hooks themselves are broken, fix the hooks
3. Use --no-verify only as an absolute last resort after consulting the team

The agentic-engineering workflow relies on quality gates compounding over time.
Bypassing hooks breaks that chain.
""".strip()


def main():
    input_data = normalize(json.load(sys.stdin))

    if input_data.get("tool_name") != "Bash":
        emit_allow()

    command = input_data.get("tool_input", {}).get("command", "")

    if uses_no_verify_bypass(command):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)

    emit_allow()


def uses_no_verify_bypass(command: str) -> bool:
    cleaned = sanitize(command)
    return bool(COMMIT_BYPASS.search(cleaned) or PUSH_BYPASS.search(cleaned))


# Here-document body: `<<[-] [quote]DELIM[quote] … \n DELIM`. Non-greedy with a
# per-heredoc backref so each body is matched to its own closer, and a real
# bypass chained *after* the heredoc still shows.
HEREDOC = re.compile(
    r"<<-?\s*(?P<q>['\"]?)(?P<delim>\w+)(?P=q).*?^\s*(?P=delim)\s*$",
    re.DOTALL | re.MULTILINE,
)


def sanitize(command: str) -> str:
    command = HEREDOC.sub("", command)           # here-document bodies (PR/issue bodies)
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    command = re.sub(r"#.*", "", command)
    return command


if __name__ == "__main__":
    main()
