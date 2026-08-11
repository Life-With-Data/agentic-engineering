import { dump } from "js-yaml"
import { formatFrontmatter } from "../utils/frontmatter"
import { normalizeName, replaceSlashCommands, sanitizeDescription, uniqueName } from "../utils/names"
import type {
  ClaudeAgent,
  ClaudeCommand,
  ClaudeMcpServer,
  ClaudePlugin,
} from "../types/claude"
import type { HermesBundle, HermesGeneratedSkill } from "../types/hermes"
import type { ConvertOptions } from "./claude-to-opencode"

// Hermes (NousResearch hermes-agent) consumes the Agent Skills standard:
// SKILL.md files with name/description frontmatter under ~/.hermes/skills/.
// Commands and agents both land as generated skills (body-only per
// docs/conversion-policy.md — no per-target tool/model/mode mapping). MCP
// servers pass through as a `mcp_servers:` YAML block, which hermes-agent
// accepts in Claude snippet shape unchanged.
export function convertClaudeToHermes(
  plugin: ClaudePlugin,
  _options: ConvertOptions
): HermesBundle {
  const usedNames = new Set<string>(
    plugin.skills.map((skill) => normalizeName(skill.name))
  )

  const generatedSkills = [
    ...plugin.commands
      .filter((command) => !command.disableModelInvocation)
      .map((command) => convertCommand(command, usedNames)),
    ...plugin.agents.map((agent) => convertAgent(agent, usedNames)),
  ]

  return {
    skillDirs: plugin.skills.map((skill) => ({
      name: skill.name,
      sourceDir: skill.sourceDir,
    })),
    generatedSkills,
    mcpServersYaml: plugin.mcpServers
      ? convertMcpToConfigBlock(plugin.mcpServers)
      : undefined,
  }
}

function convertCommand(
  command: ClaudeCommand,
  usedNames: Set<string>
): HermesGeneratedSkill {
  const name = uniqueName(normalizeName(command.name), usedNames)
  const frontmatter: Record<string, unknown> = {
    name,
    description: sanitizeDescription(
      command.description ?? `Converted from Claude command ${command.name}`
    ),
  }
  const body = transformContentForHermes(command.body).trim()
  return { name, content: formatFrontmatter(frontmatter, body) }
}

function convertAgent(
  agent: ClaudeAgent,
  usedNames: Set<string>
): HermesGeneratedSkill {
  const name = uniqueName(normalizeName(agent.name), usedNames)
  const frontmatter: Record<string, unknown> = {
    name,
    description: sanitizeDescription(
      agent.description ?? `Converted from Claude agent ${agent.name}`
    ),
  }

  const sections: string[] = []
  if (agent.capabilities && agent.capabilities.length > 0) {
    sections.push(
      `## Capabilities\n${agent.capabilities
        .map((capability) => `- ${capability}`)
        .join("\n")}`
    )
  }

  const body = [
    ...sections,
    agent.body.trim().length > 0
      ? agent.body.trim()
      : `Instructions converted from the ${agent.name} agent.`,
  ].join("\n\n")

  return { name, content: formatFrontmatter(frontmatter, body) }
}

function transformContentForHermes(body: string): string {
  // Hermes loads abilities in-chat with /skill <name>; normalize Claude's
  // namespaced slash commands to the flat skill names emitted above.
  return replaceSlashCommands(body, (commandName) => {
    if (commandName.startsWith("skill:")) {
      return `/skill ${normalizeName(commandName.slice("skill:".length))}`
    }
    return `/skill ${normalizeName(commandName)}`
  })
}

export function convertMcpToConfigBlock(
  servers: Record<string, ClaudeMcpServer>
): string {
  const mcpServers: Record<string, unknown> = {}

  for (const [name, server] of Object.entries(servers)) {
    if (server.command) {
      mcpServers[name] = pruneUndefined({
        command: server.command,
        args: server.args,
        env: server.env,
        headers: server.headers,
      })
      continue
    }
    if (server.url) {
      mcpServers[name] = pruneUndefined({
        url: server.url,
        headers: server.headers,
      })
    }
  }

  return dump({ mcp_servers: mcpServers })
}

function pruneUndefined(record: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(record).filter(([, value]) => value !== undefined)
  )
}
