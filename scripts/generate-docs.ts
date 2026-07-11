#!/usr/bin/env bun
/**
 * Deterministic documentation generator.
 *
 * Regenerates the auto-managed regions of the docs site from the plugin's
 * actual components, so the reference pages can never silently drift. Replaces
 * the old manual `/release-docs` skill.
 *
 *   bun run docs:build   # rewrite the generated regions in place
 *   bun run docs:check   # exit non-zero if any committed file is out of date (CI)
 *
 * Per reference page it owns two things:
 *   1. the component card sections (between `<!-- GENERATED:<id> START/END -->`)
 *   2. the sidebar "On This Page" list (the <ul> after that heading)
 * Plus every landing-page stat marked with data-stat="<key>" (agent/command/
 * skill/mcp counts + plugin version), and the changelog page (rendered from
 * plugins/agentic-engineering/CHANGELOG.md). All other page chrome (nav,
 * header, intros, footer) is preserved verbatim.
 *
 * Components are collected from EVERY plugin directory under plugins/ (any dir
 * with a .claude-plugin/plugin.json), core plugin first. Skills render one
 * section per plugin; non-core skills are invoked as `<plugin>:<skill>`. The
 * changelog page stays core-plugin only.
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from "fs"
import path from "path"
import { parseFrontmatter } from "../src/utils/frontmatter"

const ROOT = path.resolve(import.meta.dir, "..")
const PLUGINS_DIR = path.join(ROOT, "plugins")
const CORE_PLUGIN_NAME = "agentic-engineering"
const PLUGIN = path.join(PLUGINS_DIR, CORE_PLUGIN_NAME)
const DOCS = path.join(ROOT, "docs")

export type Component = { name: string; description: string; category: string }
export type PluginSkills = { plugin: string; skills: Component[] }
type NavItem = { href: string; label: string }

/** Every plugin directory under plugins/ — core plugin first, rest alphabetical. */
export function pluginDirs(): { name: string; dir: string }[] {
  return readdirSync(PLUGINS_DIR, { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(path.join(PLUGINS_DIR, e.name, ".claude-plugin/plugin.json")))
    .map((e) => e.name)
    .sort((a, b) => (a === CORE_PLUGIN_NAME ? -1 : b === CORE_PLUGIN_NAME ? 1 : a.localeCompare(b)))
    .map((name) => ({ name, dir: path.join(PLUGINS_DIR, name) }))
}

// ---- collection ------------------------------------------------------------

function fm(file: string): { name: string; description: string } {
  const { data } = parseFrontmatter(readFileSync(file, "utf8"))
  return { name: String(data.name ?? ""), description: String(data.description ?? "").trim() }
}

function mdIn(dir: string): string[] {
  if (!existsSync(dir)) return []
  return readdirSync(dir).filter((n) => n.endsWith(".md")).map((n) => path.join(dir, n)).sort()
}

export function collectAgents(): Component[] {
  const out: Component[] = []
  for (const { dir } of pluginDirs()) {
    const agentsDir = path.join(dir, "agents")
    if (!existsSync(agentsDir)) continue
    const cats = readdirSync(agentsDir, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name)
    for (const cat of cats) for (const f of mdIn(path.join(agentsDir, cat))) out.push({ ...fm(f), category: cat })
  }
  return out
}

export function collectCommands(): Component[] {
  const out: Component[] = []
  for (const { dir } of pluginDirs()) {
    for (const f of mdIn(path.join(dir, "commands", "workflows"))) out.push({ ...fm(f), category: "workflow" })
    for (const f of mdIn(path.join(dir, "commands"))) out.push({ ...fm(f), category: "utility" })
  }
  return out
}

export function collectSkills(): PluginSkills[] {
  const out: PluginSkills[] = []
  for (const { name, dir } of pluginDirs()) {
    const skillsDir = path.join(dir, "skills")
    if (!existsSync(skillsDir)) continue
    const skills = readdirSync(skillsDir, { withFileTypes: true })
      .filter((e) => e.isDirectory() && existsSync(path.join(skillsDir, e.name, "SKILL.md")))
      .map((e) => ({ name: e.name, description: fm(path.join(skillsDir, e.name, "SKILL.md")).description, category: "skill" }))
      .sort((a, b) => a.name.localeCompare(b.name))
    if (skills.length) out.push({ plugin: name, skills })
  }
  return out
}

export function collectMcp(): Component[] {
  const out: Component[] = []
  for (const { dir } of pluginDirs()) {
    const pj = JSON.parse(readFileSync(path.join(dir, ".claude-plugin/plugin.json"), "utf8"))
    for (const [name, cfg] of Object.entries(pj.mcpServers ?? {}) as [string, any][]) {
      out.push({ name, description: String(cfg.url ?? cfg.type ?? ""), category: String(cfg.type ?? "http") })
    }
  }
  return out
}

// ---- changelog ---------------------------------------------------------
// Parses plugins/agentic-engineering/CHANGELOG.md (Keep a Changelog format)
// and renders it into docs/pages/changelog.html. Hand-rolled rather than a
// markdown-library dependency: the shape is narrow (## version headers, ###
// category headers, single/nested bullet lists, occasional prose paragraph
// or table, three inline spans) and the output needs bespoke per-category
// HTML/CSS wrapping a generic renderer wouldn't produce anyway.

export type ChangelogEntry = { version: string; date: string; lines: string[] }

export function parseChangelog(md: string): ChangelogEntry[] {
  const entries: ChangelogEntry[] = []
  let current: ChangelogEntry | null = null
  const headerRe = /^## \[([^\]]+)\] - (\d{4}-\d{2}-\d{2})/
  for (const line of md.split("\n")) {
    const m = headerRe.exec(line)
    if (m) {
      current = { version: m[1], date: m[2], lines: [] }
      entries.push(current)
      continue
    }
    if (current) current.lines.push(line)
  }
  return entries
}

function inlineMd(s: string): string {
  let out = esc(s)
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>")
  return out
}

type ListItem = { text: string; children: ListItem[] }

function parseList(lines: string[], start: number): { items: ListItem[]; next: number } {
  const items: ListItem[] = []
  let i = start
  let baseIndent: number | null = null
  while (i < lines.length) {
    const m = /^(\s*)-\s+(.*)$/.exec(lines[i])
    if (!m) break
    const indent = m[1].length
    if (baseIndent === null) baseIndent = indent
    if (indent < baseIndent) break
    if (indent > baseIndent) {
      if (items.length === 0) break
      const nested = parseList(lines, i)
      items[items.length - 1].children.push(...nested.items)
      i = nested.next
      continue
    }
    items.push({ text: m[2], children: [] })
    i++
  }
  return { items, next: i }
}

function itemsToHtml(items: ListItem[]): string {
  return `<ul>\n${items.map((it) => `<li>${inlineMd(it.text)}${it.children.length ? "\n" + itemsToHtml(it.children) : ""}</li>`).join("\n")}\n</ul>`
}

function isTableRow(line: string): boolean {
  return line.trim().startsWith("|")
}

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim())
}

function renderTable(lines: string[], start: number): { html: string; next: number } {
  const head = tableCells(lines[start])
  let i = start + 1
  if (i < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i])) i++
  const rows: string[][] = []
  while (i < lines.length && isTableRow(lines[i])) {
    rows.push(tableCells(lines[i]))
    i++
  }
  const thead = `<thead><tr>${head.map((c) => `<th>${inlineMd(c)}</th>`).join("")}</tr></thead>`
  const tbody = `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inlineMd(c)}</td>`).join("")}</tr>`).join("")}</tbody>`
  return { html: `<table>${thead}${tbody}</table>`, next: i }
}

/** Render a block of markdown (paragraphs, bullet lists, one table form) into HTML. */
function renderMarkdown(lines: string[]): string {
  const blocks: string[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === "" || line.trim() === "---") {
      i++
      continue
    }
    if (/^\s*-\s+/.test(line)) {
      const { items, next } = parseList(lines, i)
      blocks.push(itemsToHtml(items))
      i = next
      continue
    }
    if (isTableRow(line)) {
      const { html, next } = renderTable(lines, i)
      blocks.push(html)
      i = next
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() !== "" && !/^\s*-\s+/.test(lines[i]) && !isTableRow(lines[i])) {
      para.push(lines[i].trim())
      i++
    }
    blocks.push(`<p>${inlineMd(para.join(" "))}</p>`)
  }
  return blocks.join("\n")
}

const CHANGELOG_CATEGORY_META: Record<string, { icon: string; cssClass: string }> = {
  Added: { icon: "fa-plus", cssClass: "added" },
  Changed: { icon: "fa-arrows-rotate", cssClass: "changed" },
  Fixed: { icon: "fa-bug", cssClass: "fixed" },
  Removed: { icon: "fa-minus", cssClass: "removed" },
  Enhanced: { icon: "fa-arrow-up", cssClass: "improved" },
  Improved: { icon: "fa-arrow-up", cssClass: "improved" },
  Summary: { icon: "fa-list", cssClass: "summary" },
  Philosophy: { icon: "fa-lightbulb", cssClass: "philosophy" },
  Contributors: { icon: "fa-users", cssClass: "contributors" },
  Credits: { icon: "fa-award", cssClass: "credits" },
  "Merged PRs": { icon: "fa-code-merge", cssClass: "merged-prs" },
  "Preserved (no behavior change)": { icon: "fa-shield-halved", cssClass: "preserved" },
}

/** Split an entry's raw lines into a leading prose preamble plus `### Category` groups. */
function splitByCategory(lines: string[]): { preamble: string[]; categories: { name: string; lines: string[] }[] } {
  const categoryRe = /^### (.+)$/
  const firstHeader = lines.findIndex((l) => categoryRe.test(l))
  const preamble = firstHeader === -1 ? lines : lines.slice(0, firstHeader)
  const categories: { name: string; lines: string[] }[] = []
  if (firstHeader !== -1) {
    let name = categoryRe.exec(lines[firstHeader])![1]
    let body: string[] = []
    for (let i = firstHeader + 1; i <= lines.length; i++) {
      const line = lines[i]
      const m = line !== undefined ? categoryRe.exec(line) : null
      if (m || i === lines.length) {
        categories.push({ name, lines: body })
        if (m) {
          name = m[1]
          body = []
        }
        continue
      }
      body.push(line)
    }
  }
  return { preamble, categories }
}

function renderChangelogEntry(entry: ChangelogEntry, isOldest: boolean): string {
  const { preamble, categories } = splitByCategory(entry.lines)
  const blocks: string[] = []
  const preambleHtml = renderMarkdown(preamble)
  if (preambleHtml) blocks.push(`<p class="version-description">${preambleHtml.replace(/^<p>|<\/p>$/g, "")}</p>`)
  for (const g of categories) {
    const meta = CHANGELOG_CATEGORY_META[g.name] ?? { icon: "fa-circle-dot", cssClass: slug(g.name) }
    blocks.push(
      `<div class="changelog-category ${meta.cssClass}">\n` +
        `<h3><i class="fa-solid ${meta.icon}"></i> ${esc(g.name)}</h3>\n` +
        `${renderMarkdown(g.lines)}\n` +
        `</div>`,
    )
  }
  const badge = isOldest
    ? `<span class="version-badge">Initial Release</span>`
    : /^\d+\.0\.0$/.test(entry.version)
      ? `<span class="version-badge major">Major Release</span>`
      : ""
  return (
    `<section id="v${entry.version}" class="version-section">\n` +
    `  <div class="version-header">\n` +
    `    <h2>v${esc(entry.version)}</h2>\n` +
    `    <span class="version-date">${esc(entry.date)}</span>\n` +
    (badge ? `    ${badge}\n` : "") +
    `  </div>\n` +
    `${blocks.join("\n")}\n` +
    `</section>`
  )
}

export function buildChangelog(entries: ChangelogEntry[]): { inner: string; nav: NavItem[] } {
  const inner = entries.map((e, i) => renderChangelogEntry(e, i === entries.length - 1)).join("\n\n")
  const nav = entries.map((e) => ({ href: `#v${e.version}`, label: `v${e.version}` }))
  return { inner, nav }
}

// ---- html helpers ----------------------------------------------------------

export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
}

/** Replace the inner content of a marker pair, or splice in on first run. */
function spliceContent(html: string, id: string, beginAnchor: string, endAnchor: string, inner: string): string {
  const startMark = `<!-- GENERATED:${id} START`
  const endMark = `<!-- GENERATED:${id} END -->`
  if (html.includes(startMark)) {
    const s = html.indexOf(startMark)
    const ls = html.lastIndexOf("\n", s) + 1
    const indent = html.slice(ls, s)
    const e = html.indexOf(endMark)
    const eolEnd = html.indexOf("\n", e)
    return html.slice(0, ls) + wrap(indent, id, inner) + html.slice(eolEnd === -1 ? html.length : eolEnd)
  }
  const b = html.indexOf(beginAnchor)
  if (b === -1) throw new Error(`generate-docs: begin anchor not found for "${id}": ${beginAnchor}`)
  const ls = html.lastIndexOf("\n", b) + 1
  const indent = html.slice(ls, b)
  const eAnchor = html.indexOf(endAnchor, b)
  if (eAnchor === -1) throw new Error(`generate-docs: end anchor not found for "${id}": ${endAnchor}`)
  const eLine = html.lastIndexOf("\n", eAnchor) + 1
  return html.slice(0, ls) + wrap(indent, id, inner) + "\n" + html.slice(eLine)
}

function wrap(indent: string, id: string, inner: string): string {
  return (
    `${indent}<!-- GENERATED:${id} START — auto-generated by scripts/generate-docs.ts (run: bun run docs:build); do not edit by hand -->\n` +
    `${inner}\n` +
    `${indent}<!-- GENERATED:${id} END -->`
  )
}

/** Rewrite the <ul> that follows the "On This Page" sidebar heading. Idempotent. */
function replaceOnThisPage(html: string, items: NavItem[]): string {
  const h = html.indexOf("On This Page")
  if (h === -1) return html
  const ulStart = html.indexOf("<ul>", h)
  const ulEnd = html.indexOf("</ul>", ulStart)
  if (ulStart === -1 || ulEnd === -1) return html
  const lineStart = html.lastIndexOf("\n", ulStart) + 1
  const indent = html.slice(lineStart, ulStart)
  const liIndent = indent + "  "
  const lis = items.map((it) => `${liIndent}<li><a href="${it.href}">${esc(it.label)}</a></li>`).join("\n")
  return html.slice(0, ulStart) + `<ul>\n${lis}\n${indent}</ul>` + html.slice(ulEnd + "</ul>".length)
}

// ---- card / section renderers ----------------------------------------------

function section(id: string, icon: string, heading: string, count: number, cards: string[]): string {
  return (
    `        <section id="${id}">\n` +
    `          <h2><i class="fa-solid ${icon}"></i> ${heading} (${count})</h2>\n` +
    `${cards.join("\n")}\n` +
    `        </section>`
  )
}

function card(kind: string, id: string, header: string, description: string, invocation: string): string {
  return (
    `          <div class="${kind}-detail" id="${id}">\n` +
    `            <div class="${kind}-detail-header">\n` +
    `${header}\n` +
    `            </div>\n` +
    `            <p class="${kind}-detail-description">${esc(description)}</p>\n` +
    `            <div class="card-code-block">\n` +
    `              <pre><code>${esc(invocation)}</code></pre>\n` +
    `            </div>\n` +
    `          </div>`
  )
}

const AGENT_CATS = [
  { key: "review", nav: "Review", heading: "Review Agents", icon: "fa-code-pull-request" },
  { key: "research", nav: "Research", heading: "Research Agents", icon: "fa-magnifying-glass" },
  { key: "workflow", nav: "Workflow", heading: "Workflow Agents", icon: "fa-arrows-spin" },
  { key: "design", nav: "Design", heading: "Design Agents", icon: "fa-palette" },
  { key: "docs", nav: "Docs", heading: "Docs Agents", icon: "fa-book" },
]

function buildAgents(agents: Component[]): { inner: string; nav: NavItem[] } {
  const sections: string[] = []
  const nav: NavItem[] = []
  const cats = [...AGENT_CATS.map((c) => c.key), ...new Set(agents.map((a) => a.category))].filter((c, i, arr) => arr.indexOf(c) === i)
  for (const key of cats) {
    const items = agents.filter((a) => a.category === key)
    if (!items.length) continue
    const meta = AGENT_CATS.find((c) => c.key === key) ?? { key, nav: key, heading: `${key} Agents`, icon: "fa-cube" }
    const id = `${key}-agents`
    const cards = items.map((a) =>
      card(
        "agent",
        a.name,
        `              <h3>${esc(a.name)}</h3>\n              <span class="agent-badge">${esc(meta.nav)}</span>`,
        a.description,
        `claude agent ${a.name} "..."`,
      ),
    )
    sections.push(section(id, meta.icon, meta.heading, items.length, cards))
    nav.push({ href: `#${id}`, label: `${meta.nav} (${items.length})` })
  }
  return { inner: sections.join("\n\n"), nav }
}

const COMMAND_GROUPS = [
  { key: "workflow", id: "workflow-commands", nav: "Workflow", heading: "Workflow Commands", icon: "fa-arrows-spin" },
  { key: "utility", id: "utility-commands", nav: "Utility", heading: "Utility Commands", icon: "fa-screwdriver-wrench" },
]

function buildCommands(commands: Component[]): { inner: string; nav: NavItem[] } {
  const sections: string[] = []
  const nav: NavItem[] = []
  for (const g of COMMAND_GROUPS) {
    const items = commands.filter((c) => c.category === g.key)
    if (!items.length) continue
    const cards = items.map((c) =>
      card(
        "command",
        slug(c.name),
        `              <code class="command-detail-name">/${esc(c.name)}</code>`,
        c.description,
        `/${c.name}`,
      ),
    )
    sections.push(section(g.id, g.icon, g.heading, items.length, cards))
    nav.push({ href: `#${g.id}`, label: `${g.nav} (${items.length})` })
  }
  return { inner: sections.join("\n\n"), nav }
}

function buildSkills(groups: PluginSkills[]): { inner: string; nav: NavItem[] } {
  const sections: string[] = []
  const nav: NavItem[] = []
  for (const g of groups) {
    const core = g.plugin === CORE_PLUGIN_NAME
    const id = core ? "all-skills" : `${slug(g.plugin)}-skills`
    const heading = core ? "Skills" : `${g.plugin} Plugin Skills`
    const cards = g.skills.map((s) =>
      card("skill", s.name, `              <h3>${esc(s.name)}</h3>`, s.description, `skill: ${core ? s.name : `${g.plugin}:${s.name}`}`),
    )
    sections.push(section(id, "fa-wand-magic-sparkles", heading, g.skills.length, cards))
    nav.push({ href: `#${id}`, label: `${heading} (${g.skills.length})` })
  }
  return { inner: sections.join("\n\n"), nav }
}

function buildMcp(mcp: Component[]): { inner: string; nav: NavItem[] } {
  const sections: string[] = []
  const nav: NavItem[] = []
  for (const s of mcp) {
    const id = slug(s.name)
    sections.push(
      `        <section id="${id}">\n` +
        `          <h2><i class="fa-solid fa-server"></i> ${esc(s.name)}</h2>\n` +
        `          <p class="mcp-detail-description">Type: <code>${esc(s.category)}</code>${s.description ? ` · <code>${esc(s.description)}</code>` : ""}</p>\n` +
        `        </section>`,
    )
    nav.push({ href: `#${id}`, label: esc(s.name) })
  }
  return { inner: sections.join("\n\n"), nav }
}

// ---- site stats (counts + version) -----------------------------------------
// Every stat the site displays is owned here so it can never drift. Mark a spot
// with data-stat="<key>" on any element (e.g. <span data-stat="agents">30</span>
// or <div class="stat-number" data-stat="skills">35</div>): the generator
// overwrites that element's text from the live component counts / plugin version
// on every `docs:build`, and `docs:check` fails CI if a committed file is stale.
// Counts are marketplace-wide (all plugins), matching the landing-page cards.

export type SiteStats = Record<string, string | number>

export function applyStats(html: string, stats: SiteStats): string {
  return html.replace(
    /(<(\w+)\b[^>]*\bdata-stat="([a-z]+)"[^>]*>)[\s\S]*?(<\/\2>)/g,
    (m, open, _tag, key, close) => (key in stats ? `${open}${stats[key]}${close}` : m),
  )
}

// ---- driver ----------------------------------------------------------------

type FileUpdate = { file: string; next: string }

export function buildUpdates(): FileUpdate[] {
  const agents = collectAgents()
  const commands = collectCommands()
  const skills = collectSkills()
  const mcp = collectMcp()

  const read = (rel: string) => readFileSync(path.join(DOCS, rel), "utf8")
  const updates: FileUpdate[] = []

  const changelog = parseChangelog(readFileSync(path.join(PLUGIN, "CHANGELOG.md"), "utf8"))

  const pages: Array<{ file: string; id: string; begin: string; end: string; built: { inner: string; nav: NavItem[] } }> = [
    { file: "pages/agents.html", id: "agents", begin: "<!-- Review Agents -->", end: "<!-- Navigation -->", built: buildAgents(agents) },
    { file: "pages/commands.html", id: "commands", begin: "<!-- Workflow Commands -->", end: "<!-- Navigation -->", built: buildCommands(commands) },
    { file: "pages/skills.html", id: "skills", begin: "<!-- Development Tools -->", end: "<!-- Navigation -->", built: buildSkills(skills) },
    { file: "pages/mcp-servers.html", id: "mcp", begin: "<!-- Playwright -->", end: "<!-- Manual Configuration -->", built: buildMcp(mcp) },
    { file: "pages/changelog.html", id: "changelog", begin: "<!-- Versions -->", end: "</article>", built: buildChangelog(changelog) },
  ]

  for (const p of pages) {
    let html = read(p.file)
    html = spliceContent(html, p.id, p.begin, p.end, p.built.inner)
    html = replaceOnThisPage(html, p.built.nav)
    updates.push({ file: path.join(DOCS, p.file), next: html })
  }

  const skillCount = skills.reduce((n, g) => n + g.skills.length, 0)
  const version = String(JSON.parse(readFileSync(path.join(PLUGIN, ".claude-plugin/plugin.json"), "utf8")).version ?? "")
  const stats: SiteStats = { agents: agents.length, commands: commands.length, skills: skillCount, mcp: mcp.length, version }
  updates.push({ file: path.join(DOCS, "index.html"), next: applyStats(read("index.html"), stats) })

  return updates
}

function main() {
  const check = process.argv.includes("--check")
  const stale: string[] = []
  for (const { file, next } of buildUpdates()) {
    if (readFileSync(file, "utf8") === next) continue
    stale.push(path.relative(ROOT, file))
    if (!check) writeFileSync(file, next)
  }
  if (check && stale.length) {
    console.error(`Docs out of date — run \`bun run docs:build\`:\n  ${stale.join("\n  ")}`)
    process.exit(1)
  }
  console.log(check ? "Docs up to date." : stale.length ? `Rebuilt: ${stale.join(", ")}` : "Docs already current.")
}

if (import.meta.main) main()
