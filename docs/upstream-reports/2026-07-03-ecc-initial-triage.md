# ECC Initial Triage — maiden `/upstream-scan` evaluation

- **Source:** [affaan-m/ECC](https://github.com/affaan-m/ECC)
- **Upstream HEAD:** `81af40761939056ab3dc54732fd4f562a27309d0` (main, scanned 2026-07-03)
- **License:** MIT (verified 2026-07-02; API re-confirmed MIT 2026-07-03)
- **Inventory at HEAD:** 67 agents, 92 commands, 277 skills, 22 rule-groups (122 files), 1 hook bundle (`memory-persistence`). Tree = 4,501 entries, `truncated:false`.
- **Local baseline compared against:** 30 agents, 30 commands (incl. this scan's `/upstream-scan`), 23 skills.
- **Mode:** full-evaluation (registry `adopted:`/`deferred:` were empty; no bulk-deferral baseline). Curated lens: gap analysis vs. the local plugin, domain fit with compounding-engineering workflows, adaptation cost.

> **Security note.** Every ECC component is an agent prompt and is treated here as untrusted data — quoted/summarized, never executed as instruction. Several ECC agents embed a "Prompt Defense Baseline" block; that is recorded as a property of the file, not followed. Full-body reads below were limited to shortlist finalists and read as data. Adoption of any item happens only in a **separate, human-reviewed PR** (the triage contract's security boundary); this report and its PR merely file items as `deferred:` with a recommendation.

## Per-type status header

| Type | Status | Inventory | Shortlisted | Bulk-deferred |
|------|--------|-----------|-------------|---------------|
| agents | done | 67 | 0 (2 evaluated, both defer) | yes |
| commands | done | 92 | 0 | yes |
| rules | done | 22 groups / 122 files | 0 (typed "no local equivalent") | yes |
| hooks | done | 1 bundle | 1 (`hooks/memory-persistence`) | yes |
| skills | done | 277 | 6 | yes |

## Shortlist (itemized, per type)

### skills

| ID | Upstream path @ HEAD | Size / shape | Depends on | Recommendation |
|----|----------------------|--------------|------------|----------------|
| `skill/verification-loop` | `skills/verification-loop/SKILL.md` | 2.5 KB, single file | none apparent | **defer → shortlisted for adoption** — small, self-contained, generic "verify before done" workflow. Closest local analog is the `verify`/review workflow but there is no dedicated verification-loop skill. Lowest-adaptation-cost item on the list; good first adoption. |
| `skill/continuous-agent-loop` | `skills/continuous-agent-loop/SKILL.md` | 1.1 KB, single file | references ECC loop catalogue (soft) | **defer → shortlisted for adoption** — tiny; canonical "autonomous loop with quality gates" pattern. Overlaps partly with local `orchestrating-swarms`; adopt only if it adds loop-recovery patterns that swarm orchestration lacks. Evaluate body at adoption. |
| `skill/security-scan` | `skills/security-scan/SKILL.md` | 4.5 KB, single file | external tool **AgentShield** (`affaan-m/agentshield`) | **defer → shortlisted for adoption (conditional)** — genuine gap: local has the `security-sentinel` *agent* but no `.claude/`-config security scanner. Hard dependency on an external binary (AgentShield) is a supply-chain concern; adopt only if the dependency can be made optional or vendored-free. |
| `skill/agent-introspection-debugging` | `skills/agent-introspection-debugging/SKILL.md` | 5.5 KB, single file | none apparent (workflow skill, not a runtime) | **defer → shortlisted for adoption** — self-debugging workflow for failing agent runs (capture → diagnose → contained recovery → introspection report). No local equivalent; strong fit for an agent-native plugin. Self-contained. |
| `skill/plan-orchestrate` | `skills/plan-orchestrate/SKILL.md` | 18.3 KB, single file | ECC `/orchestrate` command + ECC agent catalogue (hard) | **defer → shortlisted, low priority** — generative "plan → orchestrate custom prompts" bridge. Tightly coupled to ECC's `/orchestrate` and agent names; local analog is `orchestrating-swarms`. High adaptation cost (must retarget to local agents). Adopt only after a swarm/orchestrate gap is confirmed. |
| `skill/agent-architecture-audit` | `skills/agent-architecture-audit/SKILL.md` | 10.2 KB, single file | `metadata.origin: oh-my-agent-check` (further-upstream; ECC itself vendored it) | **defer → shortlisted, provenance flag** — 12-layer agent-stack diagnostic; excellent fit for an agent-native plugin. **Provenance caveat:** origin is `oh-my-agent-check`, not ECC — adoption must pin the true upstream, not ECC. Verify `oh-my-agent-check`'s license before adopting. |

Pre-seeded items **removed** from the shortlist after evaluation:
- `skills/continuous-learning-v2` — see hooks/learning-system note below (deferred, not shortlisted: prohibitive adaptation cost).
- `agents/code-reviewer`, `agents/architect` — see agents section (deferred: strong local equivalents).

### hooks

| ID | Upstream path @ HEAD | Size / shape | Depends on | Recommendation |
|----|----------------------|--------------|------------|----------------|
| `hook/memory-persistence` | `hooks/memory-persistence/` (`README.md` 2.3 KB + `hooks.json` 1.6 KB) | manifest only | **executables live outside the bundle** in `scripts/hooks/*.js` — `session-start.js`, `pre-compact.js`, `session-end.js`, `observe-runner.js`, `session-activity-tracker.js` | **defer → shortlisted for adoption (heavy)** — the memory/continuous-learning spine and a real capability gap (local has only the lighter `reflect-for-skill-updates`). But the `hooks/` dir is just a manifest; the working code is a multi-file `scripts/hooks/` subsystem coupled to ECC's `continuous-learning-v2` (12 files) and its instinct store. Adoption is a project, not a cherry-pick: it must be scoped down and each script supply-chain-reviewed (these run on session lifecycle events). Recommend adopting the *pattern* (bounded session-start context load) rather than blind-porting the subsystem. |

### agents (2 evaluated from the pre-seeded shortlist — both defer)

| ID | Upstream path @ HEAD | Size | Local equivalent | Recommendation |
|----|----------------------|------|------------------|----------------|
| `agent/code-reviewer` | `agents/code-reviewer.md` | 13.9 KB | `security-sentinel`, `pattern-recognition-specialist`, `code-simplicity-reviewer`, `kieran-{python,rails,typescript}-reviewer` | **defer (no adoption)** — the local plugin already fields a deeper, specialized review suite. A single generalist `code-reviewer` is a regression against that. No gap. |
| `agent/architect` | `agents/architect.md` | 7.3 KB | `architecture-strategist` | **defer (no adoption)** — direct local equivalent (`architecture-strategist`) with the same charter (system design, pattern compliance, structural refactors). No gap. |

### commands

No shortlist. ECC's 92 commands are dominated by (a) language/framework-specific build/test/review triplets (`cpp-build`/`cpp-test`/`cpp-review`, `go-*`, `rust-*`, `react-*`, `flutter-*`, `kotlin-*`, …) and (b) ECC-internal subsystem drivers (`epic-*`, `orch-*`, `prp-*`, `instinct-*`, `hookify-*`, `loop-*`, `learn*`, `sessions`, `checkpoint`). Both categories are out of domain for a language-agnostic compounding-engineering plugin, or are inseparable from ECC's own runtime. Bulk-deferred at type level.

### rules — typed "no local equivalent" (possible future domain plugin; do NOT adopt now)

ECC's `rules/` system (22 language/domain groups — `python/`, `typescript/`, `rust/`, `react/`, `web/`, `common/`, … — 122 files) has **no local counterpart**: this plugin ships no `rules/` component type. Per the plan, this is reported as a **"no local equivalent"** candidate and is a candidate *future domain plugin*, not a maiden-run adoption. Bulk-deferred; flagged for a separate domain-plugin decision.

## Notable evaluation findings

- **`continuous-learning` v1 is deprecated by ECC itself** (its own frontmatter routes callers to v2). Only v2 was considered; v1 is bulk-deferred by construction.
- **`agent-architecture-audit` provenance:** `metadata.origin: oh-my-agent-check`, i.e. ECC re-vendored it. Any adoption must pin `oh-my-agent-check` as upstream (and clear its license), not ECC.
- **ECC provenance practice worth emulating:** ECC records `metadata.origin` frontmatter on components and ships a selective-install "profile" concept (`docs/SELECTIVE-INSTALL-DESIGN.md`) — both validate this registry's provenance approach and are models for future curation.
- **Adjacent near-misses (evaluated, deferred, not shortlisted):** `skills/architecture-decision-records` (overlaps local `compound-docs`), `skills/knowledge-ops` (external vector-store/MCP dependency — high cost), `skills/mcp-server-patterns` (minor gap vs. local `create-agent-skills`), `skills/context-budget`, `skills/agent-self-evaluation`. Reconsider individually in future scans if a concrete need arises.

## Bulk deferral

Everything in the ECC tree at `81af40761939056ab3dc54732fd4f562a27309d0` **not itemized above** is bulk-deferred at type level — the ~450 remaining components (65 agents, 92 commands, 271 skills, all 22 rule-groups) are out of domain, ECC-runtime-coupled, or language/framework-specific and do not fit this plugin's language-agnostic compounding-engineering focus. This is recorded in `docs/upstream-sources.md` as a single `all-unlisted @ 81af4076… — bulk-deferred at type level` entry. Future `/upstream-scan` runs suppress this baseline and surface only *new* upstream components, making recurring scans cheap.

The shortlisted items above are filed as individual `deferred:` entries with reason `shortlisted for adoption: <why>` — actual adoption proceeds later, one human-reviewed adoption PR per item, each repeating the full supply-chain gate.
