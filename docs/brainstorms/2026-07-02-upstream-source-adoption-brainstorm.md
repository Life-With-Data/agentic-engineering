---
date: 2026-07-02
topic: upstream-source-adoption
---

# Upstream Source Adoption: ECC Analysis + Recurring Tracking

## What We're Building

Two connected things:

1. **A decision on ECC** ([affaan-m/ECC](https://github.com/affaan-m/ECC)): curated cherry-picks into the existing `agentic-engineering` plugin — not wholesale vendoring, not a source-named second plugin. ECC is a 224K-star, MIT-licensed agent-harness system with 67 agents, 277 skills, 92 commands, 23 rules, and hooks. It is itself installable as a marketplace (`ecc@ecc`), so mirroring it has no value; selectively adapting its best components does.

2. **An upstream-source tracking system** so adoption becomes recurring rather than one-off:
   - A registry (`docs/upstream-sources.md`) listing each source: repo URL, license, last-reviewed commit/date, components adopted (with links to adopting PRs), and candidates deferred.
   - A scan command in the plugin (e.g. `/upstream-scan`) that walks the registry, diffs each source since its last-reviewed commit, and surfaces new adoption candidates.
   - A **biweekly scheduled cloud agent** that runs the scan and **opens/updates a GitHub issue** on `aagnone3/agentic-engineering` with candidates per source.

Seed sources: `affaan-m/ECC`, `EveryInc/compound-engineering-plugin` (fork upstream), `aagnone3/agent-leverage` (both prior adoptions came from here).

## Why This Approach

**Approaches considered for where adoptions land:**

- **A: Existing plugin only** — matches all prior precedent (agent-leverage adoptions), guardrails already cover it.
- **B: New `ecc-picks` plugin** — rejected: organizes by *source* rather than *domain*; the consistency tests and docs generator hardcode the single plugin; a mirror-subset of an installable marketplace is redundant.
- **C: A by default, new plugins for distinct domains (chosen)** — cherry-picks default into `agentic-engineering`, organized by function. A new plugin is created only when a coherent standalone *domain* emerges (e.g. ECC's `rules/` — a component type this repo doesn't have). Plugins are justified by domain coherence, never by upstream source.

**Approaches considered for tracking:** registry-only (manual habit, would decay), registry + manual command (still relies on remembering), **scheduled automation (chosen)** — registry + scan command + biweekly cron agent reporting to a GitHub issue. Zero-touch discovery; adoption itself stays deliberate and human-reviewed via PRs.

## Key Decisions

- **ECC inclusion = curated cherry-picks into the existing plugin**: adapt components to be repo-agnostic (agent-leverage precedent), bump version, pass `bun test`.
- **Multi-plugin axis is domain, not source**: new plugins only for coherent standalone domains; never `<source>-picks`.
- **Registry format**: markdown at `docs/upstream-sources.md` — human-readable, PR-diffable; per-source last-reviewed commit SHA makes scans incremental.
- **Scan is a plugin command**: the scanner itself becomes a shareable component (compounding), invoked both manually and by the schedule.
- **Cadence & destination**: biweekly; findings land in a GitHub issue on origin (`aagnone3/agentic-engineering`), linking candidates to their upstream paths/commits.
- **Provenance recording stays lightweight**: registry + commit message + CHANGELOG mention. No frontmatter provenance field or test enforcement for now (YAGNI; revisit if the registry proves insufficient).
- **License check is part of adoption**: registry records each source's license (ECC: MIT ✓).

## Resolved Questions

- *Existing plugin or new plugin for ECC?* → Existing, via Approach C above.
- *Can the scheduled agent reach all seed sources?* → Yes; all three are on GitHub (agent-leverage under `aagnone3`).
- *Should the first ECC curation pass be part of this work?* → Yes — the maiden run of `/upstream-scan` doubles as the ECC component-by-component evaluation; its output (a candidates issue) drives the first cherry-pick PRs.

## Open Questions

- (none — resolved above)

## Next Steps

→ `/workflows:plan` for implementation details (registry schema, scan command prompt, schedule setup, first-run ECC evaluation).
