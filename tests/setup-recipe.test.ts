// The setup skill's Step 4.5 gitignore recipe is executable documentation: its
// flags are load-bearing (`check-ignore --no-index` especially — plain
// check-ignore NEVER reports a tracked path as ignored, so without the flag a
// legacy tracked agentic-engineering.local.md would re-append the entry on
// every run) and it lives only in markdown, unguarded by the count/frontmatter
// tests. Per docs/solutions/testing-patterns/recorded-fixtures-must-be-load-bearing.md,
// verification that nothing executes reads as coverage it isn't — so this test
// extracts the recipe from the SKILL.md VERBATIM (extraction-by-construction:
// if the block moves, renames, or is "simplified", the test fails or runs the
// new text) and executes it in isolated temp git repos across the six core
// scenarios from todos/004 (PR #72 review synthesis).
//
// The `root=... gitignore=... tracked=...` status line is asserted exactly:
// the SKILL declares it the recipe's only observable output — Step 4.5's
// consent gate and Step 5's summary parse those tokens, so wording drift is a
// real regression, not test brittleness.

import { describe, expect, test, afterAll } from "bun:test"
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "fs"
import { tmpdir } from "os"
import path from "path"

const ROOT = path.resolve(import.meta.dir, "..")
const SKILL = path.join(ROOT, "plugins/agentic-engineering/skills/setup/SKILL.md")
// The exact literal the recipe must append (never a glob — the committed
// agentic-engineering.md differs by one token and must never be ignored).
const ENTRY = "agentic-engineering.local.md"

// ---- verbatim extraction ----------------------------------------------------

function extractStep45Recipe(): string {
  const md = readFileSync(SKILL, "utf8")
  const heading = md.match(/^## Step 4\.5/m)
  if (!heading || heading.index === undefined) {
    throw new Error(`"## Step 4.5" heading not found in ${SKILL}`)
  }
  const afterHeading = md.slice(heading.index + heading[0].length)
  const nextHeading = afterHeading.search(/^## /m)
  const section = nextHeading === -1 ? afterHeading : afterHeading.slice(0, nextHeading)
  const block = section.match(/^```bash[ \t]*\n([\s\S]*?)^```[ \t]*$/m)
  if (!block) {
    throw new Error(`no fenced bash block found in the Step 4.5 section of ${SKILL}`)
  }
  return block[1]
}

let cachedRecipe: string | null = null
function recipe(): string {
  if (cachedRecipe === null) cachedRecipe = extractStep45Recipe()
  return cachedRecipe
}

// ---- isolated execution harness ----------------------------------------------

// realpath so every asserted path (and git's repo discovery) is symlink-free —
// on macOS tmpdir() lives under /var, a symlink to /private/var.
const SANDBOX = realpathSync(mkdtempSync(path.join(tmpdir(), "setup-recipe-")))
const RECIPE_SH = path.join(SANDBOX, "step45-recipe.sh")
const GITCONFIG = path.join(SANDBOX, "gitconfig")
// Hermetic git: the user's/system's config could set core.excludesFile or
// broader ignore rules that would make check-ignore pass for the wrong reason.
writeFileSync(
  GITCONFIG,
  "[user]\n\tname = test\n\temail = test@example.com\n[init]\n\tdefaultBranch = main\n"
)
const ENV: Record<string, string> = {
  PATH: process.env.PATH ?? "/usr/bin:/bin",
  HOME: SANDBOX,
  GIT_CONFIG_GLOBAL: GITCONFIG,
  GIT_CONFIG_NOSYSTEM: "1",
  // Repo discovery must never climb above the sandbox (the non-git scenario
  // would otherwise depend on where the OS tmpdir happens to live).
  GIT_CEILING_DIRECTORIES: SANDBOX,
  LC_ALL: "C",
}

afterAll(() => rmSync(SANDBOX, { recursive: true, force: true }))

function sh(cmd: string[], cwd: string) {
  const proc = Bun.spawnSync(cmd, { cwd, env: ENV, stdout: "pipe", stderr: "pipe" })
  return { code: proc.exitCode, out: proc.stdout.toString(), err: proc.stderr.toString() }
}

function runRecipe(cwd: string) {
  if (!existsSync(RECIPE_SH)) writeFileSync(RECIPE_SH, recipe())
  return sh(["bash", RECIPE_SH], cwd)
}

function scenarioDir(name: string): string {
  const dir = path.join(SANDBOX, name)
  mkdirSync(dir, { recursive: true })
  return dir
}

function initRepo(dir: string): void {
  const r = sh(["git", "init", "-q", dir], SANDBOX)
  if (r.code !== 0) throw new Error(`git init failed: ${r.err}`)
}

function entryLines(gitignorePath: string): number {
  return readFileSync(gitignorePath, "utf8")
    .split("\n")
    .filter((line) => line === ENTRY).length
}

// ---- the six scenarios --------------------------------------------------------

describe("setup skill Step 4.5 recipe", () => {
  test("the Step 4.5 heading and its fenced bash block exist in the SKILL.md", () => {
    // extractStep45Recipe throws (failing this test with the reason) if the
    // heading or the block is missing.
    expect(recipe().trim().length).toBeGreaterThan(0)
  })

  test("fresh repo, run from a subdirectory: entry lands in the root .gitignore, file ignored and untracked", () => {
    const repo = scenarioDir("fresh")
    initRepo(repo)
    const sub = path.join(repo, "nested", "subdir")
    mkdirSync(sub, { recursive: true })
    // The file setup would have just written.
    writeFileSync(path.join(repo, ENTRY), "---\nissue_tracker: none\n---\n")

    const run = runRecipe(sub)
    expect(run.code).toBe(0)
    expect(run.out.trim()).toBe(`root=${repo} gitignore=added tracked=0`)

    // Appended at the repo ROOT, not the subdirectory the recipe ran from.
    expect(existsSync(path.join(sub, ".gitignore"))).toBe(false)
    expect(readFileSync(path.join(repo, ".gitignore"), "utf8")).toBe(`${ENTRY}\n`)

    // The acceptance command, verbatim, from the repo root:
    expect(sh(["git", "check-ignore", "-q", "--no-index", ENTRY], repo).code).toBe(0)
    // Untracked, and git no longer offers the file for staging:
    expect(sh(["git", "ls-files", "--error-unmatch", ENTRY], repo).code).not.toBe(0)
    expect(sh(["git", "status", "--porcelain"], repo).out).not.toContain(ENTRY)
  })

  test("legacy tracked copy: TRACKED detected, entry appended exactly once across a re-run", () => {
    const repo = scenarioDir("legacy-tracked")
    initRepo(repo)
    writeFileSync(path.join(repo, ENTRY), "legacy committed local config\n")
    expect(sh(["git", "add", ENTRY], repo).code).toBe(0)
    expect(sh(["git", "commit", "-q", "-m", "legacy: local config committed"], repo).code).toBe(0)

    const gitignore = path.join(repo, ".gitignore")
    const first = runRecipe(repo)
    expect(first.code).toBe(0)
    expect(first.out.trim()).toBe(`root=${repo} gitignore=added tracked=1`)
    expect(entryLines(gitignore)).toBe(1)

    // Why --no-index is load-bearing: while the file is still tracked, plain
    // check-ignore refuses to report it ignored — only --no-index sees the
    // entry that was just appended.
    expect(sh(["git", "check-ignore", "-q", ENTRY], repo).code).not.toBe(0)
    expect(sh(["git", "check-ignore", "-q", "--no-index", ENTRY], repo).code).toBe(0)

    // Re-run while STILL tracked: appends nothing.
    const second = runRecipe(repo)
    expect(second.code).toBe(0)
    expect(second.out.trim()).toBe(`root=${repo} gitignore=entry present tracked=1`)
    expect(entryLines(gitignore)).toBe(1)
  })

  test("broader *.local.md pattern pre-exists: nothing appended, .gitignore byte-identical", () => {
    const repo = scenarioDir("broader-pattern")
    initRepo(repo)
    const gitignore = path.join(repo, ".gitignore")
    const before = "*.local.md\n"
    writeFileSync(gitignore, before)

    const run = runRecipe(repo)
    expect(run.code).toBe(0)
    expect(run.out.trim()).toBe(`root=${repo} gitignore=entry present tracked=0`)
    expect(readFileSync(gitignore, "utf8")).toBe(before)
  })

  test(".gitignore without trailing newline: the last existing pattern survives the append intact", () => {
    const repo = scenarioDir("no-trailing-newline")
    initRepo(repo)
    const gitignore = path.join(repo, ".gitignore")
    writeFileSync(gitignore, "node_modules") // no trailing \n

    const run = runRecipe(repo)
    expect(run.code).toBe(0)
    expect(run.out.trim()).toBe(`root=${repo} gitignore=added tracked=0`)
    // Without the tail -c1 newline repair this would read
    // "node_modulesagentic-engineering.local.md", corrupting both patterns.
    expect(readFileSync(gitignore, "utf8")).toBe(`node_modules\n${ENTRY}\n`)
    expect(sh(["git", "check-ignore", "-q", "--no-index", "node_modules"], repo).code).toBe(0)
    expect(sh(["git", "check-ignore", "-q", "--no-index", ENTRY], repo).code).toBe(0)
  })

  test("non-git directory: silent skip — no .gitignore created, root=none", () => {
    const dir = scenarioDir("not-a-repo")

    const run = runRecipe(dir)
    expect(run.code).toBe(0)
    expect(run.out.trim()).toBe("root=none gitignore=n/a tracked=n/a")
    expect(run.err).toBe("")
    expect(existsSync(path.join(dir, ".gitignore"))).toBe(false)
  })

  test("symlinked .gitignore: append refused, never writes through the link, no duplicates on re-run", () => {
    const dir = scenarioDir("symlinked")
    const repo = path.join(dir, "repo")
    mkdirSync(repo)
    initRepo(repo)
    // Link target deliberately OUTSIDE the repo — the guard exists so an
    // autonomous append can never write through a link to a foreign file.
    const target = path.join(dir, "shared-gitignore")
    const before = "node_modules\n"
    writeFileSync(target, before)
    symlinkSync(target, path.join(repo, ".gitignore"))

    for (const attempt of [1, 2]) {
      const run = runRecipe(repo)
      expect(run.code).toBe(0)
      expect(run.out.trim()).toBe(`root=${repo} gitignore=failed tracked=0`)
      expect(readFileSync(target, "utf8")).toBe(before) // byte-identical after attempt ${attempt}
    }
    expect(lstatSync(path.join(repo, ".gitignore")).isSymbolicLink()).toBe(true)
  })
})
