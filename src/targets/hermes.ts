import path from "path"
import { backupFile, copyDir, ensureDir, writeText } from "../utils/files"
import type { HermesBundle } from "../types/hermes"

export async function writeHermesBundle(
  outputRoot: string,
  bundle: HermesBundle
): Promise<void> {
  const paths = resolveHermesPaths(outputRoot)

  await ensureDir(paths.skillsDir)

  for (const skill of bundle.skillDirs) {
    await copyDir(skill.sourceDir, path.join(paths.skillsDir, skill.name))
  }

  for (const skill of bundle.generatedSkills) {
    await writeText(
      path.join(paths.skillsDir, skill.name, "SKILL.md"),
      skill.content + "\n"
    )
  }

  if (bundle.mcpServersYaml) {
    const backupPath = await backupFile(paths.mcpServersPath)
    if (backupPath) {
      console.log(`Backed up existing MCP snippet to ${backupPath}`)
    }
    await writeText(paths.mcpServersPath, bundle.mcpServersYaml)
    console.log(
      `MCP servers written to ${paths.mcpServersPath}; merge the mcp_servers block into your Hermes config.yaml (or wire each with \`hermes mcp add\`).`
    )
  }
}

function resolveHermesPaths(outputRoot: string) {
  // Write directly into ~/.hermes or a project .hermes dir; otherwise nest
  // under .hermes.
  const base = path.basename(outputRoot)
  const root =
    base === ".hermes" || base === "hermes"
      ? outputRoot
      : path.join(outputRoot, ".hermes")
  return {
    skillsDir: path.join(root, "skills"),
    mcpServersPath: path.join(root, "agentic-engineering", "mcp-servers.yaml"),
  }
}
