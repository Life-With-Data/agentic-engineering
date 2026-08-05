import { describe, expect, test } from "bun:test"
import { existsSync, promises as fs } from "fs"
import os from "os"
import path from "path"
import { writeCursorBundle } from "../src/targets/cursor"
import type { CursorBundle } from "../src/types/cursor"

describe("writeCursorBundle", () => {
  test("writes rules, commands, skills, and mcp.json", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cursor-test-"))
    const bundle: CursorBundle = {
      rules: [{ name: "security-reviewer", content: "---\nalwaysApply: false\n---\n\nRule" }],
      commands: [{ name: "plan", content: "<!-- Plan -->\n\nPlan the work." }],
      skillDirs: [
        {
          name: "skill-one",
          sourceDir: path.join(import.meta.dir, "fixtures", "sample-plugin", "skills", "skill-one"),
        },
      ],
      mcpServers: {
        local: { command: "npx", args: ["-y", "pkg"] },
      },
    }

    await writeCursorBundle(tempRoot, bundle)

    expect(existsSync(path.join(tempRoot, ".cursor", "rules", "security-reviewer.mdc"))).toBe(true)
    expect(existsSync(path.join(tempRoot, ".cursor", "commands", "plan.md"))).toBe(true)
    expect(existsSync(path.join(tempRoot, ".cursor", "skills", "skill-one", "SKILL.md"))).toBe(true)
    expect(existsSync(path.join(tempRoot, ".cursor", "mcp.json"))).toBe(true)

    const mcp = JSON.parse(await fs.readFile(path.join(tempRoot, ".cursor", "mcp.json"), "utf8"))
    expect(mcp.mcpServers.local.command).toBe("npx")
  })

  test("writes directly into a .cursor output root without double nesting", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cursor-home-"))
    const cursorRoot = path.join(tempRoot, ".cursor")
    const bundle: CursorBundle = {
      rules: [{ name: "r", content: "rule" }],
      commands: [{ name: "c", content: "command" }],
      skillDirs: [],
    }

    await writeCursorBundle(cursorRoot, bundle)

    expect(existsSync(path.join(cursorRoot, "rules", "r.mdc"))).toBe(true)
    expect(existsSync(path.join(cursorRoot, "commands", "c.md"))).toBe(true)
    expect(existsSync(path.join(cursorRoot, ".cursor"))).toBe(false)
  })

  test("backs up existing mcp.json before overwriting", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cursor-backup-"))
    const cursorRoot = path.join(tempRoot, ".cursor")
    await fs.mkdir(cursorRoot, { recursive: true })
    const mcpPath = path.join(cursorRoot, "mcp.json")
    const original = { mcpServers: { old: { command: "old" } } }
    await fs.writeFile(mcpPath, JSON.stringify(original))

    const bundle: CursorBundle = {
      rules: [],
      commands: [],
      skillDirs: [],
      mcpServers: { newServer: { command: "new" } },
    }

    await writeCursorBundle(cursorRoot, bundle)

    const next = JSON.parse(await fs.readFile(mcpPath, "utf8"))
    expect(next.mcpServers.newServer.command).toBe("new")

    const files = await fs.readdir(cursorRoot)
    const backup = files.find((name) => name.startsWith("mcp.json.bak."))
    expect(backup).toBeDefined()
  })
})
