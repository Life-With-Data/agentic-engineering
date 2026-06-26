// Guards against the "added a component but forgot to update X" class of drift.
// Every declared count / list / version that describes the agentic-engineering
// plugin is checked against the filesystem truth. Runs in CI via `bun test`.
//
// If this fails: the message names the exact file + component that is out of
// sync. Fix the source of truth (add the missing row, bump the count, etc.) —
// do not relax the assertion.

import { describe, expect, test } from "bun:test"
import { existsSync, readdirSync, readFileSync } from "fs"
import path from "path"
import { parseFrontmatter } from "../src/utils/frontmatter"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGIN = path.join(ROOT, "plugins/agentic-engineering")

function mdFilesRecursive(dir: string): string[] {
  if (!existsSync(dir)) return []
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...mdFilesRecursive(p))
    else if (entry.name.endsWith(".md")) out.push(p)
  }
  return out
}

function frontmatterName(file: string): string {
  return String(parseFrontmatter(readFileSync(file, "utf8")).data.name ?? "")
}

// ---- filesystem truth -------------------------------------------------------

const agentFiles = mdFilesRecursive(path.join(PLUGIN, "agents"))
const commandFiles = mdFilesRecursive(path.join(PLUGIN, "commands"))
const skillDirs = readdirSync(path.join(PLUGIN, "skills"), { withFileTypes: true })
  .filter((e) => e.isDirectory() && existsSync(path.join(PLUGIN, "skills", e.name, "SKILL.md")))
  .map((e) => e.name)

const counts = {
  agents: agentFiles.length,
  commands: commandFiles.length,
  skills: skillDirs.length,
}

const pluginJson = JSON.parse(readFileSync(path.join(PLUGIN, ".claude-plugin/plugin.json"), "utf8"))
const marketplace = JSON.parse(readFileSync(path.join(ROOT, ".claude-plugin/marketplace.json"), "utf8"))
const mcpCount = Object.keys(pluginJson.mcpServers ?? {}).length

const pluginReadme = readFileSync(path.join(PLUGIN, "README.md"), "utf8")
const rootReadme = readFileSync(path.join(ROOT, "README.md"), "utf8")
const indexHtml = readFileSync(path.join(ROOT, "docs/index.html"), "utf8")

// ---- declared counts match the filesystem ----------------------------------

describe("declared counts match filesystem", () => {
  test("plugin.json description", () => {
    expect(pluginJson.description).toContain(`${counts.agents} agents`)
    expect(pluginJson.description).toContain(`${counts.commands} commands`)
    expect(pluginJson.description).toContain(`${counts.skills} skills`)
  })

  test("marketplace.json description", () => {
    const desc = marketplace.plugins[0].description
    expect(desc).toContain(`${counts.agents} specialized agents`)
    expect(desc).toContain(`${counts.commands} commands`)
    expect(desc).toContain(`${counts.skills} skills`)
  })

  test("plugin README components table", () => {
    expect(pluginReadme).toContain(`| Agents | ${counts.agents} |`)
    expect(pluginReadme).toContain(`| Commands | ${counts.commands} |`)
    expect(pluginReadme).toContain(`| Skills | ${counts.skills} |`)
    expect(pluginReadme).toContain(`| MCP Servers | ${mcpCount} |`)
  })

  test("root README components table", () => {
    expect(rootReadme).toContain(`| Specialized agents | ${counts.agents} |`)
    expect(rootReadme).toContain(`| Commands | ${counts.commands} |`)
    expect(rootReadme).toContain(`| Skills | ${counts.skills} |`)
    expect(rootReadme).toContain(`| MCP servers | ${mcpCount} |`)
  })

  test("docs/index.html landing-page stats (agents, commands, skills, mcp)", () => {
    const nums = [...indexHtml.matchAll(/<div class="stat-number">(\d+)<\/div>/g)].map((m) => Number(m[1]))
    expect(nums.slice(0, 4)).toEqual([counts.agents, counts.commands, counts.skills, mcpCount])
  })
})

// ---- version parity ---------------------------------------------------------

describe("version parity", () => {
  test("plugin.json and marketplace.json agree", () => {
    expect(pluginJson.version).toBe(marketplace.plugins[0].version)
  })
})

// ---- every component is documented in the plugin README ---------------------

describe("plugin README documents every command (by frontmatter name)", () => {
  test.each(commandFiles.map((f) => [path.basename(f), frontmatterName(f)] as const))(
    "%s → /%s is in README",
    (_file, name) => {
      expect(name).not.toBe("") // every command must declare a name
      expect(pluginReadme).toContain(`/${name}`)
    },
  )
})

describe("plugin README documents every agent", () => {
  test.each(agentFiles.map((f) => path.basename(f, ".md")))("%s is in README", (slug) => {
    expect(pluginReadme).toContain(slug)
  })
})

describe("plugin README documents every skill", () => {
  test.each(skillDirs)("%s is in README", (slug) => {
    expect(pluginReadme).toContain(slug)
  })
})

// ---- frontmatter hygiene ----------------------------------------------------

describe("commands and agents declare name + description", () => {
  test.each([...commandFiles, ...agentFiles].map((f) => [path.relative(PLUGIN, f), f] as const))(
    "%s",
    (_rel, file) => {
      const { data } = parseFrontmatter(readFileSync(file, "utf8"))
      expect(typeof data.name).toBe("string")
      expect(String(data.name).length).toBeGreaterThan(0)
      expect(typeof data.description).toBe("string")
      expect(String(data.description).length).toBeGreaterThan(0)
    },
  )
})

describe("skills declare name (matching dir) + description", () => {
  test.each(skillDirs)("%s/SKILL.md", (dir) => {
    const { data } = parseFrontmatter(readFileSync(path.join(PLUGIN, "skills", dir, "SKILL.md"), "utf8"))
    expect(data.name).toBe(dir)
    expect(typeof data.description).toBe("string")
    expect(String(data.description).length).toBeGreaterThan(0)
  })
})
