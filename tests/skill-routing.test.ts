// Tier-2 skill-routing evals: a deterministic, zero-dependency, CI-safe check
// that the skill *catalog* routes well — that each skill's description carries
// the vocabulary users actually say, and that no two descriptions collide.
//
// Ported (algorithm adapted, code rewritten in TypeScript) from
// addyosmani/agent-skills scripts/run-evals.js — the Tier-2 half only. The
// Tier-3 behavioral runner (which shells out to `claude -p` and spends tokens)
// is intentionally NOT ported: this suite stays free and hermetic.
// Upstream-Ref: addyosmani/agent-skills@4e8bd9fde4a38cd009053e649f4cdc7cd36b568b:scripts/run-evals.js
//
// Two things are checked, both against a stemmed TF-IDF model built over every
// skill's `name` (weighted 2x) + `description`:
//   1. Collision — all-pairs cosine similarity between descriptions. A pair at
//      or above ERROR (0.75) fails the suite (two skills that overlap this much
//      are a routing hazard); a pair at or above WARN (0.50) logs a warning.
//   2. Trigger routing — seed case files under tests/skill-routing-cases/ list
//      positive prompts (must rank their skill within top-k) and negative
//      prompts (must NOT rank their skill #1; an `owner` skill must outrank it).
//
// If a collision fails: the right fix is almost always to sharpen one of the two
// descriptions, not to relax the threshold. A genuinely intentional overlap goes
// in COLLISION_ALLOWLIST below (validator-owned, with a reason) — never by
// watering down a skill's frontmatter. If a routing case fails: tune the *prompt*
// to how users actually talk, or fix the description if it truly lacks the
// vocabulary — never edit the description just to pass a contrived prompt.

import { describe, expect, test } from "bun:test"
import { existsSync, readdirSync, readFileSync } from "fs"
import path from "path"
import { parseFrontmatter } from "../src/utils/frontmatter"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGINS_DIR = path.join(ROOT, "plugins")
const CASES_DIR = path.join(ROOT, "tests/skill-routing-cases")

const COLLISION_WARN = 0.5
const COLLISION_ERROR = 0.75
const DEFAULT_TOP_K = 3

// Flagship skills that must always carry a seed routing case, so the seed set
// can't silently shrink below the five it shipped with.
const REQUIRED_CASE_SKILLS = [
  "brainstorming",
  "verification-loop",
  "land-pr",
  "compound-docs",
  "operating-principles",
] as const

// Intentionally-overlapping description pairs, exempted from the collision
// error. Anti-bypass by design: an exemption lives HERE, in the validator, with
// a reason — never as watered-down frontmatter in the skills themselves, which
// would degrade real routing to silence a test. Each entry must reference two
// real skills that genuinely still collide (>= ERROR); the self-check below
// fails on any stale entry. Empty today: no pair on the current catalog reaches
// even the 0.50 warn threshold.
const COLLISION_ALLOWLIST: { a: string; b: string; reason: string }[] = []

// ---- text pipeline (stemmed TF-IDF) ----------------------------------------
// A deliberately light lexical model: enough to cluster morphological variants
// ("branch"/"branching", "simplify"/"simplified") without a real stemmer. It
// approximates routing lexically; it cannot judge semantics (that is Tier 3).

const STOP = new Set([
  "a", "an", "and", "any", "are", "as", "at", "be", "before", "by", "for",
  "from", "in", "into", "is", "it", "its", "my", "need", "needs", "of", "on",
  "or", "our", "so", "that", "the", "them", "this", "to", "use", "want", "we",
  "when", "with", "you", "your", "help", "me", "i",
])

const SUFFIXES = ["ally", "ing", "ed", "es", "al"]
const VOWELS = "aeiou"

function stem(token: string): string {
  let t = token
  for (const suffix of SUFFIXES) {
    if (t.length > suffix.length + 3 && t.endsWith(suffix)) {
      t = t.slice(0, -suffix.length)
      break
    }
  }
  if (t.length > 3 && t.endsWith("s") && !t.endsWith("ss")) t = t.slice(0, -1)
  if (t.length > 4 && t.endsWith("e")) t = t.slice(0, -1)
  // Collapse a doubled trailing consonant left by -ing/-ed ("committ" -> "commit").
  const last = t[t.length - 1]
  if (t.length > 4 && last === t[t.length - 2] && !VOWELS.includes(last)) {
    t = t.slice(0, -1)
  }
  // Normalize trailing y so "simplify" clusters with "simplifies"/"simplified".
  if (t.length > 3 && t.endsWith("y")) t = `${t.slice(0, -1)}i`
  return t
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/[\s-]+/)
    .filter((t) => t.length > 2 && !STOP.has(t))
    .map(stem)
}

function termFreq(tokens: string[]): Map<string, number> {
  const tf = new Map<string, number>()
  for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1)
  return tf
}

type Corpus = {
  docs: Map<string, Map<string, number>>
  idf: (term: string) => number
}

function buildCorpus(skills: Skill[]): Corpus {
  // One document per skill: name tokens counted twice (a skill's own name is a
  // strong routing signal) plus its description tokens.
  const docs = new Map<string, Map<string, number>>()
  for (const s of skills) {
    const nameTokens = tokenize(s.name.replace(/-/g, " "))
    docs.set(s.name, termFreq([...nameTokens, ...nameTokens, ...tokenize(s.description)]))
  }
  const df = new Map<string, number>()
  for (const tf of docs.values()) {
    for (const term of tf.keys()) df.set(term, (df.get(term) ?? 0) + 1)
  }
  const n = docs.size
  const idf = (term: string) => Math.log(1 + n / (1 + (df.get(term) ?? 0)))
  return { docs, idf }
}

function toVector(tf: Map<string, number>, idf: (t: string) => number): Map<string, number> {
  const v = new Map<string, number>()
  for (const [term, freq] of tf) v.set(term, freq * idf(term))
  return v
}

function cosine(a: Map<string, number>, b: Map<string, number>): number {
  let dot = 0
  let normA = 0
  let normB = 0
  for (const [term, weight] of a) {
    normA += weight * weight
    const other = b.get(term)
    if (other) dot += weight * other
  }
  for (const weight of b.values()) normB += weight * weight
  if (!normA || !normB) return 0
  return dot / (Math.sqrt(normA) * Math.sqrt(normB))
}

function rankSkills(prompt: string, corpus: Corpus): { name: string; score: number }[] {
  const promptVec = toVector(termFreq(tokenize(prompt)), corpus.idf)
  const scores = [...corpus.docs].map(([name, tf]) => ({
    name,
    score: cosine(promptVec, toVector(tf, corpus.idf)),
  }))
  scores.sort((x, y) => y.score - x.score)
  return scores
}

// ---- catalog + case loading -------------------------------------------------

type Skill = { name: string; description: string; plugin: string }

function loadSkills(): Skill[] {
  const skills: Skill[] = []
  for (const plugin of readdirSync(PLUGINS_DIR, { withFileTypes: true })) {
    if (!plugin.isDirectory()) continue
    const skillsDir = path.join(PLUGINS_DIR, plugin.name, "skills")
    if (!existsSync(skillsDir)) continue
    for (const entry of readdirSync(skillsDir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue
      const file = path.join(skillsDir, entry.name, "SKILL.md")
      if (!existsSync(file)) continue
      const { data } = parseFrontmatter(readFileSync(file, "utf8"))
      skills.push({
        name: String(data.name ?? entry.name),
        description: String(data.description ?? ""),
        plugin: plugin.name,
      })
    }
  }
  return skills
}

type TriggerPrompt = { prompt: string; top_k?: number; owner?: string }
type RoutingCase = {
  skill_name: string
  trigger?: { positive?: TriggerPrompt[]; negative?: TriggerPrompt[] }
}

function loadCases(): { file: string; data: RoutingCase }[] {
  if (!existsSync(CASES_DIR)) return []
  return readdirSync(CASES_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => ({ file: f, data: JSON.parse(readFileSync(path.join(CASES_DIR, f), "utf8")) as RoutingCase }))
}

// ---- filesystem truth (loaded once) -----------------------------------------

const skills = loadSkills()
const skillNames = new Set(skills.map((s) => s.name))
const corpus = buildCorpus(skills)
const cases = loadCases()

function pct(sim: number): string {
  return `${(sim * 100).toFixed(0)}%`
}

function isAllowlisted(a: string, b: string): boolean {
  return COLLISION_ALLOWLIST.some(
    (e) => (e.a === a && e.b === b) || (e.a === b && e.b === a),
  )
}

function similarity(a: string, b: string): number {
  return cosine(toVector(corpus.docs.get(a)!, corpus.idf), toVector(corpus.docs.get(b)!, corpus.idf))
}

// All description pairs at or above the warn threshold, computed once.
const flaggedPairs: { a: string; b: string; sim: number }[] = []
{
  const names = [...corpus.docs.keys()]
  for (let i = 0; i < names.length; i += 1) {
    for (let j = i + 1; j < names.length; j += 1) {
      const sim = similarity(names[i], names[j])
      if (sim >= COLLISION_WARN) flaggedPairs.push({ a: names[i], b: names[j], sim })
    }
  }
  flaggedPairs.sort((x, y) => y.sim - x.sim)
}

// ---- catalog sanity ---------------------------------------------------------

describe("skill catalog", () => {
  test("catalog is non-empty and every skill declares a description", () => {
    expect(skills.length).toBeGreaterThan(0)
    for (const s of skills) {
      expect(s.description.length).toBeGreaterThan(0)
    }
  })

  test("skill names are unique across plugins (the TF-IDF corpus keys by name)", () => {
    const seen = new Map<string, string>()
    const dupes: string[] = []
    for (const s of skills) {
      const prior = seen.get(s.name)
      if (prior) dupes.push(`${s.name}: ${prior} and ${s.plugin}`)
      else seen.set(s.name, s.plugin)
    }
    expect(dupes).toEqual([])
  })
})

// ---- collision check --------------------------------------------------------

describe("skill-description routing collisions (all-pairs cosine over TF-IDF)", () => {
  test("no two skill descriptions collide at or above the error threshold", () => {
    for (const p of flaggedPairs) {
      if (p.sim < COLLISION_ERROR) {
        console.warn(`  ⚠  overlap ${pct(p.sim)} (>= ${pct(COLLISION_WARN)}): ${p.a} <-> ${p.b}`)
      }
    }
    const unexpected = flaggedPairs
      .filter((p) => p.sim >= COLLISION_ERROR && !isAllowlisted(p.a, p.b))
      .map((p) => `${p.a} <-> ${p.b} @ ${pct(p.sim)}`)
    expect(unexpected).toEqual([])
  })

  test("every COLLISION_ALLOWLIST entry references real skills and still collides", () => {
    for (const e of COLLISION_ALLOWLIST) {
      expect(skillNames.has(e.a)).toBe(true)
      expect(skillNames.has(e.b)).toBe(true)
      expect(similarity(e.a, e.b)).toBeGreaterThanOrEqual(COLLISION_ERROR)
    }
  })
})

// ---- routing case schema ----------------------------------------------------

describe("routing case files are well-formed", () => {
  test.each(cases.map((c) => [c.file, c] as const))("%s", (file, c) => {
    const expected = file.replace(/\.json$/, "")
    expect(c.data.skill_name).toBe(expected)
    expect(skillNames.has(expected)).toBe(true)
    expect((c.data.trigger?.positive ?? []).length).toBeGreaterThan(0)
    expect((c.data.trigger?.negative ?? []).length).toBeGreaterThan(0)
  })

  test.each(REQUIRED_CASE_SKILLS.map((s) => [s] as const))(
    "required flagship skill %s has a routing case",
    (name) => {
      expect(skillNames.has(name)).toBe(true)
      expect(cases.some((c) => c.data.skill_name === name)).toBe(true)
    },
  )
})

// ---- trigger routing --------------------------------------------------------

type PositiveRow = readonly [label: string, skill: string, prompt: string, topK: number]
type NegativeRow = readonly [label: string, skill: string, prompt: string, owner: string | undefined]

const positiveRows: PositiveRow[] = cases.flatMap((c) =>
  (c.data.trigger?.positive ?? []).map(
    (t) => [`${c.data.skill_name} <= "${t.prompt}"`, c.data.skill_name, t.prompt, t.top_k ?? DEFAULT_TOP_K] as const,
  ),
)

const negativeRows: NegativeRow[] = cases.flatMap((c) =>
  (c.data.trigger?.negative ?? []).map(
    (t) => [`${c.data.skill_name} =/= "${t.prompt}"`, c.data.skill_name, t.prompt, t.owner] as const,
  ),
)

describe("positive trigger prompts route to their skill within top-k", () => {
  test.each(positiveRows)("%s", (_label, skill, prompt, topK) => {
    const ranking = rankSkills(prompt, corpus)
    const idx = ranking.findIndex((r) => r.name === skill)
    expect(idx).toBeGreaterThanOrEqual(0)
    expect(ranking[idx].score).toBeGreaterThan(0)
    // Ranked strictly within the top-k window (idx 0..topK-1).
    expect(idx).toBeLessThan(topK)
  })
})

describe("negative trigger prompts do not hijack another skill's route", () => {
  test.each(negativeRows)("%s", (_label, skill, prompt, owner) => {
    const ranking = rankSkills(prompt, corpus)
    // Fail only on a real (nonzero) #1 match — a zero-score #1 means the prompt
    // simply shares no vocabulary, which is not an over-broad description.
    const top = ranking[0]
    expect(top.name === skill && top.score > 0).toBe(false)

    // With an owner, the negative becomes a pairwise routing test: the declared
    // owner must outrank this skill (with a real score), which prevents vacuous
    // passes where the prompt matches nothing at all.
    if (owner !== undefined) {
      expect(skillNames.has(owner)).toBe(true)
      const ownerIdx = ranking.findIndex((r) => r.name === owner)
      const selfIdx = ranking.findIndex((r) => r.name === skill)
      expect(ranking[ownerIdx].score).toBeGreaterThan(0)
      expect(ownerIdx).toBeLessThan(selfIdx)
    }
  })
})
