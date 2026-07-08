// Guards against the "added a component but forgot to update X" class of drift.
// Every declared count / list / version that describes the agentic-engineering
// (core) plugin is checked against the filesystem truth, and every other plugin
// under plugins/ gets basic checks (skill count in descriptions, version parity
// with marketplace.json, skill frontmatter). Runs in CI via `bun test`.
//
// If this fails: the message names the exact file + component that is out of
// sync. Fix the source of truth (add the missing row, bump the count, etc.) —
// do not relax the assertion.

import { describe, expect, test } from "bun:test"
import { existsSync, readdirSync, readFileSync } from "fs"
import path from "path"
import { parseFrontmatter } from "../src/utils/frontmatter"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGINS_DIR = path.join(ROOT, "plugins")
const CORE_PLUGIN_NAME = "agentic-engineering"
const PLUGIN = path.join(PLUGINS_DIR, CORE_PLUGIN_NAME)

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

function skillDirsIn(pluginDir: string): string[] {
  const dir = path.join(pluginDir, "skills")
  if (!existsSync(dir)) return []
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(path.join(dir, e.name, "SKILL.md")))
    .map((e) => e.name)
}

// ---- filesystem truth -------------------------------------------------------

const agentFiles = mdFilesRecursive(path.join(PLUGIN, "agents"))
const commandFiles = mdFilesRecursive(path.join(PLUGIN, "commands"))
const skillDirs = skillDirsIn(PLUGIN)

const nonCorePlugins = readdirSync(PLUGINS_DIR, { withFileTypes: true })
  .filter(
    (e) =>
      e.isDirectory() &&
      e.name !== CORE_PLUGIN_NAME &&
      existsSync(path.join(PLUGINS_DIR, e.name, ".claude-plugin/plugin.json")),
  )
  .map((e) => e.name)
  .sort()

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
    // Skills (like all landing stats) are marketplace-wide: core plugin + every other plugin under plugins/.
    const totalSkills = counts.skills + nonCorePlugins.reduce((n, p) => n + skillDirsIn(path.join(PLUGINS_DIR, p)).length, 0)
    const nums = [...indexHtml.matchAll(/<div class="stat-number">(\d+)<\/div>/g)].map((m) => Number(m[1]))
    expect(nums.slice(0, 4)).toEqual([counts.agents, counts.commands, totalSkills, mcpCount])
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

// ---- non-core plugins: basic consistency checks ------------------------------
// Every plugin under plugins/ other than the core one gets at minimum: a
// marketplace.json entry, an accurate "Includes N skill(s)" phrase in both
// descriptions, version parity, and skill frontmatter hygiene.

describe.each(nonCorePlugins)("non-core plugin: %s", (name) => {
  const dir = path.join(PLUGINS_DIR, name)
  const pj = JSON.parse(readFileSync(path.join(dir, ".claude-plugin/plugin.json"), "utf8"))
  const entry = marketplace.plugins.find((p: { name: string }) => p.name === name)
  const skills = skillDirsIn(dir)
  const skillPhrase = `Includes ${skills.length} skill${skills.length === 1 ? "" : "s"}`

  test("has a marketplace.json entry", () => {
    expect(entry).toBeDefined()
  })

  test(`plugin.json description declares "${skillPhrase}"`, () => {
    expect(pj.description).toContain(skillPhrase)
  })

  test(`marketplace.json description declares "${skillPhrase}"`, () => {
    expect(entry?.description).toContain(skillPhrase)
  })

  test("plugin.json and marketplace.json versions agree", () => {
    expect(pj.version).toBe(entry?.version)
  })

  if (skills.length) {
    test.each(skills)("skill %s declares name (matching dir) + description", (skillDir) => {
      const { data } = parseFrontmatter(readFileSync(path.join(dir, "skills", skillDir, "SKILL.md"), "utf8"))
      expect(data.name).toBe(skillDir)
      expect(typeof data.description).toBe("string")
      expect(String(data.description).length).toBeGreaterThan(0)
    })
  }
})
