---
date: 2026-07-14
topic: convert-commands-to-skills
github_issue: 134
---

# Migrate the Core Plugin's Commands into Skills

## What We're Building

Literally migrate all 28 command files under `plugins/agentic-engineering/commands/` (20 top-level utility commands + 8 `workflows:*` commands) into skill format (`skills/<name>/SKILL.md`), then delete `commands/` from the core `agentic-engineering` plugin entirely. This is a source-level migration, not a per-target conversion: after this change, the plugin authors only skills, everywhere, for every product — including Claude Code itself.

Motivating context: the repo already has a converter pipeline (`src/converters/`) that auto-converts commands into skill-equivalents *per target* for products lacking native command support (Codex, Copilot). That pattern stays valuable for genuinely command-less targets, but it doesn't address the underlying premise here — the user wants the *source of truth* to be skills-only, since Claude Code's own spec has merged commands into skills (`.claude/commands/x.md` and `.claude/skills/x/SKILL.md` both produce `/x` and behave identically — confirmed in this repo's own `skills/create-agent-skills/references/official-spec.md`). Authoring only skills going forward removes the dual-format maintenance burden and gives every future converter target (including a not-yet-built ChatGPT target) one input format instead of two.

## Why This Approach

Rejected alternative: keep commands as a distinct component type and rely entirely on per-target converters (like Codex's `convertCommandSkill()`) to produce skill-equivalents downstream. That was the status quo and is what the repeated "add a new target" pattern (Copilot, Gemini CLI, Cursor CLI) already assumes — but it means every new target re-derives the same command→skill mapping, and Claude Code itself carries two component types that the platform has already unified. Converting at the source is simpler and matches where the platform is headed.

This is largely a **mechanical restructuring, not a behavioral rewrite**: 17 of the 28 commands already set `disable-model-invocation`, meaning they already use skill-native frontmatter semantics under Claude Code's merged commands/skills model. Skill frontmatter already supports everything commands use (`argument-hint`, `disable-model-invocation`, `user-invocable`, `allowed-tools`).

## Key Decisions

- **Scope: core `agentic-engineering` plugin only** (28 commands). Other marketplace plugins (marketing, small-business, sales, productivity, design, gws, vercel, etc.) are out of scope for this pass — this establishes the pattern; other plugins can follow later once proven.
- **Hard cutover, no compatibility shims.** Delete `commands/` outright rather than keeping thin command files alongside skills — consistent with this repo's own CLAUDE.md guidance against backwards-compatibility hacks, and avoids a permanently dual-format plugin.
- **Rename the 8 `workflows:*` commands to hyphenated skill names** (`workflows:plan` → `workflows-plan`, etc.). Skill `name` frontmatter only allows lowercase letters, numbers, and hyphens — colons aren't valid. The hyphen preserves the visual grouping and still avoids collision with Claude Code's built-in `/plan` and `/review`. This is a visible breaking change: every internal cross-reference between commands (they invoke each other by name throughout this repo), every doc, and any external muscle-memory around `/workflows:plan` needs updating.
- **Also normalize the 3 underscore-named commands** (`generate_command.md`, `resolve_parallel.md`, `resolve_todo_parallel.md`) to hyphens (`generate-command`, `resolve-parallel`, `resolve-todo-parallel`) for the same reason — skill names don't allow underscores either.
- **Single atomic migration, not phased.** All 28 files move in one PR rather than piloting the 8 workflow commands first. Since the change is mechanical rather than risky/behavioral, a phased rollout mainly adds a longer window where `tests/plugin-consistency.test.ts`, docs generation, and README component tables have to reconcile two formats at once — not worth the complexity for a low-risk change.

## Resolved Questions

- **Does the converter pipeline (`src/converters/`) need updating in the same plan?** Yes. Codex's `convertCommandSkill()` and any Copilot-equivalent logic specifically special-case "commands" as input and synthesize skills from them; once `commands/` is deleted, that logic breaks or becomes dead code, and `bun test`'s converter suites would fail immediately. Fixing the converter pipeline is in scope for the same plan/PR as the markdown migration — not a deferred follow-up — so CI stays green throughout. The plan needs a full inventory of every place `commands/` is referenced by path first: converters, `tests/plugin-consistency.test.ts`, `scripts/generate-docs.ts`, both READMEs, and `plugin.json` component counts.

- **Do per-target content-transform functions (Task-call/slash-ref/`.claude/`-path rewrites) need to be extended to cover the 28 migrated skill files?** No — not in scope for this migration. Verified empirically: these transforms already run *only* on commands today, never on the 35 existing skills (skills pass through every converter untouched as `skillDirs`). 17 of those 35 existing skills already contain `/workflows:*`, `Task(...)`, or `.claude/`-path references that go unrewritten in generated output today. If that's a real problem, it's a pre-existing gap affecting the whole skills pipeline, not something this migration introduces or worsens — the 28 migrated files simply join the same treatment 35 files already get. Out of scope; file separately if it turns out to matter in practice.

- **How should OpenCode's "from-commands" permission-derivation mode be handled once `commands/` is empty?** Repoint it at skills' `allowed-tools` frontmatter instead of commands', preserving today's permission behavior for OpenCode users rather than silently degrading to an all-deny set.

- **Does Cursor's native manifest (`.cursor-plugin/plugin.json`) need to keep its explicit `"commands": "./commands/"` field to preserve slash-invocation for these 28?** No — drop the field. Confirmed via Cursor's own docs (cursor.com/help/customization/skills): skills already "show up in the same `/` slash menu as commands," and `disable-model-invocation: true` on a skill "behave[s] like a traditional slash command" requiring explicit `/skill-name` invocation — functionally identical to what commands provided. **Pre-ship verification note:** a Cursor community forum report (https://forum.cursor.com/t/disable-model-invocation-true-completely-hides-plugin-delivered-skills-from-command-palette/155748) describes `disable-model-invocation: true` sometimes hiding *plugin-delivered* skills from the palette entirely — worth a real install-and-check before calling this done, since 17 of the 28 migrated files use that flag.

## Next Steps

→ `/workflows:plan`
