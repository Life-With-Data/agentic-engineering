---
report_repo: aagnone3/agentic-engineering
report_label: upstream-scan
---

# Upstream Sources

Registry of external repositories that inspire adoptions into this marketplace.
Scanned by the `/upstream-scan` command (manually or on a schedule); scan results
land as GitHub issues on `report_repo` labeled `report_label`. This file holds
**configuration and provenance only** — no scan state. The scanner reads it and
never writes it.

<!-- SCHEMA (linted by tests/upstream-registry.test.ts)

One `##` heading per source. The heading text MUST equal the GitHub `owner/name`
slug — it is the canonical source key used in issue titles and markers.

Required fields per source (each a `- field: value` list item; values run to the
end of the line — no inline comments):
  - repo:        https URL of the source repository
  - license:     SPDX id + the date it was verified, e.g. `MIT (verified 2026-07-02)`
  - visibility:  public | private
  - scan:        auto | manual-only   (scheduled runs skip manual-only sources)
  - adopted:     list (possibly empty) of adopted components
  - deferred:    list (possibly empty) of reviewed-and-not-adopted components

Optional depend-track field (see docs/dependency-policy.md; linted by
tests/dependency-policy.test.ts). One line per upstream plugin we formally
depend on via a local plugin.json `dependencies` array:
  - dependency: <plugin-name> (<upstream-dir>) @ <marketplace-name>, unversioned|<semver-range> — PR <url-or-#NN> — @who YYYY-MM-DD
A source with a `dependency:` line for plugin P must not have `adopted:`
entries whose upstream path is under P's <upstream-dir> (mutual exclusion),
and an unversioned dependency forces `scan: auto`.

Entry grammar — ` — ` (space-emdash-space) is the field delimiter; free-text
fields must not contain it. Candidate IDs are `<type>/<name>` in the SOURCE repo
(rename-tolerant; the upstream path is supplementary):
  adopted entry:
    - <type>/<name> (upstream: <path>@<commit-sha>, adapted|verbatim) — PR <url-or-#NN> — @who YYYY-MM-DD
  deferred entry:
    - <type>/<name> — <reason> — @who YYYY-MM-DD
  bulk deferral (covers every component present in the source tree at <sha> that
  is not itemized above it):
    - all-unlisted @ <commit-sha> — bulk-deferred at type level, see <triage report path> — @who YYYY-MM-DD

PRIVATE SOURCES (`visibility: private`): entries must not disclose non-public
component details. Components already public via their adopting PRs are fine.
The private repo's existence appearing here is a recorded, accepted risk;
content disclosure is not.

TRIAGE CONTRACT (the closing half of the scan loop):
A scan issue is resolved by a *triage PR* (agent- or human-authored; always
human-reviewed — that review is the security boundary against upstream prompt
injection). The triage PR:
  1. Files each reported candidate under `adopted:` or `deferred:` using the
     entry grammar above (the issue body includes a ready-to-paste block).
  2. Records/updates the source's `license:` line on first triage.
Adoption PRs additionally must:
  - Adapt, never blind-copy (rewrite into local conventions).
  - Pin provenance: `upstream: <path>@<sha>` in the registry entry and an
    `Upstream-Ref: <owner>/<repo>@<sha>:<path>` commit-message trailer.
  - Pass a supply-chain review — scripts: network calls, curl-pipe-sh, env
    exfiltration, writes outside the repo, obfuscation; prompts/skills:
    embedded instructions to fetch remote URLs, weaken permissions, or
    exfiltrate; dependencies: pinned.
  - Bump plugin version + counts + CHANGELOG and pass `bun test`.
Re-adoption after an upstream change repeats the same gate — adopting v1 of a
component confers no trust on v2.
-->

## coreyhaines31/marketingskills

- repo: https://github.com/coreyhaines31/marketingskills
- license: MIT (verified 2026-07-07)
- visibility: public
- scan: auto
- adopted:
  - skill/seo-audit (upstream: skills/seo-audit/SKILL.md@6c6017451dcd340f3aaab3e354e28eed8aa782aa, adapted) — PR #81 — @aagnone3 2026-07-07
- deferred:

## affaan-m/ECC

- repo: https://github.com/affaan-m/ECC
- license: MIT (verified 2026-07-02)
- visibility: public
- scan: auto
- adopted:
  - skill/verification-loop (upstream: .agents/skills/verification-loop/SKILL.md@81af40761939056ab3dc54732fd4f562a27309d0, adapted) — PR #61 — @aagnone3 2026-07-06
- deferred:
  - skill/agent-introspection-debugging — shortlisted for adoption: agent self-debug workflow with no local equivalent, self-contained — @aagnone3 2026-07-03
  - skill/continuous-agent-loop — shortlisted for adoption: autonomous-loop-with-quality-gates pattern, adopt if additive over local orchestrating-swarms — @aagnone3 2026-07-03
  - skill/security-scan — shortlisted for adoption: .claude config security scanner filling the gap beside the security-sentinel agent, conditional on removing the hard AgentShield dependency — @aagnone3 2026-07-03
  - skill/agent-architecture-audit — shortlisted for adoption: 12-layer agent-stack diagnostic, must pin true upstream oh-my-agent-check and verify its license — @aagnone3 2026-07-03
  - skill/plan-orchestrate — shortlisted for adoption: plan-to-orchestrate bridge, low priority given high retarget cost versus local swarm orchestration — @aagnone3 2026-07-03
  - hook/memory-persistence — shortlisted for adoption: session-lifecycle memory spine, adopt the bounded-context pattern rather than the scripts/hooks subsystem with each script supply-chain reviewed — @aagnone3 2026-07-03
  - all-unlisted @ 81af40761939056ab3dc54732fd4f562a27309d0 — bulk-deferred at type level, see docs/upstream-reports/2026-07-03-ecc-initial-triage.md — @aagnone3 2026-07-03

## EveryInc/compound-engineering-plugin

- repo: https://github.com/EveryInc/compound-engineering-plugin
- license: unknown (record at first triage)
- visibility: public
- scan: auto
- adopted:
- deferred:

## addyosmani/agent-skills

- repo: https://github.com/addyosmani/agent-skills
- license: MIT (verified 2026-07-10)
- visibility: public
- scan: auto
- adopted:
  - skill/interview-me (upstream: skills/interview-me/SKILL.md@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #102 — @aagnone3 2026-07-10
  - skill/observability-and-instrumentation (upstream: skills/observability-and-instrumentation/SKILL.md@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #99 — @aagnone3 2026-07-10
  - skill/security-and-hardening (upstream: skills/security-and-hardening/SKILL.md@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #103 — @aagnone3 2026-07-10
  - skill/test-driven-development (upstream: skills/test-driven-development/SKILL.md@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #104 — @aagnone3 2026-07-10
  - hook/sdd-cache (upstream: hooks/sdd-cache-pre.sh@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #107 — @aagnone3 2026-07-10
  - skill/debugging-and-error-recovery (upstream: skills/debugging-and-error-recovery/SKILL.md@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #100 — @aagnone3 2026-07-10
  - skill/api-and-interface-design (upstream: skills/api-and-interface-design/SKILL.md@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #101 — @aagnone3 2026-07-10
  - skill/doubt-driven-development (upstream: skills/doubt-driven-development/SKILL.md@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #105 — @aagnone3 2026-07-10
  - script/run-evals (upstream: scripts/run-evals.js@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b, adapted) — PR #106 — @aagnone3 2026-07-10
- deferred:
  - all-unlisted @ 4e8bd9fde4a38cd009053e649f4cdc7cd36b568b — bulk-deferred at type level, see docs/upstream-reports/2026-07-10-agent-skills-initial-triage.md — @aagnone3 2026-07-10

## mattpocock/skills

- repo: https://github.com/mattpocock/skills
- license: MIT (verified 2026-07-10)
- visibility: public
- scan: auto
- adopted:
- deferred:
  - skill/codebase-design — shortlisted for adoption: deep-module design vocabulary (deletion test, two-adapter seam rule, interface-as-test-surface, dependency-category to test-strategy mapping, design-it-twice parallel-agent pattern); fills the design-time architecture gap beside the review-time architecture-strategist and complements the in-flight api-and-interface-design (PR #101, API contracts vs module depth); standalone and author-neutral — @aagnone3 2026-07-10
  - skill/prototype — shortlisted for adoption: throwaway-prototype discipline (logic-vs-UI branch selection, existing-route variant switcher spec, capture-when-done via throwaway branch as primary source); no local equivalent for the pre-implementation spike moment; standalone — @aagnone3 2026-07-10
  - skill/resolving-merge-conflicts — shortlisted for adoption: intent-archaeology conflict resolution (primary sources per hunk, preserve-both-intents, always-resolve-never-abort, run-checks-after); genuine gap that recurring cross-PR version races hit in practice; tiny and standalone — @aagnone3 2026-07-10
  - skill/handoff — shortlisted for adoption: session-handoff document discipline (reference-not-copy rule, suggested-skills routing metadata, temp-dir placement, secret redaction); no local session-bridge equivalent for multi-session lifecycle work; tiny and standalone — @aagnone3 2026-07-10
  - skill/to-tickets — shortlisted for adoption: work-item decomposition with context-window-sized tracer-bullet slices, blocking-edge frontier scheduling, and the expand-contract wide-refactor exception; adapt the tracker contract to lifecycle-board verbs (the costly part) — @aagnone3 2026-07-10
  - skill/wayfinder — shortlisted for adoption, second wave: fog-of-war multi-session planning (map-as-index, fog graduation test, one-ticket-per-session, claim-before-work concurrency); complements the lifecycle board; adopt after to-tickets settles the tracker-adaptation pattern — @aagnone3 2026-07-10
  - skill/diagnosing-bugs — shortlisted for adoption, second wave, conditional: feedback-loop-first debugging (10-way loop ladder, red-capable gate with pasted-output proof, ranked falsifiable hypotheses); first fold the ladder into the debugging-slot owner (debugging-and-error-recovery, PR #100, already slated for superpowers systematic-debugging enhancements) as references, adopt standalone only if it does not fit there — @aagnone3 2026-07-10
  - skill/domain-modeling — shortlisted for adoption, second wave: domain-glossary and ADR discipline (ADR triple gate, single-paragraph minimal ADR template, CONTEXT.md glossary format with avoid-lists); pairs with codebase-design; reconcile file-location conventions with compound-docs first — @aagnone3 2026-07-10
  - all-unlisted @ 391a2701dd948f94f56a39f7533f8eea9a859c87 — bulk-deferred at type level, see docs/upstream-reports/2026-07-10-mattpocock-skills-initial-triage.md — @aagnone3 2026-07-10

## aagnone3/agent-leverage

- repo: https://github.com/aagnone3/agent-leverage
- license: unlicensed-private (verified 2026-07-02)
- visibility: private
- scan: manual-only
- adopted:
  - hook/block-no-verify (upstream: .claude/hooks/block-no-verify.py@8a428a2d61925ec046a7ad77e89eadeddee30e54, adapted) — PR #22 — @aagnone3 2026-07-02
  - hook/prevent-main-commit (upstream: .claude/hooks/prevent-main-commit.py@8a428a2d61925ec046a7ad77e89eadeddee30e54, adapted) — PR #22 — @aagnone3 2026-07-02
  - command/ci-resolve-workflow-issues (upstream: .claude/commands/ci:resolve-workflow-issues.md@8a428a2d61925ec046a7ad77e89eadeddee30e54, adapted) — PR #22 — @aagnone3 2026-07-02
  - skill/reflect-for-skill-updates (upstream: .claude/skills/reflect-for-skill-updates/SKILL.md@8a428a2d61925ec046a7ad77e89eadeddee30e54, adapted) — PR #24 — @aagnone3 2026-07-02
- deferred:

## obra/superpowers

- repo: https://github.com/obra/superpowers
- license: MIT (verified 2026-07-10)
- visibility: public
- scan: auto
- adopted:
- deferred:
  - skill/receiving-code-review — shortlisted for adoption: response-side review discipline (verify-claims-before-implementing, external-reviewer verification gate, no performative agreement, grep-backed YAGNI check on suggestions) filling the gap beside the mechanical pr-comment-resolver/resolve-pr-parallel surface; self-contained, recast the human-partner persona and keep the in-thread gh reply mechanics — @aagnone3 2026-07-10
  - skill/writing-skills — shortlisted for adoption as an enhancement into create-agent-skills, not a third authoring skill: TDD-for-skills iron law, subagent pressure-testing protocol, match-the-form-to-the-failure taxonomy, persuasion principles; co-locate adapted testing-skills-with-subagents.md and persuasion-principles.md as references and reconcile the description-only-triggers rule with the official what+when spec at adoption time — @aagnone3 2026-07-10
  - skill/subagent-driven-development — shortlisted for adoption, second wave once the in-flight addyosmani wave (PRs #100-#107) lands: fresh-implementer-per-task execution protocol (four status codes, file-based context handoff, per-task BASE discipline, compaction-proof progress ledger, reviewer anti-pre-judging trip-wires, one-fixer economics) plus three portable clean bash scripts; retarget plan/review/TDD/finish references to workflows:plan, local review agents, test-driven-development, land-pr — @aagnone3 2026-07-10
  - all-unlisted @ d884ae04edebef577e82ff7c4e143debd0bbec99 — bulk-deferred at type level, see docs/upstream-reports/2026-07-10-superpowers-initial-triage.md — @aagnone3 2026-07-10

## Graphify-Labs/graphify

Consumed as an **external CLI**, not by adopting components — the same shape as
`headroomlabs-ai/headroom` below. The `setup` skill offers `uv tool install graphifyy` (note: the
PyPI package is `graphifyy`, the CLI is `graphify`), and graphify registers its own assistant skill
via `graphify install`. Shipping a local copy of that skill would collide with the upstream-installed
one, so `adopted:` is empty **by design**, not by omission, and `scan: manual-only` stops the scanner
re-proposing components we have deliberately chosen not to vendor. Wired into `/workflows-compound`
behind the `graphify_refresh` flag, which refreshes an existing graph and never builds one.

- repo: https://github.com/Graphify-Labs/graphify
- license: MIT (verified 2026-07-15)
- visibility: public
- scan: manual-only
- adopted:
- deferred:

## headroomlabs-ai/headroom

Consumed as an **external CLI**, wrapped by the local `headroom` skill — which documents install and
usage rather than vendoring upstream code — and offered by the `setup` skill. Registered here as a
backfill: it predates this entry and had none, which quietly broke the "one ledger" invariant in
[dependency-policy.md](dependency-policy.md) that says every external source has a registry entry.
`scan: manual-only` because there are no components to mine; `adopted:` is empty by design.

- repo: https://github.com/headroomlabs-ai/headroom
- license: Apache-2.0 (verified 2026-07-15)
- visibility: public
- scan: manual-only
- adopted:
- deferred:
