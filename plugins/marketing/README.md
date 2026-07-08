# marketing

Thin marketing domain plugin for the `agentic-engineering` marketplace. Holds
marketing components consumed under the two-track external dependency policy
(`docs/dependency-policy.md`): adopted skills are adapted and provenance-pinned
in `docs/upstream-sources.md`; any future whole-plugin dependencies are
declared in this plugin's `plugin.json` `dependencies` array.

The core `agentic-engineering` plugin stays engineering-specific and
dependency-free; marketing lives here.

## Skills

| Skill | What it does | Provenance |
|-------|--------------|------------|
| `seo-audit` | Expert SEO audit: crawlability, indexation, Core Web Vitals, on-page, international/hreflang, E-E-A-T, site-type-specific issue catalogs, prioritized action plan | Adopted (adapted) from [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) `skills/seo-audit` — MIT |

## Complementary plugins (not required)

- **`marketing-skills`** (coreyhaines31/marketingskills) — the upstream
  catalog of ~46 marketing skills. Install alongside for the full set:
  `claude plugin marketplace add coreyhaines31/marketingskills`.
- **Anthropic `marketing` plugin** (anthropics/knowledge-work-plugins) —
  connector-driven reporting (Ahrefs, Amplitude, Klaviyo, …). Its skills pull
  live data once connectors are authorized; this plugin's skills carry the
  practitioner knowledge.

## Attribution

`skills/seo-audit` is adapted from
[coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills),
© Corey Haines, MIT License. See the pinned upstream commit in
`docs/upstream-sources.md`.
