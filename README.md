# Agentic Engineering

[![Build Status](https://github.com/aagnone3/agentic-engineering/actions/workflows/ci.yml/badge.svg)](https://github.com/aagnone3/agentic-engineering/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/@aagnone3/agentic-plugin)](https://www.npmjs.com/package/@aagnone3/agentic-plugin)

A Claude Code plugin built on one idea: **each unit of engineering work should make the next one easier — not harder.**

Most codebases drift the other way. Every feature adds complexity, every shortcut adds debt, and the work gets slower over time. This plugin inverts that by turning a deliberate loop — explore, plan, build, review, and *capture what you learned* — into first-class tooling: **30 agents, 27 commands, and 22 skills** that compound on each other.

It works in Claude Code first, and converts to a dozen other AI coding tools (OpenCode, Codex, Cursor, Droid, Gemini, Copilot, and more).

> Built on the compounding-engineering philosophy from [Every](https://every.to/source-code/my-ai-had-already-fixed-the-code-before-i-saw-it). This is an independent fork that adds tracker-aware workflows, a steering orchestrator, and cross-tool conversion.

## The loop

The pipeline is the heart of the plugin. Each stage leaves an artifact the next stage picks up, so the whole thing is resumable — and every cycle makes the next one cheaper.

```
brainstorm → plan → [deepen] → work → review → compound → repeat
```

| Command | What it does |
|---------|--------------|
| `/workflows:brainstorm` | Explore *what* to build before committing to *how* |
| `/workflows:plan` | Turn an idea into a detailed, tracker-linked implementation plan |
| `/workflows:work` | Execute the plan — branches/worktrees, tests, and a PR |
| `/workflows:review` | Multi-agent review before merge; findings become tracked todos |
| `/workflows:compound` | Capture the solution so the next occurrence is a lookup, not a re-investigation |

Two ways to run the loop without babysitting it:

- **`/workflows:orchestrate`** — drives the entire pipeline for you, handling the menial transitions automatically and pausing *only* at the decisions that actually need you (which approach, plan approval, which findings to fix). Think `/goal` for the whole workflow.
- **`/lfg`** (and **`/slfg`** for swarm parallelism) — runs the loop fully autonomously, end to end, no human in the loop.

📊 **[See FLOWS.md](plugins/agentic-engineering/FLOWS.md)** for mermaid diagrams of every flow and where the orchestrator pauses for you.

The workflows auto-detect your issue tracker — [beads](https://github.com/gastownhall/beads), Linear, GitHub Issues, or none — and adapt their bookkeeping accordingly.

## Install

**Claude Code:**

```bash
/plugin marketplace add https://github.com/aagnone3/agentic-engineering
/plugin install agentic-engineering
```

**Cursor:**

```text
/add-plugin agentic-engineering
```

## Use it in other AI tools

This repo ships a Bun/TypeScript CLI ([`@aagnone3/agentic-plugin`](https://www.npmjs.com/package/@aagnone3/agentic-plugin)) that converts the plugin into other tools' native formats:

```bash
bunx @aagnone3/agentic-plugin install agentic-engineering --to <target>
```

| Target | Output | Notes |
|--------|--------|-------|
| `claude` | passthrough | Claude Code format, copied as-is |
| `opencode` | `~/.config/opencode` | `opencode.json` deep-merged; your `model`/`theme`/`provider` win |
| `codex` | `~/.codex/prompts`, `~/.codex/skills` | each command → a prompt + a skill |
| `cursor` | Cursor format | — |
| `droid` | `~/.factory/` | Claude tool names mapped to Factory equivalents |
| `pi` | `~/.pi/agent/` | includes `mcporter.json` for MCPorter |
| `gemini` | `.gemini/` | commands as `.toml`; skills pass through unchanged |
| `copilot` | `.github/` | agents get Copilot frontmatter; MCP env vars prefixed `COPILOT_MCP_` |
| `kiro` | `.kiro/` | stdio MCP servers only (HTTP skipped) |

All non-Claude targets are **experimental** and may change as the formats evolve.

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
- **Gemini** — skills (from agents), commands (`.toml`), and `settings.json` (MCP) under `.gemini/`. Namespaced commands create directories (`workflows:plan` → `commands/workflows/plan.toml`).
- **Copilot** — agents (`.agent.md`), skills (`SKILL.md`), and `copilot-mcp-config.json` under `.github/`. Agents get `description`, `tools: ["*"]`, `infer: true`.
- **Kiro** — custom agents (`.json` + prompt `.md`), skills, steering files (from CLAUDE.md), and `mcp.json` under `.kiro/`. Agents get `includeMcpJson: true`; only stdio MCP servers supported.

</details>

## Sync your personal config

Mirror your own Claude Code setup (`~/.claude/`) into other tools:

```bash
bunx @aagnone3/agentic-plugin sync --target <opencode|codex|pi|droid|copilot>
```

Syncs personal skills from `~/.claude/skills/` (as symlinks, so edits reflect immediately) and MCP servers from `~/.claude/settings.json`.

## What's inside

| Component | Count |
|-----------|-------|
| Specialized agents | 30 |
| Commands | 27 |
| Skills | 22 |
| MCP servers | 1 |

→ **[Full component reference](plugins/agentic-engineering/README.md)** — every agent, command, and skill.

## Why it works

The split is roughly **80% planning and review, 20% execution.** Plan thoroughly before writing code, review hard to catch issues *and* capture the learning, then codify that knowledge so it's reusable. Quality stays high, so future changes stay cheap — and the system gets smarter every time you use it.

## Learn more

- [Compound engineering: how Every codes with agents](https://every.to/chain-of-thought/compound-engineering-how-every-codes-with-agents)
- [The story behind compounding engineering](https://every.to/source-code/my-ai-had-already-fixed-the-code-before-i-saw-it)
