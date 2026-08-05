import { describe, expect, test } from "bun:test"
import { existsSync, promises as fs } from "fs"
import path from "path"
import os from "os"
import { writeGeminiBundle } from "../src/targets/gemini"
import type { GeminiBundle } from "../src/types/gemini"

describe("writeGeminiBundle", () => {
  test("writes skills, commands, and settings.json", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "gemini-test-"))
    const bundle: GeminiBundle = {
      generatedSkills: [
        {
          name: "security-reviewer",
          content: "---\nname: security-reviewer\ndescription: Security\n---\n\nReview code.",
        },
      ],
      skillDirs: [
        {
          name: "skill-one",
          sourceDir: path.join(import.meta.dir, "fixtures", "sample-plugin", "skills", "skill-one"),
        },
      ],
      commands: [
        {
          name: "plan",
          content: 'description = "Plan"\nprompt = """\nPlan the work.\n"""',
        },
      ],
      mcpServers: {
        playwright: { command: "npx", args: ["-y", "@anthropic/mcp-playwright"] },
      },
    }

    await writeGeminiBundle(tempRoot, bundle)

    expect(existsSync(path.join(tempRoot, ".gemini", "skills", "security-reviewer", "SKILL.md"))).toBe(true)
    expect(existsSync(path.join(tempRoot, ".gemini", "skills", "skill-one", "SKILL.md"))).toBe(true)
    expect(existsSync(path.join(tempRoot, ".gemini", "commands", "plan.toml"))).toBe(true)
    expect(existsSync(path.join(tempRoot, ".gemini", "settings.json"))).toBe(true)

    const skillContent = await fs.readFile(
      path.join(tempRoot, ".gemini", "skills", "security-reviewer", "SKILL.md"),
      "utf8",
    )
    expect(skillContent).toContain("Review code.")

    const commandContent = await fs.readFile(
      path.join(tempRoot, ".gemini", "commands", "plan.toml"),
      "utf8",
    )
    expect(commandContent).toContain("Plan the work.")

    const settingsContent = JSON.parse(
      await fs.readFile(path.join(tempRoot, ".gemini", "settings.json"), "utf8"),
    )
    expect(settingsContent.mcpServers.playwright.command).toBe("npx")
  })

  test("namespaced commands create subdirectories", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "gemini-ns-"))
    const bundle: GeminiBundle = {
      generatedSkills: [],
      skillDirs: [],
      commands: [
        {
          name: "workflows/plan",
          content: 'description = "Plan"\nprompt = """\nPlan.\n"""',
        },
      ],
    }

    await writeGeminiBundle(tempRoot, bundle)

    expect(existsSync(path.join(tempRoot, ".gemini", "commands", "workflows", "plan.toml"))).toBe(true)
  })

  test("does not double-nest when output root is .gemini", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "gemini-home-"))
    const geminiRoot = path.join(tempRoot, ".gemini")
    const bundle: GeminiBundle = {
      generatedSkills: [
        { name: "reviewer", content: "Reviewer skill content" },
      ],
      skillDirs: [],
      commands: [
        { name: "plan", content: "Plan content" },
      ],
    }

    await writeGeminiBundle(geminiRoot, bundle)

    expect(existsSync(path.join(geminiRoot, "skills", "reviewer", "SKILL.md"))).toBe(true)
    expect(existsSync(path.join(geminiRoot, "commands", "plan.toml"))).toBe(true)
    // Should NOT double-nest under .gemini/.gemini
    expect(existsSync(path.join(geminiRoot, ".gemini"))).toBe(false)
  })

  test("handles empty bundles gracefully", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "gemini-empty-"))
    const bundle: GeminiBundle = {
      generatedSkills: [],
      skillDirs: [],
      commands: [],
    }

    await writeGeminiBundle(tempRoot, bundle)
    expect(existsSync(tempRoot)).toBe(true)
  })

  test("backs up existing settings.json before overwrite", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "gemini-backup-"))
    const geminiRoot = path.join(tempRoot, ".gemini")
    await fs.mkdir(geminiRoot, { recursive: true })

    // Write existing settings.json
    const settingsPath = path.join(geminiRoot, "settings.json")
    await fs.writeFile(settingsPath, JSON.stringify({ mcpServers: { old: { command: "old-cmd" } } }))

    const bundle: GeminiBundle = {
      generatedSkills: [],
      skillDirs: [],
      commands: [],
      mcpServers: {
        newServer: { command: "new-cmd" },
      },
    }

    await writeGeminiBundle(geminiRoot, bundle)

    // New settings.json should have the new content
    const newContent = JSON.parse(await fs.readFile(settingsPath, "utf8"))
    expect(newContent.mcpServers.newServer.command).toBe("new-cmd")

    // A backup file should exist
    const files = await fs.readdir(geminiRoot)
    const backupFiles = files.filter((f) => f.startsWith("settings.json.bak."))
    expect(backupFiles.length).toBeGreaterThanOrEqual(1)
  })

  test("merges mcpServers into existing settings.json without clobbering other keys", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "gemini-merge-"))
    const geminiRoot = path.join(tempRoot, ".gemini")
    await fs.mkdir(geminiRoot, { recursive: true })

    // Write existing settings.json with other keys
    const settingsPath = path.join(geminiRoot, "settings.json")
    await fs.writeFile(settingsPath, JSON.stringify({
      model: "gemini-2.5-pro",
      mcpServers: { old: { command: "old-cmd" } },
    }))

    const bundle: GeminiBundle = {
      generatedSkills: [],
      skillDirs: [],
      commands: [],
      mcpServers: {
        newServer: { command: "new-cmd" },
      },
    }

    await writeGeminiBundle(geminiRoot, bundle)

    const content = JSON.parse(await fs.readFile(settingsPath, "utf8"))
    // Should preserve existing model key
    expect(content.model).toBe("gemini-2.5-pro")
    // Should preserve existing MCP server
    expect(content.mcpServers.old.command).toBe("old-cmd")
    // Should add new MCP server
    expect(content.mcpServers.newServer.command).toBe("new-cmd")
  })
})
