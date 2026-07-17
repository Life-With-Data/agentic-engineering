// Merge-time gate for docs/conversion-policy.md — the cross-agent asset-support
// policy. Support conversion only where a shared standard makes it free AND
// failure-safe; stop at Claude-only the moment faithful conversion needs
// per-target mapping tables (hooks, above all). This test freezes the current
// converter/target hook surface so nobody can quietly grow hook conversion into
// another target and re-introduce the leaky, security-fail-open surface the
// policy rejects.
//
// If this fails: a converter changed its hook handling — review
// docs/conversion-policy.md and update deliberately; do not relax the assertion.
//
// Style mirrors tests/dependency-policy.test.ts: module-level readFileSync of
// source text, regex/Set assertions in describe blocks, no imports from src/,
// no fixtures, no mocks.

import { describe, expect, test } from "bun:test"
import { readFileSync, readdirSync, existsSync } from "fs"
import path from "path"

const ROOT = path.resolve(import.meta.dir, "..")
const CONVERTERS_DIR = path.join(ROOT, "src/converters")
const TARGETS_DIR = path.join(ROOT, "src/targets")

// ---- frozen policy sets (change these deliberately, with a policy review) ----

// Converters that legitimately reference `plugin.hooks`. Four warn-and-drop,
// one (opencode) actually emits. Any other converter touching plugin.hooks is a
// policy violation.
const HOOK_REFERENCING = new Set(["cursor", "copilot", "gemini", "kiro", "opencode"])

// Converters that read plugin.hooks only to console.warn and drop them.
const WARN_DROP = new Set(["cursor", "copilot", "gemini", "kiro"])

// The single converter permitted to emit a hook artifact (opencode's native
// TS-plugin format, written as `converted-hooks.ts`).
const HOOK_EMITTER = "opencode"

// ---- helpers -----------------------------------------------------------------

const targetOf = (file: string) => file.replace(/^claude-to-/, "").replace(/\.ts$/, "")

const converterFiles = readdirSync(CONVERTERS_DIR).filter(
  (f) => /^claude-to-.+\.ts$/.test(f),
)
const converterSource: Record<string, string> = Object.fromEntries(
  converterFiles.map((f) => [targetOf(f), readFileSync(path.join(CONVERTERS_DIR, f), "utf8")]),
)

const targetFiles = readdirSync(TARGETS_DIR).filter((f) => /\.ts$/.test(f))
const targetSource: Record<string, string> = Object.fromEntries(
  targetFiles.map((f) => [f, readFileSync(path.join(TARGETS_DIR, f), "utf8")]),
)

// A console.warn(...) whose argument text mentions hooks. `s` flag so the match
// spans multi-line console.warn( \n "…hooks…" ) calls.
const HOOK_WARN = /console\.warn\([^)]*hook/is

// ---- invariant 1: frozen hook surface ----------------------------------------

describe("frozen hook surface", () => {
  test("exactly the allowed converters reference plugin.hooks", () => {
    const referencing = new Set(
      Object.entries(converterSource)
        .filter(([, src]) => /plugin\.hooks/.test(src))
        .map(([t]) => t),
    )
    expect([...referencing].sort()).toEqual([...HOOK_REFERENCING].sort())
  })

  test("claude, codex, droid, pi reference plugin.hooks nowhere", () => {
    for (const t of ["claude", "codex", "droid", "pi"]) {
      expect(converterSource[t]).toBeDefined()
      expect(/plugin\.hooks/.test(converterSource[t])).toBe(false)
    }
  })
})

// ---- invariant 2: warn-droppers drop -----------------------------------------

describe("warn-droppers drop", () => {
  for (const t of WARN_DROP) {
    test(`${t} warns about hooks and emits no hook artifact`, () => {
      expect(converterSource[t]).toBeDefined()
      expect(HOOK_WARN.test(converterSource[t])).toBe(true)
      expect(converterSource[t].includes("converted-hooks")).toBe(false)
    })
  }
})

// ---- invariant 3: opencode is the sole hook-emitter --------------------------

describe("opencode is the sole hook-emitter", () => {
  test("exactly claude-to-opencode.ts references converted-hooks", () => {
    const emitters = Object.entries(converterSource)
      .filter(([, src]) => src.includes("converted-hooks"))
      .map(([t]) => t)
    expect(emitters).toEqual([HOOK_EMITTER])
  })

  test("no target writer references hooks (targets are hook-agnostic)", () => {
    for (const [file, src] of Object.entries(targetSource)) {
      expect({ file, hasHook: /hook/i.test(src) }).toEqual({ file, hasHook: false })
    }
  })
})

// ---- invariant 4: safety hooks curated, not generated ------------------------

describe("safety hooks are curated, not generated", () => {
  const CURATED = ["hooks-codex.json", "hooks-cursor.json"]

  const collect = (dir: string): string[] => {
    const out: string[] = []
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) out.push(...collect(p))
      else if (/\.(ts|js|json|mjs|cjs)$/.test(e.name)) out.push(p)
    }
    return out
  }

  test("no file under src/ or scripts/ references the curated hook manifests", () => {
    const files = [
      ...collect(path.join(ROOT, "src")),
      ...(existsSync(path.join(ROOT, "scripts")) ? collect(path.join(ROOT, "scripts")) : []),
    ]
    const offenders = files.filter((f) => {
      const src = readFileSync(f, "utf8")
      return CURATED.some((name) => src.includes(name))
    })
    expect(offenders).toEqual([])
  })
})

// ---- invariant 5: doc ↔ test linkage -----------------------------------------

describe("doc ↔ test linkage", () => {
  test("docs/conversion-policy.md exists and names this test", () => {
    const doc = path.join(ROOT, "docs/conversion-policy.md")
    expect(existsSync(doc)).toBe(true)
    expect(readFileSync(doc, "utf8").includes("tests/conversion-policy.test.ts")).toBe(true)
  })
})
