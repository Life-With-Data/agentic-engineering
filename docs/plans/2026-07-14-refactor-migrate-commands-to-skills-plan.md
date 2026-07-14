---
title: Migrate Core Plugin Commands into Skills
type: refactor
date: 2026-07-14
origin: docs/brainstorms/2026-07-14-convert-commands-to-skills-brainstorm.md
github_issue: 134
---

# Migrate Core Plugin Commands into Skills

## Overview

Migrate all 28 command files in `plugins/agentic-engineering/commands/` into skill format (`skills/<name>/SKILL.md`), then delete `commands/` from the core `agentic-engineering` plugin entirely. This is a hard cutover in a single atomic PR: no compatibility shims, no phased rollout, no dual-authored transition period. After this change, the core plugin authors only skills — for Claude Code, Cursor, and every other product target — matching the platform reality that Claude Code has already merged commands into skills as one mechanism.

## Problem Statement / Motivation

The core plugin currently maintains two component types (`commands/` and `skills/`) that Claude Code's own spec has functionally unified: a file at `.claude/commands/x.md` and a skill at `.claude/skills/x/SKILL.md` both produce `/x` and behave identically, with skill frontmatter already supporting everything commands use (`argument-hint`, `disable-model-invocation`, `user-invocable`). Maintaining the split costs real overhead — every "add a target" pass (Copilot, Codex, Gemini CLI, Cursor CLI) has had to re-derive the same command→skill mapping downstream — for a distinction the platform no longer requires upstream. Converting at the source removes that duplication and gives every future converter target, including a not-yet-built ChatGPT target, one input format instead of two.

## Proposed Solution

Move each of the 28 command files into a directory-per-skill layout under `skills/`, translating frontmatter 1:1 (all fields commands use are already valid skill frontmatter) and resolving two naming conflicts the skill spec forces: the 8 `workflows:*` commands lose their colon (skill names allow only lowercase letters, numbers, hyphens) and become hyphenated (`workflows:plan` → `workflows-plan`); the 3 underscore-named commands (`generate_command`, `resolve_parallel`, `resolve_todo_parallel`) become hyphenated for the same reason. Every internal cross-reference to an old name — inside other skills, agents, and both READMEs — gets updated to match.

Two real (non-cosmetic) code fixes ride along in the same PR because they'd otherwise silently regress: the skill parser doesn't currently read `allowed-tools`/`argument-hint` the way the command parser does, and OpenCode's permission-derivation mode reads `allowed-tools` only from commands. Both get fixed at the parser level, not worked around per-target.

## Why This Approach

(See `docs/brainstorms/2026-07-14-convert-commands-to-skills-brainstorm.md` for the full alternatives analysis — the primary decisions carried forward are core-plugin-only scope, hard cutover with no compat shims, hyphenated renames, and a single atomic migration rather than phased.)

**Corrected scope for the converter pipeline** (a mid-planning finding that overrides the brainstorm's original framing): `src/converters/` is not specific to this plugin. The sync CLI's entry point (`src/parsers/claude-home.ts`'s `loadClaudeHome()`) aggregates a user's entire `~/.claude/` setup — every installed plugin's commands and skills, from any marketplace — before conversion. Confirmed via `find plugins -maxdepth 2 -type d -name commands`: **no other plugin in this marketplace has a `commands/` directory** (marketing, small-business, sales, productivity, design, gws, vercel, etc. are already skills-only), but a user could still have other command-bearing plugins installed from elsewhere. Deleting or "cleaning up" the converters' command-handling code (`convertCommandSkill()`, `convertCommand()`, etc. across all 8 target converters) would be a real regression for any such user — that code stays exactly as-is. The only required converter-adjacent changes are the two parser-parity fixes below, which are general improvements (they help every skill, not just these 28), not command-removal cleanup.

## Technical Approach

### Architecture

**1. Parser parity fix (prerequisite for everything else — do this first).**

`src/parsers/claude.ts`: `loadCommands()` (lines 77–99) parses `allowed-tools` and `argument-hint` into `ClaudeCommand`; `loadSkills()` (lines 101–119) does not — `ClaudeSkill` only carries `name`, `description`, `disableModelInvocation`, `sourceDir`, `skillPath`. Extend the `ClaudeSkill` type with `allowedTools?` and `argumentHint?`, and extend `loadSkills()` to parse both fields from SKILL.md frontmatter (they're already valid per the official spec — this is a pre-existing parser gap, not new surface). Add parser unit tests covering a skill with both fields set.

**2. OpenCode permission-derivation fix.**

`src/converters/claude-to-opencode.ts`'s `applyPermissions()` (lines 296–395) builds OpenCode's permission config from `command.allowedTools` in `"from-commands"` mode. Extend it to also read `skill.allowedTools` (now available per fix #1) so a skills-only plugin (this one, post-migration) still produces a real permission set instead of silently degrading to all-deny. This is additive — plugins that still have commands keep working exactly as today.

**3. Cursor native manifest.**

`plugins/agentic-engineering/.cursor-plugin/plugin.json`: drop the `"commands": "./commands/"` field. Confirmed via Cursor's own docs (cursor.com/help/customization/skills): skills already appear in Cursor's `/` slash menu, and `disable-model-invocation: true` makes a skill "behave like a traditional slash command" — functionally equivalent to what the commands field provided. **Pre-ship verification:** a Cursor community forum report (forum.cursor.com/t/disable-model-invocation-true-completely-hides-plugin-delivered-skills-from-command-palette/155748) describes plugin-delivered skills with `disable-model-invocation: true` sometimes vanishing from the palette — since 17 of the 28 migrated files use that flag, do a real Cursor install-and-check before calling this done (see Validation).

**4. Content migration (the bulk of the diff).**

For each of the 28 files: create `skills/<new-name>/SKILL.md`, carry the body verbatim, translate frontmatter (`name:` → new hyphenated value where applicable; `disable-model-invocation`, `argument-hint`, `allowed-tools` unchanged). One exception: `commands/create-agent-skill.md`'s entire body is `Invoke the create-agent-skills skill for: $ARGUMENTS` — migrating it verbatim produces a skill named `create-agent-skill` sitting one letter from the pre-existing `create-agent-skills` skill, doing nothing but redirecting to it. Delete rather than migrate; anything that referenced `/create-agent-skill` should reference `/create-agent-skills` directly instead. Delete `plugins/agentic-engineering/commands/` (including `commands/workflows/`) once all 28 (27, net the deletion) are moved.

**Full rename table:**

| Old command name | New skill name |
|---|---|
| `workflows:brainstorm` | `workflows-brainstorm` |
| `workflows:compound` | `workflows-compound` |
| `workflows:groom` | `workflows-groom` |
| `workflows:merge` | `workflows-merge` |
| `workflows:orchestrate` | `workflows-orchestrate` |
| `workflows:plan` | `workflows-plan` |
| `workflows:review` | `workflows-review` |
| `workflows:work` | `workflows-work` |
| `generate_command` | `generate-command` |
| `resolve_parallel` | `resolve-parallel` |
| `resolve_todo_parallel` | `resolve-todo-parallel` |
| `create-agent-skill` | *(deleted — redirect to existing `create-agent-skills`)* |
| all other 16 (already valid names) | unchanged, just relocated |

**5. Cross-reference sweep.** Update every reference to an old name found by the research pass, at minimum:
- Skills: `file-todos`, `compound-docs`, `land-pr` (7+ refs, incl. `scripts/pr-landable-status`), `reflect-for-skill-updates`, `document-review`, `lifecycle` (7+ refs, incl. `references/gh-recipes.md`), `setup` (multiple refs), `brainstorming`, `git-worktree`, `doubt-driven-development`, `interview-me`, `test-strategy-reviewer`, `debugging-and-error-recovery`, `test-driven-development` (incl. `references/testing-patterns.md`).
- Agents: `research/git-history-analyzer.md`, `research/learnings-researcher.md`, `review/acceptance-criteria-reviewer.md` (in its own frontmatter `description`), `review/code-simplicity-reviewer.md`.
- `plugins/agentic-engineering/README.md` and `plugins/agentic-engineering/FLOWS.md` (both need substantial rewrites, not just find-replace — see Documentation Plan).
- Root `README.md`.
- Note two **pre-existing** orphaned README rows unrelated to this migration but touched by the same rewrite: `/sync` and `/resolve_pr_parallel` are documented in the README's Utility Commands table with no corresponding file. Remove them while rewriting rather than migrating nonexistent commands.

**6. Test updates.**

- `tests/plugin-consistency.test.ts`: update the six blocks identified in research — component-count strings in `plugin.json`/`marketplace.json`/both READMEs/`docs/index.html` descriptions (commands → 0, drop the "commands" stat entirely rather than assert `0`, per the docs-site decision below); the Cursor manifest field check (remove `commands` from the `cursorPaths` array and the `existsSync` check); the "manifest component paths resolve" check; README-completeness `test.each(commandFiles...)` blocks become empty/no-op (harmless, but delete rather than leave as dead test scaffolding); frontmatter-hygiene `test.each([...commandFiles, ...agentFiles])` drops the command half (skills already have their own equivalent block that the 27 migrated files join automatically).
- `tests/upstream-registry.test.ts:15`: update the hardcoded path from `plugins/agentic-engineering/commands/upstream-scan.md` to `plugins/agentic-engineering/skills/upstream-scan/SKILL.md`.
- `tests/flagless-gh.test.ts`: no code change required — `mdFilesRecursive()` on a missing `commands/` returns `[]` gracefully, and the union collapses to `skillFiles` alone. Update only the stale header comment ("greps every command and skill markdown file").
- Add a unit test asserting `loadSkills()` parses `allowed-tools` and `argument-hint` (fix #1).
- Add/extend an OpenCode converter test covering `"from-commands"` mode against a commands-empty, skills-with-allowedTools fixture (fix #2).
- Converter test suites (`{pi,codex,kiro,copilot,cursor,gemini,droid}-converter.test.ts`, `converter.test.ts`) build synthetic in-memory fixtures independent of the real plugin — **leave these untouched**; they remain valid regression coverage for command-bearing plugins generally, per the corrected converter scope above.

### System-Wide Impact

- **Interaction graph:** the ~19 cross-reference files above invoke these commands/skills by name (Task calls, slash-style prose refs, `Skill()` allowed-tools entries) — a missed rename leaves a dangling reference that either silently fails to resolve or resolves to nothing at runtime. The cross-reference sweep must be exhaustive, not sampled.
- **Error propagation:** N/A — this is a static content/config migration, no new runtime error paths beyond the parser and OpenCode permission changes, both covered by new unit tests.
- **State lifecycle risks:** none — no persistent state, no migrations of data, no lifecycle-board interaction beyond the plan's own tracking.
- **API surface parity:** the plugin's public surface (what a Claude Code user, Cursor user, or converter consumer sees) changes deliberately — `/workflows:plan` becomes `/workflows-plan`, etc. This is the intended, accepted breaking change (see Version Bump below), not a parity gap to close.
- **Integration test scenarios:** (1) fresh Claude Code plugin install, confirm all 27 migrated skills appear and are invocable with their new names; (2) a `disable-model-invocation: true` skill in this batch is NOT auto-triggered by conversational context but IS invocable via explicit `/name`; (3) `bun run sync --target opencode` against the migrated plugin produces a non-empty, correct permission set (fix #2); (4) native Cursor install shows the migrated skills in the `/` menu, including a `disable-model-invocation` one (pre-ship verification for the forum-reported bug); (5) `bun test` full suite green.

### External System Wiring

No external wiring required — this is entirely within-repo config and code.

## Alternative Approaches Considered

See brainstorm doc: rejected keeping commands as a distinct type relying solely on per-target converters (status quo — re-derives the mapping per target instead of once at the source); rejected marketplace-wide scope (too large a single change); rejected a phased/piloted rollout (unnecessary given the change is mechanical, not risky).

## Acceptance Criteria

### Functional Requirements

- [ ] All 27 skills (28 minus the deleted `create-agent-skill` redirect) exist under `plugins/agentic-engineering/skills/<name>/SKILL.md` with frontmatter and body carried forward correctly.
- [ ] `plugins/agentic-engineering/commands/` no longer exists.
- [ ] The 8 `workflows:*` skills are named per the rename table; the 3 underscore commands are hyphenated.
- [ ] Every cross-reference identified in the research sweep (skills, agents, both READMEs, FLOWS.md) uses the new names — zero references to old command names remain (`grep -r "workflows:plan\|workflows:groom\|workflows:work\|workflows:brainstorm\|workflows:compound\|workflows:merge\|workflows:orchestrate\|workflows:review\|generate_command\|resolve_parallel\b\|resolve_todo_parallel" plugins/agentic-engineering/ --include=*.md` returns nothing outside historical docs like CHANGELOG.md/brainstorms/plans).
- [ ] `ClaudeSkill` type and `loadSkills()` parse `allowed-tools` and `argument-hint`.
- [ ] OpenCode's `"from-commands"` permission mode produces a non-empty, correct permission set when converting a commands-empty/skills-with-allowedTools plugin.
- [ ] `.cursor-plugin/plugin.json` has no `commands` field.
- [ ] `plugin.json` and `marketplace.json` versions bumped to `4.0.0` (MAJOR — see rationale below); descriptions drop "commands" entirely and update skill count to 62 (35 existing + 27 migrated — 28 commands minus the deleted `create-agent-skill` redirect).
- [ ] `CHANGELOG.md` documents the migration under a new version entry.

### Non-Functional Requirements

- [ ] No change in behavior for any of the 8 target converters for plugins that still have commands (verified by leaving their test suites green and untouched).
- [ ] `bun run docs:build` regenerates `docs/index.html` stats and any `<!-- GENERATED -->` blocks correctly with the new counts.

### Quality Gates

- [ ] `bun test` passes in full.
- [ ] `bun run typecheck` passes.
- [ ] `bun run docs:check` passes.
- [ ] `cat .claude-plugin/marketplace.json | jq .` and the plugin.json equivalent both validate.

## Validation

**How a reviewer proves this behaves — not merely that it compiles:**

- **Automated:** `bun test` (full suite, including the new parser and OpenCode tests), `bun run typecheck`, `bun run docs:check`.
- **Integration:** run `bun run sync --target opencode` (or the equivalent CLI invocation) against the migrated plugin and inspect the generated permission config for non-empty, correct entries derived from skills' `allowed-tools`.
- **Manual:**
  1. `claude /plugin marketplace add /path/to/agentic-engineering && claude /plugin install agentic-engineering` — confirm the `/` menu lists all 27 migrated skills under their new names, and that a sample `disable-model-invocation: true` skill (e.g. `/workflows-groom`) invokes correctly while NOT appearing as an auto-triggered suggestion from unrelated conversation.
  2. Install natively in Cursor per `docs/multi-platform-native-plugins.md` §5, confirm the same skills appear in Cursor's `/` menu, specifically re-checking the forum-reported `disable-model-invocation` visibility bug against a couple of the 17 affected skills.
  3. `bun run docs:build` then visually spot-check `docs/pages/skills.html` (63 entries) and confirm `docs/pages/commands.html` was removed (see docs decision below) along with its nav-chrome links across the 6 hand-written pages.
- **Rollback:** revert the single migration PR — since this is a pure content/config + two additive parser changes with no data migration, a straight `git revert` is safe and complete.

## Success Metrics

Zero broken cross-references (grep-verifiable), `bun test` green, and a real Claude Code + Cursor install both showing the full skill set with correct invocation semantics.

## Dependencies & Prerequisites

Fix #1 (parser parity) must land before fix #2 (OpenCode permissions), since #2 depends on `ClaudeSkill.allowedTools` existing. The content migration (task 4) can proceed independently/in parallel with fixes #1–#3, but the cross-reference sweep (task 5) and test updates (task 6) depend on the content migration being complete (need final file paths/names to reference).

## Risk Analysis & Mitigation

- **Missed cross-reference** → dangling `/old-name` reference. Mitigation: the grep-based acceptance criterion above is exhaustive, not a sample; run it as a CI-style check before merge.
- **Cursor `disable-model-invocation` visibility bug** (community-reported, unconfirmed against this repo's exact setup) → some of the 17 flagged skills could be invisible in Cursor's palette. Mitigation: explicit manual verification step in Validation; if confirmed, file as a follow-up against Cursor rather than blocking this migration (it's a Cursor-side bug, not something this repo's manifest can work around).
- **Version-bump blast radius**: MAJOR (`3.22.0` → `4.0.0`) is the correct call per this repo's own CLAUDE.md ("MAJOR: Breaking changes, major reorganization") — every `/workflows:*` slash-command reference anywhere (scripts, muscle memory, external docs) breaks. No aliasing/redirect is planned (would reintroduce the dual-format maintenance burden this migration exists to remove); the CHANGELOG entry should say so explicitly and loudly.

## Resource Requirements

Single-session implementation; no infrastructure or external service needs.

## Future Considerations

This establishes the pattern for migrating other marketplace plugins to skills-only if desired later (none currently have commands, so no immediate follow-up is required). It also removes the source-format obstacle for a future ChatGPT converter target, though building that target is separate, unscoped work.

## Documentation Plan

- `plugins/agentic-engineering/README.md`: replace the "Commands" component-table row and the full "## Commands" section (Workflow + Utility tables) with the migrated entries folded into "## Skills" — the embedded lifecycle/issue-tracker prose currently living inside the Workflow Commands section (original README lines ~91–110) must be relocated into the new Skills section, not dropped.
- Root `README.md`: update hero prose ("31 agents, 28 commands, and 35 skills" → new counts, no commands), the `workflows:*` table (rename + fold into skills framing), and per-target install/notes rows that reference command-specific behavior (Codex, Gemini, OpenCode, Droid rows currently describe command handling that no longer applies to this plugin specifically).
- `plugins/agentic-engineering/FLOWS.md`: update the `/workflows:*`, `/deepen-plan`, `/triage`, `/upstream-scan` references to new names.
- `plugins/agentic-engineering/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`: description strings updated to new counts (and `.cursor-plugin/plugin.json` additionally drops the `commands` field per fix #3).
- **Docs site decision:** delete `docs/pages/commands.html` and its `buildUpdates()` entry in `scripts/generate-docs.ts` rather than leave a permanently-empty "Commands (0)" page — consistent with the hard-cutover, no-compat-shim decision. Manually update the hand-written sidebar nav ("Commands (N)" link) and `nav-prev`/`nav-next` chains across the 6 affected pages (`agents.html`, `changelog.html`, `mcp-servers.html`, `skills.html`, `getting-started.html`, and `commands.html` itself, which is being removed) since this chrome sits outside `bun run docs:build`'s generated markers. Re-run `bun run docs:build && bun run docs:check` after.

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-07-14-convert-commands-to-skills-brainstorm.md](../brainstorms/2026-07-14-convert-commands-to-skills-brainstorm.md) — key decisions carried forward: core-plugin-only scope, hard cutover with no compat shims, hyphenated renames for colon/underscore names, single atomic migration, OpenCode permission fix, Cursor manifest field drop.

### Internal References

- `src/parsers/claude.ts:77-119` — `loadCommands()`/`loadSkills()` parity gap.
- `src/converters/claude-to-opencode.ts:296-395` — `applyPermissions()`.
- `plugins/agentic-engineering/.cursor-plugin/plugin.json` — native Cursor manifest.
- `tests/plugin-consistency.test.ts` — component-count and manifest-path assertions.
- `tests/upstream-registry.test.ts:15` — hardcoded command path.
- `scripts/generate-docs.ts` — `collectCommands()`/`buildCommands()`/`docs/pages/commands.html` entry.
- `docs/solutions/plugin-versioning-requirements.md` — versioning workflow this plan follows.

### External References

- [Cursor Skills docs](https://cursor.com/help/customization/skills) — confirms skills appear in Cursor's `/` menu with `disable-model-invocation` semantics matching commands.
- [Cursor forum: disable-model-invocation hides plugin-delivered skills from palette](https://forum.cursor.com/t/disable-model-invocation-true-completely-hides-plugin-delivered-skills-from-command-palette/155748) — unconfirmed bug report, pre-ship verification item.
- `plugins/agentic-engineering/skills/create-agent-skills/references/official-spec.md` — this repo's own copy of the official Claude Code skill spec, confirming commands/skills are merged and the full frontmatter field set.
