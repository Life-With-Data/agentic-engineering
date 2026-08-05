import { describe, expect, test } from "bun:test"
import { existsSync, promises as fs } from "fs"
import os from "os"
import path from "path"
import { writeClaudeBundle } from "../src/targets/claude"
import type { ClaudePlugin } from "../src/types/claude"

describe("writeClaudeBundle", () => {
  test("copies the source plugin tree to a named subdirectory", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "claude-writer-"))
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin")
    const bundle: ClaudePlugin = {
      root: fixtureRoot,
      manifest: { name: "agentic-engineering", version: "1.0.0" },
      agents: [],
      commands: [],
      skills: [],
    }

    await writeClaudeBundle(tempRoot, bundle)

    expect(
      existsSync(path.join(tempRoot, "agentic-engineering", ".claude-plugin", "plugin.json")),
    ).toBe(true)
    expect(existsSync(path.join(tempRoot, "agentic-engineering", "agents", "agent-one.md"))).toBe(true)
    expect(existsSync(path.join(tempRoot, "agentic-engineering", "skills", "skill-one", "SKILL.md"))).toBe(
      true,
    )
  })

  test("writes directly when output root already ends in plugin name", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "claude-writer-direct-"))
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin")
    const directRoot = path.join(tempRoot, "agentic-engineering")
    const bundle: ClaudePlugin = {
      root: fixtureRoot,
      manifest: { name: "agentic-engineering", version: "1.0.0" },
      agents: [],
      commands: [],
      skills: [],
    }

    await writeClaudeBundle(directRoot, bundle)

    expect(existsSync(path.join(directRoot, ".claude-plugin", "plugin.json"))).toBe(true)
    expect(existsSync(path.join(directRoot, "commands", "command-one.md"))).toBe(true)
    expect(existsSync(path.join(directRoot, "agentic-engineering"))).toBe(false)
  })
})
