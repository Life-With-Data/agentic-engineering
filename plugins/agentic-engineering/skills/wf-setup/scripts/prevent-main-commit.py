#!/usr/bin/env python3
"""
Claude Code hook to block direct commits to the main branch.

The agentic-engineering workflow is PR-based (plan → work → PR → review →
merge). Never commit directly to `main`/`master` — branch off and open a PR so
code review, CI, and the `land-pr` flow apply.

Push policy is deliberately NOT enforced here. A client-side refspec check
decides from the shape of the phrasing rather than from what the push would
actually do: it blocks `git push origin main` while `git push` and
`git push --force origin HEAD` from `main` do the same thing and pass. It also
blocks `git push origin main`, which is a required step of the delivery
lifecycle on forges without a PR flow. Push and force-push policy belongs on
the server, where it binds every client, identity, and phrasing — buzz
(`buzz repos protect set --ref refs/heads/main --push owner --no-force-push`)
and GitHub rulesets both own it.

The commit rule below decides from live branch state rather than from the
command's stated target, so rewording the refspec cannot get around it. It is
not airtight against every spelling of the verb itself: global git options
between the words (`git -c x=y commit`, `git --no-pager commit`) are not
matched today. See issue #364, tracking parity with
`block-no-verify.py`'s sanitizer.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import emit_allow, normalize, strip_quotes

PROTECTED_BRANCHES = {"main", "master"}


def main():
    input_data = normalize(json.load(sys.stdin))

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if tool_name != "Bash":
        emit_allow()

    stripped = strip_quotes(command)

    if re.search(r"\bgit\s+commit\b", stripped) is None:
        emit_allow()

    branch = current_branch()

    if branch in PROTECTED_BRANCHES:
        block(
            f"Direct commit to `{branch}` is not allowed.",
            "Branch off and open a PR instead:",
            "  git checkout -b <type>/<description>",
        )

    emit_allow()


def current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def block(*lines: str):
    msg = ["", "❌ BLOCKED: " + lines[0], ""]
    msg.extend(lines[1:])
    msg.append("")
    print("\n".join(msg), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
