import type { SkillDir } from "./claude"

export type PiPrompt = {
  name: string
  content: string
}

export type PiGeneratedSkill = {
  name: string
  content: string
}

export type PiExtensionFile = {
  name: string
  content: string
}

export type PiMcporterServer = {
  description?: string
  baseUrl?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  headers?: Record<string, string>
}

export type PiMcporterConfig = {
  mcpServers: Record<string, PiMcporterServer>
}

export type PiBundle = {
  prompts: PiPrompt[]
  skillDirs: SkillDir[]
  generatedSkills: PiGeneratedSkill[]
  extensions: PiExtensionFile[]
  mcporterConfig?: PiMcporterConfig
}
