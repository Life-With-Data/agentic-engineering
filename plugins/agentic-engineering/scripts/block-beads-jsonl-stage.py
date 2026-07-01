#!/usr/bin/env python3
"""
Claude Code hook to block staging the gitignored beads JSONL exports.

`.beads/issues.jsonl`, `.beads/interactions.jsonl`, and `.beads/events.jsonl` are passive
exports that the `bd` CLI regenerates on every mutation whenever a project uses beads as its
issue tracker (see `workflow-repo-preflight.py` tracker detection and the `land-pr` / `work`
skills' beads bindings). Tracking them produces constant working-tree churn, so beads projects
deliberately gitignore them — the source of truth is the Dolt DB, synced via `bd dolt push`,
not git.

A plain `git add` of these paths already fails via `.gitignore`, but the error is cryptic, and
a force-add (`git add -f`) would silently re-track the files and reintroduce that churn. This
hook turns that into a clear, actionable block. It only fires when the exports actually exist
under `.beads/`, so it is a no-op for the majority of projects that don't use beads.
"""
import json
import re
import sys
from pathlib import Path

BEADS_EXPORT = re.compile(r"\.beads/(?:issues|interactions|events)\.jsonl\b")
GIT_ADD = re.compile(r"\bgit\s+add\b")

ERROR_MSG = """
❌ BLOCKED: Don't stage the beads JSONL exports.

`.beads/{issues,interactions,events}.jsonl` are gitignored, auto-regenerated exports — `bd`
rewrites them on every mutation. Tracking them produces constant working-tree churn, so they
are untracked on purpose.

To share bead state, sync the Dolt DB instead:
    bd dolt push      # publish your changes
    bd dolt pull      # receive others' changes

If these files are dirty in your working tree, that's expected — leave them untracked. Do NOT
force-add them (`git add -f`); that re-introduces the churn.
""".strip()


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    if not any(Path(f".beads/{name}.jsonl").exists() for name in ("issues", "interactions", "events")):
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")
    cleaned = sanitize(command)

    if GIT_ADD.search(cleaned) and BEADS_EXPORT.search(cleaned):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


def sanitize(command: str) -> str:
    """Strip quoted strings and comments so prose mentioning these paths
    (docs, echoes, commit messages) can't false-trigger."""
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    command = re.sub(r"#.*", "", command)
    return command


if __name__ == "__main__":
    main()
