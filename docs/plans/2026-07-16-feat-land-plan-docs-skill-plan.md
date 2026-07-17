---
title: Create the land-plan-docs skill
type: feat
date: 2026-07-16
origin: docs/plans/2026-07-14-feat-land-plan-docs-step-plan.md  # parent plan (#145)
github_issue: 147
---

# ✨ Create the `land-plan-docs` skill

## Overview

Add a new skill, `plugins/agentic-engineering/skills/land-plan-docs/SKILL.md`, that commits
and opens a PR for one or more join-keyed plan docs (`docs/plans/**`) written in a single
groom/plan run. This is the **foundational deliverable** of the parent plan #145: every
other sub-issue (the `/workflows:groom`, `/workflows:plan`, and `/deepen-plan` wiring) depends
on this skill existing first. This plan is scoped to the **skill file only** — the command
wiring is tracked in sibling sub-issues of #145 and is explicitly out of scope here.

## Problem Statement / Motivation

`/workflows:groom` and `/workflows:plan` write plan docs to `docs/plans/*.md` carrying a
`github_issue: N` frontmatter join key — the sole bridge between docs-as-content and the
board-as-state. Today nothing commits, pushes, or PRs those files; they are left untracked in
the worktree and can be lost to a `git clean`, a worktree prune, or grooming in one worktree
and implementing in another — misfiring the lifecycle gate as `repair_needed` even when the
board correctly reads `planned`. `land-plan-docs` closes that gap by landing the plan doc(s)
as a docs-only PR.

## Proposed Solution

A single self-contained skill file modeled on the proven conventions of
[`land-docs`](../../plugins/agentic-engineering/skills/land-docs/SKILL.md) — scope check,
auto-merge-armed-at-creation, and the checks decision-tree — but adapted for **pre-work,
possibly multi-doc, plan artifacts**:

- **Input:** a list of `{issue_number, plan_doc_path}` pairs (a batch of 1..N) — one for a
  simple item, N+1 for an epic plus N children groomed in the same run.
- **Scope check (narrowed vs. `land-docs`):** `git add` only the exact join-keyed
  `docs/plans/**` paths for this run. Tolerate unrelated dirty files elsewhere in the tree;
  abort only when a *different* `docs/plans/**` file (outside this run's join keys) is also
  dirty (ambiguous ownership). This is deliberately narrower than `land-docs`'s whole-diff
  allowlist, because a plan run legitimately coexists with dirty product code.
- **Idempotency:** before branching, detect an existing open or merged PR tied to the join
  key(s) — via a recognizable branch-name prefix and/or label — and no-op, reporting the
  existing PR link, rather than re-branching.
- **Branch/commit/PR:** branch from a synced default; one branch, one commit, one PR covering
  all docs in the batch; a conventional `docs:` commit message enumerating the issue numbers.
- **Push-rejection handling:** on a race with a concurrent run, retry with a fresh
  branch-name suffix, bounded to ~2 attempts.
- **Auto-merge:** arm at creation (`gh pr merge --auto --squash --delete-branch`) where the
  repo allows it; if the repo disallows auto-merge, report the repo-settings blocker plainly
  (mirroring `land-docs`'s fallback) and fall back to watch-then-report — never silently skip
  arming.
- **Hook/CI failures:** fix mechanically (bounded ~2 attempts) or surface to the user — never
  `--no-verify`, never a direct push to the default branch, never a self-merge without human
  approval or an armed auto-merge.
- **Report:** one line stating the PR number/URL and status (`landed` / `pending` / `needs
  approval` / `skipped: <reason>`) — never silent.

## Technical Considerations

- **Architecture impact:** one new skill file. No changes to command files, board writers, or
  lifecycle semantics in this issue — purely additive.
- **Frontmatter conventions** (mirror `land-pr`/`land-docs`): `name` matches the directory
  (`land-plan-docs`); `description` states what + when and cross-links `land-docs`;
  `disable-model-invocation: true` (invoked deliberately by commands / sub-agents, not
  model-triggered); `allowed-tools` scoped to `Bash(gh *)`, `Bash(git *)`, `Read`.
- **Not `land-docs`:** do **not** reuse the name — `land-docs` is purpose-built for post-merge
  compound knowledge (`docs/solutions/**`), single-issue, post-merge timing, no batching,
  referenced only from `/workflows:compound`. Cross-link the two skills' descriptions to each
  other, the same way `land-docs` already cross-links `land-pr`.
- **Fork-trap guardrail:** every `gh` write carries an explicit `--repo "$ORIGIN"` (resolve
  `ORIGIN` once via `gh repo view --json nameWithOwner`).
- **No lychee assumption:** the repo has no enforced lychee/pre-commit link check today (no
  `.lychee.toml`, no lychee in `.github/workflows/*.yml`). Write hook/CI-failure handling
  generically, not lychee-specific.

## System-Wide Impact

- **Interaction graph:** the skill is a leaf delivered as a delegated (Sonnet) sub-agent per
  the parent plan — invoked by the wiring sub-issues, not by this issue. It calls out only to
  `git` and `gh`; it is **not** a lifecycle writer and stamps no board state.
- **Error propagation:** scope-check failure → abort + surface (never half-commit or silently
  drop). Push race → bounded retry with fresh suffix. Hook/CI failure → bounded mechanical fix
  or surface. None of these fail the enclosing groom/plan run silently.
- **State lifecycle risks:** none introduced here — the board-`planned` stamp is owned by the
  caller (`/workflows:plan` Step 7), which runs before the land step. This skill only persists
  the artifact and reports its PR status; it never claims `planned`.
- **API surface parity:** `land-docs` (compound / post-merge / single-issue / auto-merge-only)
  and `land-plan-docs` (groom-plan / pre-work / batched / approval-or-auto-merge) stay parallel
  but distinct surfaces — this issue does not unify them.
- **Integration test scenarios** (from parent #145, validated by sibling sub-issue #5):
  1. Single crisp item → one plan doc → one PR, auto-merge arms, status `landed`/`pending`.
  2. Epic + 3 children in one run → 4 plan docs → exactly one PR, one branch, one commit.
  3. Re-run on an already-`planned` item → detect existing PR for the join key → no-op with
     the existing PR link, never re-branch.
  4. Standalone plan run with unrelated dirty product-code files present → commit only the
     join-keyed doc path(s) and succeed; do not abort on unrelated dirt.
  5. Two concurrent runs push near-simultaneously → second push rejected → retry with fresh
     suffix → still succeeds without failing the run.

## External System Wiring

- **System:** GitHub repository settings (genuine external config this skill depends on).
- **Configuration object:** "Allow auto-merge" — repo Settings → General → Pull Requests.
- **Where it lives:** GitHub repo settings UI (or `gh api repos/{owner}/{repo} -f
  allow_auto_merge=true`); not managed by this repo's IaC today.
- **Verification step:** open a test docs-only PR via `land-plan-docs` and confirm `gh pr merge
  <N> --auto` succeeds. If it errors, that's a repo-settings blocker — the skill reports it
  plainly and falls back to watch-then-report, never a silent skip. (This external check is
  exercised by the wiring sub-issues, not by this skill-only issue.)

## Acceptance Criteria

- [ ] Skill exists at `plugins/agentic-engineering/skills/land-plan-docs/SKILL.md` with
      compliant frontmatter (`name` matches dir, `description` states what + when and
      cross-links `land-docs`, `allowed-tools` scoped to `Bash(gh *)`/`Bash(git *)`/`Read`,
      `disable-model-invocation: true`).
- [ ] Accepts a batch of N plan docs → produces one branch, one commit, one PR.
- [ ] Scope check tolerates unrelated dirty files elsewhere; aborts only on ambiguous
      `docs/plans/**` ownership (a `docs/plans/**` file outside this run's join keys is dirty).
- [ ] Idempotency check detects an existing open/merged PR for the join key(s) and no-ops with
      the existing PR link.
- [ ] Push-rejection retry (bounded ~2 attempts, fresh branch suffix) is specified.
- [ ] Auto-merge armed at creation where allowed; explicit, graceful fallback where not.
- [ ] Hook/CI failure handling matches the fix-or-surface decision tree; no `--no-verify`, no
      direct-to-default push, no unapproved self-merge.
- [ ] Report format emits one line: PR number/URL + status (`landed` / `pending` / `needs
      approval` / `skipped: <reason>`) — never silent.
- [ ] Skill-compliance: no unlinked `references/`/`scripts/`/`assets/` mentions; imperative
      voice; `bun test` (plugin-consistency) still passes with the new skill counted.

## Validation

**How a reviewer proves this behaves — not merely that the file parses.**

- **Automated:**
  - `bun test` — plugin-consistency suite passes with `land-plan-docs` counted (README tables,
    `plugin.json`/`marketplace.json` descriptions, `docs/index.html` stats all reconciled).
  - `bun run typecheck` passes.
  - `cat .claude-plugin/marketplace.json | jq .` and the same for `plugin.json` — valid JSON.
  - `grep -E '`(references|assets|scripts)/[^`]+`' plugins/agentic-engineering/skills/land-plan-docs/SKILL.md`
    returns nothing (no unlinked references).
- **Manual (dry run, per issue #147's Validation):** invoke the skill against a scratch branch
  state with (a) a single synthetic plan doc and (b) three synthetic plan docs from one
  simulated batch; confirm one PR each time, correct scope (only the join-keyed paths staged),
  and correct auto-merge/approval reporting.
- **Automated end-to-end:** none for this issue — it is a skill/prompt file, not executable
  code; the five integration scenarios are exercised later by sibling sub-issue #5.
- **Rollback:** purely additive — revert the new skill file and re-run `bun run docs:build` to
  drop it from the generated docs. No board/lifecycle semantics change.

## Dependencies & Risks

- **Blocked by:** none — this is the foundational skill.
- **Blocks:** the `/workflows:groom`, `/workflows:plan`, and `/deepen-plan` wiring sub-issues
  of #145 (all depend on this skill existing first).
- **Risk — naming confusion with `land-docs`:** mitigated by the distinct name and reciprocal
  cross-links in both descriptions.
- **Risk — auto-merge repo permission:** degrade to "open PR, report status," never a silent
  skip.

## Sources & References

### Origin

- **Parent plan:** [docs/plans/2026-07-14-feat-land-plan-docs-step-plan.md](2026-07-14-feat-land-plan-docs-step-plan.md)
  (#145) — full rationale, the 5 integration scenarios, and the non-functional acceptance
  criteria this skill must satisfy. Key decisions carried forward: distinct-name-not-`land-docs`;
  narrowed scope check (tolerate unrelated dirt); batched N+1 docs in one PR; delegated Sonnet
  sub-agent execution.

### Internal References

- `plugins/agentic-engineering/skills/land-docs/SKILL.md` — scope-check pattern, auto-merge
  armed at creation, checks decision-tree (the conventions this skill adapts; do **not** reuse
  the name).
- `plugins/agentic-engineering/skills/land-pr/SKILL.md` — frontmatter/template conventions
  (`name`/`description`/`disable-model-invocation`/`allowed-tools`), fork-trap `--repo` rule.
- `plugins/agentic-engineering/CLAUDE.md` — skill compliance checklist and versioning rules.
- `plugins/agentic-engineering/skills/lifecycle/SKILL.md` — "Docs are content; the board is
  state. The join key is the only bridge."

### Related Work

- Parent issue: #145. This issue: #147.
