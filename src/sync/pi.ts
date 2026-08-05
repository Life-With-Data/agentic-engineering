import fs from "fs/promises";
import path from "path";
import type { ClaudeHomeConfig } from "../parsers/claude-home";
import type { PiMcporterConfig } from "../types/pi";
import { convertMcpToMcporter } from "../converters/claude-to-pi";
import { syncSkills } from "../utils/symlink";

export async function syncToPi(
  config: ClaudeHomeConfig,
  outputRoot: string
): Promise<void> {
  await syncSkills(config.skills, path.join(outputRoot, "skills"));

  if (Object.keys(config.mcpServers).length > 0) {
    const mcporterPath = path.join(
      outputRoot,
      "agentic-engineering",
      "mcporter.json"
    );
    await fs.mkdir(path.dirname(mcporterPath), { recursive: true });

    const existing = await readJsonSafe(mcporterPath);
    const converted = convertMcpToMcporter(config.mcpServers);
    const merged: PiMcporterConfig = {
      mcpServers: {
        ...(existing.mcpServers ?? {}),
        ...converted.mcpServers,
      },
    };

    await fs.writeFile(mcporterPath, JSON.stringify(merged, null, 2), {
      mode: 0o600,
    });
  }
}

async function readJsonSafe(
  filePath: string
): Promise<Partial<PiMcporterConfig>> {
  try {
    const content = await fs.readFile(filePath, "utf-8");
    return JSON.parse(content) as Partial<PiMcporterConfig>;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return {};
    }
    throw err;
  }
}
