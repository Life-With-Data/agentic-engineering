// Merge-time gate for docs/dependency-policy.md — the two-track external
// dependency model (Track A: adopt components via the upstream registry;
// Track B: formal plugin.json dependencies). Keeps the tracks cohesive:
// every formal dependency is registered, allowlisted, and mutually exclusive
// with adoptions from the same upstream plugin.
//
// If this fails: fix the plugin.json, marketplace.json, or registry line it
// names — do not relax the assertion.

import { describe, expect, test } from "bun:test"
import { readFileSync, readdirSync, existsSync } from "fs"
import path from "path"

const ROOT = path.resolve(import.meta.dir, "..")
const REGISTRY = path.join(ROOT, "docs/upstream-sources.md")
const MARKETPLACE = path.join(ROOT, ".claude-plugin/marketplace.json")
const CORE_PLUGIN = "agentic-engineering"

// ---- collect local plugin manifests -----------------------------------------

type Dep = { name: string; version?: string; marketplace?: string }
type Manifest = { plugin: string; deps: Dep[] }

const pluginsDir = path.join(ROOT, "plugins")
const manifests: Manifest[] = readdirSync(pluginsDir, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => path.join(pluginsDir, d.name, ".claude-plugin/plugin.json"))
  .filter(existsSync)
  .map((p) => {
    const json = JSON.parse(readFileSync(p, "utf8"))
    const deps: Dep[] = (json.dependencies ?? []).map((e: string | Dep) =>
      typeof e === "string" ? { name: e } : e,
    )
    return { plugin: json.name as string, deps }
  })

const marketplace = JSON.parse(readFileSync(MARKETPLACE, "utf8"))
const localPluginNames = new Set<string>(marketplace.plugins.map((p: { name: string }) => p.name))
const allowlist: string[] = marketplace.allowCrossMarketplaceDependenciesOn ?? []

// ---- parse registry dependency: lines ----------------------------------------

// Grammar: <plugin-name> (<upstream-dir>) @ <marketplace-name>, unversioned|<range> — PR <ref> — @who YYYY-MM-DD
const DEP_LINE =
  /^([\w.-]+) \(([^)]+)\) @ ([\w.-]+), (unversioned|\S+) — PR \S+ — @[\w-]+ \d{4}-\d{2}-\d{2}$/

type RegistryDep = { plugin: string; dir: string; marketplace: string; version: string }
type RegistrySource = {
  slug: string
  scan: string
  deps: RegistryDep[]
  adoptedPaths: string[]
  rawDepLines: string[]
}

const registryContent = readFileSync(REGISTRY, "utf8").replace(/<!--[\s\S]*?-->/g, "")
const registrySources: RegistrySource[] = [...registryContent.matchAll(/^## (.+)$/gm)].map(
  (m, i, all) => {
    const start = m.index! + m[0].length
    const end = i + 1 < all.length ? all[i + 1].index! : registryContent.length
    const block = registryContent.slice(start, end)
    const rawDepLines = [...block.matchAll(/^- dependency: (.+)$/gm)].map((x) => x[1].trim())
    const deps = rawDepLines
      .map((l) => l.match(DEP_LINE))
      .filter((x): x is RegExpMatchArray => x !== null)
      .map((x) => ({ plugin: x[1], dir: x[2], marketplace: x[3], version: x[4] }))
    const adoptedSection = block.match(/^- adopted:\n((?: {2}- .*\n?)*)/m)?.[1] ?? ""
    const adoptedPaths = [...adoptedSection.matchAll(/\(upstream: (\S+)@[0-9a-f]{7,40},/g)].map(
      (x) => x[1],
    )
    return {
      slug: m[1].trim(),
      scan: block.match(/^- scan: *(\S+)/m)?.[1] ?? "",
      deps,
      adoptedPaths,
      rawDepLines,
    }
  },
)

const registryDeps = registrySources.flatMap((s) => s.deps)

// ---- invariants ---------------------------------------------------------------

describe("core plugin stays dependency-free", () => {
  test(`${CORE_PLUGIN} declares no dependencies`, () => {
    const core = manifests.find((m) => m.plugin === CORE_PLUGIN)
    expect(core).toBeDefined()
    expect(core!.deps).toEqual([])
  })
})

describe("registry dependency: line grammar", () => {
  test("every dependency: line parses", () => {
    for (const src of registrySources) {
      for (const line of src.rawDepLines) {
        expect(line).toMatch(DEP_LINE)
      }
    }
  })

  test("unversioned dependencies force scan: auto", () => {
    for (const src of registrySources) {
      if (src.deps.some((d) => d.version === "unversioned")) {
        expect(src.scan).toBe("auto")
      }
    }
  })

  test("mutual exclusion: no adoptions from a depended-on plugin's directory", () => {
    for (const src of registrySources) {
      for (const dep of src.deps) {
        const dir = dep.dir.replace(/^\.\//, "").replace(/\/$/, "")
        for (const adopted of src.adoptedPaths) {
          expect(adopted.replace(/^\.\//, "").startsWith(`${dir}/`)).toBe(false)
        }
      }
    }
  })
})

describe("plugin.json dependencies ↔ registry ↔ allowlist", () => {
  test("every external dependency is registered with a dependency: line", () => {
    for (const m of manifests) {
      for (const dep of m.deps) {
        if (!dep.marketplace) {
          // Same-marketplace dep: must name another local plugin, no registry entry needed.
          expect(localPluginNames.has(dep.name)).toBe(true)
          continue
        }
        const registered = registryDeps.some(
          (r) => r.plugin === dep.name && r.marketplace === dep.marketplace,
        )
        expect(registered).toBe(true)
      }
    }
  })

  test("every cross-marketplace dependency's marketplace is allowlisted", () => {
    for (const m of manifests) {
      for (const dep of m.deps) {
        if (dep.marketplace) {
          expect(allowlist).toContain(dep.marketplace)
        }
      }
    }
  })

  test("no standing trust: every allowlist entry is used by some dependency", () => {
    const used = new Set(manifests.flatMap((m) => m.deps.map((d) => d.marketplace)).filter(Boolean))
    for (const entry of allowlist) {
      expect(used.has(entry)).toBe(true)
    }
  })

  test("no registry dependency: line without a declaring plugin.json", () => {
    const declared = new Set(
      manifests.flatMap((m) => m.deps.filter((d) => d.marketplace).map((d) => `${d.name}@${d.marketplace}`)),
    )
    for (const r of registryDeps) {
      expect(declared.has(`${r.plugin}@${r.marketplace}`)).toBe(true)
    }
  })
})
