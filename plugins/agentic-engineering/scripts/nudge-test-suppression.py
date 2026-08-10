#!/usr/bin/env python3
"""
PreToolUse (Bash + Write/Edit/MultiEdit) — NON-BLOCKING nudge away from
suppressing test signal instead of fixing it.

Two green-washing moves get a gentle reminder (never a block):

  1. A Bash command that lets a failing or empty run report success — the
     zero-tests escape hatch (`--passWithNoTests` and friends) or disabling a
     test-infra safety net (`TESTCONTAINERS_RYUK_DISABLED=`).
  2. A file mutation that *adds* a skipped/focused test to a test file
     (`it.skip` / `describe.only` / `xit`, a pytest/unittest skip decorator, a
     Go `t.Skip(`, a Rust `#[ignore]`). Skipping or focusing is the easy way to
     get a suite green while hiding a real failure.

Why a nudge and not a block: each of these has legitimate, reviewed uses (a spec
that genuinely cannot run in this environment, a temporary focus during
debugging). The plugin's testing stage wants the signal preserved, so this
surfaces the tradeoff without standing in the way. Prefer fixing the root cause
(make the test infra reachable, fix the glob, repair the failing spec) or
gating the skip explicitly and visibly over a bare `.skip`.

Never blocks: this hook only ever exits 0. Advisory output uses Claude Code's
`systemMessage` + `additionalContext` channel (this hook is wired on Claude
Code only, like nudge-todowrite-to-tracker.py).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import normalize, strip_quotes

# Bash commands that silence a failing or empty test run.
GREENWASH_CMD_RE = re.compile(
    r"--passWithNoTests\b"
    r"|--pass-with-no-tests\b"
    r"|--allowEmptyTestSuite\b"
    r"|\bTESTCONTAINERS_RYUK_DISABLED\s*=",
    re.IGNORECASE,
)

# Files whose content this guard treats as test code.
TEST_PATH_RE = re.compile(
    r"\.(test|spec)\.[cm]?[jt]sx?$"          # foo.test.ts / bar.spec.jsx
    r"|\.integration\.test\.[cm]?[jt]sx?$"
    r"|(^|/)__tests__/"                        # JS __tests__ dir
    r"|(^|/)test_[^/]*\.py$|_test\.py$"        # pytest / unittest
    r"|_test\.go$"                             # Go
    r"|(^|/)tests?/.*\.rs$",                   # Rust test modules
    re.IGNORECASE,
)

# Skipped/focused-test markers added to a test file.
SKIP_MARKER_RE = re.compile(
    r"\b(?:it|test|describe|context)\.(?:skip|only)\s*\("   # it.skip( / describe.only(
    r"|\bx(?:it|describe|test)\s*\("                         # xit( / xdescribe(
    r"|@(?:pytest\.mark\.skip(?:if)?|unittest\.skip(?:If|Unless)?)\b"
    r"|\bt\.Skip\s*\("                                        # Go
    r"|#\[ignore\]",                                          # Rust
)

CMD_MESSAGE = (
    "this command reaches for a test-suppression escape hatch "
    "(--passWithNoTests / disabling a test-infra safety net), which lets a "
    "failing or empty run report success. Prefer fixing the root cause — make "
    "the test infra reachable, fix the test glob — over silencing the signal."
)

SKIP_MESSAGE = (
    "this edit adds a skipped or focused test (it.skip / describe.only / xit / "
    "a skip decorator) to a test file. Skipping or focusing is an easy way to "
    "get a suite green while hiding a real failure. Prefer fixing the "
    "underlying failure, or gate the skip explicitly and visibly (a documented "
    "condition) rather than a bare .skip."
)

DOC_PATH_RE = re.compile(r"\.(md|mdx|markdown|txt|rst)$", re.IGNORECASE)


def _added_text(tool_name: str, tool_input: dict) -> str:
    """Content newly introduced by a file mutation (not context/removed)."""
    if tool_name == "Write":
        return tool_input.get("content", "") or ""
    if tool_name == "Edit":
        return tool_input.get("new_string", "") or ""
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", []) or []
        return "\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict))
    return ""


def resolve_message(tool_name: str, tool_input: dict) -> "str | None":
    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        # Strip quoted spans / comments so a *mentioned* flag (an echo, a
        # comment) does not nudge — only a flag actually in the command does.
        scan = strip_quotes(command)
        scan = re.sub(r"#.*", "", scan)
        return CMD_MESSAGE if GREENWASH_CMD_RE.search(scan) else None

    if tool_name in ("Write", "Edit", "MultiEdit"):
        file_path = tool_input.get("file_path", "") or ""
        normalized = "/" + file_path.replace("\\", "/").lstrip("/")
        if DOC_PATH_RE.search(file_path) or "/hooks/" in normalized or "/scripts/" in normalized:
            return None  # a doc or this guard's own tooling naming the pattern
        if not TEST_PATH_RE.search(file_path):
            return None
        return SKIP_MESSAGE if SKIP_MARKER_RE.search(_added_text(tool_name, tool_input)) else None

    return None


def _main() -> int:
    try:
        payload = normalize(json.load(sys.stdin))
    except ValueError:
        return 0

    message = resolve_message(payload.get("tool_name", ""), payload.get("tool_input", {}))
    if not message:
        return 0

    print(json.dumps({
        "systemMessage": f"Reminder: {message}",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": f"Non-blocking reminder: {message} Proceeding with the call.",
        },
    }))
    return 0


def main() -> int:
    # Contract: this hook only ever exits 0. A broken nudge must never block a
    # legitimate test command or edit.
    try:
        return _main()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
