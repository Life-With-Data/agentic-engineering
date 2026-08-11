# Hermes target

Converts the Claude plugin for [NousResearch hermes-agent](https://github.com/NousResearch/hermes-agent),
which consumes the Agent Skills standard (`SKILL.md` with `name`/`description`
frontmatter) from `~/.hermes/skills/` and MCP servers via a `mcp_servers` block
in its `config.yaml` (Claude-format server snippets work unchanged).

## Layout

```
<root>/                        # ~/.hermes by default; --hermes-home overrides
  skills/<name>/SKILL.md       # shipped skills copied; commands + agents generated
  agentic-engineering/mcp-servers.yaml   # ready-to-merge mcp_servers: block
```

`--output <dir>` nests under `<dir>/.hermes` unless the directory is already
named `.hermes` or `hermes`.

## Asset mapping

Per [the conversion policy](../conversion-policy.md):

| Claude asset | Hermes output |
|---|---|
| Skills | Copied verbatim into `skills/` (shared `SKILL.md` standard). |
| Commands | Generated skills (`name` + `description` frontmatter, body verbatim); commands marked `disable-model-invocation` are skipped. Loadable in-chat with `/skill <name>`. |
| Agents | Generated skills, body-only — persona/system prompt and description; no tool/model/mode/delegation mapping. |
| MCP servers | Passthrough `mcp_servers:` YAML snippet at `agentic-engineering/mcp-servers.yaml`. Merge into `~/.hermes/config.yaml` or wire each server with `hermes mcp add`. Existing snippet is backed up before overwrite. |
| Hooks | Not converted (policy-frozen; see `tests/conversion-policy.test.ts`). |

## Content transforms

Namespaced Claude slash commands in command bodies (`/workflows:plan`) become
Hermes skill loads (`/skill workflows-plan`). Name collisions across skills,
commands, and agents are resolved with numeric suffixes.

## Usage

```bash
npx github:Life-With-Data/agentic-engineering install agentic-engineering --to hermes
# or to a project-local root:
bun run src/index.ts convert ./plugins/agentic-engineering --to hermes --hermes-home ./.hermes
```
