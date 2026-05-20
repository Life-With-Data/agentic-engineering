#!/usr/bin/env python3
"""Stop-hook safety net: block turn termination if any plan file modified in this
session is missing a tracker ID in its YAML frontmatter.

A plan is a markdown file under ``docs/plans/`` (recursively, but in practice flat).
A tracker ID is one of ``bead_id``, ``linear_issue``, or ``github_issue``.

The hook reads its input JSON from stdin (per Claude Code hook contract), inspects
the session transcript for Write/Edit/MultiEdit/NotebookEdit tool calls that
touched plan files, then validates each file's frontmatter. If any file is
unfaithful to the contract, the hook emits a ``decision: block`` payload so the
agent re-runs Step 7 of ``/workflows:plan`` before exiting the turn.

If ``stop_hook_active`` is true the hook short-circuits to avoid infinite loops.
Tracker resolution mode is read indirectly: if frontmatter says ``issue_tracker:
none`` (explicit carve-out from Step 7), the file is allowed through.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

TRACKER_FIELDS = ("bead_id", "linear_issue", "github_issue")
PLAN_PATH_RE = re.compile(r"(?:^|/)docs/plans/[^/]+\.md$")
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def load_transcript_paths(transcript_path: str) -> list[str]:
    """Return the set of plan file paths touched by edit tools in the transcript."""
    seen: list[str] = []
    if not transcript_path or not os.path.exists(transcript_path):
        return seen

    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # tool_use entries can live a few places depending on transcript
                # version; scan recursively for any dict with name+input.
                for candidate in _walk(record):
                    if not isinstance(candidate, dict):
                        continue
                    name = candidate.get("name")
                    if name not in EDIT_TOOLS:
                        continue
                    inp = candidate.get("input") or {}
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if not fp or not isinstance(fp, str):
                        continue
                    if PLAN_PATH_RE.search(fp) and fp not in seen:
                        seen.append(fp)
    except OSError:
        pass
    return seen


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the leading ``---`` YAML frontmatter block into a flat str dict.

    Minimal parser — only ``key: value`` lines, ignores quoting/nesting since
    tracker fields are always scalars. Returns empty dict if no frontmatter.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    out: dict[str, str] = {}
    for line in block.splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def has_tracker_id(meta: dict[str, str]) -> bool:
    for field in TRACKER_FIELDS:
        value = meta.get(field, "").strip()
        if not value:
            continue
        # Skip template placeholders like ``bd-NNN`` / ``ENG-NNN`` / ``123``.
        if value.endswith("-NNN") or value == "123":
            continue
        return True
    return False


def is_none_carveout(meta: dict[str, str]) -> bool:
    return meta.get("issue_tracker", "").strip().lower() == "none"


def evaluate(paths: list[str]) -> list[str]:
    """Return a list of human-readable problems."""
    problems: list[str] = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            # File deleted or unreadable — skip silently.
            continue
        meta = parse_frontmatter(text)
        if has_tracker_id(meta) or is_none_carveout(meta):
            continue
        problems.append(path)
    return problems


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    if payload.get("stop_hook_active"):
        return 0

    transcript_path = payload.get("transcript_path") or ""
    plan_paths = load_transcript_paths(transcript_path)
    if not plan_paths:
        return 0

    problems = evaluate(plan_paths)
    if not problems:
        return 0

    listing = "\n".join(f"  - {p}" for p in problems)
    reason = (
        "Refusing to end turn: the following plan files were created or modified "
        "this session but have no tracker ID in their YAML frontmatter "
        "(bead_id / linear_issue / github_issue). Run Step 7 of /workflows:plan "
        "to create a tracker issue and write the ID back to the plan, or set "
        "`issue_tracker: none` in the frontmatter if the un-tracked carve-out is "
        "intentional.\n\n"
        f"{listing}"
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
