// Durable control for the "fork trap" on gh WRITES that the PreToolUse hook
// (.claude/hooks/block-upstream-pr.sh) cannot see once they run inside a shell
// snippet a human copies, a subagent executes, or a script wraps — the hook only
// inspects the top-level Bash tool command. This test greps every command and
// skill markdown file for `gh issue|gh project|gh api` invocations inside bash
// code fences and requires each to be self-targeting: an explicit --repo/--owner
// (literal or documented variable form like `--repo "$REPORT_REPO"`), OR a
// read-only subcommand (reads can't leak a write to upstream), OR an entry in the
// ALLOWLIST below.
//
// If this fails: a new flagless gh WRITE was added to a command/skill. Either add
// the explicit --repo/--owner flag (preferred) or, if it is a legitimate
// exception (a legacy snippet, a placeholder, a self-enforcing script), add it to
// ALLOWLIST with a one-line justification. Do NOT relax the matcher.
//
// Scope note: this scans .md files only. Shell scripts under skills/**/scripts/
// are not markdown and are covered by their own in-script --repo/--owner
// discipline (Security invariant 7); the hook + this grep are backstops.

import { describe, expect, test } from "bun:test"
import { existsSync, readdirSync, readFileSync } from "fs"
import path from "path"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGIN = path.join(ROOT, "plugins/agentic-engineering")

// ---- allowlist: known-legitimate flagless gh invocations --------------------
// Keyed by "<relpath-from-plugin>:<line>". Each entry is a legacy or placeholder
// snippet that is NOT a live upstream-write risk. Keep this list small and
// current — every entry is a debt the lifecycle rewrite (Phase 3) is expected to
// pay down (these two are the pre-rewrite `github` plain-mode issue writers).
const ALLOWLIST: Record<string, string> = {
  // Legacy `github` plain-mode plan-issue writer. Runs against gh's default repo
  // (pinned to origin by the SessionStart hook); rewritten to route through
  // lifecycle_board.py --set-status in Phase 3.
  "commands/workflows/plan.md:642":
    "legacy `github` mode: gh issue create against pinned default repo",
  // Legacy `github` plain-mode issue-close snippet with a <issue-number>
  // placeholder. Same pinned-default-repo rationale; rewritten in Phase 3 to
  // invoke the shared reconciler.
  "commands/workflows/work.md:453":
    "legacy `github` mode: gh issue close placeholder against pinned default repo",
}

// ---- fence-aware scanner ----------------------------------------------------

const BASH_LANGS = new Set(["bash", "sh", "shell", "console", ""])
// A gh issue|project|api invocation (word-boundary; skips e.g. `github`).
const GH_CALL = /\bgh\s+(issue|project|api)\b/
// Read-only subcommands that cannot leak a write to upstream.
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
  // `gh api <path>` with no write method is a read; `gh api graphql` is judged by
  // the hook's ProjectV2-mutation leg, not this grep, so treat it as read here.
  if (/\bgh\s+api\b/.test(text) && !API_WRITE_METHOD.test(text)) return true
  return READ_ONLY.test(text) && !API_WRITE_METHOD.test(text)
}

// ---- the assertion ----------------------------------------------------------

describe("flagless gh writes are guarded", () => {
  const commandFiles = mdFilesRecursive(path.join(PLUGIN, "commands"))
  const skillFiles = mdFilesRecursive(path.join(PLUGIN, "skills"))
  const files = [...commandFiles, ...skillFiles]

  test("scans at least the known command + skill surface", () => {
    // Guards against a broken scanner silently finding nothing.
    expect(files.length).toBeGreaterThan(10)
  })

  test("every gh issue|project|api write carries --repo/--owner or is allowlisted", () => {
    const violations: string[] = []
    const unusedAllow = new Set(Object.keys(ALLOWLIST))

    for (const file of files) {
      for (const hit of collectGhCalls(file)) {
        const key = `${hit.rel}:${hit.line}`
        if (key in ALLOWLIST) {
          unusedAllow.delete(key)
          continue
        }
        if (isRead(hit.text)) continue
        if (HAS_TARGET_FLAG.test(hit.text)) continue
        violations.push(`${key}: ${hit.text}`)
      }
    }

    expect(
      violations,
      `Flagless gh WRITE(s) with no --repo/--owner and not allowlisted:\n` +
        violations.join("\n") +
        `\n\nAdd the explicit flag, or add the key to ALLOWLIST in ` +
        `tests/flagless-gh.test.ts with a justification.`,
    ).toEqual([])

    // Keep the allowlist honest: a stale entry means the snippet moved or was
    // fixed — remove it so a future flagless write at that key is caught.
    expect(
      [...unusedAllow],
      `Stale ALLOWLIST entries (no matching gh call) — remove them:`,
    ).toEqual([])
  })
})
