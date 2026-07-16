#!/usr/bin/env python3
"""Normalize hook stdin payloads across Claude Code, Cursor, and Codex.

Safety scripts use a common `tool_name` + `tool_input` envelope. Cursor's
`beforeShellExecution` sends a top-level `command`, and Cursor `preToolUse`
uses `tool_name: "Shell"` instead of `"Bash"`. Codex uses the same envelope,
but preserves canonical tool names such as `apply_patch` and supplies that
tool's patch text as `tool_input.command`.
"""
from __future__ import annotations


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
