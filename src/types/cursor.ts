import type { ClaudeMcpServer, SkillDir } from "./claude"

export type CursorRule = {
  name: string
  content: string
}

export type CursorCommand = {
  name: string
  content: string
}

export type CursorBundle = {
  rules: CursorRule[]
  commands: CursorCommand[]
  skillDirs: SkillDir[]
  mcpServers?: Record<string, ClaudeMcpServer>
}
