# Cross-Agent Asset-Support (Conversion) Policy

How this marketplace decides *which* Claude plugin assets the converter CLI
(`src/`) may transpile into other agent platforms, and how faithfully. The repo
ships one converter per target — `src/converters/claude-to-{claude,codex,copilot,
cursor,droid,gemini,kiro,opencode,pi}.ts` — and "we support 9 agents" hides that
support means radically different things per asset.

Enforced by `tests/conversion-policy.test.ts` (mechanical invariants over
converter/target source text). This document is the human-readable rationale;
the test is the source of enforcement. When the two disagree, the test wins —
fix the code it names, do not relax the assertion.

## The deciding test

> **Support cross-agent conversion only where a shared standard or near-total
> semantic overlap makes conversion nearly free _and_ failure-safe. The moment
> faithful conversion needs per-target mapping tables — especially where a silent
> mis-conversion is harmful — stop at Claude-only.**

Two forces set the bar. **Freeness:** a standard (Agent Skills `SKILL.md`, MCP
config, `AGENTS.md`) means conversion is passthrough, not translation.
**Failure-safety:** where a mistranslation degrades harmlessly (a command that
reads slightly off) conversion is cheap to be wrong about; where it fails
*silently and dangerously* (a security hook that fails **open**) the cost of a
subtle bug dwarfs the value of the feature.

## Per-asset verdict table

| Asset | Verdict | Rationale |
|---|---|---|
| **Skills** | ✅ CONVERT | Agent Skills standard (`SKILL.md`). Solved problem. |
| **Commands** | ✅ CONVERT | Named prompt body + light frontmatter; universal, degrades harmlessly. |
| **MCP servers** | ✅ CONVERT (passthrough) | MCP is the cross-agent standard; near-identical shape everywhere. |
| **Memory / rules (CLAUDE.md)** | ✅ CONVERT | `AGENTS.md` is the emerging cross-agent standard. |
| **Agents (subagents)** | ⚠️ CONVERT BODY ONLY | Port persona/system-prompt + description; **no** per-target tool/model/mode/delegation mapping. Where a target has no subagent concept, emit as skill/command. |
| **Hooks** | ❌ CLAUDE-ONLY (frozen exception: opencode) | No standard; per-target decision protocols; security fail-open risk. Do **not** grow hook conversion. Safety hooks for other agents stay **hand-authored + curated**, never generated. |

### Why hooks are the hard "no"

Hooks have no cross-agent standard. Each target has a different event model,
matcher syntax, and — the killer — **decision protocol** (allow/deny/ask,
`failClosed`, exit codes). A mis-converted *security* hook that silently fails
**open** is worse than no hook at all. This is not hypothetical: commit #171
("emit Cursor allow decision so failClosed hooks stop blocking Shell") was a
hand-fix of hook decision semantics for a single agent — direct proof the
abstraction leaks under maintenance.

The current converters already vote this way, de facto: four converters
(`claude-to-{cursor,copilot,gemini,kiro}.ts`) read `plugin.hooks` only to
`console.warn` and **drop** them; four more (`claude-to-{claude,codex,droid,
pi}.ts`) never read `plugin.hooks` at all. The policy freezes that reality so the
next contributor cannot quietly "add hook support" to another target and
re-introduce the leaky, unsafe surface this decision rejects.

## The opencode exception (deliberate carve-out)

Exactly one converter emits a hook artifact: `claude-to-opencode.ts` maps hooks
into opencode's native TS-plugin format, writing a `converted-hooks.ts` file
artifact. Removing that is a converter refactor and is **out of scope** here, so
the policy **freezes the hook-conversion surface at exactly opencode**: opencode
may keep emitting `converted-hooks.ts`; **no other converter may read
`plugin.hooks` to emit hooks.** This is the precise, enforceable form of "don't
build a hook converter."

Note the emission lives entirely in the **converter**, not the target writer.
The `src/targets/*.ts` writers are hook-agnostic — none of them reference hooks
at all — so the "sole hook-emitter" invariant is asserted at the converter level
(only `claude-to-opencode.ts` mentions `converted-hooks`), and separately the
targets are asserted to stay hook-free.

## Safety hooks: curated, not converted

Security hooks *do* reach other agents — but by **hand-authored curation**, not
conversion. `plugins/agentic-engineering/hooks/hooks-codex.json` and
`hooks-cursor.json` carry a hand-picked subset of the shell-blocking safety
scripts, wired through the **native** `.codex-plugin` / `.cursor-plugin`
manifests. No converter and no build script generates them (zero references under
`src/` and `scripts/`). Their *content* is validated by
`tests/plugin-consistency.test.ts`; this policy asserts only that nothing
*generates* them, so the two tests do not duplicate assertions.

## Invariants

Each item maps 1:1 to a test case in `tests/conversion-policy.test.ts`. The
frozen sets live in clearly-commented constants there; a deliberate policy change
is a one-line, reviewed edit — not a relaxed assertion.

1. **Frozen hook surface.** Among `src/converters/claude-to-*.ts`, the converters
   that reference `plugin.hooks` are **exactly** `{cursor, copilot, gemini, kiro,
   opencode}`; `{claude, codex, droid, pi}` reference it **nowhere**.
2. **Warn-droppers drop.** Each of `{cursor, copilot, gemini, kiro}` contains a
   hooks-related `console.warn` **and** emits no hook artifact (no
   `converted-hooks`).
3. **opencode is the sole hook-emitter.** Among the converters, exactly
   `claude-to-opencode.ts` contains `converted-hooks`; and no `src/targets/*.ts`
   writer references hooks at all (targets are hook-agnostic).
4. **Safety hooks are curated, not generated.** No file under `src/` or
   `scripts/` references `hooks-codex.json` or `hooks-cursor.json` — nothing
   generates them.
5. **Doc↔test linkage.** This document exists and names
   `tests/conversion-policy.test.ts` as its source of enforcement.
