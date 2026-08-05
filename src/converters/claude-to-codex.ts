import { formatFrontmatter } from "../utils/frontmatter"
import { normalizeName, replaceSlashCommands, sanitizeDescription, uniqueName } from "../utils/names"
import type { ClaudeAgent, ClaudeCommand, ClaudePlugin } from "../types/claude"
import type { CodexBundle, CodexGeneratedSkill } from "../types/codex"
import type { ConvertOptions } from "./claude-to-opencode"

export function convertClaudeToCodex(
  plugin: ClaudePlugin,
  _options: ConvertOptions,
): CodexBundle {
  const promptNames = new Set<string>()
  const skillDirs = plugin.skills.map((skill) => ({
    name: skill.name,
    sourceDir: skill.sourceDir,
  }))

  const usedSkillNames = new Set<string>(skillDirs.map((skill) => normalizeName(skill.name)))
  const commandSkills: CodexGeneratedSkill[] = []
  const invocableCommands = plugin.commands.filter((command) => !command.disableModelInvocation)
  const prompts = invocableCommands.map((command) => {
    const promptName = uniqueName(normalizeName(command.name), promptNames)
    const commandSkill = convertCommandSkill(command, usedSkillNames)
    commandSkills.push(commandSkill)
    const content = renderPrompt(command, commandSkill.name)
    return { name: promptName, content }
  })

  const agentSkills = plugin.agents.map((agent) => convertAgent(agent, usedSkillNames))
  const generatedSkills = [...commandSkills, ...agentSkills]

  return {
    prompts,
    skillDirs,
    generatedSkills,
    mcpServers: plugin.mcpServers,
  }
}

function convertAgent(agent: ClaudeAgent, usedNames: Set<string>): CodexGeneratedSkill {
  const name = uniqueName(normalizeName(agent.name), usedNames)
  const description = sanitizeDescription(
    agent.description ?? `Converted from Claude agent ${agent.name}`,
  )
  const frontmatter: Record<string, unknown> = { name, description }

  let body = transformContentForCodex(agent.body.trim())
  if (agent.capabilities && agent.capabilities.length > 0) {
    const capabilities = agent.capabilities.map((capability) => `- ${capability}`).join("\n")
    body = `## Capabilities\n${capabilities}\n\n${body}`.trim()
  }
  if (body.length === 0) {
    body = `Instructions converted from the ${agent.name} agent.`
  }

  const content = formatFrontmatter(frontmatter, body)
  return { name, content }
}

function convertCommandSkill(command: ClaudeCommand, usedNames: Set<string>): CodexGeneratedSkill {
  const name = uniqueName(normalizeName(command.name), usedNames)
  const frontmatter: Record<string, unknown> = {
    name,
    description: sanitizeDescription(
      command.description ?? `Converted from Claude command ${command.name}`,
    ),
  }
  const sections: string[] = []
  if (command.argumentHint) {
    sections.push(`## Arguments\n${command.argumentHint}`)
  }
  if (command.allowedTools && command.allowedTools.length > 0) {
    sections.push(`## Allowed tools\n${command.allowedTools.map((tool) => `- ${tool}`).join("\n")}`)
  }
  // Transform Task agent calls to Codex skill references
  const transformedBody = transformContentForCodex(command.body.trim())
  sections.push(transformedBody)
  const body = sections.filter(Boolean).join("\n\n").trim()
  const content = formatFrontmatter(frontmatter, body.length > 0 ? body : command.body)
  return { name, content }
}

/**
 * Transform Claude Code content to Codex-compatible content.
 *
 * Handles multiple syntax differences:
 * 1. Task agent calls: Task agent-name(args) → Use the $agent-name skill to: args
 * 2. Slash commands: /command-name → /prompts:command-name
 * 3. Agent references: @agent-name → $agent-name skill
 *
 * This bridges the gap since Claude Code and Codex have different syntax
 * for invoking commands, agents, and skills.
 */
function transformContentForCodex(body: string): string {
  let result = body

  // 1. Transform Task agent calls
  // Match: Task repo-research-analyst(feature_description)
  // Match: - Task learnings-researcher(args)
  const taskPattern = /^(\s*-?\s*)Task\s+([a-z][a-z0-9-]*)\(([^)]+)\)/gm
  result = result.replace(taskPattern, (_match, prefix: string, agentName: string, args: string) => {
    const skillName = normalizeName(agentName)
    const trimmedArgs = args.trim()
    return `${prefix}Use the $${skillName} skill to: ${trimmedArgs}`
  })

  // 2. Transform slash command references
  // Match: /command-name or /workflows:command but NOT /path/to/file or URLs
  // Look for slash commands in contexts like "Run /command", "use /command", etc.
  // Avoid matching file paths (contain multiple slashes) or URLs (contain ://)
  result = replaceSlashCommands(result, (commandName) => `/prompts:${normalizeName(commandName)}`)

  // 3. Rewrite .claude/ paths to .codex/
  result = result
    .replace(/~\/\.claude\//g, "~/.codex/")
    .replace(/\.claude\//g, ".codex/")

  // 4. Transform @agent-name references
  // Match: @agent-name in text (not emails)
  const agentRefPattern = /@([a-z][a-z0-9-]*-(?:agent|reviewer|researcher|analyst|specialist|oracle|sentinel|guardian|strategist))/gi
  result = result.replace(agentRefPattern, (_match, agentName: string) => {
    const skillName = normalizeName(agentName)
    return `$${skillName} skill`
  })

  return result
}

function renderPrompt(command: ClaudeCommand, skillName: string): string {
  const frontmatter: Record<string, unknown> = {
    description: command.description,
    "argument-hint": command.argumentHint,
  }
  const instructions = `Use the $${skillName} skill for this command and follow its instructions.`
  // Transform Task calls in prompt body too (not just skill body)
  const transformedBody = transformContentForCodex(command.body)
  const body = [instructions, "", transformedBody].join("\n").trim()
  return formatFrontmatter(frontmatter, body)
}
