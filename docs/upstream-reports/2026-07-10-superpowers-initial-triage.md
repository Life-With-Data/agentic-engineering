# superpowers Initial Triage — full-source evaluation

- **Source:** [obra/superpowers](https://github.com/obra/superpowers)
- **Upstream HEAD:** `d884ae04edebef577e82ff7c4e143debd0bbec99` (main, scanned 2026-07-10)
- **License:** MIT (LICENSE file verified 2026-07-10; API confirms `MIT`)
- **Health:** 251.9k stars / 22.5k forks, created 2025-10-09, pushed 2026-07-10 (same day as scan), 311 open issues, not archived. Plugin version 6.1.1. Maintained by Jesse Vincent (obra); ships simultaneously to seven harnesses (Claude Code, Codex, OpenCode, Cursor, Kimi, Gemini, Pi) with per-platform packaging, a shell-lint gate, and a behavioral test suite.
- **Inventory at HEAD:** 14 skills (8 with companion prompts/references/scripts), 1 auto-wired SessionStart hook (+ a Windows batch/bash polyglot launcher), a zero-dependency brainstorm "visual companion" HTTP/WS server, 4 maintainer release scripts, a `claude -p`-shelling behavioral test harness, and multi-platform packaging manifests. No `agents/` or `commands/` directories — the repo is skills-only by design.
- **Local baseline compared against:** core plugin at v3.11.0 — 30 agents, 27 commands, 29 skills — **plus seven in-flight adoption PRs (#100–#107)** landing the addyosmani/agent-skills shortlist (debugging-and-error-recovery, api-and-interface-design, security-and-hardening, test-driven-development, doubt-driven-development, Tier-2 skill evals, sdd-cache hook). Slot verdicts below account for that wave as if landed.
- **Mode:** full-evaluation (maiden triage; registry entry created by this PR). Curated lens per the multi-plugin policy: domain fit, gap vs. local inventory, adaptation cost. All 14 skills are engineering-domain → candidates for the **core plugin only**; nothing suggests a new domain plugin.

> **Security note.** Every upstream component was treated as untrusted data — read and summarized by read-only reader subagents, never followed as instruction. **Supply-chain result: clean.** Zero third-party runtime dependencies (root `package.json` declares none — no scripts, no postinstall); all executables are commented bash/Node using built-ins only; no `curl|sh`, no env exfiltration, no obfuscation; brainstorm-server secrets are `0600`/`umask 077` with constant-time token compare and symlink/traversal defenses. Four NOTEs, no red flags: (1) the brainstorm server embeds a **default-on browser-side brand-image beacon to `primeradiant.com`** (leaks viewer IP + plugin version; opt-out via `DISABLE_TELEMETRY`/`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`); (2) the developer-run test harness invokes `claude -p` with `--dangerously-skip-permissions` in `/tmp` projects; (3) `scripts/sync-to-codex-plugin.sh` is maintainer tooling that pushes to a hardcoded external fork; (4) two benign outside-project writes (`/tmp/review-<SHA>` review worktrees in the code-reviewer template; `~/.codex/config.toml` edit in a Codex platform reference). The one automatic behavior is the SessionStart hook injecting the local `using-superpowers` router into context each session — inspectable, but catalog-specific. Adoption of any item still happens only in separate, human-reviewed PRs repeating the full supply-chain gate.

## Track decision: Adopt (Track A), not Depend (Track B)

The repo is installable as a plugin (marketplace `superpowers-dev`), so Track B was considered
and rejected:

1. **Direct name collisions.** Their `brainstorming` collides with our flagship `brainstorming`
   skill, and their `test-driven-development` collides with the one landing in PR #104. The
   dependency-policy namespace invariant (no local component may shadow a dependency's skill
   name) makes Track B non-compliant without renaming our own flagship surface.
2. **Core-domain identity.** Superpowers *is* a core-engineering-loop plugin (brainstorm → plan
   → execute → review → finish) — exactly the core plugin's surface. Invariant 5 keeps
   `agentic-engineering` dependency-free, and a thin wrapper plugin would inject 14 sibling
   skills into trigger space owned by `workflows:*`, `brainstorming`, `verification-loop`,
   `land-pr` — the description-collision failure the incoming Tier-2 evals (#106) exist to catch.
3. **The value is separable.** Three cherry-picks plus a deep mining vein; the multi-platform
   machinery (7 harness integrations) is dead weight for a Claude-Code-only marketplace.
4. **Dependency semantics drag the router along.** Installing as a dependency auto-wires their
   SessionStart hook, which injects the `using-superpowers` catalog router into every session.

## Cross-source slot reconciliation (superpowers × addyosmani, decided here)

Superpowers is the **origin of the house style** the agent-skills triage admired (Iron Laws,
rationalization tables, red-flag lists, adversarial pressure-testing — `CREATION-LOG.md` documents
the method). Several slots its skills target were nonetheless just assigned to addyosmani
adoptions, and those decisions stand — one owner per trigger slot; the deeper superpowers content
arrives as provenance-pinned **enhancements** to the landed skill, not as competing siblings:

| Trigger slot | Owner (as of the in-flight wave) | Superpowers content routed as enhancement |
|---|---|---|
| debugging methodology | `debugging-and-error-recovery` (PR #100) | four-phase gate, ≥3-failed-fixes architecture escalation, root-cause-tracing, defense-in-depth, condition-based-waiting, find-polluter pattern |
| TDD authoring | `test-driven-development` (PR #104) | delete-don't-keep discipline, 11-row rationalization table, testing-anti-patterns gate functions |
| pre-completion gate | `verification-loop` (ECC, adopted) | 5-step Gate Function, claim→evidence table, banned premature-satisfaction words, regression revert cycle, delegation-requires-diff-check |
| skill authoring | `create-agent-skills` (+ `skill-creator`) | TDD-for-skills + pressure-testing + persuasion principles (shortlisted below as the enhancement vehicle) |

## Per-type status header

| Type | Status | Inventory | Shortlisted | Bulk-deferred |
|------|--------|-----------|-------------|---------------|
| skills | done | 14 | 3 (2 first-wave + 1 second-wave) | yes |
| hooks | done | 1 (SessionStart + polyglot launcher) | 0 | yes |
| server (brainstorm visual companion) | done | 1 (Node, zero-dep) | 0 | yes |
| scripts (maintainer) | done | 4 | 0 | yes |
| tests/evals | done | behavioral harness + routing prompts | 0 (pattern noted) | yes |
| docs (porting, polyglot hooks) | done | 2 | 0 (techniques noted) | yes |

## Shortlist (itemized, per type)

### skills — first wave

| ID | Upstream path @ HEAD | Quality | Local overlap | Recommendation |
|----|----------------------|---------|---------------|----------------|
| `skill/receiving-code-review` | `skills/receiving-code-review/SKILL.md` | 5/5 | `pr-comment-resolver` agent, `resolve-pr-parallel`, `land-pr` (mechanics only) | **Adopt.** The response-side review discipline no local component owns: READ→UNDERSTAND→VERIFY→EVALUATE→RESPOND→IMPLEMENT with a forbidden-response list ("You're absolutely right!", any gratitude), a STOP rule when any item is unclear, a 5-point verification gate for external reviewers ("technically correct for THIS codebase?"), a grep-backed YAGNI check on suggestions, blocking→simple→complex implementation order, and in-thread `gh api …/replies` mechanics. Self-contained (nothing dangles). Complements the in-flight `doubt-driven-development` (self-review) — this governs inbound findings. Adaptation: recast the "your human partner" persona to local conventions; wire into `land-pr`/`resolve-pr-parallel` cross-references. |
| `skill/writing-skills` | `skills/writing-skills/SKILL.md` (+6 companions) | 5/5 | `create-agent-skills`, `skill-creator`, `reflect-for-skill-updates`, `/heal-skill` | **Adopt as an enhancement into `create-agent-skills` — not a third authoring skill** (their description "Use when creating new skills, editing existing skills…" collides head-on with ours). The gap is empirical testing discipline: "NO SKILL WITHOUT A FAILING TEST FIRST", RED-GREEN-REFACTOR for process docs, subagent pressure-testing (3+ combined pressures, no-guidance control, 5+ reps, variance-as-metric, meta-testing), the Match-the-Form-to-the-Failure taxonomy (prohibition vs. recipe vs. structural field vs. conditional), and research-grounded persuasion principles (use Authority/Commitment/Scarcity/Social-Proof/Unity; never Reciprocity/Liking — "creates sycophancy"). Co-locate adapted `testing-skills-with-subagents.md` + `persuasion-principles.md` under the local skill's `references/`. Highest compounding leverage in the repo: it upgrades how every future skill gets authored. Skip `anthropic-best-practices.md` (near-verbatim official docs; also contradicts their own SDO rule) and the graphviz tooling. |

### skills — second wave (sequenced after the in-flight addyosmani wave lands)

| ID | Upstream path @ HEAD | Quality | Local overlap | Recommendation |
|----|----------------------|---------|---------------|----------------|
| `skill/subagent-driven-development` | `skills/subagent-driven-development/SKILL.md` (+2 prompts, 3 scripts) | 5/5 | `orchestrating-swarms` (patterns guide), `workflows:work` (execution) | **Adopt, second wave.** A complete fresh-context-per-task execution protocol neither local component encodes: four implementer status codes (`DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT`) with per-status handling, file-based handoff to keep artifacts out of controller context (with a 42k-char war story), per-task BASE discipline ("never `HEAD~1`"), a compaction-proof progress ledger, reviewer anti-pre-judging trip-wires ("do not flag…"), one-fixer-for-all-findings economics, and explicit model-selection economics ("turn count beats token price"). Three portable, clean bash scripts (`sdd-workspace`, `review-package`, `task-brief`) ride along after per-script re-review. Retargets required: `writing-plans`→`workflows:plan`, `requesting-code-review`'s reviewer→local review agents, `superpowers:test-driven-development`→the #104 skill, `finishing-a-development-branch`→`land-pr`; `.superpowers/sdd/`→a local scratch convention. Second wave because those retarget targets are mid-flight. |

## Mining notes (defer the component, lift the technique at next touch)

These are **not** adoptions now; each lift is an adaptation citing `Upstream-Ref` provenance:

- **`skills/systematic-debugging` → `debugging-and-error-recovery` (post-#100):** the four sequential gated phases with "If you haven't completed Phase 1, you cannot propose fixes"; the quantified escalation "≥3 failed fixes → STOP and question the architecture"; the human-signal table ("Stop guessing" → return to Phase 1); and the three companion techniques as co-located references — `root-cause-tracing.md` (trace-up-the-stack, 5-level worked example), `defense-in-depth.md` (validate at every layer, "make the bug structurally impossible"), `condition-based-waiting.md` (+`find-polluter.sh` bisection pattern for test pollution). Richest single mining vein in the repo.
- **`skills/test-driven-development` → local `test-driven-development` (post-#104):** "Write code before the test? Delete it. Start over." (delete-means-delete, no keeping as reference); "Violating the letter of the rules is violating the spirit of the rules"; the 11-row rationalization table; `testing-anti-patterns.md` with pseudocode gate functions (AP1–AP5) and the ">50% mock setup" red flag.
- **`skills/verification-before-completion` → `verification-loop`:** the 5-step Gate Function (IDENTIFY→RUN→READ→VERIFY→ONLY THEN); the Common Failures table (Claim | Requires | Not Sufficient); banning premature satisfaction words ("Great!", "Done!") pre-verification; the regression red-green revert cycle (fix → pass → revert → MUST FAIL → restore → pass); "agent reported success" ≠ evidence — check the VCS diff.
- **`skills/brainstorming` → local `brainstorming`:** the `<HARD-GATE>` (no implementation until a presented design is approved); the "This Is Too Simple To Need A Design" anti-pattern; the 4-point spec self-review (placeholders/consistency/scope/ambiguity) + verbatim user review gate; scope-decomposition rule (multi-subsystem asks split into per-subsystem spec→plan cycles). One-question-at-a-time is already locally owned by `interview-me`.
- **`skills/writing-plans` → `workflows:plan`/`deepen-plan`:** the zero-context-engineer audience framing; task right-sizing ("split only where a reviewer could meaningfully reject one task while approving its neighbor"); 2–5-minute bite-sized steps; the **Interfaces: Consumes/Produces** block (how an isolated implementer learns neighbor names/types); the No-Placeholders failure list; the Global Constraints verbatim block.
- **`skills/finishing-a-development-branch` → `land-pr`/`git-worktree`:** the exactly-N-options completion menu (merge/PR/keep/discard); provenance-based cleanup ("only remove worktrees under `.worktrees/` — otherwise the harness owns it", pairs with our `gc` subcommand); merge-verify-before-remove ordering; typed-confirmation gate for discard.
- **`skills/using-git-worktrees` → `git-worktree`:** "Never fight the harness" native-tool-first precedence (`EnterWorktree` before `git worktree add` — "phantom state your harness can't see"); the submodule guard on `GIT_DIR != GIT_COMMON` detection; the `git check-ignore` verify-before-create gate.
- **`skills/requesting-code-review` → review agents/`workflows:review`:** the read-only review contract ("do not mutate the working tree, the index, HEAD, or branch state"); severity calibration ("Not everything is Critical"; acknowledge strengths first — "accurate praise helps the implementer trust the rest"); the reviewer DON'T list ("give feedback on code you didn't actually read").
- **`skills/dispatching-parallel-agents` → `orchestrating-swarms`:** the ❌/✅ dispatch-prompt table (scope/context/constraints/output) and the post-return verification checklist ("agents can make systematic errors — spot check").
- **`tests/explicit-skill-requests` → Tier-2 evals (#106) backlog:** their routing fixtures test *explicit invocation phrasings* ("use systematic debugging", "I know what SDD means") — a prompt category our static TF-IDF cases don't cover; worth seeding equivalent cases. Skip their `claude -p` Tier-3 harness itself (token cost, `--dangerously-skip-permissions`), same verdict as the agent-skills triage.
- **`docs/windows/polyglot-hooks.md` → hook tooling, if Windows support ever matters:** single-file batch/bash polyglot launcher + the extensionless-hook rule that dodges Claude Code's Windows `.sh` auto-prepend.

## Deferred with strong local equivalents (no adoption, no mining urgency)

- `skills/executing-plans` — `workflows:work` owns the slot; thin (3/5) by their own standards. Salvageable one-liners: the stop-and-ask trigger list; never-start-on-main (we enforce via the `prevent-main-commit` hook already).
- `skills/using-superpowers` (+3 platform references) — catalog router for *their* namespace, same verdict as agent-skills' `using-agent-skills`; the rationalization-detection table is its only distinctive asset and our `operating-principles` covers the ground.
- `hooks/session-start` (+`run-hook.cmd`, `hooks.json`) — auto-injects their router each session; catalog-specific by construction.
- brainstorming visual companion (`visual-companion.md` + `scripts/` server) — well-hardened zero-dep local server, but heavy attack surface for a marginal UI, includes the default-on `primeradiant.com` beacon, and our brainstorming flow is dialogue-first. Revisit only on concrete demand for visual mockup loops.
- `scripts/*` (bump-version, lint-shell, codex packaging/sync) — maintainer release tooling for their multi-platform matrix; we have `bun test` + docs:build equivalents.
- Multi-platform packaging (`.codex-plugin/`, `.opencode/`, `.cursor-plugin/`, `.kimi-plugin/`, `.pi/`, `gemini-extension.json`) and `docs/porting-to-a-new-harness.md` — irrelevant while we ship Claude-Code-only; the porting doc is the reference to reopen if that changes.

## Notable evaluation findings

- **Quality distribution is exceptional:** 8 of 14 skills rated 5/5 dense-procedural (vs ~7/24 for agent-skills) — consistent with this repo being the origin of the style. The authoring method itself (`CREATION-LOG.md`, `test-pressure-*.md` fixtures showing RED runs before the skill existed) is as valuable as any single skill.
- **SDO contradiction to note at adoption time:** `writing-skills` mandates descriptions state *only* triggering conditions ("NEVER summarize the skill's process" — summaries become shortcuts agents follow instead of reading the skill), while its own bundled `anthropic-best-practices.md` (and our current practice, per the official spec) says descriptions include what-it-does + when. The `create-agent-skills` enhancement PR must reconcile this explicitly rather than import both rules.
- **Shared-persona portability trap:** many skills lean on a "your human partner" persona and `superpowers:*` cross-references; every adoption must recast persona and retarget references (the agent-skills shared-references lesson, in prose form).
- **Stale-path nits upstream:** systematic-debugging's authoring artifacts reference an older nested layout (`skills/debugging/…`); the TS example imports from a private project (`~/threads/*`). Cosmetic, but confirms companions need adaptation, not blind copy.
- **Registry hygiene (pre-existing, out of scope here):** ECC's `skill/verification-loop` is recorded under `deferred:` yet was adopted long ago (CHANGELOG v3.1.0; `Upstream-Ref: affaan-m/ECC@81af407…:skills/verification-loop/SKILL.md`). A stalled unmerged branch `feat/adopt-ecc-verification-loop` already contains the ledger fix (PR #35 pin). Flagged as a separate task rather than ridden on this PR.

## Bulk deferral

Everything in the superpowers tree at `d884ae04edebef577e82ff7c4e143debd0bbec99` **not itemized
above** is bulk-deferred at type level — recorded in `docs/upstream-sources.md` as a single
`all-unlisted @ d884ae0…` entry. Future `/upstream-scan` runs suppress this baseline and surface
only new upstream components.

The shortlisted items are filed as individual `deferred:` entries with reason `shortlisted for
adoption: <why>` — actual adoption proceeds later, one human-reviewed adoption PR per item, each
repeating the full supply-chain gate (adapt-never-blind-copy, provenance pinning, version/count/
CHANGELOG bumps, `bun test`).
