#!/usr/bin/env python3
"""
Claude Code hook to block hardcoding a Slack *incoming webhook* URL
(`hooks.slack.com/services/...`) into code, config, or a Bash command.

Why this is a guardrail worth shipping:
- A Slack incoming-webhook URL **is a live credential** — anyone who has the
  URL can post to the channel. Writing one into a source file or CI config
  leaks that secret into git history (and often into build logs), where it is
  hard to fully revoke.
- Ad-hoc incoming webhooks also fragment notification wiring: they bypass the
  auth, channel config, and single code path of a connected Slack app / MCP
  integration, so alerts drift out of one place into scattered `curl`s.

The unmistakable signal is the incoming-webhook host+path
`hooks.slack.com/services/`, which appears in the webhook URL itself and in the
`curl`/fetch calls that post to it. That string essentially never appears for
any legitimate reason, so this is a precise, low-false-positive guard — in the
spirit of the other hooks here, which avoid naive substring matching.

Correct alternative: read the webhook from an environment variable / secret
manager instead of hardcoding it, or route the notification through a connected
Slack app / the Slack MCP tooling (`chat.postMessage`) rather than an incoming
webhook.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import normalize

# Canonical Slack incoming-webhook host + path prefix. Matches both
# https://hooks.slack.com/services/... URLs and bare references.
WEBHOOK_RE = re.compile(r"hooks\.slack\.com/services/", re.IGNORECASE)

ERROR_MSG = """
❌ BLOCKED: Slack *incoming webhook* URL detected (hooks.slack.com/services/...).

A Slack incoming-webhook URL is a live credential — hardcoding it into code, CI
config, or a shell command leaks a secret into git history and build logs, and
scatters your Slack notifications outside a single, authenticated code path.

Instead:
1. Read the webhook from an environment variable / secret manager — never inline
   the URL in a tracked file.
2. Better: send through a connected Slack app or the Slack MCP tooling
   (chat.postMessage), which handles auth and channel config for you.

Documentation files that merely *describe* the anti-pattern are exempt.
""".strip()

# Prose / documentation files that legitimately *mention* the webhook host
# without *using* it. Editing these is allowed (mirrors the other hooks here,
# which deliberately don't fire on prose that merely names a blocked path).
DOC_PATH_RE = re.compile(r"\.(md|mdx|markdown|txt|rst)$", re.IGNORECASE)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$")
PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$")


def main():
    input_data = normalize(json.load(sys.stdin))

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    text = extract_text(tool_name, tool_input)
    if text and WEBHOOK_RE.search(text):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)  # Exit code 2 blocks the tool call

    sys.exit(0)


def extract_text(tool_name: str, tool_input: dict) -> str:
    """Return the text to scan, depending on which tool is being used.

    Covers Bash commands (e.g. a curl to a webhook URL) and file mutations
    (Write/Edit/MultiEdit/apply_patch) that would add a webhook URL to code or config.
    Documentation files, and this guard's own tooling, are exempt — they
    describe the anti-pattern rather than introduce it.
    """
    if tool_name == "Bash":
        return tool_input.get("command", "") or ""

    if tool_name == "apply_patch":
        return extract_apply_patch_additions(tool_input.get("command", "") or "")

    file_path = tool_input.get("file_path", "") or ""
    if DOC_PATH_RE.search(file_path):
        return ""  # prose mention, not a real integration
    if "/hooks/" in file_path or "/scripts/" in file_path:
        return ""  # a guard/script that references the pattern by design

    if tool_name == "Write":
        return tool_input.get("content", "") or ""

    if tool_name == "Edit":
        return tool_input.get("new_string", "") or ""

    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", []) or []
        return "\n".join(
            e.get("new_string", "") for e in edits if isinstance(e, dict)
        )

    return ""


def extract_apply_patch_additions(command: str) -> str:
    """Return added patch lines for non-exempt files.

    Codex serializes its primary edit tool as ``apply_patch`` with the complete
    patch in ``tool_input.command``. Only ``+`` lines introduce content; context
    and removed lines must not trigger the guard. If the payload is not a
    recognizable Codex patch, return it verbatim so the security check fails
    closed for a webhook-bearing mutation rather than silently bypassing it.
    """
    additions: list[str] = []
    current_path = ""
    saw_file_header = False

    for line in command.splitlines():
        file_match = PATCH_FILE_RE.match(line)
        if file_match:
            current_path = file_match.group(1).strip()
            saw_file_header = True
            continue

        move_match = PATCH_MOVE_RE.match(line)
        if move_match:
            current_path = move_match.group(1).strip()
            continue

        if line.startswith("*** Delete File:"):
            current_path = ""
            saw_file_header = True
            continue

        if not current_path or is_exempt_path(current_path):
            continue

        if line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:])

    return "\n".join(additions) if saw_file_header else command


def is_exempt_path(file_path: str) -> bool:
    """Match the same documentation and hook-tooling exemptions across paths."""
    normalized = "/" + file_path.replace("\\", "/").lstrip("/")
    return bool(
        DOC_PATH_RE.search(file_path)
        or "/hooks/" in normalized
        or "/scripts/" in normalized
    )


if __name__ == "__main__":
    main()
