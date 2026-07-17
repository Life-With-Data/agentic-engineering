---
title: "Establish a cross-agent asset-support (conversion) policy"
type: docs
date: 2026-07-17
github_issue: 176
---

# Establish a cross-agent asset-support (conversion) policy

## Overview

The repo ships a Bun/TypeScript converter CLI (`src/`) that transpiles the Claude
`agentic-engineering` plugin into 9 targets (claude, opencode, codex, cursor, droid,
pi, copilot, gemini, kiro). Today every asset type is *treated* as convertible, but
the fidelity and safety vary wildly by asset — and that variance is undocumented and
unenforced. This item codifies a **simplicity-first, per-asset support policy** as a
top-level rationale doc (`docs/conversion-policy.md`) backed by a mechanical guardrail
test (`tests/conversion-policy.test.ts`), mirroring the established
[`docs/dependency-policy.md`](../dependency-policy.md) ↔ `tests/dependency-policy.test.ts`
pair ("doc = rationale, test = truth").

The deciding test the policy encodes:

> **Support cross-agent conversion only where a shared standard or near-total semantic
> overlap makes conversion nearly free _and_ failure-safe. The moment faithful
> conversion needs per-target mapping tables — especially where a silent mis-conversion
> is harmful — stop at Claude-only.**

## Problem Statement / Motivation

"We support 9 agents" hides that support means radically different things per asset:

- **Skills / commands / MCP / memory** convert cleanly because a standard or near-total
  overlap exists (Agent Skills `SKILL.md`, MCP config, AGENTS.md).
- **Agents (subagents)** convert only at the *prompt-body* level; the wiring
  (tool allowlists, model tiers, primary-vs-subagent, delegation) is per-target and leaky.
- **Hooks** have no cross-agent standard. Each target has a different event model,
  matcher syntax, and — the killer — **decision protocol** (allow/deny/ask, failClosed,
  exit codes). A mis-converted *security* hook that silently fails **open** is worse than
  no hook at all.

Evidence this is already the de-facto reality (gathered during review, confirmed by
source audit — see Sources):

- **Per-converter hook audit:** `claude-to-{cursor,copilot,gemini,kiro}.ts` explicitly
  `console.warn`-and-drop hooks; `claude-to-{codex,droid,pi}.ts` never read `plugin.hooks`
  at all; **only `claude-to-opencode.ts` maps them** (into `plugins/converted-hooks.ts`).
- **Hooks are hand-maintained** in `plugins/agentic-engineering/hooks/hooks-codex.json`
  and `hooks-cursor.json` — only 2 agents, only the 4 security shell-blocking scripts, only
  a hand-picked subset, wired through the **native** `.codex-plugin` / `.cursor-plugin`
  manifests (not the converter). No script or converter generates them (confirmed: zero
  references under `src/` and `scripts/`). This is **curation, not conversion.**
- Recent commit #171 ("emit Cursor allow decision so failClosed hooks stop blocking Shell")
  is a hand-fix of hook **decision semantics** for one agent — direct proof the abstraction
  leaks under maintenance.

Without a written+enforced policy, the next contributor will "add hook support" to another
target, re-introducing exactly the leaky, unsafe surface this decision rejects.

## Proposed Solution

Two artifacts plus a cross-link:

1. **`docs/conversion-policy.md`** — the human-readable rationale. States the deciding
   test, then a per-asset verdict table, then the opencode exception, then names the
   enforcing test. Mirrors `dependency-policy.md`'s shape: title → short preamble naming
   the test → thematic `##` sections → a numbered "invariants" section where each bolded
   item maps to a test case. ~90–120 lines, prose-heavy.

2. **`tests/conversion-policy.test.ts`** — the mechanical guardrail. Reads converter/target
   **source text** (no fixtures, no mocks — the `dependency-policy.test.ts` style) and
   asserts the frozen surface. Auto-discovered by `bun test`; requires no changes to any
   existing test.

3. **Cross-link** — the doc names the test as its source of enforcement; the test asserts
   the doc exists and references the test back (a deliberate, light doc↔test linkage that
   `dependency-policy` leaves as convention-only — see Open Questions).

### The per-asset verdict table (to appear in the doc)

| Asset | Verdict | Rationale |
|---|---|---|
| **Skills** | ✅ CONVERT | Agent Skills standard (`SKILL.md`). Solved. |
| **Commands** | ✅ CONVERT | Named prompt body + light frontmatter; universal, degrades harmlessly. |
| **MCP servers** | ✅ CONVERT (passthrough) | MCP is the cross-agent standard; near-identical shape everywhere. |
| **Memory / rules (CLAUDE.md)** | ✅ CONVERT | AGENTS.md is the emerging cross-agent standard. |
| **Agents (subagents)** | ⚠️ CONVERT BODY ONLY | Port persona/system-prompt + description; **no** per-target tool/model/mode/delegation mapping. Where a target has no subagent concept, emit as skill/command. |
| **Hooks** | ❌ CLAUDE-ONLY (frozen exception: opencode) | No standard; per-target decision protocols; security fail-open risk. Do **not** grow hook conversion. Safety hooks for other agents stay **hand-authored + curated**, never generated. |

### The opencode exception (deliberate carve-out)

`claude-to-opencode.ts` already maps hooks to opencode's native TS-plugin format. Removing
that is a converter refactor and is **out of scope for this item** (see Non-Goals). The
policy therefore **freezes the hook-conversion surface at exactly opencode**: opencode may
keep emitting `plugins/converted-hooks.ts`; **no other target may read `plugin.hooks` to
emit hooks.** This is the precise, enforceable form of "don't build a hook converter."

## Technical Considerations

- **Test style:** module-level file reads + regex/set assertions grouped in `describe`
  blocks, no `src/` imports, no fixtures — exactly `tests/dependency-policy.test.ts`.
- **Brittleness is the feature:** asserting an *exact set* of files may reference
  `plugin.hooks` is intentionally strict. A new converter that starts handling hooks
  fails the test, forcing a conscious policy review — the same way `dependency-policy`
  asserts an exact grammar.
- **No overlap with `plugin-consistency.test.ts`:** that test already validates the
  *content* of the hand-authored `hooks-*.json` (safety-script coverage, `failClosed`,
  command-shape regexes). The new test asserts only **non-generation** (no `src/`/`scripts/`
  reference produces them), so the two do not duplicate assertions.

## System-Wide Impact

- **Interaction graph:** none at runtime — this adds a doc and a test. The test runs in the
  existing `bun test` gate (CI).
- **Error propagation:** a policy violation surfaces as a failing test in CI, naming the
  offending converter/target file.
- **State lifecycle risks:** none — no persistent state, no migrations.
- **API surface parity:** the doc becomes a sibling of `docs/dependency-policy.md`; consider
  a one-line pointer from `CLAUDE.md`'s "Manifest constraints / external dependencies" area
  or `AGENTS.md`'s provider checklist so contributors find it (see Acceptance Criteria).
- **Integration test scenarios:** covered by the guardrail test itself.

## External System Wiring

**No external wiring required.** Pure in-repo documentation + test.

## Acceptance Criteria

- [ ] **`docs/conversion-policy.md` exists**, mirroring `docs/dependency-policy.md`'s
      structure: a title, a short preamble that **names `tests/conversion-policy.test.ts`
      as the source of enforcement** ("this document is the human-readable rationale; the
      test is the source of enforcement"), the deciding-test statement, the per-asset
      verdict table (CONVERT / CONVERT-BODY-ONLY / CLAUDE-ONLY), the opencode carve-out,
      and a numbered "invariants" section whose items map 1:1 to test cases.
- [ ] **`tests/conversion-policy.test.ts` exists** and mechanically asserts, at minimum:
  - [ ] **Frozen hook surface:** among `src/converters/claude-to-*.ts`, the files that
        reference `plugin.hooks` are **exactly** `{cursor, copilot, gemini, kiro, opencode}`;
        `{claude, codex, droid, pi}` reference it **nowhere**.
  - [ ] **Warn-droppers drop:** each of `cursor, copilot, gemini, kiro` contains a
        hooks-related `console.warn` and emits **no** hook field/artifact.
  - [ ] **opencode is the sole hook-emitting target:** among `src/targets/*.ts`, only
        `opencode.ts` contains a hook-output write; the other 8 writers reference no hook
        output.
  - [ ] **Safety hooks are curated, not generated:** `hooks-codex.json` / `hooks-cursor.json`
        are referenced by **zero** files under `src/` and `scripts/` (no generator).
  - [ ] **Doc↔test linkage:** `docs/conversion-policy.md` exists and contains the literal
        string `tests/conversion-policy.test.ts`.
- [ ] The policy doc **points at the test** as the source of enforcement, per the repo's
      "the test is the source of truth" convention.
- [ ] A discoverability pointer to the new policy exists from at least one of `CLAUDE.md` /
      `AGENTS.md` (a single line, next to the existing dependency-policy references).
- [ ] **All gates pass:** `bun test`, `bun run typecheck`, and `bun run docs:check` are green.

## Validation

**How a reviewer proves this behaves — not that it compiles.**

- **Automated:**
  - `bun test tests/conversion-policy.test.ts` → all new assertions pass.
  - **Negative proof (do + revert):** temporarily add a `plugin.hooks` reference to
    `src/converters/claude-to-codex.ts` and confirm `bun test tests/conversion-policy.test.ts`
    **fails** naming codex; revert. This proves the guardrail actually bites.
  - `bun test` (full suite) and `bun run typecheck` → green (no regressions;
    `plugin-consistency` still passes).
  - `bun run docs:check` → green (adding a plain `docs/*.md` does not trip generated-docs
    drift — confirmed: `generate-docs.ts` does not enumerate top-level `docs/*.md`).
- **Manual:** read `docs/conversion-policy.md` end-to-end; confirm each numbered invariant
  has a corresponding `test()` and the verdict table matches the six rows above.
- **Rollback:** delete both new files and the CLAUDE.md/AGENTS.md pointer line; no other
  code references them, so revert is clean and self-contained.

## Success Metrics

- A contributor attempting to add hook conversion to a non-opencode target is stopped by a
  red CI check that names the file and points at the policy — zero silent expansions.
- The policy is discoverable (linked from CLAUDE.md/AGENTS.md) so the decision is not
  re-litigated in future PRs.

## Dependencies & Risks

- **Risk — over-strict test causes false failures on legitimate refactors.** Mitigation:
  assert on `plugin.hooks` references and hook-output writes specifically, not on incidental
  substrings; keep the allowed-set list in one clearly-commented constant so a deliberate
  policy change is a one-line, reviewed edit (mirroring `dependency-policy`'s directive
  comment: "if this fails, fix the thing it names — do not relax the assertion").
- **Risk — the opencode carve-out reads as inconsistent with 'Claude-only'.** Mitigation:
  the doc states the carve-out explicitly and records the removal question as an open item.
- **No blocking dependencies.** Net-new doc + test; no schema, no external system.

## Open Questions

1. **Should opencode's hook conversion also be removed** to make hooks *purely* Claude-only?
   The decision's rationale (decision-protocol leak, security fail-open) arguably applies to
   opencode too, but removal is a converter refactor (out of scope here). **Deferred:** this
   item freezes+grandfathers opencode and records the question; a future item can decide
   removal. Flagged in the groomed packet.
2. **Codify doc↔test linkage as a repeatable convention?** `dependency-policy` leaves it as
   convention-only. This item adds a light linkage assertion; whether to backport the same
   check to the dependency pair is out of scope.

## Sources & References

### Internal References
- Pattern to mirror (doc): [docs/dependency-policy.md](../dependency-policy.md)
- Pattern to mirror (test): `tests/dependency-policy.test.ts` — read-source + regex/set
  assertions in `describe` blocks; header directive comment; no `src/` imports.
- Hook audit (converters): `src/converters/claude-to-{cursor,copilot,gemini,kiro}.ts`
  (warn-drop), `claude-to-{codex,droid,pi,claude}.ts` (no `plugin.hooks` ref),
  `claude-to-opencode.ts:72,158-191` (maps hooks).
- Hook output write: `src/targets/opencode.ts:82-87` → `plugins/converted-hooks.ts`
  (the sole hook-emitting writer).
- Hand-authored safety hooks: `plugins/agentic-engineering/hooks/hooks-codex.json`,
  `hooks-cursor.json`; validated (content) by `tests/plugin-consistency.test.ts` (native
  `.codex-plugin`/`.cursor-plugin` manifests), generated by nothing.
- Drift-safety: `scripts/generate-docs.ts` does not enumerate top-level `docs/*.md`;
  `bun test` auto-discovers `tests/*.test.ts` with no file-count gate.

### Related Work
- Commit #171 — "emit Cursor allow decision so failClosed hooks stop blocking Shell"
  (evidence the per-agent hook decision-protocol leaks).
- `AGENTS.md` — "Adding a New Target Provider" checklist (the code counterpart this policy
  bounds).
