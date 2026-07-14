# Changelog

## [0.2.0](https://github.com/Life-With-Data/agentic-engineering/compare/marketing-v0.1.0...marketing-v0.2.0) (2026-07-14)


### Features

* **marketing:** adopt seo-audit skill from coreyhaines31/marketingskills ([#81](https://github.com/Life-With-Data/agentic-engineering/issues/81)) ([0bca23f](https://github.com/Life-With-Data/agentic-engineering/commit/0bca23f9a84ece15b5886665351a3ee243087c63))
* **workflows:plan:** Add smart research decision logic ([#100](https://github.com/Life-With-Data/agentic-engineering/issues/100)) ([c50208d](https://github.com/Life-With-Data/agentic-engineering/commit/c50208d4130a2b4295bc2b34c8d099688e6fd826))

## 0.1.0 — 2026-07-07

First release of the marketing domain plugin — the first Track A adoption
under `docs/dependency-policy.md`.

### Added

- `seo-audit` skill, adopted (adapted) from
  [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills)
  `skills/seo-audit` @ `6c60174` (MIT). Adaptations: removed upstream
  cross-skill references from the frontmatter description; dropped
  upstream-specific `evals/`; rewrote Related Skills to point at optionally
  installed plugins (upstream `marketing-skills`, Anthropic `marketing`).
  References (`ai-writing-detection.md`, `international-seo.md`) retained.
