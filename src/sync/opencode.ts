import fs from "fs/promises"
import path from "path"
import type { ClaudeHomeConfig } from "../parsers/claude-home"
import { convertMcp } from "../converters/claude-to-opencode"
import { syncSkills } from "../utils/symlink"

export async function syncToOpenCode(
  config: ClaudeHomeConfig,
  outputRoot: string,
): Promise<void> {
  await syncSkills(config.skills, path.join(outputRoot, "skills"))

  // Merge MCP servers into opencode.json
  if (Object.keys(config.mcpServers).length > 0) {
    const configPath = path.join(outputRoot, "opencode.json")
    const existing = await readJsonSafe(configPath)
    const mcpConfig = convertMcp(config.mcpServers)
    existing.mcp = { ...(existing.mcp ?? {}), ...mcpConfig }
    await fs.writeFile(configPath, JSON.stringify(existing, null, 2), { mode: 0o600 })
  }
}

async function readJsonSafe(filePath: string): Promise<Record<string, unknown>> {
  try {
    const content = await fs.readFile(filePath, "utf-8")
    return JSON.parse(content) as Record<string, unknown>
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return {}
    }
    throw err
  }
}
