import type { ClaudeMcpServer, SkillDir } from "./claude"

export type CodexPrompt = {
  name: string
  content: string
}

export type CodexGeneratedSkill = {
  name: string
  content: string
}

export type CodexBundle = {
  prompts: CodexPrompt[]
  skillDirs: SkillDir[]
  generatedSkills: CodexGeneratedSkill[]
  mcpServers?: Record<string, ClaudeMcpServer>
}
