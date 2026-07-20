#!/usr/bin/env python3
"""
Claude Code hook to block staging the Beads JSONL exports.

`.beads/issues.jsonl`, `.beads/interactions.jsonl`, and `.beads/events.jsonl`
are passive exports that `bd` regenerates on every mutation. When Beads is the
active issue tracker, committing them produces constant working-tree churn —
every `bd create`/`bd update`/`bd close` rewrites the file — so they should be
gitignored and shared via `bd dolt push`, not git. The source of truth is the
Dolt DB.

A plain `git add .beads/issues.jsonl` already fails via .gitignore, but the
error ("paths are ignored") is cryptic, and a force-add (`git add -f`) would
silently re-track the files and resurrect the churn. This hook turns that into
a clear, actionable block.

The agentic-engineering workflow treats Beads as a first-class tracker
(the `wf-grooming` planning route writes `bead_id:`, the `wf-development` work route runs `bd ready`/`bd
close`, the `wf-review` comprehensive-review route files findings as beads). This guard protects that
integration from the JSONL-churn footgun.

Design notes:
- Only fires when `git add` is the actual command verb AND an explicit beads
  export path is named, so prose that merely *mentions* the paths (docs,
  echoes, quoted commit messages) is NOT blocked.
- Ignores `git add -A` / `git add .` (gitignore already excludes the exports)
  and tracked config like `.beads/config.yaml` — only the passive JSONL exports
  are guarded.
"""
import json
import re
import sys

# Matches an explicit beads export path on a `git add` command.
BEADS_EXPORT = re.compile(r"\.beads/(?:issues|interactions|events)\.jsonl\b")
GIT_ADD = re.compile(r"\bgit\s+add\b")

ERROR_MSG = """
❌ BLOCKED: Don't stage the Beads JSONL exports.

`.beads/{issues,interactions,events}.jsonl` are gitignored, auto-regenerated
exports — bd rewrites them on every mutation. Tracking them produces constant
working-tree churn, so they should stay untracked.

To share bead state, sync the Dolt DB instead:
    bd dolt push      # publish your changes
    bd dolt pull      # receive others' changes

If these files are dirty in your working tree, that's expected — leave them
untracked. Do NOT force-add them (`git add -f`); that re-introduces the churn.
""".strip()


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")
    cleaned = sanitize(command)

    if GIT_ADD.search(cleaned) and BEADS_EXPORT.search(cleaned):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)  # Exit code 2 blocks the command

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
