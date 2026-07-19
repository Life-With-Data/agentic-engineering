---
title: "feat(hooks): adopt check-gh-identity guard; drop prime-beads-context"
type: feat
date: 2026-07-19
origin: docs/brainstorms/2026-07-19-evaluate-check-gh-identity-prime-beads-hooks-brainstorm.md
github_issue: 58
---

# feat(hooks): adopt `check-gh-identity` guard; drop `prime-beads-context`

## Overview

Resolve the adopt-or-drop question captured in #58 for the two hooks that closed
PR #26 bundled from `aagnone3/agent-leverage` and no surviving PR carries:

- **`check-gh-identity.py` → ADOPT (adapted).** Add it to the plugin's safety-net
  PreToolUse hook family as an **opt-in** guard that verifies the active `gh`
  identity before GitHub-mutating commands. Silent no-op until a repo/machine
  declares an expected identity.
- **`prime-beads-context.sh` → DROP.** Record it as a `deferred:` provenance entry
  with rationale; do **not** implement it.

The verdicts and their evidence are in the origin brainstorm
(see brainstorm: docs/brainstorms/2026-07-19-evaluate-check-gh-identity-prime-beads-hooks-brainstorm.md).

## Problem Statement / Motivation

The plugin's fork-trap (`block-upstream-pr.sh`) guards *which repository* a `gh`
write targets; `workflow-repo-preflight.py` only reports *authenticated-yes/no*.
**Nothing checks *which* `gh` account is acting.** In a multi-account setup this
lets an agent push or open a PR as the wrong identity — a real footgun with no
existing guard. `check-gh-identity` closes that gap and slots cleanly into the
existing safety-net family (`block-no-verify`, `prevent-main-commit`,
`block-slack-webhook`, `block-db-push`).

`prime-beads-context` pulls the opposite way from a deliberate architectural
decision: Beads is a demoted, non-authoritative scratchpad and GitHub Projects is
the sole authoritative tracker (`plan-tracker-guard.py`,
`nudge-todowrite-to-tracker.py`, `block-beads-jsonl-stage.py`). A `SessionStart`
Beads primer re-elevates what was intentionally demoted, so it is dropped — but
recorded so a future `/upstream-scan` won't re-propose it.

## Proposed Solution

Adopt `check-gh-identity` as an **opt-in** PreToolUse Bash guard following the
plugin's established hook conventions, and close the `prime-beads-context` question
in the provenance registry.

**Opt-in, silent-when-unconfigured (design default).** The hook does nothing unless
the repo/machine declares an expected identity via a frontmatter key in an untracked
`agentic-engineering.local.md` (a *tracked* copy ignored, mirroring
`nudge-todowrite-to-tracker.py`'s `nudge_todowrite`). Unconfigured → allow. This
matches the plugin's settled precedent that per-machine behavior must not ride a PR.

## Technical Considerations

- **Cross-harness parity.** Like every safety guard, it must run on Claude
  (`PreToolUse`/Bash), Cursor (`beforeShellExecution`), and Codex (`PreToolUse`),
  using `hook_payload.py` normalization, `emit_allow()` on the allow path (Cursor
  `failClosed` treats empty stdout as failure), and exit 2 to block. The
  `install-hooks` skill must carry a **byte-identical** bundled copy (enforced by
  `tests/install-hooks-skill-sync.test.ts`).
- **Precision.** Fire only when the command verb is genuinely GitHub-mutating
  (`git push`, `gh pr create`, `gh issue`/`gh api`/`gh project` writes). Read-only
  `gh` calls, quoted strings, comments, and `echo`/`grep` mentions must not
  false-trigger — same quote-strip / segment-aware discipline as the sibling guards.
- **Cost when irrelevant.** No expected-identity configured → resolve to allow
  before any `gh api user` call, so an unconfigured repo pays nothing.
- **`prime-beads-context` writes no code** — documentation-only closure.

## System-Wide Impact

- **Interaction graph:** A new PreToolUse hook fires on matching Bash commands
  before execution; on block it returns exit 2 with the reason on stderr, exactly
  like the existing guards. No other component changes behavior.
- **Error propagation:** Fail-open on malformed stdin / unreadable config (a broken
  guard must never wedge legitimate `gh` use), matching the family's conservatism.
- **API surface parity:** The hook must be wired in all three harness configs +
  the `install-hooks` bundle, or the guard silently won't fire on some platforms.
- **Config surface:** Adds one opt-in `agentic-engineering.local.md` frontmatter
  key — a candidate for the future config registry (#91); note but don't block on it.

## External System Wiring

No external wiring required. The hook shells out to the already-present `gh` CLI
(`gh api user`) and reads local config; no third-party dashboard, webhook, OAuth
app, env var, or credential is introduced.

## Acceptance Criteria

- [ ] `check-gh-identity.py` exists under `plugins/agentic-engineering/scripts/`,
      adapted from the agent-leverage source, using `hook_payload.py`, `emit_allow`,
      and exit-2-to-block.
- [ ] The guard is **opt-in**: silent `allow` when no expected identity is
      configured; blocks a GitHub-mutating command only when the active `gh`
      identity ≠ the configured expected identity.
- [ ] Precise matching: read-only `gh` calls and prose mentions (quotes, comments,
      `echo`/`grep`) are never blocked; false-positive/false-negative edges pinned
      by `tests/check_gh_identity_test.py`.
- [ ] Wired into `plugin.json`, `hooks/hooks-cursor.json`, `hooks/hooks-codex.json`,
      and a byte-identical `skills/install-hooks/scripts/` copy; `HOOKS.md` documents it.
- [ ] `bun test` passes: `install-hooks-skill-sync`, plugin-consistency (component
      counts), and the new hook test all green.
- [ ] `docs/upstream-sources.md` records under `aagnone3/agent-leverage`:
      `adopted:` `check-gh-identity` and `deferred:` `prime-beads-context` (with
      the demoted-Beads rationale and pinned `upstream: …@sha` refs).
- [ ] `prime-beads-context.sh` is **not** added to the codebase.

## Validation

- **Automated:**
  - `python3 -m unittest plugins/agentic-engineering/tests/check_gh_identity_test.py` — new edge tests pass.
  - `bun test` — `install-hooks-skill-sync.test.ts` (byte-identical bundle) and
    plugin-consistency (component counts across `plugin.json` / READMEs / docs) pass.
- **Manual:**
  - With an `expected_gh_identity:` set to a *different* login than the active one,
    `echo '{"tool_name":"Bash","tool_input":{"command":"gh pr create"}}' | python3 scripts/check-gh-identity.py; echo $?`
    → exit 2 (blocked, reason on stderr).
  - With it set to the *active* login (or unset): same command → `{"permission":"allow"}` exit 0.
  - `echo '{"command":"grep -- expected_gh_identity ."}' | …` → allowed (prose mention).
- **Rollback:** revert the PR — removes the script, its wiring in all configs, the
  bundled copy, the test, and the `HOOKS.md` section; the `deferred:` registry entry
  is inert documentation and can stay.

## Success Metrics

- No behavioral change for repos that don't opt in (zero new prompts / blocks).
- For opt-in repos, a wrong-identity `gh` mutation is blocked before it reaches GitHub.

## Dependencies & Risks

- **Design-before-impl:** the expected-identity contract (sub-task 1) gates the
  implementation (sub-task 2); wiring/docs (3) follow the implementation.
- **Risk — over-broad matching** blocks legitimate read-only `gh` use → mitigated by
  the precise-verb tests, mirroring the existing guards.
- **Risk — Cursor `failClosed`** blocks on empty stdout → mitigated by `emit_allow`.
- **Related:** the opt-in flag is future config-registry (#91) surface — note, don't couple.

## Sources & References

- **Origin brainstorm:** [docs/brainstorms/2026-07-19-evaluate-check-gh-identity-prime-beads-hooks-brainstorm.md](../brainstorms/2026-07-19-evaluate-check-gh-identity-prime-beads-hooks-brainstorm.md) — verdicts: adopt `check-gh-identity`, drop `prime-beads-context`; opt-in silent-when-unset design default.
- `plugins/agentic-engineering/scripts/HOOKS.md` — hook family, conventions, cross-harness wiring table.
- `plugins/agentic-engineering/scripts/nudge-todowrite-to-tracker.py` — opt-in local-frontmatter precedent + demoted-Beads doctrine.
- `plugins/agentic-engineering/scripts/workflow-repo-preflight.py` — existing `gh auth` usage (read-only).
- `docs/upstream-sources.md` — `aagnone3/agent-leverage` registry entry (adoption sha `8a428a2d`).
- Related issue: #58. Original bundle: closed PR #26. Config surface: #91.
