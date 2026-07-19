---
title: "test: re-key config-registry meta.get allowlist by stable key, not line number"
type: test
date: 2026-07-19
github_issue: 203
---

# 🧪 Re-key the config-registry `meta.get` allowlist by a stable identifier, not line number

Re-key the `ALLOWLIST` in [`tests/config-registry.test.ts`](../../tests/config-registry.test.ts) so its entries no longer carry a source line number. Today each entry is keyed by `"<plugin>:<relpath>:<line>"` (e.g. `"agentic-engineering:scripts/lifecycle_board.py:1089"`), so **any insertion above an allowlisted read shifts its line and silently breaks the test** — it surfaces as a confusing pair of failures (a "stale allowlist entry" *and* an "unregistered read") that have nothing to do with the change that triggered them. This is exactly the churn seen in [#202](https://github.com/Life-With-Data/agentic-engineering/pull/202), where adding code above `find_docs_for_issue` shifted the read from line 948 → 1089 and forced a pure-churn allowlist-key bump.

Re-key on the **stable key literal** — `"<plugin>:<relpath>:<key>"` — for both the forward check and the stale-entry check, and add a focused assertion proving the new keying survives a line shift.

## Context

- The scanner ([`tests/config-registry.test.ts`](../../tests/config-registry.test.ts)) matches `meta.get("literal")` reads via the `META_GET` regex (L60) and, for each hit, builds `allowKey = "<plugin>:<rel>:<line>"` (L126). It skips a read if `allowKey in ALLOWLIST` (L127-130), else requires the key be registered in `config_registry.py` (L131). The stale check asserts every `<plugin>:*` allowlist entry was matched (`unusedAllow`, L120-122 / L147-150).
- There is exactly **one** allowlist entry today (L32-36): the `github_issue` read in `find_docs_for_issue` (`plugins/agentic-engineering/scripts/lifecycle_board.py:1089`), which is a `docs/plans/*.md` plan-tracker field, **not** an `agentic-engineering(.local).md` config flag — so it is correctly allowlisted rather than registered.
- **Collision safety is verified.** A repo-wide scan (`grep -rnE "meta\.get\(\s*['\"][A-Za-z_][\w-]*['\"]" plugins/*/scripts/*.py`) shows `github_issue` appears as a `meta.get("literal")` read **exactly once**. The other literal reads — `github_project_owner`/`github_project_number` (`lifecycle_board.py:417-418`), `issue_tracker` (`plan-tracker-guard.py:137`), `nudge_todowrite` (`nudge-todowrite-to-tracker.py:85`) — are all **registered** config flags, so none are allowlisted and none collide. Keying by `<plugin>:<relpath>:<key>` is therefore unambiguous today.
- **Guard the collision assumption for the future.** So a *later* second `meta.get("github_issue")` read in the same file can't silently share an allowlist waiver, keep the scan collision-aware: when two allowlisted reads would map to the same `<plugin>:<relpath>:<key>`, that is a hard failure (the entry must then be split by enclosing symbol) rather than a silent double-waiver. This preserves the option #203 flagged ("combine with enclosing-function name") without paying its parsing cost now.
- This aligns with the repo's guardrail-test doctrine — **assert the invariant category, not a frozen literal** (see [`docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md`](../../docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md)). A line number is a frozen literal; the enclosing (plugin, file, key) tuple is the stable invariant.

## Approach

Recommended: **key-literal** (`"<plugin>:<relpath>:<key>"`) — simplest, and collision-safe as verified above.

1. Change the single `ALLOWLIST` entry key from `…lifecycle_board.py:1089` to `…lifecycle_board.py:github_issue` (keep the same justification string).
2. In the forward check, build `allowKey` from `hit.key` instead of `hit.line` (`"<plugin>:<hit.rel>:<hit.key>"`). The violation message may still *report* `hit.line` for locate-ability (line number in the message is fine — it just must not be part of the key).
3. The stale-entry check (`unusedAllow`) already keys off `ALLOWLIST` keys, so it inherits the new keying with no logic change beyond matching the new key shape.
4. Add a collision guard: if two distinct reads resolve to the same `allowKey` and both are allowlisted, fail with a clear message telling the author to split by enclosing symbol.
5. Add a focused test that proves line-shift robustness of the keying (a unit-level assertion over the key-builder, or a comment-documented invariant), so a future line shift can never reintroduce the churn.

Fallback (only if a same-key collision ever arises): key by `"<plugin>:<relpath>:<enclosing-symbol>:<key>"`, parsing the nearest preceding `def ` — deferred until actually needed.

## Acceptance Criteria

- [ ] `ALLOWLIST` keys carry **no line number**; the forward check and the stale-entry check both key off the stable `<plugin>:<relpath>:<key>` identifier.
- [ ] The `find_docs_for_issue` `github_issue` read remains allowlisted and passing.
- [ ] Adding or removing lines above an allowlisted read no longer breaks the test.
- [ ] A same-key collision between two allowlisted reads fails loudly (not a silent double-waiver).
- [ ] A focused assertion/guardrail proves the keying survives a line shift.
- [ ] `bun test` and `bun run typecheck` pass.

## Validation

- **Automated:** `bun test` (whole suite, incl. `tests/config-registry.test.ts`) and `bun run typecheck` both green.
- **Manual line-shift check:** insert a blank line above the allowlisted `meta.get("github_issue", "")` read in `plugins/agentic-engineering/scripts/lifecycle_board.py`, run `bun test` and confirm `config-registry.test.ts` still passes, then revert the blank line.
- **Negative check (intent preserved):** temporarily add a new unregistered `meta.get("bogus_key")` read to a `plugins/agentic-engineering/scripts/*.py` file and confirm `bun test` fails with the "Unregistered config-flag read" message, then revert.
- **Rollback:** the change is confined to `tests/config-registry.test.ts`; revert that file to restore prior behavior.

## Sources

- Issue: #203
- Motivating PR (line-shift churn): [#202](https://github.com/Life-With-Data/agentic-engineering/pull/202)
- Target file: [`tests/config-registry.test.ts`](../../tests/config-registry.test.ts) — `ALLOWLIST` (L32), forward check (L116-134), stale check (L147-150)
- Allowlisted read: `plugins/agentic-engineering/scripts/lifecycle_board.py:1089` (`find_docs_for_issue`, def L1075)
- Doctrine: [`docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md`](../../docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md)
