---
title: "fix(beads): silence export.git-add churn + stop block-hook prose false-positives"
type: fix
date: 2026-07-18
github_issue: 95
---

# fix(beads): silence `export.git-add` churn + stop block-hook prose false-positives

Two separable defects in the plugin's beads (`bd`) integration, filed together in #95. Both stem from the plugin owning the "JSONL export stays untracked; share via dolt" doctrine (`scripts/block-beads-jsonl-stage.py`) but not completing it.

> **Grooming note (autonomous):** Under the current lifecycle, **beads is a demoted, opt-in, non-authoritative implementer scratchpad**, not a tracker (`skills/setup/SKILL.md:138-140`, `scripts/plan-tracker-guard.py:6-7`, `skills/lifecycle/SKILL.md:151-155`). The only live `bd` *mutation* the plugin performs is `bd remember` in compound (`skills/workflows-compound/SKILL.md:101-103`). That reframes #95's severity: the export warning now fires only when a human opts into `bd`, so this is a UX paper-cut + a doc-drift cleanup, **not** a correctness bug in the lifecycle. The block-hook false-positive (Problem B) is the sharper defect — it blocks legitimate `gh issue create` commands.

## Overview

**Problem A — `export.git-add` warning churn (doc/behavior gap).** With beads active, every `bd` mutation prints:

```
Warning: auto-export: git add failed: exit status 1: The following paths are ignored by
one of your .gitignore files: .beads/issues.jsonl
```

because the plugin gitignores the JSONL export (correct) and ships `block-beads-jsonl-stage.py` to keep it untracked (correct), but never disables bd's *own* `export.git-add` (default `true`), which then tries to auto-stage that ignored file after every write and fails. The intuitive fix — `export.git-add: false` in the **tracked** `.beads/config.yaml` — is **empirically ignored by bd**; the setting is read only from bd's **Dolt DB** or the `BD_EXPORT_GIT_ADD` env var.

**Problem B — block hook false-positives on prose.** `scripts/block-beads-jsonl-stage.py` blocks any command where the substrings `git add` **and** a `.beads/*.jsonl` path both appear *anywhere in the command string*, with **no inspection of the command verb/argv**. A `gh issue create` whose **body** mentions both tokens (e.g. a heredoc `--body-file -`) is wrongly blocked — the exact trap that initially blocked filing #95.

## Problem Statement / Motivation

- **Problem A** wastes agent tokens: the warning fires on every opt-in `bd` write and gets re-investigated and re-explained session after session because the "obvious" config.yaml fix silently does nothing. The plugin created the condition (gitignored export) that makes bd warn, so completing the doctrine is the plugin's responsibility.
- **Problem B** is a live correctness defect in a shipped hook: it blocks legitimate `gh`/`echo`/documentation commands that merely *mention* the export path near the phrase "git add" — including filing issues *about* this very topic.
- **Drift:** the hook's own docstring (`scripts/block-beads-jsonl-stage.py:17-20`) still describes beads as a *first-class tracker* (`/workflows-plan` writes `bead_id:`, `/workflows-work` runs `bd ready`/`bd close`) — a world every other skill has already retired. Any change here should reconcile that drift, not append to it.

### Evidence — deterministic A/B (from #95, verified against a real repo)

Tests used real content mutations (a no-op `bd update` doesn't export), `export.interval 1s`, `BD_EXPORT_GIT_ADD` stripped, and the DB override cleared:

| Config source under test | Result on forced writes |
|---|---|
| `.beads/config.yaml` nested `export:` → `git-add: false` (committed) | **WARNS** (ignored by bd) |
| `.beads/config.yaml` flat `export.git-add: false` (committed) | **WARNS** (ignored by bd) |
| `bd config set export.git-add false` (Dolt DB) | **clean** |
| `BD_EXPORT_GIT_ADD=false` (env) | **clean** |

The only working, cross-machine, repo-scoped fix is the **DB setting**, propagated via `bd dolt push` (teammates get it on `bd dolt pull`). The env var works but is machine-local and doesn't travel with the repo.

## Proposed Solution

Three tasks, mapped to #95's own "suggested actions". Land the doctrine/docs first, then the bootstrap that references it; the hook fix is independent.

1. **Harden the block hook (Problem B)** — anchor matching to the command *verb/argv* so only a real `git add` (or `git ... add`) staging a beads export path blocks; prose bodies passed to `gh`/`echo`/heredocs pass through. Add **category-based** regression tests (heredoc body, unquoted `gh` body) — assert the *invariant category*, not a literal spelling (per `docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md`). Reconcile the stale "first-class tracker" docstring in the same edit.
2. **Document the gotcha + reconcile drift (Problem A, docs)** — a canonical note: `.beads/config.yaml` silently ignores `export.git-add`; the working knob is `bd config set export.git-add false` (Dolt DB, travels via `bd dolt push`) or `BD_EXPORT_GIT_ADD=false` (machine-local); under the opt-in-scratchpad model the warning is benign and should not be re-investigated. Anchor it in the hook's `ERROR_MSG`/docstring and a new `HOOKS.md` section.
3. **Bootstrap the DB setting (Problem A, behavior)** — when beads is *already initialized* in a repo (`.beads/` present), have the setup flow run `bd config set export.git-add false` once (idempotent) and note that `bd dolt push` shares it. Strictly gated to the beads-detected branch — never install or `bd init` for users who have not opted in.

## Technical Considerations

- **Single-source scope (verified):** `block-beads-jsonl-stage.py` is **Claude-only, single-copy** — it is *not* byte-duplicated under `skills/install-hooks/scripts/` (only the four portable guards are: `block-db-push`, `block-no-verify`, `block-slack-webhook`, `prevent-main-commit`), and `tests/install-hooks-skill-sync.test.ts` does not cover it. So Task 1 edits exactly `scripts/block-beads-jsonl-stage.py` + `tests/block_beads_jsonl_stage_test.py` — no mirror copy to keep in sync. (Re-confirm before editing.)
- **Matcher design:** the current logic (`block-beads-jsonl-stage.py:35-36,63-65`) is two whole-string regexes ANDed; `sanitize()` (`:70-76`) strips only inline `'…'`/`"…"`/`#` comments, missing heredocs and unquoted bodies. The fix parses the leading token(s): block only when the resolved command verb is `git` and the effective subcommand is `add` (accounting for global flags like `git -C … add`). Prefer erring toward *allow* — a missed block is recoverable (the JSONL is gitignored anyway; worst case the user sees the same benign warning), whereas a false block halts legitimate work.
- **No bootstrap step exists today:** `skills/setup/SKILL.md` Step 3.5 only *detects* a tracker; `workflow-repo-preflight.py:332-361` only *probes* beads (`which bd`, `.beads/` dir). Task 3 adds the first `bd config set` the plugin performs, in the beads-detected branch near Step 3.5/3.6.
- **Idempotency:** `bd config set export.git-add false` is safe to re-run; guard on `.beads/` presence and `which bd` so it no-ops cleanly where beads isn't used.

## System-Wide Impact

- **Interaction graph:** `block-beads-jsonl-stage.py` is a `PreToolUse(Bash)` hook (`scripts/HOOKS.md:23`). Loosening its match set changes which Bash commands are allowed to run — the risk is *under*-blocking (a genuine `git add .beads/issues.jsonl` slips through), which the tests must pin. The bootstrap (Task 3) runs a `bd` mutation during setup — a new side effect on a user's Dolt DB, gated to opt-in beads users.
- **Error propagation:** the hook exits `2` to block; Task 1 must preserve exit-code semantics for the genuine-staging case and return `0` for prose.
- **API surface parity:** no other hook matches on beads paths; the change is local to this one script.
- **State lifecycle risks:** Task 3 mutates the repo's Dolt DB. It must be idempotent and must not run outside the beads-detected branch, or it could error on machines without `bd`.
- **Integration test scenarios:** (a) `gh issue create` heredoc body containing "git add .beads/issues.jsonl" → **allowed**; (b) real `git add .beads/issues.jsonl` → **blocked** (exit 2); (c) `git -C sub add .beads/events.jsonl` → **blocked**; (d) `echo "run git add .beads/issues.jsonl"` (unquoted prose) → **allowed**.

## External System Wiring

**No external wiring required.** `bd`/beads is a local CLI + local Dolt DB; there is no third-party console, webhook, OAuth app, or env var beyond the machine-local `BD_EXPORT_GIT_ADD` (which this plan explicitly treats as non-canonical because it doesn't travel with the repo). No provider-side configuration exists to verify.

## Acceptance Criteria

- [ ] **Task 1 — hook hardening:** `block-beads-jsonl-stage.py` blocks a command **only** when its resolved verb is `git` and the effective subcommand is `add` staging a `.beads/*.jsonl` path; a `gh issue create` heredoc/`--body-file` body and unquoted `echo` prose that merely mention the tokens are **allowed**.
- [ ] Regression tests added for: heredoc `gh` body (allowed), unquoted `gh`/`echo` body (allowed), real `git add .beads/issues.jsonl` (blocked, exit 2), and `git -C … add` of a beads export (blocked). Tests assert the **category** (verb-anchored block), not a frozen literal string.
- [ ] The stale "first-class tracker" docstring (`:17-20`) is corrected to the demoted-scratchpad reality; `ERROR_MSG` remains accurate.
- [ ] **Task 2 — docs:** a canonical note documents that `.beads/config.yaml` is ignored, the working knob is the Dolt DB setting (+ `bd dolt push`) or `BD_EXPORT_GIT_ADD`, and the warning is benign under the opt-in model. Anchored in `HOOKS.md` (new section) and the hook's docstring/`ERROR_MSG`. Agents are told to stop re-investigating it.
- [ ] **Task 3 — bootstrap:** when `.beads/` exists and `bd` is on PATH, the setup flow runs `bd config set export.git-add false` once (idempotent), noting `bd dolt push` shares it; it never runs for non-beads repos and never installs/`init`s beads.
- [ ] `bun test` passes (no component-count drift — all edits are to existing scripts/tests/skills). The Python hook test passes via `python3 -m unittest`.
- [ ] PR title uses a Conventional Commit type; version/CHANGELOG left to release-please.

## Validation

**How a reviewer proves this behaves — not that it compiles.**

- **Automated:**
  - `python3 -m unittest plugins/agentic-engineering/tests/block_beads_jsonl_stage_test.py -v` — new heredoc/unquoted-prose "allowed" cases + genuine-staging "blocked" cases pass.
  - `bun test` — full gate (consistency + converter suites) green.
- **Manual (Problem B):** in a repo with the hook active, run a `gh issue create` whose heredoc body contains `git add .beads/issues.jsonl` → command runs (not blocked). Then run a literal `git add .beads/issues.jsonl` → blocked with the guidance message (exit 2).
- **Manual (Problem A):** with beads initialized, `bd config set export.git-add false` then a forced `bd` mutation → no `auto-export: git add failed` warning. Confirm `.beads/config.yaml`'s `export.git-add` is *not* the effective source (`bd config get export.git-add` reads the DB).
- **Rollback:** revert the PR. The bootstrap's only durable effect is a Dolt DB config value; `bd config set export.git-add true` restores the prior behavior. The hook revert restores the whole-string matcher (re-introduces the false-positive but no data risk).

## Success Metrics

- Zero `auto-export: git add failed` warnings during opt-in `bd` use after bootstrap.
- Zero false blocks of `gh`/`echo`/heredoc commands that mention the export path.
- The gotcha stops recurring in sessions (no repeated re-investigation of config.yaml).

## Dependencies & Risks

- **Task 3 depends on Task 2** — land the canonical doctrine note first, then have the bootstrap reference it (avoids two divergent explanations). Task 1 is independent and can land first.
- **Risk (Task 1):** over-loosening lets a genuine `git add` of a beads export through. Mitigation: verb-anchored match + explicit "blocked" tests for the genuine cases; bias-to-allow is acceptable because the export is gitignored regardless.
- **Risk (Task 3):** running a `bd` mutation during setup is a new repo side effect. Mitigation: strict `.beads/`-present + `which bd` guard, idempotent, opt-in only.
- **Relation to #170/#191/#192** (de-dup hook scripts between `scripts/` and `skills/install-hooks/scripts/`): this hook is *not* in the duplicated set, so those refactors don't collide — but re-confirm the enforced file list in `install-hooks-skill-sync.test.ts` before editing.

## Sources & References

- **Origin issue:** #95 (this plan is joined to it via `github_issue: 95`).
- Match logic & sanitizer gap: `plugins/agentic-engineering/scripts/block-beads-jsonl-stage.py:35-36,63-65,70-76`
- Stale first-class-tracker docstring: `plugins/agentic-engineering/scripts/block-beads-jsonl-stage.py:17-20`; error message: `:45-47`
- Only double-quoted prose test today: `plugins/agentic-engineering/tests/block_beads_jsonl_stage_test.py:80-82`
- Beads demoted to scratchpad: `skills/setup/SKILL.md:138-140`, `scripts/plan-tracker-guard.py:6-7`, `skills/workflows-plan/SKILL.md:211,730`, `skills/lifecycle/SKILL.md:151-155`
- Only live `bd` mutation: `skills/workflows-compound/SKILL.md:101-103`
- Preflight probes (no bootstrap): `scripts/workflow-repo-preflight.py:332-361`
- HOOKS.md table row (no prose section yet): `scripts/HOOKS.md:23`; byte-dup sync scope: `scripts/HOOKS.md:8-14`
- Institutional learnings: `docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md` (assert category not literal — and this file *names* `block-beads-jsonl-stage.py` as a stale-reference trap), `docs/solutions/integration-issues/skills-mutating-user-repos-git-gotchas.md` (git-boundary / `core.hooksPath` gotchas)
- Conventions: root `CLAUDE.md` (release-please owns version/CHANGELOG; `bun test` gate), `plugins/agentic-engineering/CLAUDE.md`
</content>
</invoke>

