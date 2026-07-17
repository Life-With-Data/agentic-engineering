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
// Detection is deliberately STRUCTURAL, not tied to a single literal spelling,
// so the guardrail fails CLOSED against the realistic ways hook conversion could
// grow (a differently-named emitted artifact, bracket/optional access to the
// hooks field, a hook-logic helper import, a newly-added curated manifest). A
// known repo learning — docs/solutions/testing-patterns/grep-acceptance-checks-
// and-subset-fixtures-give-false-confidence.md — is exactly why these assertions
// key on categories (any hook-named artifact, any mention of "hook") rather than
// frozen substrings.
//
// Residual limitation (documented, not chased with a fragile regex): all hook
// logic must live INLINE in each src/converters/claude-to-*.ts. If a future
// converter delegated hook emission to a helper module whose filename contains
// no "hook" substring, the emission scan below would not see it — that refactor
// must update this test. The no-hook-import guard (invariant 3) closes the
// common form of this vector.
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
const CURATED_HOOKS_DIR = path.join(ROOT, "plugins/agentic-engineering/hooks")

// ---- frozen policy sets (change these deliberately, with a policy review) ----

// Converters that legitimately read the plugin's hooks field. Four warn-and-drop,
// one (opencode) actually emits. Any other converter touching hooks is a policy
// violation.
const HOOK_REFERENCING = new Set(["cursor", "copilot", "gemini", "kiro", "opencode"])

// Converters that read hooks only to console.warn and drop them.
const WARN_DROP = new Set(["cursor", "copilot", "gemini", "kiro"])

// The single converter permitted to emit a hook artifact (opencode's native
// TS-plugin format, currently written as `converted-hooks.ts`).
const HOOK_EMITTER = "opencode"

// ---- structural detectors (category, not a single literal spelling) ----------

// Reads the plugin hooks field: `plugin.hooks`, `plugin?.hooks`, or
// `plugin["hooks"]` / `plugin['hooks']`. Broader than one literal so a converter
// cannot quietly access hooks via optional/bracket syntax and slip the net.
const HOOK_ACCESS = /plugin\??\.hooks\b|plugin\[\s*["']hooks["']\s*\]/

// Emits a hook artifact: a `name:` field whose filename mentions "hook". Catches
// any renamed emitter (`plugin-hooks.ts`, `hooks-generated.ts`), not just the
// current `converted-hooks.ts`.
const HOOK_EMIT = /name:\s*["'`][^"'`]*hooks?[^"'`]*\.(?:ts|js|mjs|cjs|json)["'`]/i

// An import line that pulls in a hook-logic module. Hook handling must stay
// inline in the converter (see header) so the scans above can see it.
const HOOK_IMPORT = /^\s*import[^\n]*hook/im

// A console.warn(...) whose text mentions hooks. NB: `[^)]*` stops at the first
// `)`, so a warn message containing a paren before the word "hook" would fail
// this (a loud false-FAIL on benign rewording, never a silent pass); the `s`
// flag is belt-and-suspenders since `[^)]*` already crosses newlines.
const HOOK_WARN = /console\.warn\([^)]*hook/is

// ---- source loads ------------------------------------------------------------

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

// ---- invariant 1: frozen hook surface ----------------------------------------

describe("frozen hook surface", () => {
  test("exactly the allowed converters read the plugin hooks field", () => {
    const referencing = new Set(
      Object.entries(converterSource)
        .filter(([, src]) => HOOK_ACCESS.test(src))
        .map(([t]) => t),
    )
    expect([...referencing].sort()).toEqual([...HOOK_REFERENCING].sort())
  })

  test("claude, codex, droid, pi mention hooks in no form at all", () => {
    // Stronger than a `plugin.hooks`-only check: any mention of "hook" (a
    // destructure `const { hooks } = plugin`, a helper import, a comment) in a
    // converter that is supposed to be hook-free trips this.
    for (const t of ["claude", "codex", "droid", "pi"]) {
      expect(converterSource[t]).toBeDefined()
      expect(/hook/i.test(converterSource[t])).toBe(false)
    }
  })
})

// ---- invariant 2: warn-droppers drop -----------------------------------------

describe("warn-droppers drop", () => {
  for (const t of WARN_DROP) {
    test(`${t} warns about hooks and emits no hook artifact`, () => {
      expect(converterSource[t]).toBeDefined()
      expect(HOOK_WARN.test(converterSource[t])).toBe(true)
      expect(HOOK_EMIT.test(converterSource[t])).toBe(false)
    })
  }
})

// ---- invariant 3: opencode is the sole hook-emitter --------------------------

describe("opencode is the sole hook-emitter", () => {
  test("exactly opencode emits a hook-named artifact", () => {
    const emitters = Object.entries(converterSource)
      .filter(([, src]) => HOOK_EMIT.test(src))
      .map(([t]) => t)
      .sort()
    expect(emitters).toEqual([HOOK_EMITTER])
  })

  test("no converter imports a hook-logic helper module", () => {
    // Hook logic stays inline so the emission/access scans can see it.
    const importers = Object.entries(converterSource)
      .filter(([, src]) => HOOK_IMPORT.test(src))
      .map(([t]) => t)
    expect(importers).toEqual([])
  })

  test("no target writer references hooks (targets are hook-agnostic)", () => {
    for (const [file, src] of Object.entries(targetSource)) {
      expect({ file, hasHook: /hook/i.test(src) }).toEqual({ file, hasHook: false })
    }
  })
})

// ---- invariant 4: safety hooks curated, not generated ------------------------

describe("safety hooks are curated, not generated", () => {
  // Derived from the filesystem, not a frozen list, so a newly-added curated
  // manifest (e.g. hooks-droid.json) is covered automatically.
  const CURATED = existsSync(CURATED_HOOKS_DIR)
    ? readdirSync(CURATED_HOOKS_DIR).filter((f) => /^hooks-.+\.json$/.test(f))
    : []

  const collect = (dir: string): string[] => {
    const out: string[] = []
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) out.push(...collect(p))
      else if (/\.(ts|js|json|mjs|cjs)$/.test(e.name)) out.push(p)
    }
    return out
  }

  test("the curated hook manifests exist (sanity: the guard has something to protect)", () => {
    expect(CURATED.length).toBeGreaterThan(0)
  })

  test("no file under src/ or scripts/ references any curated hook manifest", () => {
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
