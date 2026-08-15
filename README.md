# Agentic Engineering

[![Build Status](https://github.com/Life-With-Data/agentic-engineering/actions/workflows/ci.yml/badge.svg)](https://github.com/Life-With-Data/agentic-engineering/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Life-With-Data/agentic-engineering)](https://github.com/Life-With-Data/agentic-engineering/releases)

**Each unit of work should make the next one easier — not harder.**

Most codebases drift the other way. Every feature adds complexity, every shortcut adds debt, and the work gets slower over time. This plugin inverts that by turning a deliberate loop — explore, plan, build, review, and *capture what you learned* — into first-class tooling: **25 agents and 9 workflow skills** that build on each other.

It installs natively in Claude Code, Cursor, and Codex, and converts to other AI coding tools (OpenCode, Droid, Gemini, Copilot, and more) via the Bun CLI.

> An independent project — tracker-aware workflows, a steering orchestrator, and cross-tool conversion, built as our own.

## The loop

The pipeline is the heart of the plugin. Each stage leaves an artifact the next stage picks up, so the whole thing is resumable — and every cycle makes the next one cheaper.

```
grooming → development → testing → review → delivery → documentation → repeat
```

| Skill | What it does |
|-------|--------------|
| `/wf-orchestrate` | **Default entry.** Drive a work item end to end, dispatching each stage skill |
| `/wf-auto` | **Fully autonomous.** Work the highest-priority ready ticket (or a named one) to merge — agent approves, zero gates |
| `/wf-grooming` | Discover intent, reproduce bugs, groom, and plan work |
| `/wf-development` | Implement the plan |
| `/wf-testing` | Select and run the required test and verification strategy |
| `/wf-review` | Review code, architecture, security, and pull-request feedback |
| `/wf-delivery` | Repair CI, prepare and merge PRs, and hand off releases or deployments |
| `/wf-documentation` | Create, review, and land durable documentation |
| `/wf-setup` | Adopt and configure the plugin, repository contract, lifecycle, and hooks |

Delegation is vertical: **`/wf-orchestrate`** is the default invocation path. It resolves the item's lifecycle stage, dispatches the owning stage skill, and enforces the gates between stages — fully autonomous on cleared tickets, surfacing only genuine blockers. Stage skills never route laterally to each other; each does its stage and returns control.

Or run a single stage directly, split at the `planned` boundary:

- **`/wf-grooming`** — turn an idea, bug report, or stub issue into a **groomed, ready-to-claim work item** and stop there. Bug reports must be reproduced before they are considered groomed.
- **`/wf-development`** — start from groomed, human-approved work and implement it. An ungroomed item routes back through the orchestrator to `wf-grooming` instead of being planned mid-run.

📊 **[See FLOWS.md](plugins/agentic-engineering/FLOWS.md)** for mermaid diagrams of every flow and where the orchestrator pauses for you.

The only supported tracker today is a GitHub Projects v2 lifecycle board (`github-project`); the workflows auto-detect whether the board is configured, and an unconfigured repo still works until the `wf-setup` lifecycle bootstrap configures one.

### What should I work on next?

```bash
bun run work:ready                              # the single highest-ranked ready item
bun run work:ready -- --repo owner/name         # narrow to one repo on a shared board
bun run work:ready -- --status planned          # peek at another lifecycle stage
```

Reads the bound Projects v2 board — the whole board, every repository sharing
it — and prints one JSON winner: `Status = ready_for_work`, ranked by Priority
(`p1` before `p2` before `p3`, unset last) and tie-broken to the oldest issue.
Archived items, closed issues, and pull requests never qualify. Read-only: it
changes no Status, Priority, or body. When nothing qualifies it emits
`{"ok": true, "issue": null}` and exits 0.

### Worktree cleanup

Parallel sessions leave worktrees and branches behind — under `.worktrees/` (manager-created) and `.claude/worktrees/` (harness-created). Every worktree-manager subcommand operates on both roots — including `list`, `switch`, `cleanup`, and the unattended `gc` — while `create` only ever creates under `.worktrees/`. Two plain scripts clean them up systematically; no agent needed:

```bash
bun run worktrees:sync              # just merged a PR in the browser: reap every merged
                                    # worktree in both roots and delete stale merged branches
bun run worktrees:finish -- <name>  # done with one branch: remove its worktree, delete the
                                    # branch, and fast-forward the primary tree onto base
```

Unmerged work is never touched. Evidence tiers, the grace window, and `--force` semantics live in the [git-worktree reference](plugins/agentic-engineering/skills/wf-development/references/git-worktree.md). Note the `--` — `bun run` needs it to pass arguments through to the script.

**In consuming repositories** — any repo that installs this marketplace — the same commands run through the bundled CLI, no checkout of this repo required (needs [Bun](https://bun.sh) on PATH):

```bash
npx github:Life-With-Data/agentic-engineering worktrees sync
npx github:Life-With-Data/agentic-engineering worktrees finish <name>
```

`worktrees` operates on whatever git repository you run it from and passes every argument straight through to the bundled `worktree-manager.sh`. Exit codes pass through unchanged, so it is safe to wire into scripts or hooks.

## Install

Native install is the primary path for Claude Code, Cursor, and Codex. The
[skills CLI](https://github.com/vercel-labs/skills) covers skills-only installs
for ~70 other agents with no tooling from us, and the Bun CLI converter remains
available for full converts.

**1. Claude Code** (agents, skills, MCP, full hooks):

```bash
/plugin marketplace add https://github.com/Life-With-Data/agentic-engineering
/plugin install agentic-engineering
```

**2. Cursor** (skills, agents, MCP, safety hooks):

```text
/add-plugin agentic-engineering@https://github.com/Life-With-Data/agentic-engineering
```

For local development, clone the repo and symlink the nested plugin directory,
then restart Cursor:

```bash
mkdir -p ~/.cursor/plugins/local
ln -s /absolute/path/to/agentic-engineering/plugins/agentic-engineering \
  ~/.cursor/plugins/local/agentic-engineering
```

**3. Codex** (skills, MCP, safety hooks — trust hooks when prompted):

```bash
codex plugin marketplace add Life-With-Data/agentic-engineering
codex plugin add agentic-engineering --marketplace agentic-engineering
```

Native Codex does **not** ship Claude-style agents. For that surface,
use the Bun convert path below (`--to codex`). Plugin-bundled hooks are skipped
until you review and trust them (`/hooks`).

**4. Any other agent — skills only** ([skills CLI](https://github.com/vercel-labs/skills), ~70 agents):

```bash
npx skills@latest add Life-With-Data/agentic-engineering
```

Discovers every skill in this marketplace and installs into whichever agents it
detects (Claude Code, Cursor, Codex, opencode, Copilot, Cline, Amp, …; narrow
with `--skill <names>` / `--agent <ids>`). The skills CLI installs **skills
only** — plugin hooks, agents, and MCP servers do not ride along. Each workflow
skill bundles every script it invokes, including the repository-contract
validator, so selecting an individual skill does not leave a plugin-root
dependency behind. After
installing, invoke **`wf-setup`** and select its install-hooks route to wire the four
portable safety hooks (block `--no-verify`, prevent main commits, block Slack
webhook leaks, block `prisma db push`) into your agent, or use a native
install above for the full surface.

**5. Other tools / full convert** — Bun CLI (secondary):

```bash
npx github:Life-With-Data/agentic-engineering install agentic-engineering --to <target>
# pin a release: npx github:Life-With-Data/agentic-engineering#v3.0.0 install ...
```

The same CLI also exposes `convert`, `list`, `sync`, and `worktrees` (the
bundled worktree manager — see [Worktree cleanup](#worktree-cleanup)).

| Target | Output | Notes |
|--------|--------|-------|
| `claude` | passthrough | Claude Code format, copied as-is |
| `opencode` | `~/.config/opencode` | `opencode.json` deep-merged; your `model`/`theme`/`provider` win |
| `codex` | `~/.codex/prompts`, `~/.codex/skills` | full convert for agents; prefer native install for skills/MCP/hooks |
| `cursor` | Cursor format | legacy convert; prefer native `/add-plugin` |
| `droid` | `~/.factory/` | Claude tool names mapped to Factory equivalents |
| `pi` | `~/.pi/agent/` | includes `mcporter.json` for MCPorter |
| `gemini` | `.gemini/` | skills (from agents) pass through; MCP as `settings.json` |
| `copilot` | `.github/` | agents get Copilot frontmatter; MCP env vars prefixed `COPILOT_MCP_` |
| `kiro` | `.kiro/` | stdio MCP servers only (HTTP skipped) |
| `hermes` | `~/.hermes/` | skills (incl. commands/agents as skills); MCP as `mcp_servers` YAML snippet |

Non-native convert targets are **experimental** and may change as the formats evolve.

## Configure

After installing, start the plugin's configuration flow with **`/wf-setup`** in
Claude Code or Cursor. In Codex, invoke the installed skill as **`$wf-setup`** (or
select `wf-setup` through `/skills`). It inventories the repository's existing
operational guidance, interviews only for gaps, writes the fixed capability map
in root `AGENTS.md`, and validates it before offering optional lifecycle,
configuration, and hook setup. Re-run it anytime; configuration and lifecycle
diagnostics are routes of `wf-setup` on every platform.

For a Projects lifecycle, follow the
[`wf-setup` bootstrap journey](plugins/agentic-engineering/skills/wf-setup/references/lifecycle-bootstrap.md)
through board migration, forward-binding choice, organization access, deliberate
backfill, and read-only plus live readiness checks.

<details>
<summary>Local dev & per-provider details</summary>

Run the CLI from source:

```bash
bun run src/index.ts install ./plugins/agentic-engineering --to opencode
```

- **OpenCode** — commands written as individual `~/.config/opencode/commands/<name>.md`; agents/skills/plugins to matching subdirectories. `opencode.json` is deep-merged (user values win on conflict); command files are backed up before overwrite.
- **Codex** — each Claude command becomes both a prompt and a skill (the prompt tells Codex to load the skill). Skill descriptions truncated to 1024 chars (Codex limit).
- **Droid** — commands, droids (agents), and skills under `~/.factory/`. Tool names mapped (`Bash`→`Execute`, `Write`→`Create`, …); command namespace prefixes stripped.
- **Pi** — prompts, skills, extensions, and `agentic-engineering/mcporter.json` under `~/.pi/agent/`.
- **Gemini** — skills (from agents), any commands (`.toml`), and `settings.json` (MCP) under `.gemini/`. For a command-bearing plugin, namespaced commands create directories (e.g. `foo:bar` → `commands/foo/bar.toml`); this plugin ships skills only.
- **Copilot** — agents (`.agent.md`), skills (`SKILL.md`), and `copilot-mcp-config.json` under `.github/`. Agents get `description`, `tools: ["*"]`, `infer: true`.
- **Kiro** — custom agents (`.json` + prompt `.md`), skills, steering files (from CLAUDE.md), and `mcp.json` under `.kiro/`. Agents get `includeMcpJson: true`; only stdio MCP servers supported.
- **Hermes** — skills under `~/.hermes/skills/` (bundled skills copied; commands and agents emitted as generated skills, loadable with `/skill <name>`), plus a ready-to-merge `mcp_servers` snippet at `agentic-engineering/mcp-servers.yaml`. `--hermes-home` overrides the root. See [docs/specs/hermes.md](docs/specs/hermes.md).

</details>

## Sync your personal config

Mirror your own Claude Code setup (`~/.claude/`) into other tools:

```bash
npx github:Life-With-Data/agentic-engineering sync --target <opencode|codex|pi|droid|copilot>
```

Syncs personal skills from `~/.claude/skills/` (as symlinks, so edits reflect immediately) and MCP servers from `~/.claude/settings.json`.

## What's inside

| Component | Count |
|-----------|-------|
| Specialized agents | 25 |
| Workflow skills | 9 |
| MCP servers | 1 |

→ **[Full component reference](plugins/agentic-engineering/README.md)** — every agent and workflow skill.

## Why it works

The split is roughly **80% planning and review, 20% execution.** Plan thoroughly before writing code, review hard to catch issues *and* capture the learning, then codify that knowledge so it's reusable. Quality stays high, so future changes stay cheap — and the system gets smarter every time you use it.

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for the workflow and required
checks, and [AGENTS.md](AGENTS.md) for repository guidance.

## Learn more

- [FLOWS.md](plugins/agentic-engineering/FLOWS.md) — mermaid diagrams of every workflow and where the orchestrator pauses for you
- [Multi-platform native plugin guide](docs/multi-platform-native-plugins.md) — extend a Claude Code plugin to Cursor and Codex without duplicating its implementation
- [Release process](docs/solutions/plugin-versioning-requirements.md) — versions and changelogs are computed by release-please from Conventional Commit PR titles, not hand-bumped
