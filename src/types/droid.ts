import type { SkillDir } from "./claude"

export type DroidCommandFile = {
  name: string
  content: string
}

export type DroidAgentFile = {
  name: string
  content: string
}

export type DroidBundle = {
  commands: DroidCommandFile[]
  droids: DroidAgentFile[]
  skillDirs: SkillDir[]
}
