# Agentic Engineering

[![Build Status](https://github.com/Life-With-Data/agentic-engineering/actions/workflows/ci.yml/badge.svg)](https://github.com/Life-With-Data/agentic-engineering/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Life-With-Data/agentic-engineering)](https://github.com/Life-With-Data/agentic-engineering/releases)

A Claude Code plugin built on one idea: **each unit of engineering work should make the next one easier — not harder.**

Most codebases drift the other way. Every feature adds complexity, every shortcut adds debt, and the work gets slower over time. This plugin inverts that by turning a deliberate loop — explore, plan, build, review, and *capture what you learned* — into first-class tooling: **31 agents and 62 skills** that compound on each other.

It installs natively in Claude Code, Cursor, and Codex, and converts to other AI coding tools (OpenCode, Droid, Gemini, Copilot, and more) via the Bun CLI.

> An independent project — tracker-aware workflows, a steering orchestrator, and cross-tool conversion, built as our own.

## The loop

The pipeline is the heart of the plugin. Each stage leaves an artifact the next stage picks up, so the whole thing is resumable — and every cycle makes the next one cheaper.

```
brainstorm → plan → [deepen] → work → review → compound → repeat
```

| Skill | What it does |
|-------|--------------|
| `/workflows-brainstorm` | Explore *what* to build before committing to *how* |
| `/workflows-plan` | Turn an idea into a detailed, tracker-linked implementation plan |
| `/workflows-work` | Execute the plan — branches/worktrees, tests, and a PR |
| `/workflows-review` | Multi-agent review before merge; findings become tracked todos |
| `/workflows-compound` | Capture the solution so the next occurrence is a lookup, not a re-investigation |

Run the loop without babysitting it:

- **`/workflows-orchestrate`** — fully autonomous by default: drives the entire pipeline, delegates implementation to sub-agents and reviews their work, merges once the PR is landable, and surfaces *only* genuine blockers (a material scope change, or something branch protection requires). Built for unattended runs — cron routines, overnight loops.
- **`/workflows-orchestrate --final-review`** — the same hands-off run, but it pauses once before the merge and presents a review packet for your go. Add `--steer` instead for the classic checkpoint cadence (approach, plan approval, findings triage, merge).

Or run it bifurcated, splitting grooming from implementation at the `planned` boundary:

- **`/workflows-groom`** — turn an idea, bug report, or stub issue into a **groomed, ready-to-claim work item** (brainstorm → plan → sub-issues) and *stop there*. Groom the backlog overnight, review the plans in the morning.
- **`/workflows-orchestrate --implement`** — start from groomed work and drive it to shipped (work → review → land → compound). It refuses to groom on the fly: an un-groomed item routes back to `/workflows-groom` instead of being planned mid-run.

📊 **[See FLOWS.md](plugins/agentic-engineering/FLOWS.md)** for mermaid diagrams of every flow and where the orchestrator pauses for you.

The workflows auto-detect how you track work — a GitHub Projects v2 lifecycle board (`github-project`), plain GitHub Issues (`github`), or none — and adapt their bookkeeping accordingly. [beads](https://github.com/gastownhall/beads) remains an optional, non-authoritative implementer scratchpad.

## Install

Native install is the primary path for Claude Code, Cursor, and Codex. The Bun
CLI converter remains available for other tools and for full Codex
agent/command convert.

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

**4. Other tools / full convert** — Bun CLI (secondary):

```bash
npx github:Life-With-Data/agentic-engineering install agentic-engineering --to <target>
# pin a release: npx github:Life-With-Data/agentic-engineering#v3.0.0 install ...
```

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

Non-native convert targets are **experimental** and may change as the formats evolve.

## Configure

After installing, start the plugin's configuration flow with **`/setup`** in
Claude Code or Cursor. In Codex, invoke the installed skill as **`$setup`** (or
select `setup` through `/skills`). It auto-detects your stack and walks through
review agents, the lifecycle board, the operating-principles always-on layer,
and installing the **documentation-health CI workflow** (a zero-dependency
docs-health gate plus an optional agent audit that reviews docs on every PR —
usable with a Claude Pro/Max subscription token). Re-run it anytime; Claude and
Cursor also expose `/config-flags` and `/lifecycle-doctor`, and in Codex those
same skills are available through `/skills`.

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
| Specialized agents | 31 |
| Skills | 62 |
| MCP servers | 1 |

→ **[Full component reference](plugins/agentic-engineering/README.md)** — every agent and skill.

## Why it works

The split is roughly **80% planning and review, 20% execution.** Plan thoroughly before writing code, review hard to catch issues *and* capture the learning, then codify that knowledge so it's reusable. Quality stays high, so future changes stay cheap — and the system gets smarter every time you use it.

## Learn more

- [Documentation site](https://life-with-data.github.io/agentic-engineering/) — full agent and skill reference
- [FLOWS.md](plugins/agentic-engineering/FLOWS.md) — mermaid diagrams of every workflow and where the orchestrator pauses for you
- [Multi-platform native plugin guide](docs/multi-platform-native-plugins.md) — extend a Claude Code plugin to Cursor and Codex without duplicating its implementation
- [Release process](CLAUDE.md#release-process) — versions and changelogs are computed by release-please from Conventional Commit PR titles, not hand-bumped
