import { formatFrontmatter } from "../utils/frontmatter"
import { normalizeName, sanitizeDescription, uniqueName } from "../utils/names"
import type { ClaudeAgent, ClaudeCommand, ClaudeMcpServer, ClaudePlugin } from "../types/claude"
import type { GeminiBundle, GeminiCommand, GeminiMcpServer, GeminiSkill } from "../types/gemini"
import type { ConvertOptions } from "./claude-to-opencode"

export function convertClaudeToGemini(
  plugin: ClaudePlugin,
  _options: ConvertOptions,
): GeminiBundle {
  const usedSkillNames = new Set<string>()
  const usedCommandNames = new Set<string>()

  const skillDirs = plugin.skills.map((skill) => ({
    name: skill.name,
    sourceDir: skill.sourceDir,
  }))

  // Reserve skill names from pass-through skills
  for (const skill of skillDirs) {
    usedSkillNames.add(normalizeName(skill.name))
  }

  const generatedSkills = plugin.agents.map((agent) => convertAgentToSkill(agent, usedSkillNames))

  const commands = plugin.commands.map((command) => convertCommand(command, usedCommandNames))

  const mcpServers = convertMcpServers(plugin.mcpServers)

  if (plugin.hooks && Object.keys(plugin.hooks.hooks).length > 0) {
    console.warn("Warning: Gemini CLI hooks use a different format (BeforeTool/AfterTool with matchers). Hooks were skipped during conversion.")
  }

  return { generatedSkills, skillDirs, commands, mcpServers }
}

function convertAgentToSkill(agent: ClaudeAgent, usedNames: Set<string>): GeminiSkill {
  const name = uniqueName(normalizeName(agent.name), usedNames)
  const description = sanitizeDescription(
    agent.description ?? `Use this skill for ${agent.name} tasks`,
  )

  const frontmatter: Record<string, unknown> = { name, description }

  let body = transformContentForGemini(agent.body.trim())
  if (agent.capabilities && agent.capabilities.length > 0) {
    const capabilities = agent.capabilities.map((c) => `- ${c}`).join("\n")
    body = `## Capabilities\n${capabilities}\n\n${body}`.trim()
  }
  if (body.length === 0) {
    body = `Instructions converted from the ${agent.name} agent.`
  }

  const content = formatFrontmatter(frontmatter, body)
  return { name, content }
}

function convertCommand(command: ClaudeCommand, usedNames: Set<string>): GeminiCommand {
  // Preserve namespace structure: workflows:plan -> workflows/plan
  const commandPath = resolveCommandPath(command.name)
  const pathKey = commandPath.join("/")
  uniqueName(pathKey, usedNames) // Track for dedup

  const description = command.description ?? `Converted from Claude command ${command.name}`
  const transformedBody = transformContentForGemini(command.body.trim())

  let prompt = transformedBody
  if (command.argumentHint) {
    prompt += `\n\nUser request: {{args}}`
  }

  const content = toToml(description, prompt)
  return { name: pathKey, content }
}

/**
 * Transform Claude Code content to Gemini-compatible content.
 *
 * 1. Task agent calls: Task agent-name(args) -> Use the agent-name skill to: args
 * 2. Path rewriting: .claude/ -> .gemini/, ~/.claude/ -> ~/.gemini/
 * 3. Agent references: @agent-name -> the agent-name skill
 */
export function transformContentForGemini(body: string): string {
  let result = body

  // 1. Transform Task agent calls
  const taskPattern = /^(\s*-?\s*)Task\s+([a-z][a-z0-9-]*)\(([^)]+)\)/gm
  result = result.replace(taskPattern, (_match, prefix: string, agentName: string, args: string) => {
    const skillName = normalizeName(agentName)
    return `${prefix}Use the ${skillName} skill to: ${args.trim()}`
  })

  // 2. Rewrite .claude/ paths to .gemini/
  result = result
    .replace(/~\/\.claude\//g, "~/.gemini/")
    .replace(/\.claude\//g, ".gemini/")

  // 3. Transform @agent-name references
  const agentRefPattern = /@([a-z][a-z0-9-]*-(?:agent|reviewer|researcher|analyst|specialist|oracle|sentinel|guardian|strategist))/gi
  result = result.replace(agentRefPattern, (_match, agentName: string) => {
    return `the ${normalizeName(agentName)} skill`
  })

  return result
}

function convertMcpServers(
  servers?: Record<string, ClaudeMcpServer>,
): Record<string, GeminiMcpServer> | undefined {
  if (!servers || Object.keys(servers).length === 0) return undefined

  const result: Record<string, GeminiMcpServer> = {}
  for (const [name, server] of Object.entries(servers)) {
    const entry: GeminiMcpServer = {}
    if (server.command) {
      entry.command = server.command
      if (server.args && server.args.length > 0) entry.args = server.args
      if (server.env && Object.keys(server.env).length > 0) entry.env = server.env
    } else if (server.url) {
      entry.url = server.url
      if (server.headers && Object.keys(server.headers).length > 0) entry.headers = server.headers
    }
    result[name] = entry
  }
  return result
}

/**
 * Resolve command name to path segments.
 * workflows:plan -> ["workflows", "plan"]
 * plan -> ["plan"]
 */
function resolveCommandPath(name: string): string[] {
  return name.split(":").map((segment) => normalizeName(segment))
}

/**
 * Serialize to TOML command format.
 * Uses multi-line strings (""") for prompt field.
 */
export function toToml(description: string, prompt: string): string {
  const lines: string[] = []
  lines.push(`description = ${formatTomlString(description)}`)

  // Use multi-line string for prompt
  const escapedPrompt = prompt.replace(/\\/g, "\\\\").replace(/"""/g, '\\"\\"\\"')
  lines.push(`prompt = """`)
  lines.push(escapedPrompt)
  lines.push(`"""`)

  return lines.join("\n")
}

function formatTomlString(value: string): string {
  return JSON.stringify(value)
}
