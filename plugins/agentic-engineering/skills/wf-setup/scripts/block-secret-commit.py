#!/usr/bin/env python3
"""
Claude Code hook to block introducing a *live credential* into a Bash command,
a tracked file, or a Codex patch.

Why this is a guardrail worth shipping:
- A provider secret (a live API key, a cloud access key, a private key) is a
  bearer credential — whoever holds it can act as you. Writing one into a
  tracked file bakes it into git history and build logs, where it is hard to
  fully revoke; passing one on a Bash command line leaks it into shell history
  and process listings. The correct home for a secret is an environment
  variable or a secret manager, never a committed string.
- This complements `block-slack-webhook.py` (one specific live credential) with
  the broader family of high-signal provider secrets.

Precision over recall. Like the other guards here, this fires only on
*structurally unmistakable* live-secret shapes — a Stripe `sk_live_…`, an AWS
`AKIA…` access key, a GitHub `ghp_…` token, a PEM private-key header, and the
like — never on a bare provider name or a `DATABASE_URL`-style connection string
that legitimately litters configs and docs. Each token match additionally has
to *look real* (mixed letters and digits, no `EXAMPLE`/`xxxx` placeholder body),
so documented sample keys like AWS's `AKIAIOSFODNN7EXAMPLE` do not trip it.

Correct alternative: read the secret from an environment variable / secret
manager and reference it by name; keep real values out of tracked files and off
the command line. If a match is a placeholder or fixture, name the file
`*.example` / `*.sample` or place it under a `fixtures/` directory (both exempt),
or move it to a documentation file.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import emit_allow, normalize

# --- Live-secret signatures --------------------------------------------------
# Each entry is (human label, compiled pattern). Patterns are deliberately
# structural and provider-specific so a match is almost never a false positive.
# Alnum-run tokens are length-bounded and further filtered by looks_real().
SECRET_PATTERNS: "list[tuple[str, re.Pattern[str]]]" = [
    ("Stripe live secret/restricted key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{20,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("OpenAI/Anthropic-style secret key", re.compile(r"\bsk-(?:ant-|proj-)?[0-9A-Za-z_\-]{20,}")),
    ("PEM private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
]

# Substrings that mark a token as an obvious placeholder rather than a real
# secret. Case-insensitive.
PLACEHOLDER_MARKERS = (
    "example", "placeholder", "your", "redacted", "dummy", "sample",
    "xxxx", "changeme", "insert", "replace", "fake",
)

ERROR_MSG = """
❌ BLOCKED: a live credential ({label}) was detected in this change.

A provider secret is a bearer credential — committing it bakes the secret into
git history and build logs (hard to fully revoke), and putting it on a Bash
command line leaks it into shell history and process listings.

Instead:
1. Read the secret from an environment variable or a secret manager and
   reference it by name — never inline the real value in a tracked file or on
   the command line.
2. If this is a placeholder, fixture, or documentation sample, name the file
   `*.example` / `*.sample`, place it under a `fixtures/` directory, or keep it
   in a Markdown/text doc — all of which are exempt.

Documentation files that merely *describe* a secret shape are exempt.
""".strip()

# Prose / documentation files that legitimately *show* a secret shape without
# introducing a real one. Mirrors block-slack-webhook.py.
DOC_PATH_RE = re.compile(r"\.(md|mdx|markdown|txt|rst)$", re.IGNORECASE)
# Placeholder / fixture files: example templates and test fixtures.
EXAMPLE_PATH_RE = re.compile(
    r"(\.example(\.[^./\\]+)?$|\.sample(\.[^./\\]+)?$|(^|/)(fixtures|__fixtures__)/)",
    re.IGNORECASE,
)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$")
PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$")


def looks_real(match: str) -> bool:
    """Filter out obvious placeholders among the alnum-run token matches.

    A real token mixes letters and digits and does not contain a placeholder
    word. PEM headers have no token body and always pass (handled by the caller,
    which only calls this for the alnum-run patterns)."""
    lowered = match.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return False
    body = match.split("_")[-1].split("-")[-1]
    has_alpha = any(c.isalpha() for c in body)
    has_digit = any(c.isdigit() for c in body)
    return has_alpha and has_digit


def find_secret(text: str) -> "str | None":
    """Return the human label of the first live-secret shape found, else None."""
    if not text:
        return None
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if label == "PEM private key":
            return label
        if looks_real(match.group(0)):
            return label
    return None


def main():
    input_data = normalize(json.load(sys.stdin))

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    text = extract_text(tool_name, tool_input)
    label = find_secret(text)
    if label:
        print(ERROR_MSG.format(label=label), file=sys.stderr)
        sys.exit(2)  # Exit code 2 blocks the tool call

    emit_allow()


def extract_text(tool_name: str, tool_input: dict) -> str:
    """Return the text to scan, depending on which tool is being used.

    Covers Bash commands (e.g. `export KEY=sk_live_...` or a heredoc writing a
    secret) and file mutations (Write/Edit/MultiEdit/apply_patch) that would add
    a secret to a tracked file. Unlike the guards that strip quoted spans to
    avoid flagging a *mentioned* flag, this guard scans the raw command: a live
    secret is almost always inside quotes, so stripping them would defeat the
    check. Documentation, example/fixture files, and this guard's own tooling
    are exempt on the file-write paths."""
    if tool_name == "Bash":
        return tool_input.get("command", "") or ""

    if tool_name == "apply_patch":
        return extract_apply_patch_additions(tool_input.get("command", "") or "")

    file_path = tool_input.get("file_path", "") or ""
    if is_exempt_path(file_path):
        return ""

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
    recognizable Codex patch, return it verbatim so the check fails closed for a
    secret-bearing mutation rather than silently bypassing it."""
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
    """Documentation, example/fixture, and hook-tooling exemptions."""
    if not file_path:
        return False
    normalized = "/" + file_path.replace("\\", "/").lstrip("/")
    return bool(
        DOC_PATH_RE.search(file_path)
        or EXAMPLE_PATH_RE.search(file_path)
        or "/hooks/" in normalized
        or "/scripts/" in normalized
    )


if __name__ == "__main__":
    main()
