# Documentation Health — Full Checklist & Rationale

The complete, cited rule set behind the `documentation-health` skill. Open this during the Audit phase. Each rule notes severity, whether it's **deterministic** (the script checks it) or **judgment** (you check it), and its source.

Sources are abbreviated inline; full URLs at the bottom.

---

## Layer 1 — Root CLAUDE.md (audience: the AI agent)

CLAUDE.md is injected in full as context on **every** session and after `/compact`. It is advisory, not enforced — hooks/permissions are the only hard enforcement. So every line costs tokens on every turn and competes for attention. The governing litmus test:

> **For each line ask: "Would removing this cause Claude to make mistakes?" If not, cut it.** Bloated CLAUDE.md files cause Claude to ignore your actual instructions.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 1.1 | ≤ ~200 lines (soft ceiling). Warn > 200, error > 300. Loaded in full regardless of length — length discipline is on you. | WARN/ERROR | det | Anthropic memory docs |
| 1.2 | **No hardcoded counts/versions/dates** (drift landmines). State where the authoritative number lives. | WARN | det | memory docs "exclude: info that changes frequently" |
| 1.3 | No file-by-file map of the codebase (explicit anti-pattern). Give orientation, not a manifest. | WARN | det | memory docs |
| 1.4 | No generic filler Claude already knows ("write clean code", "use meaningful names", "follow best practices"). | WARN | det | best-practices docs |
| 1.5 | No duplication of README/package.json content — `@import` them instead. | WARN | judgment | claude.com blog |
| 1.6 | No secrets/API keys/tokens. | ERROR | det | best-practices anti-patterns |
| 1.7 | Structured with markdown headers + bullets (Claude scans structure like a reader). | INFO | judgment | memory docs |
| 1.8 | Instructions are specific/verifiable ("Use 2-space indentation", "Run `npm test` before committing") not vague ("format properly", "test your changes"). | INFO | judgment | memory docs |
| 1.9 | All `@imports` resolve. Relative paths resolve against the **file's** dir (not cwd); `@~/…` allowed; max depth 4 hops; paths inside backticks/fences are *not* imported. | ERROR | det | memory docs |
| 1.10 | Emphasis ("IMPORTANT"/"YOU MUST"/"ALWAYS"/"NEVER") used sparingly. High density signals a too-long file where rules are getting lost — prune rather than shout, and phrase as "prefer X; exception: Y" (absolute constraints deadlock on edge cases). For zero-exception rules use a **hook**, not CLAUDE.md. | INFO | det+judgment | best-practices |
| 1.11 | Content that changes frequently, is multi-step/procedural, or is path-specific belongs in `.claude/rules/` (with `paths:` globs) or a **skill**, not CLAUDE.md. | INFO | judgment | memory docs, large-codebases |
| 1.12 | Not raw `/init` scaffolding shipped uncurated ("This file provides guidance to Claude Code…" + restated repo facts). Generated files that merely restate the repo can score *below* having no file at all. | INFO | det | ETH study |
| 1.13 | No style rules a formatter/linter config already owns (indentation, quotes, semicolons, import order) — the config is the SSOT; keep only conventions tooling can't enforce. | WARN | det+judgment | ETH study, docs-as-code |

**Reward pattern (positive signal):** a CLAUDE.md that explicitly *refuses* to hardcode counts and points at a generator/test as SSOT (this repo's own CLAUDE.md does exactly this). Note it as healthy, don't just hunt violations.

**Maintainer-note trick:** block-level HTML comments (`<!-- … -->`) are stripped before injection — use them for human-only notes ("counts auto-generated; do not hand-edit") at zero token cost.

**Empirical grounding (2026).** ETH Zurich's controlled evaluation of repo context files (arXiv 2602.11988) found they **do not generally improve task success while adding >20% inference cost**; LLM-generated files that merely restate the repo can score below no file at all, and concise human-curated ones help only modestly. Vercel's evals found **skills go un-invoked without explicit triggers** (never fired in 56% of cases → no improvement over baseline; 79% with a prompt hint; an always-loaded compact docs index scored 100%). Two design consequences: curate anything `/init` generates before shipping it, and when moving content out of CLAUDE.md match the mechanism to the content — must-know constraints stay in the (lean) always-loaded file, user-triggered vertical workflows become skills *with strong trigger phrasing*, and bulk reference becomes an on-demand index.

---

## Layer 1b — Cross-tool agent context (AGENTS.md & per-tool configs)

`AGENTS.md` ([agents.md](https://agents.md) spec) is the cross-tool standard read natively by most other coding agents (Codex, Copilot, Gemini CLI, Cursor, …). **Claude Code does not read AGENTS.md natively.** The official bridge when both exist: keep shared instructions in AGENTS.md and make CLAUDE.md `@AGENTS.md` plus any Claude-specific rules below the import — or a symlink (`ln -s AGENTS.md CLAUDE.md`; Windows needs admin/Developer Mode for symlinks, so prefer the import there). `/init` in a repo with AGENTS.md or legacy configs reads and merges them.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 1b.1 | If CLAUDE.md **and** AGENTS.md both exist, CLAUDE.md is a bridge (import or symlink) — independent copies WILL drift. | WARN | det | memory docs (AGENTS.md) |
| 1b.2 | AGENTS.md with no CLAUDE.md: add the one-line bridge so Claude Code sees the same instructions. | INFO | det | memory docs |
| 1b.3 | Legacy per-tool configs coexisting with CLAUDE.md/AGENTS.md (`.cursorrules`, `.windsurfrules`, `.clinerules`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules/`) — consolidate. | INFO | det | memory docs |
| 1b.4 | The canonical file passes the Layer-1 bar (ceiling, counts, secrets, filler) — a bridged AGENTS.md **is** launch-loaded context. | WARN/ERROR | det | — |
| 1b.5 | No contradictions across tool configs mid-migration (same rule, different phrasing per tool = drift already happened). | WARN | judgment | — |

---

## Layer 2 — Nested / directory-scoped CLAUDE.md

Discovery: on launch Claude loads every CLAUDE.md from cwd **up** to the filesystem root (broadest first, most-specific last → local wins by recency). **Child/subdirectory CLAUDE.md files are NOT loaded at launch** — they load on demand the first time Claude reads a file in that subdir, and (unlike the root file) are **not re-injected after `/compact`**. This lazy loading is the main lever for keeping context lean in a large repo.

Two more launch-loaded surfaces get the same hygiene bar: the project file may live at `./CLAUDE.md` **or** `./.claude/CLAUDE.md`; and a git-ignored `CLAUDE.local.md` beside either holds personal overrides (sandbox URLs, test data), appended **after** its CLAUDE.md at the same level so personal wins by recency. In monorepos where other teams' files get picked up, `claudeMdExcludes` (settings) skips them by glob.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 2.1 | Subsystem/package-specific conventions live in that directory's nested CLAUDE.md (or `.claude/rules/` with `paths:`), not crammed into root. | WARN | judgment | large-codebases guide |
| 2.2 | **No contradictions** across root + nested + rules (e.g. "use tabs" vs "2-space"; conflicting test commands) — Claude picks one arbitrarily. | ERROR | judgment | memory docs |
| 2.3 | Nested files owned by/versioned with their directory. | INFO | judgment | large-codebases |
| 2.4 | Choose nested CLAUDE.md when directory owners maintain their own; choose central `.claude/rules/*.md` (paths-scoped) when you want one location. Don't mix both for the same rules. | INFO | judgment | memory docs |
| 2.5 | `@import` is for organization, **not** token savings (imports expand in full at launch). To actually reduce context, use nested files / path-scoped rules / skills. | INFO | judgment | memory docs |
| 2.6 | `CLAUDE.local.md` is git-ignored and never tracked — tracked means one dev's personal overrides are shipping to the whole team. | WARN | det | memory docs |
| 2.7 | No personal preferences, sandbox URLs, or editor setup in the **team** CLAUDE.md — move them to `CLAUDE.local.md` or `~/.claude/CLAUDE.md`. | WARN | judgment | memory docs |
| 2.8 | `.claude/rules/*.md` **without** `paths:` frontmatter load at launch, same cost as CLAUDE.md — scope them. The ~200-line ceiling applies to the whole always-loaded set (root + local + unscoped rules + bridged AGENTS.md). | INFO | det | memory docs |

---

## CLAUDE.md lifecycle — when to add, when to delete, how to verify

Static checks catch structure; these keep the *content* honest over time.

**Adding — the two-strike rule.** Don't append a rule after a single model error; add it when Claude makes the same mistake a **second** time (official guidance), or when a code review catches something Claude should have known about this codebase. One-off errors are noise; repeated ones are missing context.

**Pruning.**
- A rule the agent demonstrably follows without being told (it learned the pattern from the codebase itself) is a deletion candidate — confirm with the noise-reduction test below.
- On a dependency/framework upgrade or swap, purge the rules that referenced the old one immediately — stale instructions cause debugging cycles, not just wasted tokens.

**Behavioral verification — test the file like software** (fresh session each; read-only for the repo):
1. **Cold-start test** — "Describe this project's architecture, key conventions, and how to run the tests." The agent should answer from CLAUDE.md without exploratory spelunking.
2. **Constraint test** — request a forbidden action (e.g. "push the schema change directly"). Expect a refusal that cites the rule; compliance means the rule is too weak or drowned out.
3. **Command test** — "Run the project's validation suite." Expect the exact documented command on the first try, no guessing.
4. **Noise-reduction test** — remove a suspected-redundant rule; if output quality doesn't change across a few tasks, delete it permanently.

**Debugging what actually loads.** `/memory` lists every CLAUDE.md / CLAUDE.local.md / rules file in the session; the `InstructionsLoaded` hook logs which instruction files loaded and why (invaluable for path-scoped rules). If an instruction *must* fire every time, it belongs in a hook, not prose.

---

## Layer 3 — Root README (audience: the newcomer/consumer)

The README is written for a newcomer who has *minutes* to decide "is this for me?" It is an **index + quickstart, not a manual.** Standard-Readme is the canonical machine-checkable baseline.

**Required set** (error/warn if absent): H1 Title (matches repo name) · one-line description (< 120 chars) · Install (omit only for pure-doc repos) · Usage/Quickstart · License.
**Recommended:** Badges (after title, no heading) · TOC (required by Standard-Readme if > 100 lines; GitHub auto-generates one but npm/other renderers don't) · Contributing · Maintainers/Contact.
**Ordering (Standard-Readme):** Title → Badges → short description → (Security) → (Background) → Install → Usage → (API) → (Extra) → Contributing → License.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 3.1 | H1 title present, matches repo/package name. | WARN | det | Standard-Readme, Google |
| 3.2 | One-line description present, < 120 chars, matches the package-manager description. | WARN | det | Standard-Readme |
| 3.3 | Install section (copyable). | WARN | det | Standard-Readme |
| 3.4 | Usage/Quickstart with a runnable example — "complete when someone can use it without reading the code". | WARN | det | Art of README |
| 3.5 | License section + a matching `LICENSE` file. | WARN/ERROR | det | Standard-Readme |
| 3.6 | No placeholder/template text (`TODO`, `<your-…>`, `username/repo`, "A short description of the project", `example.com`). | ERROR | det | — |
| 3.7 | No dead links or badges (run `lychee`); no 404 images. | WARN | tool | lychee |
| 3.8 | TOC in sync (`doctoc --dryrun` exits non-zero when stale). | WARN | tool | doctoc |
| 3.9 | Not bloated into a manual (warn > ~400–500 lines, or a single section that's an inline API/config reference). Move depth to `/docs`. | WARN | det+judgment | Google, Art of README, Diátaxis |
| 3.10 | Facts that live elsewhere (counts, versions, command lists) are **generated** into the README (between markers), not hand-copied. | WARN | judgment | docs-as-code |
| 3.11 | File is exactly `README.md`; < 500 KiB (GitHub truncates above that). | INFO | det | GitHub, Google |
| 3.12 | Markdown format lint (headings, lists, line length). | INFO | tool | markdownlint |

---

## Layer 4 — Nested / per-package READMEs (monorepos)

Google's rule: **every top-level directory of a code package should have an up-to-date README**, especially packages exposing interfaces to other teams (they also render when browsing that folder on GitHub). Nx/Turborepo/pnpm do *not* auto-generate these — the gap is real.

**Per-package README should contain:** one-paragraph purpose · **owner / point of contact** · **status** (deprecated? experimental? not for general release?) · copyable build/run/test commands for *this* package · links to deeper docs.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 4.1 | Every package dir (has `package.json`/`pyproject.toml`/`go.mod`/`Cargo.toml`/`Gemfile`/…) has a `README.md`. | WARN | det | Google, monorepo guides |
| 4.2 | Package README states purpose, owner/contact, and status. | WARN | judgment | Google |
| 4.3 | **Link-up/link-down hierarchy, no duplication**: root owns workspace setup; packages say "see root for setup" rather than restating it. | WARN | judgment | monorepo guide |
| 4.4 | Registry-published packages (npm etc.) are self-sufficient off GitHub — a real tension with "don't repeat the root"; resolve by making published packages self-contained and internal-only ones terse + link-heavy. | INFO | judgment | monorepo guide |
| 4.5 | Root↔package install/setup blocks haven't **diverged** (same intent, different commands = drift). | WARN | judgment | — |

---

## Layer 5 — Internal-facing docs (audience: maintainers/contributors)

### 5a. Community-health files
GitHub recognizes a fixed set, checked in `root` → `.github/` → `docs/` (first match wins). **Org-level defaults:** a public `.github` repo supplies defaults to any repo lacking its own — so distinguish "missing locally but inherited" from "genuinely absent" before flagging. Issue/PR templates are the exception: they **must** live under `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE`.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 5.1 | `README`, `LICENSE` present. | ERROR | det | GitHub community profile |
| 5.2 | `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `SUPPORT` present (or inherited from org `.github`). | WARN | det | GitHub |
| 5.3 | Issue/PR templates present and under `.github/`. | INFO | det | GitHub |

### 5b. ADRs (Architecture Decision Records)
Append-only decision log (Nygard: Title, Status, Context, Decision, Consequences; MADR adds Options/Pros-Cons). Now used widely enough to be a defensible default for non-trivial repos.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 5.4 | ADR directory exists (`docs/adr/`, `docs/decisions/`, `doc/adr/`, …) for a repo complex enough to warrant one. | INFO | det | adr.github.io |
| 5.5 | **Decisions still flowing** — flag if there's been significant architectural churn (new services, dep swaps, big diffs) since the newest ADR. A silent log in a churning repo is a health failure. | INFO | judgment | — |
| 5.6 | **Append-only** — an `accepted` ADR is *superseded*, never edited/deleted. Flag substantive edits to accepted ADRs. | WARN | judgment | adr.github.io |
| 5.7 | No ADRs stuck in `proposed` (decisions that never resolved); no broken/duplicate sequence numbers; required sections present. | INFO | det+judgment | Nygard/MADR |

### 5c. Ownership
| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 5.8 | `CODEOWNERS` exists and covers doc/code paths. | INFO | det | GitHub |
| 5.9 | Owners are still **active** members (files rot as people leave — "rule exists" ≠ "owner is active"). Report coverage %. | INFO | judgment | Koalr/Aviator |

---

## Layer 6 — External-facing docs (audience: users)

### 6a. Diátaxis (four modes, two axes: action↔cognition, study↔work)
- **Tutorial** (action + study): learning-oriented, guided, complete, end-to-end.
- **How-to** (action + work): goal-oriented recipe for a competent user; need not be complete.
- **Reference** (cognition + work): neutral, factual, mirrors the system; no instruction.
- **Explanation** (cognition + study): the "why", trade-offs, context.

Classify by *is the reader studying or working?* and *doing or knowing?* — **not** basic-vs-advanced. Detection proxies: numbered imperative steps + a promised artifact → tutorial/how-to; tables/signatures/option lists → reference; "why/because/the trade-off is" → explanation.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 6.1 | **No mode-mixing within a page** — "crossing the boundaries is at the heart of a vast number of documentation problems." Score each section; flag pages scoring high on 2+ modes. | WARN | judgment | diataxis.fr |
| 6.2 | Tutorials stay minimal and **link** to explanation/reference rather than inlining it. | WARN | judgment | diataxis.fr |
| 6.3 | Diátaxis is a **compass, not a filing cabinet** — flag mode-mixing, but don't force four literal folders onto a small project. | (advisory) | judgment | idratherbewriting critique |

### 6b. Docs-as-code hygiene
| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 6.4 | **SSOT** — each fact in exactly one place; other pages link. Duplication is the root of drift. | WARN | judgment | Write the Docs |
| 6.5 | **Reference is generated** from source (docstrings, OpenAPI, JSON Schema, `--help`), not hand-maintained. Flag hand-maintained reference that duplicates generatable facts. | WARN | judgment | passo.uno topologies |
| 6.6 | Links validated in CI (internal anchors + external URLs). | WARN | tool | lychee / Write the Docs |
| 6.7 | **Freshness**: substantive docs carry `last_reviewed`/`last_validated_commit`; flag when older than a threshold (e.g. 180/365 days) or when the referenced code changed but the stamp didn't. | INFO | judgment | TheCodeForge |
| 6.8 | **Orphans**: docs not reachable from any nav/index/sitemap and unlinked by any other doc. | INFO | judgment | — |
| 6.9 | **Colocation drift**: a doc describing a module that lives far from it, or referencing a deleted/renamed code path. | WARN | judgment | — |

### 6c. Internal-leak prevention (treat as **security**, not tidiness)
A static-site generator publishes *whatever is in the source tree* — internal architecture notes, credentials-in-examples, unreleased-feature docs, and customer names can be published by default the moment they land in a scanned directory. The mainstream literature under-serves this, which makes these checks genuinely differentiating.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 6.10 | Internal markers (`INTERNAL`, `DO NOT SHIP`, `audience: internal`, `published: false`, ticket IDs, employee names) on a **publishable** path. | WARN | det | — |
| 6.11 | `internal/` or `docs/internal/` tree is **not excluded** by the generator's config. Publishing should be **default-deny (allowlist)**, not "everything except X". | WARN | judgment | passo.uno |
| 6.12 | CI diffs the **rendered output** against source and fails if any internal-tagged path appears in the published bundle. | (recommend) | judgment | — |
| 6.13 | Secret/PII scan across the docs tree (examples are a common leak vector). | ERROR | det | — |
| 6.14 | No **load-bearing GitHub Wiki** — wikis are a separate repo, bypass PR review, CODEOWNERS, and CI link-checking. Keep docs in-repo. | INFO | judgment | — |

---

## Continuous integration

Health is *continuous* only when a gate enforces it on every change. The skill ships an example GitHub Actions workflow — [assets/doc-health.yml](assets/doc-health.yml) — with two independent tiers. Prefer a GitHub Action over a pre-commit hook: it runs the same way for every contributor, can post PR reviews, and can host the agent tier (a pre-commit hook is local, easy to `--no-verify` past, and can't call an LLM cleanly).

**Tier 1 — deterministic gate (`scan`).** Fetches the zero-dependency scanner at a chosen ref and runs it. This marketplace ships as a rolling release off `main` (no version tags), so the template defaults `DOCS_HEALTH_REF` to `main`; pin a commit SHA for a reproducible gate that can't drift under you. The strictness is a dial, not a fixed policy — set `--fail-on` to what the team will actually sustain:

| `--fail-on` | Exit 1 when… | Use for |
|-------------|--------------|---------|
| `error` | any ERROR (broken/dangerous) | the default PR gate — blocks only real breakage |
| `warn` | any ERROR **or** WARN | teams that also want drift (hardcoded counts, missing Usage) blocked |
| `info` | any finding at all | rarely a gate; a report-everything pass |
| `never` | never (report only) | scheduled sweeps that upload the `--json` artifact without blocking |

Start at `error` on PRs and, once the WARNs are burned down, ratchet to `warn` — a gate that's red on day one gets disabled. `--strict` remains a back-compat alias for `--fail-on error`.

**Tier 2 — agent in the loop (`audit`).** The deterministic gate covers maybe half the value; the judgment checks (duplication, Diátaxis mode-mixing, stale commands, README↔CLAUDE.md drift, cross-tool contradictions) need a reasoning pass. This tier runs the skill inside `anthropics/claude-code-action` (loaded via its `plugin_marketplaces` + `plugins` inputs), gated behind a label or `workflow_dispatch`/`schedule` so it doesn't spend agent minutes on every push. The action posts **as Claude** (the official Claude GitHub App identity), not the token owner.

*Propose-only, but still blocking.* Two orthogonal properties: (1) **propose-only** — the agent posts a PR review or opens a *draft* PR and never pushes to a protected branch (the review is the human gate for *applying* a fix); (2) **fail the check on a must-fix** — the agent emits a `--json-schema` structured output `{must_fix, summary}`, and a downstream step `exit 1`s when `must_fix` is true. Mark that job Required in branch protection and a judgment-confirmed must-fix *blocks merge* even though no file was written. Crucially the agent sets `must_fix` on its **judgment**, not raw scanner severity — so a WARN that's a false positive doesn't block, but a real forked-and-unbridged agent-context file does. That's the split a plain `--fail-on warn` gate can't make. Give the action `pull-requests: write` and an `ANTHROPIC_API_KEY` secret.

**Pinning & releases.** Pin the fetched scanner (and the `plugins@ref`) to an immutable ref — a `v<version>` tag or a commit SHA, never a moving branch. Producing those tags is a one-time release-automation step: a `Release` workflow that reads the plugin manifest version on push to `main` and cuts `v<version>` + a GitHub Release when it's new (notes from the CHANGELOG). For a repo that already hand-bumps the manifest and maintains a changelog under test, that manifest-version-triggered auto-tag fits better than release-please/conventional-commits, which would duplicate the existing discipline.

---

## Cross-cutting: the audience-separation matrix

The single most common structural failure is collapsing distinct audiences into one file. Enforce:

| Content | Belongs in | Never in |
|---------|-----------|----------|
| "What the project is" + fastest path to value | README | CLAUDE.md, /docs |
| "How the agent should behave here" (commands, conventions, guardrails) | CLAUDE.md (+ `.claude/rules/`) | README |
| Reference / how-to / tutorials / explanation | /docs (Diátaxis) | README (link out instead) |
| Contribution process, conduct, security policy | community-health files | README body (link to them) |
| The "why" behind a decision | ADR | code comments, scattered docs |

Cross-reference across these; never clone. The README `@import`ed into CLAUDE.md is the canonical bridge — one copy, referenced from the other.

---

## Tooling engine (delegate the mechanical; reserve judgment for substance)

| Job | Tool | Note |
|-----|------|------|
| Link checking | **lychee** (+ lychee-action) | fast, JSON output; best-in-class |
| TOC drift | **doctoc --dryrun** | non-zero exit = stale; drop-in CI check |
| Markdown format | **markdownlint** / markdownlint-cli2 | headings, lists, line length |
| README structure spec | **awesome-lint** / standard-readme presets | required sections + ordering |
| Prose / inclusive language | Vale, proselint, write-good, alex | style, not correctness |
| Generated-region drift | the repo's own generator `--check` | e.g. this repo's `bun run docs:check` |

Reserve the skill's own logic for what nothing else does well: **section presence/ordering, placeholder detection, stale-command detection, hardcoded-count/SSOT violations, community-health completeness, ADR flow, CODEOWNERS activity, monorepo README coverage, README↔CLAUDE.md drift, Diátaxis mode-mixing, and internal-leak detection.**

---

## Sources

**CLAUDE.md** — Claude Code memory docs, incl. the AGENTS.md and CLAUDE.local.md sections (code.claude.com/docs/en/memory) · best-practices (code.claude.com/docs/en/best-practices) · large-codebases (code.claude.com/docs/en/large-codebases) · Anthropic blog "Using CLAUDE.md files" (claude.com/blog/using-claude-md-files) · AI Codex anti-patterns · awesome-claude-code / awesome-claude-md.

**Cross-tool & empirical** — agents.md spec (agents.md) · Gloaguen et al., "Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?" (arXiv 2602.11988, ETH Zurich SRI) · Vercel, "AGENTS.md outperforms skills in our agent evals" (vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals).

**README** — Standard-Readme spec (github.com/RichardLitt/standard-readme) · Make a README (makeareadme.com) · Art of README (github.com/noffle/art-of-readme) · GitHub About READMEs · Google dev-docs style guide (google.github.io/styleguide/docguide) · markdownlint · doctoc · lychee.

**Docs architecture** — Diátaxis (diataxis.fr) · Write the Docs, Docs as Code (writethedocs.org) · passo.uno docs-as-code topologies · adr.github.io / MADR / joelparkerhenderson/architecture-decision-record · GitHub community-health & CODEOWNERS docs · joelparkerhenderson/github-special-files-and-paths · TheCodeForge documentation rot · Koalr & Aviator CODEOWNERS guides · idratherbewriting (Diátaxis "compass not map" critique).
