import fs from "fs/promises"
import path from "path"
import type { ClaudeHomeConfig } from "../parsers/claude-home"
import type { CopilotMcpServer } from "../types/copilot"
import { convertMcpServers } from "../converters/claude-to-copilot"
import { syncSkills } from "../utils/symlink"

type CopilotMcpConfig = {
  mcpServers: Record<string, CopilotMcpServer>
}

export async function syncToCopilot(
  config: ClaudeHomeConfig,
  outputRoot: string,
): Promise<void> {
  await syncSkills(config.skills, path.join(outputRoot, "skills"))

  if (Object.keys(config.mcpServers).length > 0) {
    const mcpPath = path.join(outputRoot, "copilot-mcp-config.json")
    const existing = await readJsonSafe(mcpPath)
    const converted = convertMcpServers(config.mcpServers) ?? {}
    const merged: CopilotMcpConfig = {
      mcpServers: {
        ...(existing.mcpServers ?? {}),
        ...converted,
      },
    }
    await fs.writeFile(mcpPath, JSON.stringify(merged, null, 2), { mode: 0o600 })
  }
}

async function readJsonSafe(filePath: string): Promise<Partial<CopilotMcpConfig>> {
  try {
    const content = await fs.readFile(filePath, "utf-8")
    return JSON.parse(content) as Partial<CopilotMcpConfig>
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return {}
    }
    throw err
  }
}
