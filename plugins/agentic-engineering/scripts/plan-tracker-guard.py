#!/usr/bin/env python3
"""Stop-hook safety net: block turn termination if any plan file modified in
this session lacks a tracker ID (``github_issue``) in its YAML frontmatter,
unless the plan explicitly opts out with ``issue_tracker: none``.

Under the unified lifecycle, GitHub is the sole authoritative tracker; beads is
demoted to a non-authoritative scratchpad, so ``bead_id`` is no longer a valid
tracker ID for plans.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Final, Iterator

TRACKER_FIELDS: Final = ("github_issue",)
PLAN_PATH_RE: Final = re.compile(r"(?:^|/)docs/plans/[^/]+\.md$")
EDIT_TOOLS: Final = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
FRONTMATTER_FENCE_RE: Final = re.compile(r"^---[ \t]*$", re.MULTILINE)
# A real ``github_issue`` value is either a bare issue number or a qualified
# ``owner/repo#N`` reference:
#   - <digits>                     e.g. 42 (bare issue number)
#   - <owner>/<repo>#<digits>      e.g. org/repo#42 (qualified form)
# Bare digits keep template placeholders like "github_issue: NNN" rejected
# (non-numeric → no match).
REAL_TRACKER_VALUE_RE: Final = re.compile(
    r"^(\d+"
    r"|[\w.-]+/[\w.-]+#\d+)$"
)
# Inline comments only count when '#' is preceded by whitespace — otherwise
# legitimate values like ``github_issue: org/repo#42`` get truncated.
INLINE_COMMENT_RE: Final = re.compile(r"\s+#.*$")
# Strip ANSI escapes and other control chars from paths before echoing to the
# user-visible block reason. Allow tab/newline (paths can't have those).
CONTROL_CHAR_RE: Final = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _walk_tool_uses(record: object) -> Iterator[dict]:
    """Yield tool_use blocks from a transcript record.

    Real Claude Code transcripts nest blocks at ``message.content[i]`` with
    ``type == "tool_use"``, but the parent shape varies across transcript
    versions (some have ``message`` at top level, others nest one deeper).
    We check the common path first and fall back to a generic scan only on
    miss so the hook survives schema drift.
    """
    if isinstance(record, dict):
        msg = record.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list):
                yield from _filter_tool_uses(content)
                return
        # Fallback: scan all values recursively. Only reached if the common
        # path missed, so the cost is paid only on schema drift.
        for value in record.values():
            yield from _walk_tool_uses(value)
    elif isinstance(record, list):
        yield from _filter_tool_uses(record)


def _filter_tool_uses(blocks: list) -> Iterator[dict]:
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield block


def load_transcript_paths(transcript_path: str) -> list[str]:
    """Return ordered, de-duplicated plan paths touched by edit tools."""
    paths: dict[str, None] = {}
    if not transcript_path or not os.path.exists(transcript_path):
        return []
    try:
        with Path(transcript_path).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for block in _walk_tool_uses(record):
                    if block.get("name") not in EDIT_TOOLS:
                        continue
                    inp = block.get("input") or {}
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if isinstance(fp, str) and PLAN_PATH_RE.search(fp):
                        paths.setdefault(fp, None)
    except OSError as exc:
        print(f"plan-tracker-guard: cannot read transcript: {exc}", file=sys.stderr)
    return list(paths)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse leading ``---`` YAML frontmatter into a flat string dict.

    Only handles ``key: value`` scalars — sufficient because all tracker
    fields and the ``issue_tracker`` carve-out are scalars. Returns ``{}``
    when no proper fenced block exists.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}
    # Find a closing fence that occupies its own line; skip the opening fence.
    match = FRONTMATTER_FENCE_RE.search(text, pos=4)
    if not match:
        return {}
    body = text[3 : match.start()]
    out: dict[str, str] = {}
    for line in body.splitlines():
        line = INLINE_COMMENT_RE.sub("", line).rstrip()
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
        if value and REAL_TRACKER_VALUE_RE.match(value):
            return True
    return False


def is_none_carveout(meta: dict[str, str]) -> bool:
    # Accept the YAML-ish null aliases for parity with hand-edited frontmatter.
    return meta.get("issue_tracker", "").strip().lower() in {"none", "null", "~"}


def safe_path_for_reason(path: str) -> str:
    return CONTROL_CHAR_RE.sub("?", path)


def is_safe_plan_path(path: str) -> bool:
    """Reject paths that resolve outside ``cwd/docs/plans`` or are symlinks.

    The transcript can carry attacker-influenced paths (a compromised tool
    call could record ``../../../../etc/passwd.md`` and the regex's suffix
    match would still pass). Containment plus symlink rejection keeps the
    blast radius bounded to the workspace's plan directory.
    """
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if Path(path).is_symlink():
        return False
    plans_dir = (Path.cwd() / "docs" / "plans").resolve()
    try:
        return resolved.is_relative_to(plans_dir)
    except AttributeError:
        # is_relative_to landed in 3.9 — should always exist in supported
        # Pythons, but degrade gracefully.
        try:
            resolved.relative_to(plans_dir)
            return True
        except ValueError:
            return False


def evaluate(paths: list[str]) -> list[str]:
    """Return a list of plan paths that need a tracker ID but don't have one."""
    problems: list[str] = []
    for path in paths:
        if not is_safe_plan_path(path):
            print(
                f"plan-tracker-guard: skipping unsafe path {safe_path_for_reason(path)!r}",
                file=sys.stderr,
            )
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"plan-tracker-guard: cannot read {safe_path_for_reason(path)!r}: {exc}",
                file=sys.stderr,
            )
            continue
        meta = parse_frontmatter(text)
        if has_tracker_id(meta) or is_none_carveout(meta):
            continue
        problems.append(path)
    return problems


REMEDIATION = (
    "Refusing to end turn — the following plan files lack a tracker ID "
    "in their YAML frontmatter (github_issue):\n\n"
    "{listing}\n\n"
    "Fix each file by either:\n"
    "  (a) Creating a GitHub issue and writing the ID into the frontmatter:\n"
    "        gh issue create --title '<t>' --body-file <plan-path>\n"
    "                   → set 'github_issue: <N>'\n"
    "  (b) OR setting 'issue_tracker: none' in the frontmatter to opt out\n"
    "      (the documented un-tracked carve-out).\n"
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        # json.JSONDecodeError is a subclass of ValueError.
        payload = {}

    if payload.get("stop_hook_active"):
        return 0

    plan_paths = load_transcript_paths(payload.get("transcript_path") or "")
    if not plan_paths:
        return 0

    problems = evaluate(plan_paths)
    if not problems:
        return 0

    listing = "\n".join(f"  - {safe_path_for_reason(p)}" for p in problems)
    reason = REMEDIATION.format(listing=listing)
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
