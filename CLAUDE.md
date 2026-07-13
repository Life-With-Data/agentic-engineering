# Claude Code Plugin Marketplace

This repository is a Claude Code plugin marketplace that distributes the `agentic-engineering` plugin to developers building with AI-powered tools.

## Repository Structure

```
agentic-engineering/
├── .claude-plugin/
│   └── marketplace.json          # Marketplace catalog (lists available plugins)
├── docs/                         # Documentation site (GitHub Pages)
│   ├── index.html                # Landing page
│   ├── css/                      # Stylesheets
│   ├── js/                       # JavaScript
│   └── pages/                    # Reference pages (generated)
└── plugins/
    └── agentic-engineering/      # The core plugin
        ├── .claude-plugin/
        │   └── plugin.json        # Plugin metadata
        ├── agents/                # Specialized AI agents (nested by category)
        ├── commands/              # Slash commands (some nested, e.g. workflows/)
        ├── skills/                # Skills (one directory per skill)
        ├── README.md              # Plugin documentation
        └── CHANGELOG.md           # Version history
```

Component counts are intentionally not listed here — they drift. The authoritative counts live in `plugins/agentic-engineering/README.md` and the two JSON manifests, where `tests/plugin-consistency.test.ts` (`bun test`) enforces they match the filesystem. MCP servers are declared in `plugin.json`'s `mcpServers` field (currently context7), not a directory.

## Philosophy: Agentic Engineering

**Each unit of engineering work should make subsequent units of work easier — not harder.** Work the loop: **Plan** the change and its impact → **Delegate** implementation to AI tools → **Assess** that it works → **Codify** learnings back into this file, a skill, or a test.

## Updating the plugin

> **The test is the source of truth, not this file.** `tests/plugin-consistency.test.ts` (run by `bun test` in CI) enforces the whole checklist below — component counts across `plugin.json` / `marketplace.json` / both READMEs / `docs/index.html`, plugin↔marketplace version parity, README completeness (every agent/command/skill slug documented), and frontmatter hygiene. Non-core plugins under `plugins/` (e.g. `plugins/marketing`) get an "Includes N skill(s)" phrase check plus version parity. **Run `bun test` before committing; a failure names the exact file/component that is out of sync.**

When you add or remove an agent, command, or skill:

1. **Bump the version** (semver) in `plugins/agentic-engineering/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` — keep them equal. MINOR for new components, PATCH for fixes/docs.
2. **Update the counts** in `plugin.json` `description`, `marketplace.json` `description`, and both READMEs' component tables. The exact expected substrings differ per file — the test encodes each one, so let a `bun test` failure tell you what to change.
3. **Document it** in `plugins/agentic-engineering/CHANGELOG.md` (Keep a Changelog format).
4. **Regenerate the docs site**: `bun run docs:build`, then `bun run docs:check` (also enforced in CI). See [Documentation Site](#documentation-site).
5. **Validate JSON**: `cat .claude-plugin/marketplace.json | jq .` and the same for `plugin.json`.

Counting note: agents and some commands are **nested** under category dirs, so use `find … -name "*.md" | wc -l` (a flat glob misses them); skills are one top-level dir each (`ls -d plugins/agentic-engineering/skills/*/ | wc -l`).

To **add a new plugin**, create `plugins/<name>/` with a `.claude-plugin/plugin.json`, `agents/`/`commands/`/`skills/` as needed, and a `README.md`; then register it in `.claude-plugin/marketplace.json`.

Skill files are `skills/<name>/SKILL.md` with YAML frontmatter (`name` matching the directory, `description` covering **what it does and when to use it**); supporting files go in `scripts/`/`references/`/`assets/` and must be linked from SKILL.md as markdown links, not bare backticks. The `create-agent-skills` skill is the full authoring guide.

### Manifest constraints

`marketplace.json` and `plugin.json` follow the official Claude Code spec — see the [plugin reference](https://docs.claude.com/en/docs/claude-code/plugins-reference). **Only include fields that are in the spec.** Do not add display-only or non-spec fields (`downloads`, `stars`, `rating`, `categories`, `featured`, `trending`, `verified`, `type`). Sticking to the spec is a hard-won learning (see [Key Learnings](#key-learnings)).

### External dependencies (two tracks)

Work from other repos enters this marketplace via exactly one of two tracks per upstream plugin — see `docs/dependency-policy.md` (enforced by `tests/dependency-policy.test.ts`):

- **Adopt** — import individual components through the `/upstream-scan` triage pipeline (`docs/upstream-sources.md`), adapted and provenance-pinned.
- **Depend** — declare a whole plugin in a local plugin's `plugin.json` `dependencies` array. Cross-marketplace deps require the marketplace in `allowCrossMarketplaceDependenciesOn` AND a `dependency:` line in the registry; unversioned deps force `scan: auto`.

The core `agentic-engineering` plugin stays dependency-free; formal dependencies live only in thin domain plugins.

## Documentation Site

The docs site (`/docs`, served by GitHub Pages) is plain HTML/CSS/JS — no build step to view. Open `docs/index.html`, or serve with `python -m http.server 8000` from `docs/`.

The reference pages and landing-page stats are **generated**, so they can't drift:

```bash
bun run docs:build      # regenerate docs/pages/*.html + docs/index.html stats
bun run docs:check      # verify in sync (also enforced in CI via `bun test`)
```

`scripts/generate-docs.ts` reads every plugin under `plugins/` (any dir with `.claude-plugin/plugin.json`, core first), rebuilds the card sections and each page's "On This Page" sidebar between `<!-- GENERATED -->` markers, updates the landing-page stat numbers (marketplace-wide totals), and renders `plugins/agentic-engineering/CHANGELOG.md` into `docs/pages/changelog.html`. **Never hand-edit generated regions or the changelog version entries** — they are overwritten on the next build and caught by `docs:check`. To add a changelog entry, edit `CHANGELOG.md` and run `bun run docs:build`. Hand-written chrome (intros, manual-config) is preserved — edit it directly. The `/release-docs` command is a thin wrapper around `bun run docs:build`.

## Testing changes

```bash
bun test        # consistency + converter suites (the gate CI runs)
bun run typecheck

# Try the plugin locally
claude /plugin marketplace add /path/to/agentic-engineering
claude /plugin install agentic-engineering
```

## Commit conventions

- `Add [component]` / `Remove [component]` — adding or removing functionality
- `Update [file] to [what changed]`, `Fix [issue]`, `Simplify [component] to [improvement]`

Include the footer:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Resources

- [Claude Code Plugin Documentation](https://docs.claude.com/en/docs/claude-code/plugins)
- [Plugin Marketplace Documentation](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces)
- [Plugin Reference](https://docs.claude.com/en/docs/claude-code/plugins-reference)

## Key Learnings

- **2024-11-22 — Count files before updating descriptions.** Adding the first skill revealed the counts were wrong (said 15 agents, actually 17). Counts appear in multiple files and must all match; `tests/plugin-consistency.test.ts` now enforces this, so `bun test` is the check.
- **2024-10-09 — Stick to the official marketplace spec.** The initial `marketplace.json` carried custom fields (`downloads`, `stars`, `rating`, `categories`, `trending`) that aren't in the spec. Removed them; custom fields confuse users and risk breaking future compatibility.
</content>
