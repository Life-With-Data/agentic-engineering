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
- deferred:
  - skill/verification-loop — shortlisted for adoption: self-contained verify-before-done workflow with no local equivalent and the lowest adaptation cost — @aagnone3 2026-07-03
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
- deferred:
  - skill/doubt-driven-development — shortlisted for adoption: in-flight adversarial fresh-context review (CLAIM/EXTRACT/DOUBT/RECONCILE/STOP) complementing the post-hoc verification-loop; retarget its agent-roster and orchestration-patterns references to local components — @aagnone3 2026-07-10
  - hook/sdd-cache — shortlisted for adoption: revalidating WebFetch doc cache (ETag/304-gated, fail-open), self-contained bash with clean supply chain; ship as opt-in wiring like upstream does — @aagnone3 2026-07-10
  - script/run-evals — shortlisted for adoption (pattern, not code): port the Tier-2 TF-IDF trigger-routing and description-collision checks to bun beside plugin-consistency.test.ts; skip the claude-shelling Tier 3 — @aagnone3 2026-07-10
  - skill/debugging-and-error-recovery — shortlisted for adoption, second wave: non-reproducible-bug decision tree and untrusted-error-output discipline beyond the local reproduce-bug workflow — @aagnone3 2026-07-10
  - skill/api-and-interface-design — shortlisted for adoption, second wave: design-time contract authoring (Hyrum's Law framing, branded types, status-code table) with no local design-time equivalent — @aagnone3 2026-07-10
  - all-unlisted @ 4e8bd9fde4a38cd009053e649f4cdc7cd36b568b — bulk-deferred at type level, see docs/upstream-reports/2026-07-10-agent-skills-initial-triage.md — @aagnone3 2026-07-10

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
