#!/usr/bin/env bun
/**
 * Mechanical sync for vendored skill scripts.
 *
 * Each wf-* skill bundles byte-identical copies of the canonical scripts it
 * depends on (see scripts/script-bundles.ts) so skills-only installs stay
 * self-contained. This script replaces manual hand-copying:
 *
 *   bun run skills:sync    # copy every canonical script over its vendored copies
 *   bun run skills:check   # exit non-zero if any vendored copy is out of sync (CI)
 *
 * Entries whose canonical path already lives inside the owning skill (the
 * canonical IS the bundled file) are skipped. File modes are copied along
 * with contents so executables stay executable.
 */
import { chmodSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "fs"
import path from "path"
import { SCRIPT_BUNDLES, type ScriptBundles } from "./script-bundles"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGIN = path.join(ROOT, "plugins", "agentic-engineering")

export type SyncPair = { canonical: string; vendored: string; label: string }
export type SyncResult = { updated: string[]; inSync: string[] }

/** Every canonical -> vendored copy pair, excluding files that are their own canonical. */
export function collectPairs(pluginDir: string, bundles: ScriptBundles): SyncPair[] {
  const pairs: SyncPair[] = []
  for (const [owner, bundle] of Object.entries(bundles)) {
    for (const [file, canonicalRel] of Object.entries(bundle)) {
      const canonical = path.join(pluginDir, canonicalRel)
      const vendored = path.join(pluginDir, "skills", owner, "scripts", file)
      if (canonical === vendored) continue
      pairs.push({ canonical, vendored, label: path.join("skills", owner, "scripts", file) })
    }
  }
  return pairs
}

/** Sync (or, with check=true, just diff) every vendored copy against its canonical. */
export function syncScripts(pluginDir: string, bundles: ScriptBundles, check: boolean): SyncResult {
  const updated: string[] = []
  const inSync: string[] = []
  for (const { canonical, vendored, label } of collectPairs(pluginDir, bundles)) {
    const source = readFileSync(canonical)
    if (existsSync(vendored) && source.equals(readFileSync(vendored))) {
      inSync.push(label)
      continue
    }
    updated.push(label)
    if (check) continue
    mkdirSync(path.dirname(vendored), { recursive: true })
    writeFileSync(vendored, source)
    chmodSync(vendored, statSync(canonical).mode)
  }
  return { updated, inSync }
}

function main() {
  const check = process.argv.includes("--check")
  const { updated, inSync } = syncScripts(PLUGIN, SCRIPT_BUNDLES, check)
  if (check && updated.length) {
    console.error(`Vendored skill scripts out of sync — run \`bun run skills:sync\`:\n  ${updated.join("\n  ")}`)
    process.exit(1)
  }
  console.log(
    check
      ? `Vendored skill scripts in sync (${inSync.length} copies).`
      : updated.length
        ? `Updated ${updated.length} cop${updated.length === 1 ? "y" : "ies"} (${inSync.length} already in sync):\n  ${updated.join("\n  ")}`
        : `All ${inSync.length} vendored copies already in sync.`,
  )
}

if (import.meta.main) main()
