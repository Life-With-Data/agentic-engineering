import type { SkillDir } from "./claude"

export type CopilotAgent = {
  name: string
  content: string
}

export type CopilotGeneratedSkill = {
  name: string
  content: string
}

export type CopilotMcpServer = {
  type: string
  command?: string
  args?: string[]
  url?: string
  tools: string[]
  env?: Record<string, string>
  headers?: Record<string, string>
}

export type CopilotBundle = {
  agents: CopilotAgent[]
  generatedSkills: CopilotGeneratedSkill[]
  skillDirs: SkillDir[]
  mcpConfig?: Record<string, CopilotMcpServer>
}
