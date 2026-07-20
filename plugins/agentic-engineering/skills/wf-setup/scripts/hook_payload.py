#!/usr/bin/env python3
"""Normalize hook stdin payloads across Claude Code, Cursor, and Codex.

Safety scripts use a common `tool_name` + `tool_input` envelope. Cursor's
`beforeShellExecution` sends a top-level `command`, and Cursor `preToolUse`
uses `tool_name: "Shell"` instead of `"Bash"`. Codex uses the same envelope,
but preserves canonical tool names such as `apply_patch` and supplies that
tool's patch text as `tool_input.command`.

Output is normalized too, via `emit_allow()`. Cursor's `beforeShellExecution`
(and `preToolUse`) hooks require a JSON `{"permission": "allow"}` decision on
stdout to allow a call; under `failClosed: true` an empty stdout is treated as a
failure and *blocks*. Emitting the allow JSON unconditionally is safe on every
platform: Claude Code parses stdout only on exit 0 and ignores fields outside
its own schema (`hookSpecificOutput.permissionDecision`), so `permission` is
inert there and exit 0 already means allow; Codex uses the same exit-code model.
So a single shared emitter works everywhere — no per-platform branching.
"""
from __future__ import annotations

import json
import sys


def normalize(data: dict) -> dict:
    """Return a Claude-shaped hook payload dict."""
    if not isinstance(data, dict):
        return {"tool_name": "", "tool_input": {}}

    # Cursor beforeShellExecution / afterShellExecution
    if "tool_input" not in data and isinstance(data.get("command"), str):
        return {
            "tool_name": "Bash",
            "tool_input": {"command": data["command"]},
        }

    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool_name == "Shell":
        tool_name = "Bash"

    out = dict(data)
    out["tool_name"] = tool_name
    out["tool_input"] = tool_input
    return out


def emit_allow() -> None:
    """Allow the tool call and exit 0.

    Prints Cursor's required `{"permission": "allow"}` decision on stdout so a
    `failClosed: true` Cursor hook does not treat the empty-stdout allow path as
    a failure and block. Harmless on Claude Code / Codex (see module docstring).
    Terminates the process — like `sys.exit(0)`, it does not return.
    """
    print(json.dumps({"permission": "allow"}))
    sys.exit(0)
