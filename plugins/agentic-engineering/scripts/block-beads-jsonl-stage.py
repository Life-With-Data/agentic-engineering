#!/usr/bin/env python3
"""
Claude Code hook to block staging the gitignored beads JSONL exports.

Projects that use the `beads` (`bd`) issue tracker keep their source of truth
in a local Dolt DB. `.beads/issues.jsonl`, `.beads/interactions.jsonl`, and
`.beads/events.jsonl` are passive exports that `bd` regenerates on every
mutation — they are meant to stay untracked/gitignored. Committing them
produces constant working-tree churn, since every `bd` command rewrites them.

A plain `git add .beads/issues.jsonl` already fails via .gitignore, but the
error ("paths are ignored") is cryptic, and a force-add (`git add -f`) would
silently re-track the files and reintroduce that churn. This hook turns that
into a clear, actionable block, regardless of which project installs the
plugin.
"""
import json
import re
import sys

# Matches an explicit beads export path on a `git add` command.
BEADS_EXPORT = re.compile(r"\.beads/(?:issues|interactions|events)\.jsonl\b")
GIT_ADD = re.compile(r"\bgit\s+add\b")

ERROR_MSG = """
❌ BLOCKED: Don't stage the beads JSONL exports.

`.beads/{issues,interactions,events}.jsonl` are gitignored, auto-regenerated
exports — `bd` rewrites them on every mutation. Tracking them produces
constant working-tree churn, so they should stay untracked.

To share bead state, sync the Dolt DB instead:
    bd dolt push      # publish your changes
    bd dolt pull      # receive others' changes

If these files are dirty in your working tree, that's expected — leave them
untracked. Do NOT force-add them (`git add -f`); that reintroduces the churn.
""".strip()


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
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
