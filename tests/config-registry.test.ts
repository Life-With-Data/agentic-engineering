// Prevents a config flag from shipping invisibly again (the exact gap
// nudge_todowrite shipped through in PR #90, before config_registry.py
// existed): every `meta.get("some_key", ...)` read off a parsed frontmatter
// dict in plugins/*/scripts/*.py must have a matching entry in the relevant
// plugin's config_registry.py, OR be explicitly allowlisted with a
// justification (a key that belongs to a *different* frontmatter document,
// e.g. a docs/plans/*.md tracker field, not agentic-engineering(.local).md).
//
// This is a forward check (every read is registered) plus a reverse check
// (every registered flag's `owner` script exists and actually contains the
// key literal) — the reverse check is the safety net for readers that don't
// use the `meta.get("literal")` idiom this scanner targets (e.g.
// workflow-repo-preflight.py's read_local_config_tracker, which hand-rolls a
// regex instead).
//
// If this fails: a new frontmatter-key read was added without a matching
// CONFIG_FLAGS entry. Either register it in the plugin's config_registry.py
// (preferred) or, if it's a legitimate exception (a different frontmatter
// document entirely), add it to ALLOWLIST below with a one-line justification.

import { describe, expect, test } from "bun:test"
import { existsSync, readdirSync, readFileSync } from "fs"
import path from "path"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGINS_DIR = path.join(ROOT, "plugins")

// ---- allowlist: known-legitimate meta.get("literal") reads that are NOT --
// ---- agentic-engineering(.local).md config flags -------------------------
// Keyed by "<plugin>:<relpath-from-plugin>:<line>". Keep this list small and
// current — a stale entry (no matching call at that key) fails the test.
const ALLOWLIST: Record<string, string> = {
  "agentic-engineering:scripts/lifecycle_board.py:948":
    "github_issue is a docs/plans/*.md plan-tracker field (read_plan_tracker_id), " +
    "not an agentic-engineering(.local).md config flag.",
}

// ---- discovery: every plugin's scripts/*.py -------------------------------

function pluginDirs(): { name: string; dir: string }[] {
  return readdirSync(PLUGINS_DIR, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => ({ name: e.name, dir: path.join(PLUGINS_DIR, e.name) }))
    .filter((p) => existsSync(path.join(p.dir, ".claude-plugin", "plugin.json")))
}

function pyFiles(dir: string): string[] {
  if (!existsSync(dir)) return []
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".py"))
    .map((e) => path.join(dir, e.name))
}

// ---- forward check: every meta.get("literal") read is registered ---------

// `meta.get("key")` / `meta.get('key', default)` — the codebase's dominant
// idiom for reading a value off a dict returned by parse_frontmatter(). A
// variable second argument (`meta.get(field, "")`) has no literal to extract
// and is correctly ignored — those iterate a fixed, already-known field set.
const META_GET = /\bmeta\.get\(\s*(['"])([A-Za-z_][\w-]*)\1/g

type Hit = { file: string; rel: string; line: number; key: string }

function collectMetaGetReads(file: string, pluginDir: string): Hit[] {
  const rel = path.relative(pluginDir, file)
  const lines = readFileSync(file, "utf8").split("\n")
  const hits: Hit[] = []
  lines.forEach((line, i) => {
    for (const m of line.matchAll(META_GET)) {
      hits.push({ file, rel, line: i + 1, key: m[2] })
    }
  })
  return hits
}

// ---- registry parsing: config_registry.py's CONFIG_FLAGS -----------------
// Parsed from source text (not executed — this is a bun test, no Python
// runtime): each ConfigFlag entry is `key="...",` and `owner="...",` on their
// own lines, per the format config_registry.py is written in.

type RegisteredFlag = { key: string; owner: string }

function parseRegistry(registryFile: string): RegisteredFlag[] {
  const text = readFileSync(registryFile, "utf8")
  // Split on ConfigFlag( to isolate each entry's block, then pull key/owner
  // out of each block independently (order-independent within the block).
  const blocks = text.split(/\bConfigFlag\(/).slice(1)
  const flags: RegisteredFlag[] = []
  for (const block of blocks) {
    const keyMatch = block.match(/\bkey\s*=\s*"([A-Za-z_][\w-]*)"/)
    const ownerMatch = block.match(/\bowner\s*=\s*"([^"]+)"/)
    if (keyMatch && ownerMatch) {
      flags.push({ key: keyMatch[1], owner: ownerMatch[1] })
    }
  }
  return flags
}

// ---- the assertions --------------------------------------------------------

describe("config flags are registered and discoverable", () => {
  const plugins = pluginDirs()

  test("scans at least one plugin with a config_registry.py", () => {
    // Guards against a broken scanner silently finding nothing.
    const withRegistry = plugins.filter((p) =>
      existsSync(path.join(p.dir, "scripts", "config_registry.py")),
    )
    expect(withRegistry.length).toBeGreaterThanOrEqual(1)
  })

  for (const plugin of plugins) {
    const registryFile = path.join(plugin.dir, "scripts", "config_registry.py")
    if (!existsSync(registryFile)) continue

    test(`${plugin.name}: every meta.get("key") read is registered or allowlisted`, () => {
      const registered = new Set(parseRegistry(registryFile).map((f) => f.key))
      const scriptFiles = pyFiles(path.join(plugin.dir, "scripts"))
      const violations: string[] = []
      const unusedAllow = new Set(
        Object.keys(ALLOWLIST).filter((k) => k.startsWith(`${plugin.name}:`)),
      )

      for (const file of scriptFiles) {
        for (const hit of collectMetaGetReads(file, plugin.dir)) {
          const allowKey = `${plugin.name}:${hit.rel}:${hit.line}`
          if (allowKey in ALLOWLIST) {
            unusedAllow.delete(allowKey)
            continue
          }
          if (registered.has(hit.key)) continue
          violations.push(`${allowKey}: meta.get("${hit.key}")`)
        }
      }

      expect(
        violations,
        `Unregistered config-flag read(s) — a script reads a frontmatter key with no ` +
          `matching CONFIG_FLAGS entry:\n${violations.join("\n")}\n\n` +
          `Register it in ${path.relative(ROOT, registryFile)}, or if it belongs to a ` +
          `different frontmatter document entirely, add it to ALLOWLIST in ` +
          `tests/config-registry.test.ts with a justification.`,
      ).toEqual([])

      // Keep the allowlist honest: a stale entry means the read moved or was
      // removed — remove it so a future unregistered read at that key is caught.
      expect(
        [...unusedAllow],
        `Stale ALLOWLIST entries (no matching meta.get call) — remove them:`,
      ).toEqual([])
    })

    test(`${plugin.name}: every registered flag's owner script exists and names the key`, () => {
      const flags = parseRegistry(registryFile)
      expect(flags.length).toBeGreaterThan(0)

      const violations: string[] = []
      for (const flag of flags) {
        // owner is a plugin-relative path, e.g. "scripts/nudge-todowrite-to-tracker.py"
        // or "skills/setup/SKILL.md" (a writer, not a reader — still must name the key).
        const ownerPath = path.join(plugin.dir, flag.owner)
        if (!existsSync(ownerPath)) {
          violations.push(`${flag.key}: owner "${flag.owner}" does not exist`)
          continue
        }
        const ownerText = readFileSync(ownerPath, "utf8")
        if (!ownerText.includes(flag.key)) {
          violations.push(`${flag.key}: owner "${flag.owner}" does not contain the key literal`)
        }
      }

      expect(
        violations,
        `Registered flag(s) with a broken owner reference:\n${violations.join("\n")}`,
      ).toEqual([])
    })
  }
})
