import { describe, expect, test } from "bun:test"
import { promises as fs } from "fs"
import path from "path"
import os from "os"
import { syncSkills } from "../src/utils/symlink"
import type { ClaudeHomeConfig } from "../src/parsers/claude-home"

describe("droid skill sync", () => {
  test("symlinks skills to factory skills dir", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "sync-droid-"))
    const fixtureSkillDir = path.join(import.meta.dir, "fixtures", "sample-plugin", "skills", "skill-one")

    const config: ClaudeHomeConfig = {
      skills: [
        {
          name: "skill-one",
          sourceDir: fixtureSkillDir,
          skillPath: path.join(fixtureSkillDir, "SKILL.md"),
        },
      ],
      mcpServers: {
        context7: { url: "https://mcp.context7.com/mcp" },
      },
    }

    await syncSkills(config.skills, path.join(tempRoot, "skills"))

    const linkedSkillPath = path.join(tempRoot, "skills", "skill-one")
    const linkedStat = await fs.lstat(linkedSkillPath)
    expect(linkedStat.isSymbolicLink()).toBe(true)

    // Droid does not write MCP config
    const mcpExists = await fs.access(path.join(tempRoot, "mcp.json")).then(() => true).catch(() => false)
    expect(mcpExists).toBe(false)
  })

  test("skips skills with invalid names", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "sync-droid-invalid-"))
    const fixtureSkillDir = path.join(import.meta.dir, "fixtures", "sample-plugin", "skills", "skill-one")

    const config: ClaudeHomeConfig = {
      skills: [
        {
          name: "../escape",
          sourceDir: fixtureSkillDir,
          skillPath: path.join(fixtureSkillDir, "SKILL.md"),
        },
      ],
      mcpServers: {},
    }

    await syncSkills(config.skills, path.join(tempRoot, "skills"))

    const entries = await fs.readdir(path.join(tempRoot, "skills"))
    expect(entries).toHaveLength(0)
  })
})
