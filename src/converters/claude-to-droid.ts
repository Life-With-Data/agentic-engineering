import { formatFrontmatter } from "../utils/frontmatter"
import { flattenCommandName, normalizeName, replaceSlashCommands } from "../utils/names"
import type { ClaudeAgent, ClaudeCommand, ClaudePlugin } from "../types/claude"
import type { DroidBundle, DroidCommandFile, DroidAgentFile } from "../types/droid"
import type { ConvertOptions } from "./claude-to-opencode"

const CLAUDE_TO_DROID_TOOLS: Record<string, string> = {
  read: "Read",
  write: "Create",
  edit: "Edit",
  multiedit: "Edit",
  bash: "Execute",
  grep: "Grep",
  glob: "Glob",
  list: "LS",
  ls: "LS",
  webfetch: "FetchUrl",
  websearch: "WebSearch",
  task: "Task",
  todowrite: "TodoWrite",
  todoread: "TodoWrite",
  question: "AskUser",
}

const VALID_DROID_TOOLS = new Set([
  "Read",
  "LS",
  "Grep",
  "Glob",
  "Create",
  "Edit",
  "ApplyPatch",
  "Execute",
  "WebSearch",
  "FetchUrl",
  "TodoWrite",
  "Task",
  "AskUser",
])

export function convertClaudeToDroid(
  plugin: ClaudePlugin,
  _options: ConvertOptions,
): DroidBundle {
  const commands = plugin.commands.map((command) => convertCommand(command))
  const droids = plugin.agents.map((agent) => convertAgent(agent))
  const skillDirs = plugin.skills.map((skill) => ({
    name: skill.name,
    sourceDir: skill.sourceDir,
  }))

  return { commands, droids, skillDirs }
}

function convertCommand(command: ClaudeCommand): DroidCommandFile {
  const name = flattenCommandName(command.name)
  const frontmatter: Record<string, unknown> = {
    description: command.description,
  }
  if (command.argumentHint) {
    frontmatter["argument-hint"] = command.argumentHint
  }
  if (command.disableModelInvocation) {
    frontmatter["disable-model-invocation"] = true
  }

  const body = transformContentForDroid(command.body.trim())
  const content = formatFrontmatter(frontmatter, body)
  return { name, content }
}

function convertAgent(agent: ClaudeAgent): DroidAgentFile {
  const name = normalizeName(agent.name)
  const frontmatter: Record<string, unknown> = {
    name,
    description: agent.description,
    model: agent.model && agent.model !== "inherit" ? agent.model : "inherit",
  }

  const tools = mapAgentTools(agent)
  if (tools) {
    frontmatter.tools = tools
  }

  let body = agent.body.trim()
  if (agent.capabilities && agent.capabilities.length > 0) {
    const capabilities = agent.capabilities.map((c) => `- ${c}`).join("\n")
    body = `## Capabilities\n${capabilities}\n\n${body}`.trim()
  }
  if (body.length === 0) {
    body = `Instructions converted from the ${agent.name} agent.`
  }

  body = transformContentForDroid(body)

  const content = formatFrontmatter(frontmatter, body)
  return { name, content }
}

function mapAgentTools(agent: ClaudeAgent): string[] | undefined {
  const bodyLower = `${agent.name} ${agent.description ?? ""} ${agent.body}`.toLowerCase()

  const mentionedTools = new Set<string>()
  for (const [claudeTool, droidTool] of Object.entries(CLAUDE_TO_DROID_TOOLS)) {
    if (bodyLower.includes(claudeTool)) {
      mentionedTools.add(droidTool)
    }
  }

  if (mentionedTools.size === 0) return undefined
  return [...mentionedTools].filter((t) => VALID_DROID_TOOLS.has(t)).sort()
}

/**
 * Transform Claude Code content to Factory Droid-compatible content.
 *
 * 1. Slash commands: /workflows:plan → /plan, /command-name stays as-is
 * 2. Task agent calls: Task agent-name(args) → Task agent-name: args
 * 3. Agent references: @agent-name → the agent-name droid
 */
function transformContentForDroid(body: string): string {
  let result = body

  // 1. Transform Task agent calls
  // Match: Task repo-research-analyst(feature_description)
  const taskPattern = /^(\s*-?\s*)Task\s+([a-z][a-z0-9-]*)\(([^)]+)\)/gm
  result = result.replace(taskPattern, (_match, prefix: string, agentName: string, args: string) => {
    const name = normalizeName(agentName)
    return `${prefix}Task ${name}: ${args.trim()}`
  })

  // 2. Transform slash command references
  // /workflows:plan → /plan, /command-name stays as-is
  result = replaceSlashCommands(result, (commandName) => `/${flattenCommandName(commandName)}`)

  // 3. Transform @agent-name references to droid references
  const agentRefPattern = /@agent-([a-z][a-z0-9-]*)/gi
  result = result.replace(agentRefPattern, (_match, agentName: string) => {
    return `the ${normalizeName(agentName)} droid`
  })

  return result
}
