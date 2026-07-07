---
title: "feat(bootstrap): scaffold actions/add-to-project workflow for auto-add"
type: feat
status: active
date: 2026-07-07
github_issue: 63
---

# feat(bootstrap): scaffold `actions/add-to-project` workflow ✨

## Enhancement Summary

**Deepened on:** 2026-07-07
**Agents used:** security-sentinel, framework-docs-researcher (verified against the live `actions/add-to-project` `action.yml`/README + GitHub REST API), best-practices-researcher (GitHub Actions hardening, OpenSSF Scorecard, StepSecurity).

### Key decisions locked by the deepening
1. **SHA-pin by default** (was "decide at review"): scaffold `actions/add-to-project@<40-char-sha>  # v2.0.0`, resolved at scaffold time (`gh api repos/actions/add-to-project/commits/v2 --jq .sha`, fallback to the known-good `5afcf98fcd03f1c2f92c3c83f58ae24323cc57fd`). A moving `@v2` tag with a live PAT in scope is the single highest-leverage risk for a template that fans out into many repos (tj-actions/changed-files compromise class). First-party `actions/*` is **not** an exemption.
2. **Ship `.github/dependabot.yml`** (github-actions ecosystem) alongside, so the pinned SHA is auto-bumped — "pinned but not frozen." Idempotent/merge-aware (never clobber an existing dependabot config).
3. **`permissions: {}`** at top level **and** job level — not `contents: read`. The PAT does the Projects write, so `GITHUB_TOKEN` needs *zero* scopes; an explicit empty block also overrides a permissive org default.
4. **Invert token guidance** to least-privilege-first: **fine-grained PAT** (org **Projects: Read & write** + repo **Issues: Read-only** + **Pull requests: Read-only**) as the documented default → **GitHub App installation token** as the org-hardened option → **classic PAT** (`project` + `repo` for private) as the flagged account-wide fallback.
5. **Trigger safety confirmed & documented as verified:** `issues: [opened]` is low-risk (no checkout of untrusted code, no `run:` steps interpolating `github.event.issue.*`). Scaffold an inline comment forbidding future `run:` interpolation so the posture survives downstream edits.

### New considerations discovered
- `actions/add-to-project@v2` has exactly two required inputs (`project-url`, `github-token`) + two optional (`labeled`, `label-operator` — default `OR`). Scaffold omits the optional filters (add everything).
- The `orgs/` vs `users/` URL segment must match owner type **exactly** — the action does not normalize. `gh api users/<owner> --jq .type` resolves both (`Organization`→`orgs`, `User`→`users`).
- Secret-expiry failure mode: an expired fine-grained PAT surfaces as a **red workflow run** on the `add-to-project` step, not a doctor check — document the rotation cadence (~90d) and this signal.

## Overview

Issue #64 (shipped, PR #66) made the repo→board **forward binding** an explicit recorded decision: choosing `auto-add` records the intent, and `/lifecycle-doctor`'s `board_forward_binding` check **WARNs** with "no actions/add-to-project workflow is present" until the file exists. This issue (#63) supplies the **mechanism** that clears that WARN: when the operator chooses `auto-add`, bootstrap scaffolds `.github/workflows/add-to-project.yml` (the official `actions/add-to-project` Action), reducing the manual step from "click around the Projects UI" to "add one repo secret."

The built-in Projects v2 auto-add workflow has **no create/enable API** (`ProjectV2Workflow` is delete-only), but `actions/add-to-project` reproduces the outcome: it listens on issue events and calls `addProjectV2ItemById`. The only genuinely manual bit is provisioning the token secret — the default `GITHUB_TOKEN` cannot write user/org-owned Projects.

## Problem Statement / Motivation

After #66, a user who picks `auto-add` is left with a recorded decision but **no working mechanism** — new issues still don't reach the board, and doctor WARNs indefinitely. The issue itself supplies the fix: scaffold the Action. This closes the loop so `auto-add` is functional end-to-end, not just recorded.

## Proposed Solution

When `forward_binding == "auto-add"`, bootstrap scaffolds the workflow file — **idempotent** (skip if the file already exists; never clobber a user's customization) and **non-fatal** (a scaffold failure degrades to a summary warning, exactly like `link_repo`). Choosing `auto-add` **is** the opt-in (the setup skill's forward-binding question already frames it as "scaffold actions/add-to-project … needs a PAT/App-token secret"), so no extra prompt is added.

### Design decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | When does scaffolding run? | Only when `forward_binding == "auto-add"`, as a new bootstrap step after `write_committed_config` (identity + decision already committed). Not a separate CLI flag — choosing auto-add is the opt-in. |
| 2 | Idempotency | Skip (return `already_exists`) if `.github/workflows/add-to-project.yml` exists — mirrors `link_repo`'s skip-when-satisfied. Never overwrite a user-edited workflow. |
| 3 | Failure handling | Non-fatal: a write error folds into `summary["warnings"]` (board is fully usable; the file can be added by hand). Mirrors `link_repo`. |
| 4 | User vs org project URL | `actions/add-to-project` needs `project-url`: `https://github.com/users/<owner>/projects/<n>` (User) vs `https://github.com/orgs/<owner>/projects/<n>` (Organization). Resolve owner type via one `gh api users/<owner> --jq .type` call (that endpoint resolves both and returns `User`/`Organization`). |
| 5 | Secret name | Fixed `ADD_TO_PROJECT_PAT` (matches the issue's template). Documented as the one remaining manual step. |
| 6 | Action version pinning | **SHA-pin by default** (deepening decision): `actions/add-to-project@<40-char-sha>  # v2.0.0`. Resolve the SHA at scaffold time via `gh api repos/actions/add-to-project/commits/v2 --jq .sha`; if the resolve fails (offline/error), fall back to the known-good constant `5afcf98fcd03f1c2f92c3c83f58ae24323cc57fd`. A test asserts the `uses:` line carries a 40-hex SHA, never a `@v` tag. |
| 7 | Workflow hardening | `permissions: {}` at **top level and job level** (the PAT does the write; `GITHUB_TOKEN` needs nothing — stricter than `contents: read`). `on: issues: types: [opened]` only. No `run:` steps; an inline comment forbids future `run:` steps that interpolate `github.event.issue.*` (script-injection guardrail for downstream edits). |
| 8 | Location of the file | `ctx.root/.github/workflows/` (the worktree/repo root — same tree `find_auto_add_workflow` already scans, so doctor detects it immediately). |
| 9 | Dependabot | Scaffold `.github/dependabot.yml` (github-actions ecosystem, weekly) so the pinned SHA auto-bumps. Idempotent: create if absent; if a `dependabot.yml` exists, **do not parse/merge** it — emit a non-fatal warning telling the operator to add the `github-actions` ecosystem entry. |
| 10 | Optional inputs | Omit `labeled`/`label-operator` (add every opened issue). Mention them in a scaffolded comment as the customization knob. |

### Scaffolded artifacts (exact content)

`.github/workflows/add-to-project.yml` (owner segment + SHA filled at scaffold time):

```yaml
# Auto-adds newly opened issues to the lifecycle Projects v2 board.
# Scaffolded by agentic-engineering bootstrap (forward binding = auto-add).
# One manual step: add a repo secret ADD_TO_PROJECT_PAT (see the setup skill).
# SECURITY: do NOT add `run:` steps that interpolate ${{ github.event.issue.* }}
# — that reintroduces script injection. This job runs no untrusted code.
name: Add issues to project
on:
  issues:
    types: [opened]

permissions: {}   # the PAT does the Projects write; GITHUB_TOKEN needs nothing

jobs:
  add-to-project:
    runs-on: ubuntu-latest
    permissions: {}
    steps:
      - uses: actions/add-to-project@5afcf98fcd03f1c2f92c3c83f58ae24323cc57fd  # v2.0.0
        with:
          project-url: https://github.com/users/<owner>/projects/<number>   # or orgs/<owner>/...
          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}
          # Optional filter: labeled: bug,needs-triage / label-operator: OR|AND|NOT
```

`.github/dependabot.yml` (created only if absent):

```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

### Where the code changes land

- **`scripts/bootstrap_lifecycle_board.py`** — new `scaffold_add_to_project_workflow(project, ctx, runner)` (returns `{scaffolded, already_exists, path, project_url, secret_name, action_ref, warning}`); a `_resolve_owner_url_segment(ctx, runner)` helper (`users`|`orgs` via `gh api users/<owner> --jq .type`); a `_resolve_action_sha(runner)` helper (`gh api repos/actions/add-to-project/commits/v2 --jq .sha`, fallback to the pinned constant); a `_ensure_dependabot_github_actions(ctx)` helper (create-if-absent, warn-if-present); and a conditional call in `bootstrap()` (only when `forward_binding == "auto-add"`), folded into the summary + warnings exactly like `link_repo`.
- **`skills/setup/SKILL.md`** — update the `auto-add` guidance: bootstrap now writes the workflow file (and Dependabot config) automatically; the one remaining manual step is provisioning the `ADD_TO_PROJECT_PAT` secret with the **fine-grained** scopes (default), noting the App-token and classic-PAT alternatives. Drop the "(see issue #63)" forward-pointer.
- **`commands/lifecycle-doctor.md`** — the `board_forward_binding` check already handles this (PASS once the file exists); a one-line note that bootstrap scaffolds it.
- **Tests** — `bootstrap_lifecycle_board_test.py`: scaffold writes valid YAML with the right project-url (user + org via a stubbed owner-type call), `permissions: {}` present, `uses:` line is a **40-hex SHA not a `@v` tag**, idempotent skip when file exists, non-fatal on write failure, runs **only** on `auto-add` (not workflow-only/none), and the scaffolded file is detected by `lifecycle_board.find_auto_add_workflow` (cross-consistency — the two halves must agree). Dependabot: created when absent, warns when present. The SHA resolver falls back to the constant when the `gh` call fails.
- **Version/docs** — bump `plugin.json` + `marketplace.json` (3.3.0 → 3.4.0); `CHANGELOG.md`; no component-count change.

## Technical Considerations

- **Reuse the `link_repo` shape** (`bootstrap_lifecycle_board.py:491–509`): query-or-check → skip if satisfied → attempt → degrade failure to a non-fatal warning folded into the summary. The scaffold is that same pattern for a file write instead of a `gh` mutation.
- **Fork-trap discipline:** the owner-type `gh api` call passes an explicit path; no flagless `gh` that could resolve upstream.
- **`find_auto_add_workflow` agreement:** the scaffolded filename/marker (`actions/add-to-project`) must be exactly what `find_auto_add_workflow` greps for (`lifecycle_board.py`), or doctor won't detect the file it just wrote. A test pins this cross-consistency.

## External System Wiring

- **System:** GitHub Actions (the scaffolded workflow) + GitHub Projects v2 (the board it writes).
- **Config objects:** `.github/workflows/add-to-project.yml` + `.github/dependabot.yml` (in-repo, scaffolded) and a repo **Actions secret** `ADD_TO_PROJECT_PAT`.
- **Where config lives:** the workflow/dependabot files ride the repo (committed by the user after bootstrap); the secret is provisioned in the repo's *Settings → Secrets and variables → Actions* (provider UI — never readable back).
- **Why `GITHUB_TOKEN` can't do this (the crux):** the workflow-scoped `GITHUB_TOKEN` is a *repository*-scoped installation token; Projects v2 are owned by the *account* (user/org), a different ownership boundary, so no `permissions:` grant can let it write the board. A PAT or App token is unavoidable.
- **Token guidance — least-privilege first (documented in this order):**
  1. **Fine-grained PAT (default to document):** org **Projects: Read & write** + repo **Issues: Read-only** + **Pull requests: Read-only** (for a user-owned board, the account-level Projects R/W). Mandatory expiry; blast radius limited to that owner's Projects.
  2. **GitHub App installation token (org-hardened option):** scoped to the App's install + declared permissions, ~1h auto-rotating, revocable by uninstall — best for orgs, higher setup cost. (The action's docs prescribe the PAT path; the App path works but is the advanced/less-documented option.)
  3. **Classic PAT (flagged fallback):** `project` scope (+ `repo` for private repos) — **account-wide** across every project/repo the owner can see; only where fine-grained PATs are unavailable.
- **Secret hygiene:** repo secret (or org-level secret scoped to selected repos to rotate once) is pragmatic; an **environment** secret adds reviewer-gating if the board is sensitive. Rotate ~90d; an expired token surfaces as a **red `add-to-project` run**, not a doctor WARN.
- **Verification step:** open a test issue → observe it land on the board. `/lifecycle-doctor` → `board_forward_binding` PASS confirms the *file* is present; the secret itself is write-only and unverifiable from the CLI (already called out in #66's doctor detail).

## Acceptance Criteria

- [x] `scaffold_add_to_project_workflow` writes `.github/workflows/add-to-project.yml` with: correct `project-url` (User → `/users/…`, Org → `/orgs/…`), `on: issues: [opened]`, `actions/add-to-project@<40-hex-sha>  # v2.0.0` (**SHA, never a `@v` tag**), `permissions: {}` at top **and** job level, the no-`run:`-interpolation security comment, and `github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}`.
- [x] The action SHA is resolved at scaffold time (`gh api repos/actions/add-to-project/commits/v2 --jq .sha`) with a fallback to the pinned constant when the call fails.
- [x] `.github/dependabot.yml` is created (github-actions ecosystem) when absent; when present, left untouched with a non-fatal warning to add the ecosystem manually.
- [x] Runs **only** when `forward_binding == "auto-add"`; workflow-only / none scaffold nothing.
- [x] Idempotent: an existing workflow file is left untouched (returns `already_exists`), never clobbered.
- [x] Non-fatal: a write/resolve failure becomes a `summary["warnings"]` entry, never aborts bootstrap.
- [x] Owner-type resolution (`users` vs `orgs`) covered for both User and Organization (stubbed `gh api users/<owner>` in tests).
- [x] The scaffolded file is detected by `lifecycle_board.find_auto_add_workflow` (cross-consistency test) → doctor flips WARN→PASS.
- [x] A test asserts `permissions: {}` and a 40-hex SHA are present in the scaffolded YAML.
- [x] Setup skill documents `ADD_TO_PROJECT_PAT` with **fine-grained** scopes as the default (App-token + classic-PAT alternatives noted) as the one remaining manual step; the `(see #63)` pointer is removed.
- [x] Version bumped 3.3.0 → 3.4.0 in both manifests; CHANGELOG updated; `bun test` + Python suites green.

## Success Metrics

- Choosing `auto-add` during bootstrap produces a working forward-binding: the workflow file exists, `/lifecycle-doctor` `board_forward_binding` PASSes (modulo the unverifiable secret), and a new issue auto-lands once the secret is set.
- Re-running bootstrap on a repo that already has the file makes no changes to it.

## Dependencies & Risks

- **Security — token blast radius (P1, resolved in guidance).** Invert the token ordering to least-privilege-first (see External System Wiring): fine-grained PAT default, App token for orgs, classic `project`-scope PAT as the flagged account-wide fallback. The scaffold *documents* this; it cannot provision the secret.
- **Security — `permissions: {}` (P1).** The template must carry an explicit empty `permissions:` at top **and** job level (the PAT does the write; `GITHUB_TOKEN` needs nothing, and an explicit block also overrides a permissive org default). Asserted by test.
- **Supply chain — action pinning (P1, DECIDED: SHA-pin).** `@v2` is a moving tag; re-pointing it (or a maintainer-account compromise) runs arbitrary code **with `ADD_TO_PROJECT_PAT` in scope** — the tj-actions/changed-files (Mar 2025) class, amplified because a template fans the risk out to every scaffolded repo. First-party `actions/*` is **not** an exemption. Pin the full SHA (resolved at scaffold time; test asserts SHA-not-tag) **and** ship `.github/dependabot.yml` so the pin stays current ("pinned but not frozen"). If a downstream repo won't run Dependabot, a static SHA is still safer than a moving tag.
- **Trigger safety (confirmed low-risk).** `issues: [opened]` is *not* the dangerous class: no `pull_request_target`/`workflow_run`, no checkout of untrusted code, and no `run:` steps interpolating `github.event.issue.*`. The PAT secret is in scope but has no script-injection exfil path because nothing untrusted executes. The scaffolded inline comment preserves this invariant against future edits.
- **Builds on #66 (shipped).** `find_auto_add_workflow` + the `board_forward_binding` doctor check already exist in `main`; this issue only supplies the file they look for. The scaffolded marker string (`actions/add-to-project`) must match what `find_auto_add_workflow` greps for — pinned by a cross-consistency test.
- **Dependabot idempotency.** Never parse/merge an existing `dependabot.yml` (arbitrary user YAML); create-if-absent, else warn to add the `github-actions` ecosystem manually.
- **No new plugin components** — counts unchanged; version parity bump only.

## Sources & References

- **Origin issue:** [#63](https://github.com/aagnone3/agentic-engineering/issues/63).
- **Sibling (shipped):** [#64](https://github.com/aagnone3/agentic-engineering/issues/64) / PR #66 — recorded forward binding + the `board_forward_binding` doctor check this fills.
- **Mirror pattern:** `plugins/agentic-engineering/scripts/bootstrap_lifecycle_board.py:491–509` (`link_repo` — idempotent + non-fatal).
- **Detection consumer:** `plugins/agentic-engineering/scripts/lifecycle_board.py` (`find_auto_add_workflow`, `evaluate_forward_binding_check`).
- **Action docs:** `actions/add-to-project` (official, v2). Fetch current inputs via context7/framework docs at implementation time.
- **Learnings:** `docs/solutions/logic-errors/idempotent-backfill-and-recorded-config-design.md` (atomic writes, idempotent re-run), `docs/solutions/integration-issues/gh-projects-v2-backfill-item-list-shapes.md`.
