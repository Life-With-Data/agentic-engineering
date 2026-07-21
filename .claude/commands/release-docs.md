---
name: release-docs
description: Regenerate the documentation site from current plugin components (deterministic)
argument-hint: "[optional: --check to verify without writing]"
---

# Release Documentation

The docs reference pages and landing-page stats are **generated deterministically** from the plugin's actual components by `scripts/generate-docs.ts`. There is no manual card-writing step — run the generator.

## Regenerate

```bash
bun run docs:build
```

This rewrites, from the filesystem truth:

- `docs/pages/agents.html`, `skills.html`, `mcp-servers.html` — the component card sections (between `<!-- GENERATED:<id> START/END -->` markers) and each page's "On This Page" sidebar.
- `docs/pages/changelog.html` — the version entries, rendered from the plugin's `CHANGELOG.md`.
- `docs/index.html` — the `data-stat` numbers (agents / skills / MCP servers) and the plugin version.

All other page chrome (nav, intros, manual-config, footer) is preserved verbatim — edit those by hand.

## Verify

```bash
bun run docs:check   # exits non-zero if anything is out of sync
bun test             # includes the plugin-consistency + docs-generated gates
```

CI runs these on every PR via `bun test`, so the docs cannot silently drift. If `docs:check` fails, run `bun run docs:build` and commit the result.

## Dry run

```bash
bun run docs:check   # reports which files would change; writes nothing
```

## After regenerating

1. Review the diff (`git diff docs/`).
2. Commit: `docs: regenerate documentation site from components`.
3. The GitHub Pages deploy (`.github/workflows/deploy-docs.yml`) publishes `docs/` on push to `main`.

## Note

To change a card's *shape* (markup/classes) or add a new category icon, edit the renderers in `scripts/generate-docs.ts`, not the HTML — hand edits inside the `GENERATED` markers are overwritten on the next build.
