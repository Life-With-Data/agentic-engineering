// Merge-time gate for the upstream-adoption system (cargo-vet/awesome-lint pattern):
// a triage PR can never commit a registry block the scanner would misread, and the
// /upstream-scan command file can never regress into flagless gh writes (the fork trap).
//
// If this fails: fix the registry entry or command line it names — do not relax the
// assertion.

import { describe, expect, test } from "bun:test"
import { existsSync, readFileSync } from "fs"
import path from "path"
import { parseFrontmatter } from "../src/utils/frontmatter"

const ROOT = path.resolve(import.meta.dir, "..")
const REGISTRY = path.join(ROOT, "docs/upstream-sources.md")
const COMMAND = path.join(ROOT, "plugins/agentic-engineering/commands/upstream-scan.md")

// ---- registry schema --------------------------------------------------------

const raw = readFileSync(REGISTRY, "utf8")
const { data: fm, body } = parseFrontmatter(raw)

// Strip HTML comments (the schema doc) so field checks see only real content.
const content = body.replace(/<!--[\s\S]*?-->/g, "")

type Source = { slug: string; block: string }
const sources: Source[] = [...content.matchAll(/^## (.+)$/gm)].map((m, i, all) => {
  const start = m.index! + m[0].length
  const end = i + 1 < all.length ? all[i + 1].index! : content.length
  return { slug: m[1].trim(), block: content.slice(start, end) }
})

describe("registry frontmatter", () => {
  test("registry file exists", () => {
    expect(existsSync(REGISTRY)).toBe(true)
  })

  test("report_repo and report_label present and well-formed", () => {
    expect(String(fm.report_repo)).toMatch(/^[\w.-]+\/[\w.-]+$/)
    expect(String(fm.report_label).length).toBeGreaterThan(0)
    expect(String(fm.report_label).length).toBeLessThan(50) // GitHub label name limit
  })
})

describe("registry sources", () => {
  test("at least one source is registered", () => {
    expect(sources.length).toBeGreaterThan(0)
  })

  test.each(sources.map((s) => [s.slug, s] as const))("%s", (_slug, src) => {
    // H2 must be the canonical owner/name slug (issue-title/marker key).
    expect(src.slug).toMatch(/^[\w.-]+\/[\w.-]+$/)

    const field = (name: string): string | undefined =>
      src.block.match(new RegExp(`^- ${name}: *(.*)$`, "m"))?.[1]?.trim()

    // Required fields, with the repo URL agreeing with the slug.
    expect(field("repo")).toBe(`https://github.com/${src.slug}`)
    expect(field("license")).toBeTruthy()
    expect(field("visibility")).toMatch(/^(public|private)$/)
    expect(field("scan")).toMatch(/^(auto|manual-only)$/)
    expect(src.block).toMatch(/^- adopted:/m)
    expect(src.block).toMatch(/^- deferred:/m)

    // Entry grammar: every indented list entry under adopted:/deferred: must be a
    // candidate ID (<type>/<name>) or a bulk deferral, with " — "-delimited fields
    // ending in "@who YYYY-MM-DD".
    const entries = [...src.block.matchAll(/^ {2}- (.+)$/gm)].map((m) => m[1])
    for (const entry of entries) {
      expect(entry).toMatch(/^([a-z]+\/[\w:.-]+|all-unlisted @ [0-9a-f]{7,40}) /)
      expect(entry).toMatch(/ — @[\w-]+ \d{4}-\d{2}-\d{2}$/)
    }

    // Adopted entries additionally pin upstream provenance.
    const adoptedSection = src.block.match(/^- adopted:\n((?: {2}- .*\n?)*)/m)?.[1] ?? ""
    for (const m of adoptedSection.matchAll(/^ {2}- (.+)$/gm)) {
      expect(m[1]).toMatch(/\(upstream: \S+@[0-9a-f]{7,40}, (adapted|verbatim)\)/)
    }
  })
})

// ---- command-file gh discipline (fork trap) ---------------------------------

describe("upstream-scan command gh discipline", () => {
  const cmd = readFileSync(COMMAND, "utf8")
  const fencedLines = [...cmd.matchAll(/```bash\n([\s\S]*?)```/g)]
    .flatMap((m) => m[1].split("\n"))
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"))

  test("every gh issue/label invocation carries --repo", () => {
    const writes = fencedLines.filter((l) => /\bgh (issue|label) /.test(l))
    expect(writes.length).toBeGreaterThan(0) // the templates must exist
    for (const line of writes) {
      expect(line).toContain('--repo "$REPORT_REPO"')
    }
  })

  test("every gh api invocation targets an explicit repos/ path", () => {
    for (const line of fencedLines.filter((l) => /\bgh api /.test(l))) {
      expect(line).toMatch(/gh api "?repos\//)
    }
  })

  test("no gh pr invocations anywhere in fenced code", () => {
    for (const line of fencedLines) {
      expect(line).not.toMatch(/\bgh pr\b/)
    }
  })
})
