import type { SkillDir } from "./claude"

export type HermesGeneratedSkill = {
  name: string
  content: string
}

export type HermesBundle = {
  skillDirs: SkillDir[]
  generatedSkills: HermesGeneratedSkill[]
  // Ready-to-merge `mcp_servers:` YAML block for ~/.hermes/config.yaml.
  mcpServersYaml?: string
}
