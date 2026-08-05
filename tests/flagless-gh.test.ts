// Durable control that every gh WRITE in a distributed skill is
// SELF-TARGETING. These skills run in arbitrary users' repos, so a flagless
// `gh issue|project|api` write relies on gh's default-repo resolution and can
// silently land on the wrong repo. This test greps every skill
// markdown file for `gh issue|gh project|gh api` invocations inside bash code
// fences and requires each to be self-targeting: an explicit --repo/--owner
// (literal or documented variable form like `--repo "$REPORT_REPO"`), OR a
// read-only subcommand (reads can't mutate the wrong repo).
//
// If this fails: a new flagless gh WRITE was added to a skill. Add the
// explicit --repo/--owner flag. Do NOT relax the matcher.
//
// Scope note: this scans .md files only. Shell scripts under skills/**/scripts/
// are not markdown and are covered by their own in-script --repo/--owner
// discipline (Security invariant 7).

import { describe, expect, test } from "bun:test"
import { existsSync, readdirSync, readFileSync } from "fs"
import path from "path"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGIN = path.join(ROOT, "plugins/agentic-engineering")

// ---- fence-aware scanner ----------------------------------------------------

const BASH_LANGS = new Set(["bash", "sh", "shell", "console", ""])
// A gh issue|project|api invocation (word-boundary; skips e.g. `github`).
const GH_CALL = /\bgh\s+(issue|project|api)\b/
// Read-only subcommands that cannot mutate any repo.
const READ_ONLY =
  /\bgh\s+(?:issue\s+(?:list|view|status)|project\s+(?:list|view|item-list|field-list)|api\s+graphql|api\b)/
// A gh api call is a WRITE only if it names an explicit write method.
const API_WRITE_METHOD = /(?:-X|--method)\s+(?:POST|PATCH|PUT|DELETE)/
// Explicit self-targeting flag, literal or variable form (`--repo "$REPORT_REPO"`,
// `--owner aagnone3`, `--repo aagnone3/agentic-engineering`).
const HAS_TARGET_FLAG = /--(?:repo|owner)\b/

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

type Hit = { file: string; rel: string; line: number; text: string }

// Collect every gh issue|project|api invocation inside a bash code fence,
// joining backslash line-continuations so multi-line commands are judged whole.
function collectGhCalls(file: string): Hit[] {
  const rel = path.relative(PLUGIN, file)
  const lines = readFileSync(file, "utf8").split("\n")
  const hits: Hit[] = []
  let inFence = false
  let fenceLang = ""
  for (let i = 0; i < lines.length; i++) {
    const fence = lines[i].match(/^\s*```(\w*)/)
    if (fence) {
      if (!inFence) {
        inFence = true
        fenceLang = fence[1].toLowerCase()
      } else {
        inFence = false
        fenceLang = ""
      }
      continue
    }
    if (!inFence || !BASH_LANGS.has(fenceLang)) continue

    // Join a backslash-continued command onto one logical line, anchored at the
    // line where the `gh` token first appears (that is the line we key on).
    let text = lines[i]
    if (!GH_CALL.test(text)) continue
    const startLine = i + 1
    while (/\\\s*$/.test(text) && i + 1 < lines.length) {
      i += 1
      text = text.replace(/\\\s*$/, " ") + lines[i]
    }
    hits.push({ file, rel, line: startLine, text: text.trim() })
  }
  return hits
}

function isRead(text: string): boolean {
  // `gh api <path>` with no write method is a read; `gh api graphql` node IDs are
  // opaque to this grep, so treat it as read here (in-script --owner is the guard).
  if (/\bgh\s+api\b/.test(text) && !API_WRITE_METHOD.test(text)) return true
  return READ_ONLY.test(text) && !API_WRITE_METHOD.test(text)
}

// ---- the assertion ----------------------------------------------------------

describe("flagless gh writes are guarded", () => {
  const files = mdFilesRecursive(path.join(PLUGIN, "skills"))

  test("scans at least the known skill surface", () => {
    // Guards against a broken scanner silently finding nothing.
    expect(files.length).toBeGreaterThan(10)
  })

  test("every gh issue|project|api write carries --repo/--owner", () => {
    const violations: string[] = []

    for (const file of files) {
      for (const hit of collectGhCalls(file)) {
        if (isRead(hit.text)) continue
        if (HAS_TARGET_FLAG.test(hit.text)) continue
        violations.push(`${hit.rel}:${hit.line}: ${hit.text}`)
      }
    }

    expect(
      violations,
      `Flagless gh WRITE(s) with no --repo/--owner:\n` +
        violations.join("\n") +
        `\n\nAdd the explicit --repo/--owner flag.`,
    ).toEqual([])
  })
})
