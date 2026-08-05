import fs from "fs/promises"
import path from "path"
import type { ClaudeHomeConfig } from "../parsers/claude-home"
import { renderCodexConfig } from "../targets/codex"
import { syncSkills } from "../utils/symlink"

export async function syncToCodex(
  config: ClaudeHomeConfig,
  outputRoot: string,
): Promise<void> {
  await syncSkills(config.skills, path.join(outputRoot, "skills"))

  // Write MCP servers to config.toml (TOML format)
  if (Object.keys(config.mcpServers).length > 0) {
    const configPath = path.join(outputRoot, "config.toml")
    const mcpToml = renderCodexConfig(config.mcpServers) ?? ""

    // Read existing config and merge idempotently
    let existingContent = ""
    try {
      existingContent = await fs.readFile(configPath, "utf-8")
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== "ENOENT") {
        throw err
      }
    }

    // Remove any existing Claude Code MCP section to make idempotent
    const marker = "# MCP servers synced from Claude Code"
    const markerIndex = existingContent.indexOf(marker)
    if (markerIndex !== -1) {
      existingContent = existingContent.slice(0, markerIndex).trimEnd()
    }

    const newContent = existingContent
      ? existingContent + "\n\n" + marker + "\n" + mcpToml
      : "# Codex config - synced from Claude Code\n\n" + mcpToml

    await fs.writeFile(configPath, newContent, { mode: 0o600 })
  }
}
