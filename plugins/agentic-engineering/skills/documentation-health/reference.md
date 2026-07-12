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
| 1.10 | Emphasis ("IMPORTANT"/"YOU MUST") used sparingly. High density signals a too-long file where rules are getting lost — prune rather than shout. For zero-exception rules use a **hook**, not CLAUDE.md. | INFO | judgment | best-practices |
| 1.11 | Content that changes frequently, is multi-step/procedural, or is path-specific belongs in `.claude/rules/` (with `paths:` globs) or a **skill**, not CLAUDE.md. | INFO | judgment | memory docs, large-codebases |

**Reward pattern (positive signal):** a CLAUDE.md that explicitly *refuses* to hardcode counts and points at a generator/test as SSOT (this repo's own CLAUDE.md does exactly this). Note it as healthy, don't just hunt violations.

**Maintainer-note trick:** block-level HTML comments (`<!-- … -->`) are stripped before injection — use them for human-only notes ("counts auto-generated; do not hand-edit") at zero token cost.

---

## Layer 2 — Nested / directory-scoped CLAUDE.md

Discovery: on launch Claude loads every CLAUDE.md from cwd **up** to the filesystem root (broadest first, most-specific last → local wins by recency). **Child/subdirectory CLAUDE.md files are NOT loaded at launch** — they load on demand the first time Claude reads a file in that subdir, and (unlike the root file) are **not re-injected after `/compact`**. This lazy loading is the main lever for keeping context lean in a large repo.

| # | Check | Sev | Kind | Source |
|---|-------|-----|------|--------|
| 2.1 | Subsystem/package-specific conventions live in that directory's nested CLAUDE.md (or `.claude/rules/` with `paths:`), not crammed into root. | WARN | judgment | large-codebases guide |
| 2.2 | **No contradictions** across root + nested + rules (e.g. "use tabs" vs "2-space"; conflicting test commands) — Claude picks one arbitrarily. | ERROR | judgment | memory docs |
| 2.3 | Nested files owned by/versioned with their directory. | INFO | judgment | large-codebases |
| 2.4 | Choose nested CLAUDE.md when directory owners maintain their own; choose central `.claude/rules/*.md` (paths-scoped) when you want one location. Don't mix both for the same rules. | INFO | judgment | memory docs |
| 2.5 | `@import` is for organization, **not** token savings (imports expand in full at launch). To actually reduce context, use nested files / path-scoped rules / skills. | INFO | judgment | memory docs |

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

**CLAUDE.md** — Claude Code memory docs (code.claude.com/docs/en/memory) · best-practices (code.claude.com/docs/en/best-practices) · large-codebases (code.claude.com/docs/en/large-codebases) · Anthropic blog "Using CLAUDE.md files" (claude.com/blog/using-claude-md-files) · AI Codex anti-patterns · awesome-claude-code / awesome-claude-md.

**README** — Standard-Readme spec (github.com/RichardLitt/standard-readme) · Make a README (makeareadme.com) · Art of README (github.com/noffle/art-of-readme) · GitHub About READMEs · Google dev-docs style guide (google.github.io/styleguide/docguide) · markdownlint · doctoc · lychee.

**Docs architecture** — Diátaxis (diataxis.fr) · Write the Docs, Docs as Code (writethedocs.org) · passo.uno docs-as-code topologies · adr.github.io / MADR / joelparkerhenderson/architecture-decision-record · GitHub community-health & CODEOWNERS docs · joelparkerhenderson/github-special-files-and-paths · TheCodeForge documentation rot · Koalr & Aviator CODEOWNERS guides · idratherbewriting (Diátaxis "compass not map" critique).
