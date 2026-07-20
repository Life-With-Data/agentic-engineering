# Agentic Engineering Plugin

AI-powered development tools that get smarter with every use. Make each unit of engineering work easier than the last.

## Components

| Component | Count |
|-----------|-------|
| Agents | 31 |
| Skills | 7 |
| MCP Servers | 1 |

> 📊 **[FLOWS.md](FLOWS.md)** diagrams the lifecycle. **[WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md)** defines the `wf-*` architecture, repository contract, and migration map.

## Agents

Agents are organized into categories for easier discovery.

### Review (17)

| Agent | Description |
|-------|-------------|
| `acceptance-criteria-reviewer` | Verify a change satisfies its issue's documented Acceptance Criteria and Validation steps |
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

## Workflow skills

The plugin exposes seven workflow-policy skills. Every public skill uses the `wf-` prefix. Reusable procedures live as on-demand references beneath these routers and are not independently discoverable skills.

| Skill | Description |
|-------|-------------|
| `wf-grooming` | Discover intent, brainstorm, reproduce bugs, groom, and plan work |
| `wf-development` | Implement planned changes and coordinate end-to-end development |
| `wf-testing` | Select and execute layered test and verification strategies |
| `wf-review` | Review code, architecture, security, and pull-request feedback |
| `wf-delivery` | Repair CI, prepare PRs, merge, release, and hand off deployments |
| `wf-documentation` | Create, review, compound, and ship documentation |
| `wf-setup` | Adopt and configure the plugin, repository contract, lifecycle, and hooks |

### Workflow and repository layers

- `wf-*` skills are plugin-owned workflow policy: stages, gates, artifacts, and completion.
- Root `AGENTS.md` contains the fixed `Agentic Engineering Repository Contract` capability map. Each capability may point to multiple repository assets in primary-first reading order, and assets may be reused across capabilities.
- Repository skills or documents provide commands, environments, credentials procedures, infrastructure mechanics, and observable evidence. Existing names and contents are accepted without plugin-specific wrappers or annotations; `repo-` is only an optional convention for newly created operational skills.

Every adopting repository declares all ten capability keys. Missing or malformed context fails closed through `scripts/repository-context.py`; workflows never replace missing repository guidance with guesses. See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md) for the complete contract, standard workflow set, and old-to-new migration map.

#### Issue tracker

The workflow skills resolve one of three modes (`github-project | github | none`) at startup and dispatch accordingly:

- **`github-project`** — a committed board config (`github_project_owner:` + `github_project_number:` in `agentic-engineering.md` at the repo root) is present. This unlocks the full unified lifecycle: a GitHub Projects v2 board is the source of truth, every workflow skill gates on entry, and stage moves route through `scripts/lifecycle_board.py`. See the **Lifecycle** section below.
- **`github`** — plain GitHub Issues with no board stage machinery. Used when `gh` is authenticated but no board config is committed.
- **`none`** — no available GitHub tracker. Workflows return artifacts without tracker writes.

Beads is **not** a tracker mode. It remains an opt-in, non-authoritative implementer scratchpad — `bd remember` still works for disposable working state, but no gate ever reads a bead and nothing syncs. To configure the board, use `wf-setup` (which writes the committed config) or run the bootstrap script; to pin plain mode, add `issue_tracker: github` (or `none`) to your project's `agentic-engineering.local.md` (setup gitignores this file — keep it untracked; the runtime ignores a tracked copy).

#### Lifecycle

In `github-project` mode, every work item flows through nine stages on the board's built-in Status field:

```
stub → brainstormed → planned → in_progress → in_review → shipped
                                                    ↓
                              deployed / compounded (terminal refinements) · abandoned (off-ramp)
```

`deployed` and `compounded` are **order-independent** refinements of `shipped`; `abandoned` is reachable from any stage — closing an item as not-planned abandons it even post-ship (the `deployed` high-water rule applies to rollbacks, not to explicit not-planned closes). Each transition has exactly one writer, and a shared reconciler applies a closed set of five repairs. The full vocabulary — stages, writer contracts, entry-gate verdicts, claim semantics, and security invariants — lives in the [`wf-setup` lifecycle reference](skills/wf-setup/references/lifecycle.md), which workflow routers load when lifecycle state matters. Humans and agents have parity: assign yourself and drag a card to `in_progress` (the drag is the claim), or run `--claim`; manual card order in views is decorative (the API cannot read it).

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
`block-no-verify`, `prevent-main-commit`, `block-slack-webhook`).

Skills-only installs (`npx skills@latest add Life-With-Data/agentic-engineering`
via the [skills CLI](https://github.com/vercel-labs/skills)) do **not** carry
plugin-level hooks — the CLI reads nothing but `SKILL.md` directories. For that
path, the [`wf-setup` install-hooks reference](skills/wf-setup/references/install-hooks.md) bundles the
four portable safety guards and wires them into the running agent's hook
config on invocation.

One hook is opt-in:

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
- **Default-branch merges drive `shipped`.** A merged PR that closes an issue via `Closes #N` stamps `shipped` through GitHub's built-in "Item closed" automation. Git-flow repos that merge into an integration branch get the ~10-line issue-closer workflow from the [`wf-setup` lifecycle recipes](skills/wf-setup/references/lifecycle/references/gh-recipes.md), or cards stall at `in_review` with a `merged_to_non_default_branch` reconciler comment naming the fix.
- **Issues are enabled** on the repo (preflight hard-errors otherwise).
- **Issue text is untrusted data.** Titles, bodies, and comments are quoted, never obeyed; only structured, permission-gated fields (Status, assignee, labels, PR merge state, `stateReason`) drive control flow.
- **The board is agent-managed after bootstrap.** Bootstrap's fresh-project guard refuses to adopt a customized project; once set up, **do not rename the Status options** — per-entry name re-resolution turns a rename into an `option missing` hard error.
- **github.com only** — not GitHub Enterprise Server (the GraphQL surface lags). Requires **`gh` ≥ 2.94.0** with the **`project`** OAuth scope everywhere these skills run.
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

## Installation

```bash
claude /plugin install agentic-engineering
```

Then run **`/wf-setup`**. It inventories existing repository guidance, completes
and validates the root capability contract, then offers optional lifecycle,
configuration, and hook setup. Use the same router's config-flags route to
change individual settings later.

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
