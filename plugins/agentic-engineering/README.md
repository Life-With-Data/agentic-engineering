# Agentic Engineering Plugin

Workflow-guided development tools that get smarter with every use. Make each unit of engineering work easier than the last.

> 📊 **[FLOWS.md](FLOWS.md)** diagrams the lifecycle. **[WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md)** defines the `wf-*` architecture and repository contract.

## Agents

Agents are organized into categories — Review, Research, Design, Workflow. The [`agents/`](agents/) tree is the catalog: each file's frontmatter states what the agent does and when to use it.

## Workflow skills

Delegation is vertical: **`wf-orchestrate` is the default invocation path**, resolving a work item's lifecycle stage, dispatching the owning stage skill, and enforcing the gates between stages. Invoke a stage skill directly only for a genuinely single-stage request.

`wf-auto` is the maximally autonomous entry point, deliberately separate from the orchestrator: it selects the ticket when none is named, holds every approval the run needs — including the `ready_for_work` stamp other paths reserve for a human — and has **zero structural gates**. No `posture:*` label can pull it back into supervision. It reaches out only when the agent judges a question worth waking someone for.

The nine routers: `wf-orchestrate`, `wf-auto`, `wf-grooming`, `wf-development`, `wf-testing`, `wf-review`, `wf-delivery`, `wf-documentation`, `wf-setup`. Each skill's frontmatter (via `/skills`) states what it does and when to use it.

### Workflow and repository layers

See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md) for the layer model and repository contract; each router prints its own Layer, Owns, and Requires lines at runtime.

#### Issue tracker

**`github-project`** (a GitHub Projects v2 lifecycle board) is the only supported mode. An unconfigured repo still works without lifecycle claims or tracker writes — the engine's `no_board` verdict says exactly this — until the `wf-setup` lifecycle bootstrap configures a board. Everything else lives in the [lifecycle reference](skills/wf-setup/references/lifecycle.md).

#### Lifecycle

See [lifecycle reference](skills/wf-setup/references/lifecycle.md)

## Hooks

Installing the plugin wires in a small set of Claude Code hooks (declared in
[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), documented in full in
[`scripts/HOOKS.md`](scripts/HOOKS.md)). Most are always-on safety nets that keep
the groom → work → PR → review flow from being short-circuited (e.g.
`block-no-verify`, `prevent-main-commit`, `block-slack-webhook`).

Skills-only installs (`npx skills@latest add Life-With-Data/agentic-engineering`
via the [skills CLI](https://github.com/vercel-labs/skills)) do **not** carry
plugin-level hooks — the CLI reads nothing but `SKILL.md` directories. For that
path, the [`wf-setup` install-hooks reference](skills/wf-setup/references/install-hooks.md) bundles the
four portable safety guards and wires them into the running agent's hook
config on invocation.

## What this plugin assumes about your repo

The `github-project` lifecycle is opinionated about your repo's shape. Read these eyes-open before bootstrapping a board:

- **One board per owner by default.** An organization- or user-owned Project may aggregate that
  owner's repositories. Every engine operation scopes itself to the current origin repository and
  ignores foreign-repository items; a dedicated per-repository board also remains valid.
- **github.com only** — not GitHub Enterprise Server (the GraphQL surface lags). Requires **`gh` ≥ 2.94.0** with the **`project`** OAuth scope everywhere these skills run.
- **POSIX environment** — macOS, Linux, or WSL. Native Windows is untested.
- **Fork-based contributors** (origin = a personal fork, board under the canonical owner) follow the [`wf-setup` lifecycle-bootstrap journey](skills/wf-setup/references/lifecycle-bootstrap.md).

## Installation

```bash
claude /plugin install agentic-engineering
```

Then run **`/wf-setup`**. It inventories existing repository guidance, completes
and validates the root capability contract, then offers optional lifecycle,
configuration, and hook setup. Use the same router's config-flags route to
change individual settings later.

After setup, enter work through **`/wf-orchestrate`**.

## Verify your setup

Run the **`wf-setup` diagnostics route** after install or bootstrap and **before
your first work item**: it prints the full checklist with a fix per finding and
ends with a ready verdict. Pass **`--live`** for the end-to-end probe.
