#!/usr/bin/env python3
"""
PreToolUse (TodoWrite) — NON-BLOCKING nudge toward the repo's durable issue
tracker. Reuses the exact resolution chain workflow-repo-preflight.py already
establishes (local override > committed board config -> github-project,
otherwise "unconfigured"), so the reminder always names the tracker the rest
of the plugin's lifecycle tooling agrees on.

Silent (exit 0, no output) unless BOTH:
  - the repo has opted in via `nudge_todowrite: true` in
    `agentic-engineering.local.md` frontmatter (off by default — not every
    repo has a configured tracker, and the reminder would be noise otherwise)
  - a tracker actually resolves (an unconfigured repo has nothing to nudge
    toward — TodoWrite stays ephemeral in-session scratch until the wf-setup
    lifecycle bootstrap configures a board)

Under the unified lifecycle GitHub is the sole authoritative tracker; beads is
a non-authoritative scratchpad and is therefore not a nudge target here.

Never blocks: this hook only ever exits 0.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

_PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "workflow_repo_preflight",
    pathlib.Path(__file__).resolve().with_name("workflow-repo-preflight.py"),
)
assert _PREFLIGHT_SPEC is not None and _PREFLIGHT_SPEC.loader is not None
preflight = importlib.util.module_from_spec(_PREFLIGHT_SPEC)
sys.modules["workflow_repo_preflight"] = preflight
_PREFLIGHT_SPEC.loader.exec_module(preflight)

lifecycle_board = preflight.lifecycle_board

LOCAL_CONFIG_NAME = "agentic-engineering.local.md"

MESSAGES = {
    "github-project": (
        "this repo tracks durable, cross-session work on its GitHub Project "
        "board. TodoWrite is fine for ephemeral in-session steps — file "
        "anything that should outlive this session with `gh issue create` "
        "(it joins the board automatically)."
    ),
}


def _git_ok(args: "list[str]") -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def nudge_opted_in(repo_root: str) -> bool:
    """Read `nudge_todowrite: true` from the local config frontmatter.

    Security invariant (same gate as issue_tracker/board config): a
    `.local.md` that is *tracked* in git would ride a PR, letting the PR
    silently turn the nudge on/off for every clone. A tracked copy is
    ignored, so opt-in falls back to off.
    """
    config_path = pathlib.Path(repo_root) / LOCAL_CONFIG_NAME
    if not config_path.is_file():
        return False
    tracked = subprocess.run(
        ["git", "-C", repo_root, "ls-files", "--error-unmatch", config_path.name],
        text=True, capture_output=True,
    )
    if tracked.returncode == 0:
        return False
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return False
    meta = lifecycle_board.parse_frontmatter(text)
    return meta.get("nudge_todowrite", "").strip().lower() == "true"


def resolve_message(repo_root: str) -> "str | None":
    board = None
    try:
        board_ctx = lifecycle_board.repo_context()
        board = lifecycle_board.read_board_config(board_ctx)
    except lifecycle_board.BoardError:
        board = None

    tracker_info = preflight.resolve_issue_tracker(
        repo_root=repo_root,
        board_configured=board is not None,
    )
    return MESSAGES.get(tracker_info["resolved"])


def _main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}

    if payload.get("tool_name") != "TodoWrite":
        return 0

    repo_root = _git_ok(["rev-parse", "--show-toplevel"])
    if not repo_root or not nudge_opted_in(repo_root):
        return 0

    message = resolve_message(repo_root)
    if not message:
        return 0

    print(json.dumps({
        "systemMessage": f"Reminder: {message}",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": f"Non-blocking reminder: {message} Proceeding with TodoWrite.",
        },
    }))
    return 0


def main() -> int:
    # Contract: this hook only ever exits 0, no matter what goes wrong
    # (e.g. a non-UTF-8 byte in a config file raising UnicodeDecodeError
    # deep in a reused helper) — a broken nudge must never block TodoWrite.
    try:
        return _main()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
