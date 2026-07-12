# Agentic Engineering Plugin

AI-powered development tools that get smarter with every use. Make each unit of engineering work easier than the last.

## Components

| Component | Count |
|-----------|-------|
| Agents | 30 |
| Commands | 28 |
| Skills | 35 |
| MCP Servers | 1 |

> 📊 **[FLOWS.md](FLOWS.md)** — mermaid diagrams of every workflow (brainstorm → plan → work → review → compound) and how `/workflows:orchestrate` drives them.

## Agents

Agents are organized into categories for easier discovery.

### Review (16)

| Agent | Description |
|-------|-------------|
| `agent-native-reviewer` | Verify features are agent-native (action + context parity) |
| `architecture-strategist` | Analyze architectural decisions and compliance |
| `code-simplicity-reviewer` | Final pass for simplicity and minimalism |
| `data-integrity-guardian` | Database migrations and data integrity |
| `data-migration-expert` | Validate ID mappings match production, check for swapped values |
| `deployment-verification-agent` | Create Go/No-Go deployment checklists for risky data changes |
| `dhh-rails-reviewer` | Rails review from DHH's perspective |
| `integration-boundary-reviewer` | Identify untested external library calls and integration boundary gaps |
| `julik-frontend-races-reviewer` | Review JavaScript/Stimulus code for race conditions |
| `kieran-rails-reviewer` | Rails code review with strict conventions |
| `kieran-python-reviewer` | Python code review with strict conventions |
| `kieran-typescript-reviewer` | TypeScript code review with strict conventions |
| `pattern-recognition-specialist` | Analyze code for patterns and anti-patterns |
| `performance-oracle` | Performance analysis and optimization |
| `schema-drift-detector` | Detect unrelated schema.rb changes in PRs |
| `security-sentinel` | Security audits and vulnerability assessments |

### Research (5)

| Agent | Description |
|-------|-------------|
| `best-practices-researcher` | Gather external best practices and examples |
| `framework-docs-researcher` | Research framework documentation and best practices |
| `git-history-analyzer` | Analyze git history and code evolution |
| `learnings-researcher` | Search institutional learnings for relevant past solutions |
| `repo-research-analyst` | Research repository structure and conventions |

### Design (3)

| Agent | Description |
|-------|-------------|
| `design-implementation-reviewer` | Verify UI implementations match Figma designs |
| `design-iterator` | Iteratively refine UI through systematic design iterations |
| `figma-design-sync` | Synchronize web implementations with Figma designs |

### Workflow (5)

| Agent | Description |
|-------|-------------|
| `bug-reproduction-validator` | Systematically reproduce and validate bug reports |
| `editorial-style-editor` | Edit content to conform to our editorial style guide |
| `lint` | Run linting and code quality checks on Ruby and ERB files |
| `pr-comment-resolver` | Address PR comments and implement fixes |
| `spec-flow-analyzer` | Analyze user flows and identify gaps in specifications |

### Docs (1)

| Agent | Description |
|-------|-------------|
| `ankane-readme-writer` | Create READMEs following Ankane-style template for Ruby gems |

## Commands

### Workflow Commands

Core workflow commands use `workflows:` prefix to avoid collisions with built-in commands:

| Command | Description |
|---------|-------------|
| `/workflows:brainstorm` | Explore requirements and approaches before planning |
| `/workflows:plan` | Create implementation plans |
| `/workflows:review` | Run comprehensive code reviews |
| `/workflows:work` | Execute work items systematically (uses deterministic repo preflight script) |
| `/workflows:compound` | Document solved problems to compound team knowledge |
| `/workflows:orchestrate` | Drive the full pipeline (brainstorm → plan → work → review → land → compound) as the orchestrator — delegating implementation to sub-agents, reviewing their work, surfacing only blockers and a final review. Segment flags bifurcate the run: `--groom` stops once the item is planned; `--implement` starts from groomed work and refuses to groom |
| `/workflows:groom` | Groom intake (an idea, bug report, or stub issue) through brainstorm → plan and **stop once the work is groomed** — Status `planned`, join-keyed plan doc, sub-issues with dependencies. The first half of the bifurcated flow; never claims, never branches, never writes code |
| `/workflows:merge` | Land an open PR — thin entry point to the `land-pr` skill (CI wait, thread resolution, merge gate, cleanup, tracker-item close) |

#### Issue tracker

The workflow commands resolve one of three modes (`github-project | github | none`) at startup and dispatch accordingly:

- **`github-project`** — a committed board config (`github_project_owner:` + `github_project_number:` in `agentic-engineering.md` at the repo root) is present. This unlocks the full unified lifecycle: a GitHub Projects v2 board is the source of truth, every command gates on entry, and stage moves route through `scripts/lifecycle_board.py`. See the **Lifecycle** section below.
- **`github`** — plain GitHub Issues + file-todos, today's semantics, no stage machinery and no board writes. Used when `gh` is authenticated but no board config is committed.
- **`none`** — no `gh` authentication; TodoWrite and the `file-todos` skill are used unchanged.

Beads is **not** a tracker mode. It remains an opt-in, non-authoritative implementer scratchpad — `bd remember` still works for disposable working state, but no gate ever reads a bead and nothing syncs. To configure the board, run the `setup` skill (which writes the committed config) or run the bootstrap script; to pin plain mode, add `issue_tracker: github` (or `none`) to your project's `agentic-engineering.local.md` (setup gitignores this file — keep it untracked; the runtime ignores a tracked copy).

#### Lifecycle

In `github-project` mode, every work item flows through nine stages on the board's built-in Status field:

```
stub → brainstormed → planned → in_progress → in_review → shipped
                                                    ↓
                              deployed / compounded (terminal refinements) · abandoned (off-ramp)
```

`deployed` and `compounded` are **order-independent** refinements of `shipped`; `abandoned` is reachable from any stage — closing an item as not-planned abandons it even post-ship (the `deployed` high-water rule applies to rollbacks, not to explicit not-planned closes). Each transition has exactly one writer, and a shared reconciler applies a closed set of five repairs. The full vocabulary — stages, writer contracts, entry-gate verdicts, claim semantics, and security invariants — lives in the [`lifecycle` skill](skills/lifecycle/SKILL.md), which every workflow command loads. Humans and agents have parity: assign yourself and drag a card to `in_progress` (the drag is the claim), or run `--claim`; manual card order in views is decorative (the API cannot read it).

### Utility Commands

| Command | Description |
|---------|-------------|
| `/deepen-plan` | Enhance plans with parallel research agents for each section |
| `/changelog` | Create engaging changelogs for recent merges |
| `/create-agent-skill` | Create or edit Claude Code skills |
| `/generate_command` | Generate new slash commands |
| `/heal-skill` | Fix skill documentation issues |
| `/sync` | Sync Claude Code config across machines |
| `/report-bug` | Report a bug in the plugin |
| `/reproduce-bug` | Reproduce bugs using logs and console |
| `/resolve_parallel` | Resolve TODO comments in parallel |
| `/resolve_pr_parallel` | Resolve PR comments in parallel |
| `/resolve_todo_parallel` | Resolve todos in parallel |
| `/triage` | Triage and prioritize issues |
| `/test-browser` | Run browser tests on PR-affected pages |
| `/test-xcode` | Build and test iOS apps on simulator |
| `/feature-video` | Record video walkthroughs and add to PR description |
| `/agent-native-audit` | Run agent-native architecture review with scored principles |
| `/ci-resolve-workflow-issues` | Diagnose and fix failing CI checks on a pull request |
| `/upstream-scan` | Scan registered upstream repos for adoptable components and report candidates |
| `/analyze-source` | Evaluate any external resource (X post, blog, repo, tool) and return one verdict — author locally, track upstream, new plugin, install-alongside, or skip |
| `/lifecycle-doctor` | Verify the lifecycle board setup — toolchain, repo shape, board schema, delivery topology — and answer "ready for first work item: yes/no" (`--live` for the end-to-end probe) |
| `/deploy-docs` | Validate and prepare documentation for GitHub Pages deployment |
| `/config-flags` | Browse and toggle every opt-in configuration flag the plugin offers for this repo, with current value vs. default |

## Skills

One skill is designed to be **always-on**: `operating-principles` ships a paste-ready CLAUDE.md block ([claude-md-snippet.md](skills/operating-principles/assets/claude-md-snippet.md)) — ten compressed execution rules plus a trigger line that pulls the full skill in (decomposition patterns, verification playbook, failure-mode catalog) when a task warrants depth. The workflow commands load it automatically for delegated sub-agents; the snippet extends the same discipline to every session. The `setup` skill offers to install it into a repo's existing `CLAUDE.md`/`AGENTS.md` (idempotent, marker-guarded).

### Architecture & Design

| Skill | Description |
|-------|-------------|
| `agent-native-architecture` | Build AI agents using prompt-native architecture |
| `api-and-interface-design` | Author stable, hard-to-misuse API and interface contracts at design time (Hyrum's Law, One-Version Rule, branded types, status-code and naming tables) — the design-time complement to the review-time `architecture-strategist` and `integration-boundary-reviewer` agents |

### Development Tools

| Skill | Description |
|-------|-------------|
| `andrew-kane-gem-writer` | Write Ruby gems following Andrew Kane's patterns |
| `compound-docs` | Capture solved problems as categorized documentation |
| `create-agent-skills` | Expert guidance for creating Claude Code skills |
| `dhh-rails-style` | Write Ruby/Rails code in DHH's 37signals style |
| `dspy-ruby` | Build type-safe LLM applications with DSPy.rb |
| `frontend-design` | Create production-grade frontend interfaces |
| `reflect-for-skill-updates` | Turn debugging sessions into permanent skill improvements; the meta-improvement loop for agentic engineering |
| `skill-creator` | Guide for creating effective Claude Code skills |

### Content & Workflow

| Skill | Description |
|-------|-------------|
| `brainstorming` | Explore requirements and approaches through collaborative dialogue |
| `document-review` | Improve documents through structured self-review |
| `documentation-health` | Audit and repair the informational health of a repo's docs — root & nested CLAUDE.md, root & nested READMEs, and internal/external documentation — with a zero-dependency scanner and a cited best-practices checklist |
| `editorial-style-editor` | Review copy for our editorial style guide compliance |
| `file-todos` | File-based todo tracking system |
| `git-worktree` | Manage Git worktrees for parallel development |
| `interview-me` | Extract the user's true intent via a one-question-at-a-time interview (each with a falsifiable guess) to ~95% confidence before any spec, plan, or code — runs upstream of `brainstorming` |
| `land-docs` | Ship compounded knowledge (docs-only markdown) as its own PR and merge it on green — the autonomous data lane that closes out a session after the code PR lands |
| `land-pr` | Drive an open PR through CI, review threads, and approval to merge |
| `lifecycle` | The shared work-item lifecycle vocabulary — 9 stages, writer contracts, entry gates, claim semantics, and security invariants for the GitHub Projects v2 board |
| `operating-principles` | How to operate: risk-first decomposition, independent-channel verification, deliberate next-action selection — distilled from Claude Fable 5, with an always-on CLAUDE.md snippet |
| `resolve-pr-parallel` | Resolve PR review comments in parallel |
| `setup` | Configure review agents, issue tracker, lifecycle board, and the operating-principles always-on layer |

### Testing & Quality

| Skill | Description |
|-------|-------------|
| `debugging-and-error-recovery` | Root-cause debugging methodology — stop-the-line, reproduce, localize, reduce, fix the cause, guard, verify; the broader triage layer above the `/reproduce-bug` and `/report-bug` commands and the `bug-reproduction-validator` agent |
| `doubt-driven-development` | In-flight adversarial review of non-trivial decisions (CLAIM → EXTRACT → DOUBT → RECONCILE → STOP) with a fresh-context reviewer and gated cross-model escalation |
| `observability-and-instrumentation` | Instrument code as it's built so production behavior is visible: signal selection, RED/USE, a cardinality denylist, symptom-based alerting, and a verify-the-telemetry step |
| `security-and-hardening` | Harden a feature against vulnerabilities while building it — STRIDE threat modeling per trust boundary, the Always/Ask-First/Never rules, injection/XSS/SSRF patterns, reachability-keyed `npm audit` triage, and OWASP LLM Top 10; build-time counterpart to the `security-sentinel` agent |
| `test-driven-development` | Write a failing test before the code and reproduce every bug with a test before fixing it (RED-GREEN-REFACTOR, the Prove-It pattern) — the test-authoring complement to `test-strategy-reviewer` and `verification-loop` |
| `test-strategy-reviewer` | Analyze test files for coverage gaps, mock depth, and untested integration boundaries |
| `verification-loop` | Run a systematic verify-before-done loop (build, types, lint, tests, security, diff review) and produce a ready/not-ready verdict |

### Multi-Agent Orchestration

| Skill | Description |
|-------|-------------|
| `orchestrating-swarms` | Comprehensive guide to multi-agent swarm orchestration |

### File Transfer

| Skill | Description |
|-------|-------------|
| `rclone` | Upload files to S3, Cloudflare R2, Backblaze B2, and cloud storage |

### Context Compression

| Skill | Description |
|-------|-------------|
| `headroom` | Compress AI context (tool outputs, logs, RAG chunks, files) via the Headroom CLI (`uv tool install "headroom-ai[all]"`) to cut 60-95% of tokens |

### Browser Automation

| Skill | Description |
|-------|-------------|
| `agent-browser` | CLI-based browser automation using Vercel's agent-browser |

### Image Generation

| Skill | Description |
|-------|-------------|
| `gemini-imagegen` | Generate and edit images using Google's Gemini API |

**gemini-imagegen features:**
- Text-to-image generation
- Image editing and manipulation
- Multi-turn refinement
- Multiple reference image composition (up to 14 images)

**Requirements:**
- `GEMINI_API_KEY` environment variable
- Python packages: `google-genai`, `pillow`

## MCP Servers

| Server | Description |
|--------|-------------|
| `context7` | Framework documentation lookup via Context7 |

### Context7

**Tools provided:**
- `resolve-library-id` - Find library ID for a framework/package
- `get-library-docs` - Get documentation for a specific library

Supports 100+ frameworks including Rails, React, Next.js, Vue, Django, Laravel, and more.

MCP servers start automatically when the plugin is enabled.

## Hooks

Installing the plugin wires in a small set of Claude Code hooks (declared in
[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), documented in full in
[`scripts/HOOKS.md`](scripts/HOOKS.md)). Most are always-on safety nets that keep
the plan → work → PR → review flow from being short-circuited (e.g.
`block-no-verify`, `prevent-main-commit`, `block-slack-webhook`). One is opt-in:

### `sdd-cache` — revalidating WebFetch doc cache (opt-in)

A `PreToolUse` / `PostToolUse` pair that caches `WebFetch` results on disk so an
agent consulting the same official docs across sessions doesn't re-download
identical pages. It is **inert by default** and activates only when you set the
environment variable **`AGENTIC_SDD_CACHE=1`** in the shell you launch Claude
Code from. (An env var is used rather than a committed config flag so caching is
a per-machine choice that can't ride a PR and flip on for every clone; unset it
to disable.) The on-disk cache lives at `.claude/sdd-cache/` and is gitignored.

**The 304-only guarantee.** There is no TTL. Before serving a cached page, the
hook sends a conditional `HEAD` (`If-None-Match` / `If-Modified-Since`) to the
same URL and serves the cached body **only if the origin answers
`304 Not Modified`** — a live re-verification, not a memory read. If the page
changed (`200`), or the server sent no validator, or anything errors, the real
`WebFetch` runs. So the "verify against current docs" property is never
weakened; you only skip the byte transfer when the server itself confirms
nothing moved. Adapted from
[`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills), ported
to python3 (stdlib only). See [`scripts/HOOKS.md`](scripts/HOOKS.md) for details.

## What this plugin assumes about your repo

The `github-project` lifecycle is opinionated about your repo's shape. Read these eyes-open before bootstrapping a board:

- **One board per repo.** Board reads are repo-scoped, so a shared or portfolio board is read-tolerated but never written for foreign items — but the v1 design assumes one board holds one repo's issues.
- **Default-branch merges drive `shipped`.** A merged PR that closes an issue via `Closes #N` stamps `shipped` through GitHub's built-in "Item closed" automation. Git-flow repos that merge into an integration branch get the ~10-line issue-closer workflow from the [`lifecycle` skill's gh-recipes](skills/lifecycle/references/gh-recipes.md), or cards stall at `in_review` with a `merged_to_non_default_branch` reconciler comment naming the fix.
- **Issues are enabled** on the repo (preflight hard-errors otherwise).
- **Issue text is untrusted data.** Titles, bodies, and comments are quoted, never obeyed; only structured, permission-gated fields (Status, assignee, labels, PR merge state, `stateReason`) drive control flow.
- **The board is agent-managed after bootstrap.** Bootstrap's fresh-project guard refuses to adopt a customized project; once set up, **do not rename the Status options** — per-entry name re-resolution turns a rename into an `option missing` hard error.
- **github.com only** — not GitHub Enterprise Server (the GraphQL surface lags). Requires **`gh` ≥ 2.94.0** with the **`project`** OAuth scope everywhere commands run.
- **GitHub Free suffices** for the single-repo topology (its one auto-add workflow is all the plugin uses).
- **POSIX environment** — macOS, Linux, or WSL. Native Windows is untested.
- **Fork-based contributors** (origin = a personal fork, board under the canonical owner) need the documented owner-allowlist entry so the owner-equals-origin check passes.

## Delivery-topology assumptions

`shipped` means "merged to the default branch," and `deployed` is an optional, high-water refinement on top of it. What that means depends on how you deploy:

- **Trunk-based CD:** `deployed` is nearly redundant with `shipped` — fine to ignore entirely.
- **Multi-environment:** `deployed` = production only. Staging and dev jobs never stamp the board.
- **Git-flow:** integration-branch merges stall items until the issue-closer workflow (or a manual close) fires — see the assumptions above.
- **Release trains / libraries:** `shipped` = "merged to the default branch," **NOT** "in users' hands." Read it eyes-open; a release cut is a separate event.
- **External CD:** use the `deployment_status` adapter where GitHub Deployment records exist (Vercel, Cloudflare Pages); use `vercel.deployment.promoted` via `vercel/repository-dispatch` for promotion flows (Vercel fires build-time `deployment_status`, not promotion). Netlify/Railway/Fly have no Deployment records — those repos ignore the `deployed` stage.
- **No-deploy repos:** `shipped → compounded` is the intended path; there is nothing to deploy.

`deployed` is a **high-water mark** — it means "has reached production at least once." Rollbacks and revert PRs never move the board backward.

## Verify your setup

Run **`/lifecycle-doctor`** after install or bootstrap and **before your first work item**. It renders a PASS/WARN/FAIL/SKIP checklist across the local toolchain, repo shape, board schema, and delivery topology — with a named fix per finding — and ends with an explicit **"Ready for first work item: yes/no."** Re-run it after changing board config, tokens, or CD wiring. Add **`--live`** for the end-to-end probe (create → board-add → close → assert `shipped` → cleanup), which is the only path that creates anything and cleans up after itself.

## Browser Automation

This plugin uses **agent-browser CLI** for browser automation tasks. Install it globally:

```bash
npm install -g agent-browser
agent-browser install  # Downloads Chromium
```

The `agent-browser` skill provides comprehensive documentation on usage.

## Installation

```bash
claude /plugin install agentic-engineering
```

## Known Issues

### MCP Servers Not Auto-Loading

**Issue:** The bundled Context7 MCP server may not load automatically when the plugin is installed.

**Workaround:** Manually add it to your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
```

Or add it globally in `~/.claude/settings.json` for all projects.

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## License

MIT
