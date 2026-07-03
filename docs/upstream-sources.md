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

## affaan-m/ECC

- repo: https://github.com/affaan-m/ECC
- license: MIT (verified 2026-07-02)
- visibility: public
- scan: auto
- adopted:
- deferred:

## EveryInc/compound-engineering-plugin

- repo: https://github.com/EveryInc/compound-engineering-plugin
- license: unknown (record at first triage)
- visibility: public
- scan: auto
- adopted:
- deferred:

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
