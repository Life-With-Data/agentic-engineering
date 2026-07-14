---
title: "Grep-based 'zero references remain' checks and subset fixtures both give false confidence"
category: testing-patterns
tags: [migration, rename, cross-reference-sweep, grep, fixtures, false-confidence, plugin, opencode]
module: plugins/agentic-engineering, src/parsers/claude.ts, src/converters/claude-to-opencode.ts
symptom: "Two independently-written 'zero references remain' greps both passed clean while 9 stale references shipped; a converter test stayed green whether or not its own fix was reverted"
root_cause: "The grep was scoped by file extension and anchored to literal known names; the fixture's new-source contribution was a strict subset of its old-source contribution, so neither check could distinguish fix-present from fix-absent"
---

# Grep-Based Acceptance Checks and Subset Fixtures Give False Confidence

## Problem

A large migration (PR #146, issue #134) moved 28 command files into 27 skills and hard-cut over
`plugins/agentic-engineering/commands/` → `skills/<name>/SKILL.md`, renaming the 8 `workflows:*`
commands to hyphenated `workflows-*` skills. A dedicated sub-issue (#139) existed solely to sweep
every internal reference to the old names, with a grep-based acceptance criterion:

```bash
grep -r "workflows:plan\|workflows:groom\|workflows:work\|workflows:brainstorm\|workflows:compound\|workflows:merge\|workflows:orchestrate\|workflows:review\|generate_command\|resolve_parallel\|resolve_todo_parallel" \
  plugins/agentic-engineering/skills plugins/agentic-engineering/agents --include=*.md
```

This grep passed clean. The orchestrating session ran its *own* confirming grep before opening the
PR, using the same shape, and it also passed clean. The PR body claimed "grep-verified zero
remaining references." All of this was true of what the grep actually checked — and false of the
repository.

An independent `acceptance-criteria-reviewer` subagent, diffing the PR against every file type (not
just markdown), found **9 leftover references** in two more passes:

- `.py` scripts and tests entirely outside the swept directories: `scripts/block-beads-jsonl-stage.py`,
  `scripts/config_registry.py` (×2), `scripts/workflow-repo-preflight.py`, `scripts/lifecycle_board.py`,
  `tests/plan_tracker_guard_test.py`.
- A generated docs page: `docs/pages/getting-started.html` (a stale `/resolve_todo_parallel` example
  and a dangling link to a command that was deleted, not renamed).
- Prose *inside* the swept `.md` files that the literal-name regex couldn't match: generic references
  like `` `/workflows:*` `` describing "all workflow commands" (`skills/workflows-orchestrate/SKILL.md`,
  `skills/setup/SKILL.md`), and a copy-paste typo `/workflows:deepen-plan` that had never been a real
  command name (the real command was always `/deepen-plan`, no `workflows:` prefix — so it wasn't in
  the rename table for the literal grep to catch either).

Separately, an `integration-boundary-reviewer` subagent found that the one test exercising the real
parser+converter pipeline together (`tests/converter.test.ts`) could not detect a regression in the
PR's own OpenCode permission-derivation fix. The fix makes `applyPermissions()` also read
`skill.allowedTools` in addition to `command.allowedTools` (additive merge, so a skills-only plugin
stops silently degrading to an all-deny permission set). But the fixture skill's `allowed-tools`
(`Read, Edit, Bash(git:*)`) was a strict **subset** of the fixture command's — so the test's
assertions passed identically whether the merge logic was present or silently reverted.

## Solution

**For the grep, two independent scoping failures were fixed at once:**

```bash
# BAD — extension-restricted, directory-restricted, anchored to a finite literal-name list:
grep -r "workflows:plan\|...\|resolve_todo_parallel" \
  plugins/agentic-engineering/skills plugins/agentic-engineering/agents --include=*.md

# GOOD — no extension filter, full repo, plus a broader bare-namespace pass that
# catches prose/glob references and typos the literal-name list can't anticipate:
grep -rn "workflows:plan\|workflows:groom\|...\|resolve_todo_parallel" .
grep -rn "workflows:" . | grep -v "workflows-"
```

`git grep <pattern>` is a good default here too — it walks every tracked file without an
extension assumption baked in, unlike a hand-rolled `grep --include=*.ext`.

**For the fixture**, the fix was to give the new source (`skills`) a fixture value the old source
(`commands`) could not produce, then verify the new assertion is load-bearing rather than incidental:

```diff
 # tests/fixtures/sample-plugin/skills/tooled-skill/SKILL.md
-allowed-tools: Read, Edit, Bash(git:*)
+allowed-tools: Read, Edit, Bash(git:*), Bash(npm:*)
```

```diff
 # tests/converter.test.ts
   expect(bashPermission["git *"]).toBe("allow");
+  // "npm *" is granted only by the tooled-skill fixture's allowed-tools, not by any
+  // fixture command — this is the one assertion that would fail if applyPermissions()
+  // stopped merging plugin.skills into the "from-commands" permission source.
+  expect(bashPermission["npm *"]).toBe("allow");
```

Verified fail-first: temporarily reverted the one-line merge fix in `applyPermissions()`, reran the
test, confirmed the new `bashPermission["npm *"]` assertion failed (2 tests failed, not 0) — proving
the assertion actually exercises the fix — then restored the fix and confirmed both tests passed
again.

## Prevention

- **Never scope a "zero references remain" grep by file extension.** Deprecated names leak into
  scripts, tests, and generated docs as often as markdown. Default to no `--include` filter (or use
  `git grep`), excluding only mechanically-guaranteed noise (`.git`, `node_modules`, build output).
- **Supplement literal full-name regexes with a bare-namespace-prefix pass.** A finite alternation of
  known suffixes (`oldname:(a|b|c)`) cannot catch generic prose (`` `oldname:*` ``), a typo that was
  never a valid name to begin with, or a suffix nobody enumerated. A second, deliberately broader grep
  (`oldname:` unanchored, then manually triage every hit) is a falsification pass on the first one's
  "zero matches" result — treat the first clean result as a hypothesis, not a conclusion.
- **A test for an additive "also read from Y" change needs a fixture value that only Y can produce.**
  If Y's fixture contribution is a subset of the pre-existing source's, the test cannot distinguish
  "the merge works" from "the merge silently regressed" — this is the same failure class as
  [Recorded Fixtures Must Be Load-Bearing](recorded-fixtures-must-be-load-bearing.md), one level up:
  there the fixture existed but nothing loaded it; here the fixture loaded but couldn't distinguish
  anything.
- **Fail-first-check additive/merge fixes before trusting a new assertion is load-bearing**: revert
  just the fix's diff hunk, rerun the test, confirm it fails; restore, confirm it passes. One extra
  command, and it should be a standard step in the Validation section for any plan whose Acceptance
  Criteria include a new test for a merge, union, or "also check a fallback source" change — not
  deferred to review as a nice-to-have.
- **A "zero references remain" acceptance criterion survives a single confirming grep only if that
  grep is scoped correctly the first time.** In this run, the orchestrator's own pre-PR grep repeated
  the sub-issue's exact scoping mistake — a second independent check with the *same* blind spot adds
  no signal. What actually caught the gap was a reviewer diffing against every file type rather than
  re-running the same grep shape.

## Resources

- Fixed in: [PR #146](https://github.com/Life-With-Data/agentic-engineering/pull/146) (issue #134),
  commits `af80d65` (original sweep), `5041209` (first follow-up), `e17eef4` (review-driven fix: 8
  leftover references + the weak-fixture-test fix), `9376167` (final leftover, found by a fully
  unrestricted sweep).
- Findings from: `acceptance-criteria-reviewer` and `integration-boundary-reviewer`, both run as part
  of `/workflows:review`'s independent multi-agent review — the mandatory, non-skippable review gate
  is what caught both issues; the implementer's own checks (and the orchestrator's own confirming
  grep) missed both.
- Related: [Recorded Fixtures Must Be Load-Bearing](recorded-fixtures-must-be-load-bearing.md) — same
  underlying failure mode (a check that reads as coverage but structurally cannot fail), applied to a
  different symptom.
- Plan doc: `docs/plans/2026-07-14-refactor-migrate-commands-to-skills-plan.md`.
