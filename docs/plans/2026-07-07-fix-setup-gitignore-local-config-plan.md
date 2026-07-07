---
title: "fix(setup): gitignore agentic-engineering.local.md on write; detect & offer to untrack a committed copy"
type: fix
status: completed
date: 2026-07-07
github_issue: 62
---

# fix(setup): gitignore agentic-engineering.local.md on write; detect & offer to untrack a committed copy

The `setup` skill (`plugins/agentic-engineering/skills/setup/SKILL.md`) writes `agentic-engineering.local.md` into the user's project root but never ensures a `.gitignore` entry and never detects an already-committed copy. The runtime (`plugins/agentic-engineering/scripts/lifecycle_board.py` — note: under the plugin, not repo-root `scripts/` as issue #62 says) treats a tracked `.local.md` as a security threat: `read_board_config` ignores it (docstring lines 358–367, skip+warn lines 375–378) and `read_binding_config` skips it silently (lines 428–435). Result: a user who commits the file gets their local overrides silently ignored plus a stderr warning on every `lifecycle_board.py` / `bootstrap_lifecycle_board.py` / `--doctor` invocation.

This is a **SKILL.md instruction-only change** — no Python changes. The existing behavior test `test_tracked_local_config_is_ignored` (`plugins/agentic-engineering/tests/lifecycle_board_test.py:476–496`) must stay green and untouched.

## Design decisions (from research)

1. **`git check-ignore -q --no-index` is the idempotence gate, not grep.** Exact-line grep misses broader patterns (`*.local.md`), other ignore sources, and is defeated by negations. `--no-index` is load-bearing (found by live verification, not research): plain `check-ignore` never reports a *tracked* file as ignored — tracked files aren't subject to exclude rules — so against a legacy tracked copy the gate would fail every re-run and append duplicate entries. `--no-index` evaluates the exclude rules purely. Accepted limitation: if the file is ignored only via the user's global excludes, no repo-level entry is appended — acceptable because each collaborator's own setup run self-heals, and tracked-detection (the security half) is independent.
2. **Ensure the `.gitignore` entry BEFORE offering the untrack.** Otherwise a later `git add -A` re-tracks the file in the window between the two.
3. **The appended line is literally `agentic-engineering.local.md`** — never a glob. The committed board identity file `agentic-engineering.md` differs by one token and must never be ignored (setup Step 3.6 writes it).
4. **The tracked-check must also run in Step 1** (existing-file path), not only after the Step 4 write. Step 1's "View current" and "Cancel" branches exit at SKILL.md:27–28 before Step 4 — and legacy repos with a copy tracked *before* any gitignore entry existed are exactly the population exhibiting the bug (a `.gitignore` entry never untracks an already-tracked file).
5. **Anchor every git operation to `git rev-parse --show-toplevel`.** The runtime reads the file from the repo root (`RepoContext.root`, lifecycle_board.py:229–236; worktree root is correct — `read_board_config` uses `ctx.root`, line 369), while a cwd-relative write from a subdirectory would put it elsewhere.
6. **Append is autonomous; untrack is consent-gated.** Adding an ignore entry is additive and safe. `git rm --cached` mutates the index → AskUserQuestion; in non-interactive runs, never auto-run it — print the warning and the exact command instead.
7. **Tracked-detection parity with the runtime:** same command as `_is_tracked` (lifecycle_board.py:342–347): `git -C "$ROOT" ls-files --error-unmatch agentic-engineering.local.md >/dev/null 2>&1`.

## Acceptance Criteria

- [x] **New Step 4.5 "Protect the local config"** in setup SKILL.md (between Step 4 write and Step 5 confirm) with the canonical recipe below: check-ignore gate → trailing-newline-safe append (creates `.gitignore` if absent) → tracked-check → consent-gated untrack.
- [x] **Step 1 addition:** when an existing `agentic-engineering.local.md` is found, run the tracked-check immediately (before the View/Reconfigure/Cancel menu resolves) so all three branches surface a tracked copy; if tracked, warn + offer untrack right there.
- [x] **Untrack messaging:** warn states concrete consequences (runtime ignores the file's overrides and prints the stderr warning every run until untracked; the file rides any PR from the branch). After `git rm --cached`: state the deletion is **staged** — commit it (ideally together with the `.gitignore` change) or it still ships in PRs from HEAD; one-line caveat that collaborators pulling that commit have their unmodified working copies deleted. Note the rare `-f` fallback (`git rm --cached -f`, disk-safe — never touches the working file). Decline is non-blocking: setup completes; print the exact command for later.
- [x] **Not-a-git-repo:** `ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` fails → skip both git steps silently; the config write still succeeds (stack-detect + write work without git).
- [x] **Step 5 confirmation block** (SKILL.md:342–356) gains two status lines parallel to `Always-on:`: `Gitignore: entry present | added` and `Tracked: no | untracked now (deletion staged — commit it) | still tracked (declined)`.
- [x] **Non-interactive invocation:** append happens autonomously; `git rm --cached` is never auto-run — warning + exact command printed instead.
- [x] **Skill writing style:** imperative/verb-first, no second person (plugin CLAUDE.md Skill Compliance Checklist); frontmatter (`name: setup`, `description`) untouched → no docs rebuild needed.
- [x] **Release mechanics:** PATCH bump `plugins/agentic-engineering/.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` together (currently 3.3.0; open PR #69 claims 3.4.0 → use 3.4.1 if #69 merges first, else 3.3.1; decide at merge time), CHANGELOG.md `### Fixed` bold-lead entry, `bun test` green. Component counts unchanged (25 skills).
- [x] **Verification (live, in a scratch repo):** simulate the recipe end-to-end — (a) fresh repo: entry appended, `git check-ignore -q` exits 0, file untracked; (b) pre-tracked copy: after untrack, `git ls-files --error-unmatch agentic-engineering.local.md` exits non-zero and a `lifecycle_board.py` invocation no longer prints the tracked-file warning; (c) `.gitignore` with broader pattern `*.local.md`: no duplicate line appended; (d) `.gitignore` without trailing newline: last existing pattern not corrupted; (e) re-running the recipe while the copy is still tracked (untrack declined) appends nothing — exactly one entry line remains.
- [x] Optional one-liner: plugin `README.md:99` (tells users to put `issue_tracker:` in `.local.md`) gains a "keep it untracked — setup gitignores it" caveat.

## MVP

### plugins/agentic-engineering/skills/setup/SKILL.md — new Step 4.5 (core recipe)

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=""
if [ -n "$ROOT" ]; then
  # 1. Ensure ignore entry (autonomous; always before any untrack offer)
  if ! git -C "$ROOT" check-ignore -q --no-index agentic-engineering.local.md; then
    [ -s "$ROOT/.gitignore" ] && [ -n "$(tail -c1 "$ROOT/.gitignore")" ] && printf '\n' >> "$ROOT/.gitignore"
    printf 'agentic-engineering.local.md\n' >> "$ROOT/.gitignore"
  fi
  # 2. Tracked? (index check — same command as runtime _is_tracked)
  if git -C "$ROOT" ls-files --error-unmatch agentic-engineering.local.md >/dev/null 2>&1; then
    : # warn + AskUserQuestion → on yes: git -C "$ROOT" rm --cached agentic-engineering.local.md
  fi
fi
```

Instruction text around the recipe follows the in-file idiom of Step 3.7 (SKILL.md:284–292, grep-before-append) and `skills/git-worktree/scripts/worktree-manager.sh:20–25` (`ensure_gitignore`).

### Step 1 (SKILL.md:11–28) — existing-file path

After reading an existing `agentic-engineering.local.md`, run the Step 4.5 tracked-check before presenting View/Reconfigure/Cancel. If tracked: show the warning + untrack offer regardless of which option the user picks next.

### Step 5 (SKILL.md:340–356) — confirmation block

```
Saved to agentic-engineering.local.md
...
Always-on:     {…}
Gitignore:     {entry present | added}
Tracked:       {no | untracked now (deletion staged — commit it) | still tracked (declined)}
```

## Out of scope (explicit)

- **Structured `--doctor` check** for a tracked `.local.md` (natural slot exists at lifecycle_board.py `verb_doctor` "Repo shape" ~line 1480; the stderr warning already fires during doctor via `read_board_config`). Follow-up candidate, not part of #62's setup-scoped fix.
- **`workflow-repo-preflight.py` inconsistency:** `read_local_config_tracker` (lines 160–187) honors a tracked `.local.md` for tracker resolution while board identity from the same file is ignored. Pre-existing, unrelated to setup; noted for a future issue.

## Sources

- Related issue: [#62](https://github.com/aagnone3/agentic-engineering/issues/62)
- Runtime invariant: `plugins/agentic-engineering/scripts/lifecycle_board.py:358-378` (`read_board_config`), `:342-347` (`_is_tracked`), `:428-435` (`read_binding_config`); locked by `plugins/agentic-engineering/tests/lifecycle_board_test.py:476-496`
- Write site: `plugins/agentic-engineering/skills/setup/SKILL.md:299-356` (Steps 4–5), `:11-28` (Step 1)
- Gitignore-append precedents: `plugins/agentic-engineering/skills/git-worktree/scripts/worktree-manager.sh:20-25`; setup SKILL.md:284-292; this repo's root `.gitignore` (exact entry + rationale comment)
- Institutional learning: `docs/solutions/logic-errors/idempotent-backfill-and-recorded-config-design.md` (preserve-on-rerun, idempotent setup mutations)
- Release rules: `plugins/agentic-engineering/CLAUDE.md` (three-file version/CHANGELOG/README contract, Skill Compliance Checklist); `tests/plugin-consistency.test.ts:90-94,137-143`
