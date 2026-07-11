# agent-skills Initial Triage — full-source evaluation

- **Source:** [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
- **Upstream HEAD:** `4e8bd9fde4a38cd009053e649f4cdc7cd36b568b` (main, scanned 2026-07-10)
- **License:** MIT (LICENSE file verified 2026-07-10; API confirms `MIT`)
- **Health:** 76.9k stars / 8.3k forks, created 2026-02-15, pushed 2026-07-10 (same day as scan), not archived. Multi-job CI (structure validation, trigger-routing evals, command-dialect parity, plugin-install smoke test). Actively maintained by a high-profile author.
- **Inventory at HEAD:** 24 skills, 4 agents, 8 commands (×3 dialects: Claude `.md`, Gemini `.toml`, Antigravity `.toml`), 4 hook scripts (1 auto-wired SessionStart + 3 opt-in), 7 repo-root reference checklists, an eval harness (`scripts/run-evals.js` + 24 case files), 2 validators. Also ships `.codex-plugin/`, `.opencode/`, and `.agents/` integrations — the repo is simultaneously a plugin for five agent tools.
- **Local baseline compared against:** core plugin at v3.8.0 — 30 agents, 26 commands, 27 skills — plus the `marketing` domain plugin.
- **Mode:** full-evaluation (maiden triage; registry entry created by this PR). Curated lens per the multi-plugin policy: domain fit, gap vs. local inventory, adaptation cost. All 24 skills are engineering-domain → candidates for the **core plugin only**; no content suggests a new domain plugin.

> **Security note.** Every upstream component was treated as untrusted data — read and summarized by credential-free reader subagents, never followed as instruction. **Supply-chain result: clean across the repo.** Zero npm dependencies (no `package.json`); scripts import only Node built-ins; no `curl|sh`, no env exfiltration, no writes outside the project tree. The only network I/O is in the opt-in sdd-cache hooks (conditional `HEAD` revalidation against the URL the agent already asked WebFetch for) and `browser-testing-with-devtools`'s `npx -y chrome-devtools-mcp@latest` setup line (unpinned `@latest` — low-grade note, not a red flag). Several skills are actively security-positive (untrusted-error-output discipline, browser profile isolation, OWASP LLM Top 10 mappings). Adoption of any item still happens only in separate, human-reviewed PRs repeating the full supply-chain gate.

## Track decision: Adopt (Track A), not Depend (Track B)

The repo is installable as a plugin (marketplace `addy-agent-skills`), so Track B was
considered and rejected:

1. **Core-domain collision.** Its surface is exactly our core plugin's domain (plan → build →
   review → ship). Invariant 5 keeps `agentic-engineering` dependency-free, and a thin wrapper
   plugin would duplicate our own flagship surface rather than extend it.
2. **Routing collisions.** Installing 24 sibling skills wholesale would put `code-review-and-quality`,
   `planning-and-task-breakdown`, `spec-driven-development`, etc. in the trigger space already owned
   by `workflows:*`, `land-pr`, `compound-docs`, `frontend-design` — the exact description-collision
   failure its own Tier-2 eval guards against.
3. **The value is separable.** The commands are thin wrappers over their skill namespace; the
   durable value is individual skills, two hooks, the checklists, and one harness pattern —
   classic cherry-pick material.

## Per-type status header

| Type | Status | Inventory | Shortlisted | Bulk-deferred |
|------|--------|-----------|-------------|---------------|
| skills | done | 24 | 7 (5 first-wave + 2 second-wave) | yes |
| agents | done | 4 | 0 (1 mining note) | yes |
| commands | done | 8 ×3 dialects | 0 | yes |
| hooks | done | 4 scripts | 1 (`hook/sdd-cache`) | yes |
| references | done | 7 | 0 adopted standalone (ride along with their skills) | yes |
| scripts/evals | done | 3 scripts + 24 cases | 1 (`script/run-evals`, pattern-level) | yes |

## Shortlist (itemized, per type)

### skills — first wave

| ID | Upstream path @ HEAD | Quality | Local overlap | Recommendation |
|----|----------------------|---------|---------------|----------------|
| `skill/doubt-driven-development` | `skills/doubt-driven-development/SKILL.md` | 5/5 | `verification-loop` (post-hoc gates), `operating-principles` | **Adopt.** In-flight adversarial review: CLAIM → EXTRACT → DOUBT → RECONCILE → STOP with a no-CLAIM-to-reviewer anti-bias rule, 4-class finding reconciliation, 3-cycle bound, "doubt theater" checkable signal, and a fully-gated cross-model escalation protocol (read-only sandbox, stdin-not-argv, per-invocation authorization). Complementary to our post-hoc loop. Adaptation: retarget `references/orchestration-patterns.md` and the `agents/` roster to `orchestrating-swarms` + our review agents. |
| `skill/interview-me` | `skills/interview-me/SKILL.md` | 5/5 | `brainstorming` (adjacent, downstream) | **Adopt.** Confidence-gated intent extraction: mandated `HYPOTHESIS/CONFIDENCE ~N% — missing:` format, one question at a time each with a falsifiable `GUESS:`, a "want vs. should-want" buzzword detector, anti-sycophancy rule, and a concrete stop condition. Self-contained; explicitly forbids non-interactive contexts. No local equivalent for the pre-planning moment. |
| `skill/observability-and-instrumentation` | `skills/observability-and-instrumentation/SKILL.md` | 5/5 | none (nearest: `performance-oracle`) | **Adopt.** Genuine gap. Signal-selection table (log vs metric vs trace), RED/USE, hard cardinality denylist (`user_id`/`email`/`request_id` never labels), percentiles-never-averages, symptom-vs-cause alert tables, verify-the-telemetry step. Co-locate `references/observability-checklist.md` into the skill's own `references/`. |
| `skill/security-and-hardening` | `skills/security-and-hardening/SKILL.md` | 5/5 | `security-sentinel` agent (audit-time) | **Adopt.** Build-time hardening playbook: STRIDE-per-trust-boundary, Always/Ask-first/Never tiers, SSRF allowlist implementation that names its own TOCTOU/DNS-rebinding gap, reachability-keyed `npm audit` triage tree, OWASP LLM01–LLM10 mapping with model-output-is-data example. The "how to build it safely" companion to our "did they build it safely" agent. Co-locate `references/security-checklist.md`. |
| `skill/test-driven-development` | `skills/test-driven-development/SKILL.md` | 5/5 | `test-strategy-reviewer` (review-time) | **Adopt.** Authoring discipline: Prove-It (failing repro test before any bug fix), Google-style test-size resource model, real>fake>stub>mock preference order, state-not-interactions, don't-re-run-green-suites efficiency rule. Our reviewer grades tests; this writes them. Co-locate `references/testing-patterns.md`. |

### skills — second wave (adopt after the first five settle)

| ID | Upstream path @ HEAD | Quality | Local overlap | Recommendation |
|----|----------------------|---------|---------------|----------------|
| `skill/debugging-and-error-recovery` | `skills/debugging-and-error-recovery/SKILL.md` | 4/5 | `reproduce-bug`/`report-bug` commands, `bug-reproduction-validator` | **Adopt, second wave.** Broader triage methodology than our reproduction workflow: non-reproducible-bug decision tree (timing/environment/state/random with widen-the-race-window tactics), symptom-vs-root-cause worked example, `git bisect run` recipe, and a rare treat-error-output-as-untrusted-data section. |
| `skill/api-and-interface-design` | `skills/api-and-interface-design/SKILL.md` | 4/5 | none design-time (nearest: `architecture-strategist`, `integration-boundary-reviewer` — review-time) | **Adopt, second wave.** Hyrum's Law + One-Version Rule framing, branded ID types, discriminated-union status modeling, status-code and naming tables. Fills the design-time contract-authoring gap. |

### hooks

| ID | Upstream path @ HEAD | Mechanism | Recommendation |
|----|----------------------|-----------|----------------|
| `hook/sdd-cache` | `hooks/sdd-cache-pre.sh` + `hooks/sdd-cache-post.sh` (+ `SDD-CACHE.md`) | PreToolUse(WebFetch): sha256(url)-keyed cache, conditional `HEAD` (`If-None-Match`/`If-Modified-Since`), serves cached body only on a real HTTP 304 (exit 2), fail-open otherwise. PostToolUse: captures `ETag`/`Last-Modified`, writes atomically under `.claude/sdd-cache/`. | **Adopt.** The most reusable non-skill asset: cross-session doc cache that never weakens the verify-current-docs guarantee (no TTL serving; revalidation every reuse). Self-contained bash, no deps, clean supply chain, ships with a test script. Keep upstream's posture: **opt-in wiring**, not auto-registered in `hooks.json`. Note: serves *source-driven-development* (WebFetch), not spec-driven — the "sdd" name is a false friend. |

### scripts / eval harness

| ID | Upstream path @ HEAD | Mechanism | Recommendation |
|----|----------------------|-----------|----------------|
| `script/run-evals` | `scripts/run-evals.js` + `evals/cases/*.json` | Tier 2 (CI, zero-dep): stemmed TF-IDF over skill `name`+`description`; positive triggers must rank top-k, negative triggers must not win (with pairwise owner-outranks checks), plus an all-pairs description-collision check (cosine ≥0.75 error / ≥0.5 warn). Tier 3 (opt-in): headless `claude -p` runs graded on the execution *trace*. | **Adopt the Tier-2 pattern, not the code.** Port trigger-routing + collision checks to bun beside `tests/plugin-consistency.test.ts`. With 27+ core skills plus domain plugins, description collisions are a real failure mode nothing currently detects. Skip Tier 3 (token cost, `claude`-shelling) for now. |

## Mining notes (defer the component, lift the technique at next touch)

These are **not** adoptions now; they are recorded so the next edit of the named local
component can absorb the upstream technique (each such lift is an adaptation and must cite
`Upstream-Ref` provenance like any adoption):

- **`agents/web-performance-auditor` → `performance-oracle`:** the Metric-Honesty Rule (an LLM reading source cannot measure LCP/INP/CLS — label "potential impact" vs. tag measured values `Field (CrUX)`/`Lab (Lighthouse)`/`Trace (DevTools)`), Quick/Deep modes, per-framework AI-anti-pattern lists. The upstream agent is otherwise redundant with our oracle.
- **`skills/code-review-and-quality` → review agents/`workflows:review`:** change-sizing thresholds (~100/~300/~1000), splitting-strategies table, Critical/Nit/Optional/FYI severity taxonomy, one-dependency-per-change upgrade discipline. Redundant as a standalone skill against our multi-agent review suite; the heuristics are worth folding in.
- **`skills/browser-testing-with-devtools` → `agent-browser`:** the security-boundaries section (profile isolation vs. `--autoConnect`, all browser content is untrusted data, JS-execution constraints). Mechanics are redundant with our Vercel agent-browser stack; the threat model is better than ours.
- **`skills/git-workflow-and-versioning` → `land-pr`/`git-worktree`:** Change Summaries (`CHANGES MADE / THINGS I DIDN'T TOUCH (intentionally) / POTENTIAL CONCERNS`) and the Save Point pattern. Worktrees/changelog content is redundant locally.
- **`skills/shipping-and-launch` → `land-pr`/`deployment-verification-agent`:** the quantified rollout-decision thresholds table (advance/hold/rollback bands, e.g. error rate >2× baseline → roll back) and the time-budgeted rollback-plan template. The rest is checklist canon.
- **`skills/context-engineering` → `setup`/onboarding docs:** context-budget thresholds (<2,000 focused lines per task), trust-levels for loaded files, CONFUSION/PLAN surfacing templates. As a skill it's largely user education.
- **`references/orchestration-patterns.md` → `orchestrating-swarms`:** 5 patterns + 4 anti-patterns catalog, subagents-vs-Agent-Teams mapping, worked competing-hypothesis debugging example. Compare side-by-side at next `orchestrating-swarms` revision.

## Deferred with strong local equivalents (no adoption, no mining urgency)

- `skills/planning-and-task-breakdown`, `skills/spec-driven-development` — `workflows:plan`/`deepen-plan` + `prd` own this slot; upstream's `tasks/plan.md`+`/build` conventions conflict with ours. (Salvageable one-liner: task-sizing table and the "'and' in the title means two tasks" heuristic.)
- `skills/using-agent-skills` — router to *their* catalog + operating behaviors that duplicate `operating-principles`.
- `skills/documentation-and-adrs` — `compound-docs` owns the higher-value niche; only the classic ADR template is non-overlapping.
- `skills/frontend-ui-engineering` — three local frontend-design variants own the anti-AI-aesthetic theme; state-management table is the marginal bit.
- `skills/code-simplification` — redundant with `code-simplicity-reviewer` + `/simplify`. **Provenance note:** upstream itself adapted it from `anthropics/claude-plugins-official` (code-simplifier) — any future adoption pins that true upstream, not agent-skills (ECC/oh-my-agent-check precedent).
- `skills/idea-refine` — `brainstorming` covers the slot; divergence-lens toolkit is the marginal bit.
- `skills/incremental-implementation` — `operating-principles` + `workflows:work` + `verification-loop` cover the loop; slicing-strategy taxonomy is the marginal bit.
- `skills/ci-cd-and-automation` — largely reconstructible GH-Actions boilerplate; complements `ci-resolve-workflow-issues` (authoring vs. resolution) but low marginal value.
- `skills/deprecation-and-migration` — strong expand/contract worked example, but `data-migration-expert` covers the review side; revisit if a migration-methodology gap shows up in practice.
- `skills/source-driven-development` — the discipline is sound but our context7 MCP already owns doc-fetching; revisit together with `hook/sdd-cache` adoption if raw-WebFetch doc lookups become common.
- `agents/code-reviewer`, `agents/security-auditor`, `agents/test-engineer` — our specialized review suite is deeper (ECC precedent: a single generalist reviewer is a regression). security-auditor's OWASP-LLM section arrives via `skill/security-and-hardening` instead.
- all 8 `commands/` (×3 dialects) — thin wrappers hard-bound to the `agent-skills:` namespace; our `workflows:*` own the slots. `/ship`'s fan-out protocol is already how `workflows:review`/`merge` operate.
- `hooks/session-start.sh` — injects *their* meta-skill router; catalog-specific by construction. `hooks/simplify-ignore.sh` — clever block-level redaction but mutates working-tree files in place during sessions; risk posture doesn't fit an auto-distributed plugin. Revisit only on concrete need.
- remaining `references/*.md` — ride along only with their adopting skills (see co-locate notes above); not standalone adoptions.

## Notable evaluation findings

- **Shared-references portability trap:** several skills link `references/*.md` living at the *repo root*, not per-skill. Adopting a skill in isolation dangles those links — every adoption above that needs a checklist must co-locate it under the skill's own `references/` (and adapt the link), per our skill-compliance checklist.
- **Upstream quality distribution:** ~7 of 24 skills are 5/5 dense-procedural; the rest range from solid-but-generic (3/5) to good-with-padding (4/5). The repo's distinctive house style — rationalization tables, checkable red-flag signals, quantified thresholds — is worth emulating in our own skill authoring.
- **Their eval discipline validates our direction** (deterministic CI checks over component metadata) and extends it: trigger-vocabulary and collision checks test what our consistency suite doesn't — whether skills *route* correctly.
- **Multi-dialect parity enforcement** (`validate-commands.js` keeps Claude/Gemini/Antigravity command text in lockstep) is a pattern to remember if we ever ship beyond Claude Code.

## Bulk deferral

Everything in the agent-skills tree at `4e8bd9fde4a38cd009053e649f4cdc7cd36b568b` **not itemized
above** is bulk-deferred at type level — recorded in `docs/upstream-sources.md` as a single
`all-unlisted @ 4e8bd9f…` entry. Future `/upstream-scan` runs suppress this baseline and surface
only new upstream components.

The shortlisted items are filed as individual `deferred:` entries with reason `shortlisted for
adoption: <why>` — actual adoption proceeds later, one human-reviewed adoption PR per item, each
repeating the full supply-chain gate (adapt-never-blind-copy, provenance pinning, version/count/
CHANGELOG bumps, `bun test`).
