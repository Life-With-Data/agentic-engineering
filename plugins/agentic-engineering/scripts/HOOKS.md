# Plugin Hooks

Installing the **agentic-engineering** plugin activates a small set of Claude
Code hooks (wired in [`.claude-plugin/plugin.json`](../.claude-plugin/plugin.json)).
They are safety nets that keep the compounding-engineering workflow — plan →
work → PR → review → merge — from being short-circuited. They fire
automatically; there is nothing to configure.

This page explains what each hook does, why it exists, and how to test or
disable it.

## `block-no-verify.py` — PreToolUse (Bash)

**Blocks** `git commit`/`git push` that carry `--no-verify` (or the `-n` short
form on commit).

**Why:** Pre-commit / pre-push hooks catch formatting, lint, and test failures
before they reach CI. Bypassing them trades a few seconds now for a red CI run,
extra fix-up commits, and wasted CI minutes later. The plugin's value compounds
through quality gates that run every time — `--no-verify` breaks that chain.

**Precision:** It fires only when `git commit`/`git push` is the actual command
verb bypassing verification. Commands that merely *mention* the flag — a quoted
commit message, a shell comment, `grep -- --no-verify`, `echo` — are **not**
blocked. It is also segment-aware: the flag must sit in the same command segment
as the git verb, so `git commit -m ok && echo --no-verify` is allowed.

**If checks are failing:** fix the root cause, or fix the hook — don't bypass.

## `prevent-main-commit.py` — PreToolUse (Bash)

**Blocks** a `git commit` while the current branch is `main`/`master`, and an
explicit `git push` whose refspec targets `main`/`master`
(`git push origin main`, `git push origin HEAD:main`, …).

**Why:** Work should land via a feature branch and a PR, so code review, CI, and
the `land-pr` flow apply. Committing straight to `main` skips all three.

**Precision:** Quoted commit messages can't false-trigger it (a message
mentioning "merge main" is fine), and a branch merely *named* like `main`
(e.g. `main-feature`) is not treated as the protected branch.

**Correct alternative:** `git checkout -b <type>/<description>`, then open a PR.

## `plan-tracker-guard.py` — Stop

**Blocks** turn termination if a plan file (`docs/plans/*.md`) modified during
the session lacks a tracker ID (`bead_id` / `linear_issue` / `github_issue`) in
its YAML frontmatter — unless the plan opts out with `issue_tracker: none`.

**Why:** Plans that aren't linked to a tracked issue get orphaned. This keeps
`/workflows:plan` output connected to whatever issue tracker the repo uses.

## Testing hooks

Each PreToolUse hook reads a JSON payload on stdin and signals its decision via
exit code (`0` allows, `2` blocks). Drive one directly:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify"}}' \
  | python3 scripts/block-no-verify.py; echo "exit: $?"   # exit: 2 (blocked)
```

Automated regression tests live in [`../tests/`](../tests) and run in CI via
`python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'`:

- [`block_no_verify_test.py`](../tests/block_no_verify_test.py)
- [`prevent_main_commit_test.py`](../tests/prevent_main_commit_test.py)
- [`plan_tracker_guard_test.py`](../tests/plan_tracker_guard_test.py)

These pin the tricky false-positive / false-negative edges (prose that mentions
a flag, chained command segments, branches named like `main`) so the regex
guards can't silently regress.

## Disabling a hook

These hooks are intentionally conservative and should rarely need disabling. If
one is genuinely in the way (e.g. a hook itself is broken), override it in your
project's `.claude/settings.local.json` rather than editing the plugin, so your
change survives plugin updates.
