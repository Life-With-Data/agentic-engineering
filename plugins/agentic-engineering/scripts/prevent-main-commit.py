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
command's stated target, so rewording the refspec cannot get around it.

The branch is read in the repository the commit will actually run in, not in
the hook process's own working directory. Claude Code starts hooks in the
project root, so a session that works in a linked worktree (or `cd`s into one)
would otherwise be judged by the main checkout's branch. The target is resolved
per command segment, starting from the payload `cwd`: a leading `cd <dir>`
moves it, and git's own global options (`-C <dir>`, `--git-dir=...`,
`-c x=y`, `--no-pager`) are passed through to the branch query, so git itself
decides which repository they name.
"""
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import emit_allow, normalize, strip_heredocs, strip_quotes

PROTECTED_BRANCHES = {"main", "master"}

# git's global options that take their value as the *next* word. This is git's
# own fixed grammar (see `git --help`), not a list of phrasings to catch: any
# other dash option is skipped as a flag, so an unlisted flag still matches.
GIT_OPTIONS_WITH_VALUE = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
    "--super-prefix",
}
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def main():
    input_data = normalize(json.load(sys.stdin))

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if tool_name != "Bash":
        emit_allow()

    cwd = input_data.get("cwd") or os.getcwd()

    for directory, git_options in commit_targets(command, cwd):
        branch = current_branch(directory, git_options)
        if branch in PROTECTED_BRANCHES:
            block(
                f"Direct commit to `{branch}` is not allowed.",
                "Branch off and open a PR instead:",
                "  git checkout -b <type>/<description>",
            )

    emit_allow()


def commit_targets(command: str, cwd: str) -> list[tuple[str, list[str]]]:
    """Return `(directory, git global options)` for every `git commit` in
    `command`, tracking `cd` across segments so each commit is judged where it
    runs."""
    command = strip_heredocs(command).replace("\\\n", " ").replace("\n", " ; ")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        # Unbalanced quotes: fall back to a plain match judged in `cwd`.
        if re.search(r"\bgit\s+(?:-\S+\s+)*commit\b", strip_quotes(command)):
            return [(cwd, [])]
        return []

    targets = []
    segment: list[str] = []
    for token in tokens + [";"]:
        if token not in SEPARATORS:
            segment.append(token)
            continue
        while segment and ENV_ASSIGNMENT.match(segment[0]):
            segment.pop(0)
        if segment[:1] == ["cd"]:
            cwd = change_directory(cwd, segment[1:])
        else:
            # Any `git` word, not only the first, so wrappers such as `time`,
            # `sudo`, or `xargs` in front of the verb still count.
            for i, word in enumerate(segment):
                if word == "git" or word.endswith("/git"):
                    git_options = commit_options(segment[i + 1:])
                    if git_options is not None:
                        targets.append((cwd, git_options))
        segment = []
    return targets


def change_directory(cwd: str, args: list[str]) -> str:
    args = [a for a in args if a not in ("-L", "-P", "--")]
    if not args:
        return os.path.expanduser("~")
    if args[0] == "-":
        return cwd  # previous directory is unknown; stay put
    return os.path.join(cwd, os.path.expanduser(args[0]))


def commit_options(args: list[str]) -> list[str] | None:
    """If `git <args>` is a commit, return the global options before the verb;
    otherwise None."""
    options = []
    i = 0
    while i < len(args) and args[i].startswith("-"):
        options.append(args[i])
        if args[i] in GIT_OPTIONS_WITH_VALUE and i + 1 < len(args):
            options.append(args[i + 1])
            i += 1
        i += 1
    if i < len(args) and args[i] == "commit":
        return options
    return None


def current_branch(directory: str, git_options: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *git_options, "branch", "--show-current"],
            cwd=directory,
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
