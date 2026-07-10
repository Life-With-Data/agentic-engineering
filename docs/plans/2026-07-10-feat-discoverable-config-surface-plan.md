---
title: "feat(config): discoverable config surface across the marketplace — config command, doctor health section, self-declaring flag registry"
type: feat
date: 2026-07-10
github_issue: 91
---

# feat(config): discoverable config surface across the marketplace ✨

## Overview

The core plugin has quietly grown a pile of opt-in, per-repo configuration flags that live as frontmatter keys in a target repo's untracked `agentic-engineering.local.md` (and, for board identity, the committed `agentic-engineering.md`). Each flag was added by whichever script needed it, with **zero central discoverability**: nothing tells a user "here is everything you can turn on or off." The freshest example is `nudge_todowrite`, added in PR #90 straight inside `scripts/nudge-todowrite-to-tracker.py:63-85` (`nudge_opted_in`) with no surface anywhere that announces it exists.

This plan introduces a **self-declaring, per-plugin config-flag registry** and two consuming surfaces, split by temporal role to match the roles `setup` and `lifecycle-doctor` already occupy:

- **`config`** (NEW command) — anytime, revisitable: enumerate every toggleable flag across installed plugins, show current-vs-default, and safely flip the local ones.
- **`doctor`** (existing `lifecycle-doctor` command) — gains a read-only **Configuration** section that *reports* SET/UNSET/effective per flag (the only overlap with `config`: shared read, different rendering intent).
- **`setup`** (existing skill) — keeps its detection/install/bootstrap work but **delegates flag serialization** to the shared registry writer instead of hand-templating YAML.

A grep-based lint test (mirroring `tests/flagless-gh.test.ts`) makes it impossible for a new flag to ship invisibly again. Cross-plugin discovery follows the exact per-plugin-scan precedent `scripts/generate-docs.ts` already established (`pluginDirs()`, `scripts/generate-docs.ts:39-45`) — but, as Phase 2 details, that scan can only run **at repo build time** (where `plugins/` is walkable), not at runtime: Claude Code provides no way for a running command or hook to enumerate sibling installed plugins. A future in-repo plugin that ships its own flags is therefore picked up by a **build-time generator that bakes the aggregate into a committed file inside the core plugin**, the same generate-and-commit discipline `docs/pages/*.html` already use.

## Problem Statement

Four production flags exist today, read by four different scripts, documented in no single place:

| Flag | Kind | Read by | File |
|---|---|---|---|
| `issue_tracker` | enum `github-project\|github\|none` | `workflow-repo-preflight.py:160-204` (`read_local_config_tracker`); carve-out `plan-tracker-guard.py:135-137` (`is_none_carveout`) | `.local.md` |
| `review_agents` | list | `skills/setup/SKILL.md:403-421` writes it; `/workflows:review`,`/workflows:work` read it | `.local.md` |
| `plan_review_agents` | list | same as above | `.local.md` |
| `nudge_todowrite` | boolean (default off) | `nudge-todowrite-to-tracker.py:63-85` | `.local.md` |

Plus two board-identity keys that *look* like config but are not toggles — `github_project_owner` / `github_project_number`, read by `lifecycle_board.py:358-400` (`read_board_config`), committed to `agentic-engineering.md`. These must be **inventoried but excluded from any flip UI** (a PR must never be able to carry board identity — the security invariant enforced at `lifecycle_board.py:375-398`).

The consequences:

1. **No discovery.** A user cannot answer "what can I turn on?" without grepping the plugin's Python. `lifecycle-doctor` does not help — it only runs `lifecycle_board.py --doctor` (`commands/lifecycle-doctor.md:14-16`), which checks GitHub Projects board health (`verb_doctor`, `lifecycle_board.py:1442-1552`), nothing about `.local.md` flags.
2. **No enforcement.** Nothing couples "a script reads a config key" to "that key is documented." The `nudge_todowrite` addition in PR #90 is proof: a whole new opt-in landed with no discoverability obligation.
3. **Duplicated write logic.** `setup` hand-templates the frontmatter block (`skills/setup/SKILL.md:403-421`) rather than going through the atomic, byte-preserving `upsert_frontmatter_keys` (`lifecycle_board.py:262-314`) that the board bootstrap already uses. Adding a flag means editing prose in two places.

This is **not** issue #71 (generalizing `lifecycle-doctor` into a composable `/doctor --subsystem X` for *health* checks). #71 is about doctor's internal composability; this is a distinct UI surface for feature discovery/toggling. The two are aligned — the Configuration section here is shaped as a self-contained subsystem producer #71 could later absorb — but this plan neither blocks nor is blocked on #71.

It is also the philosophical **opposite** of doctor's established "silent unless something's wrong / never print on all-PASS" hook tenet (grooming notes for issue #68). A health check stays quiet when healthy; a config browser must show *everything regardless of state*. That contradiction is exactly why `config` is a separate surface and not a `--config` flag bolted onto doctor.

## Proposed Solution

Three artifacts plus a retrofit and a test.

1. **A per-plugin registry module.** Each plugin that ships config flags declares them in `scripts/config_registry.py` — a stdlib-only Python module exporting `CONFIG_FLAGS`, a list of flag descriptors (schema in Decision 1). The core plugin ships the first one, declaring the six existing keys. At **runtime**, a command only ever loads registry files under its own `${CLAUDE_PLUGIN_ROOT}` — Claude Code cannot enumerate sibling plugins from a running command (confirmed by the Hooks docs: *"Hooks cannot discover other installed plugins"*). Cross-plugin aggregation therefore happens at **build time** in this marketplace repo, mirroring `generate-docs.ts:39-45` (scan plugin directories, core first), and the result is committed as a generated file shipped inside the core plugin (Phase 2). The registry module also exposes the three CLI verbs `--inventory`, `--get`, `--set` that both consuming surfaces call.

2. **A `config` command** (`commands/config.md`) — renders the inventory as a table grouped by plugin, then uses `AskUserQuestion` to let the user flip a toggleable flag, writing through the shared `--set` verb. Read-only in non-interactive/pipeline mode.

3. **A doctor Configuration section** — `lifecycle-doctor.md` gains a step that runs `config_registry.py --inventory` and renders it read-only with a SET/UNSET vocabulary (Decision 4), distinct from the health checks' PASS/WARN/FAIL/SKIP.

4. **Retrofit** — the four existing toggles plus the two identity keys are declared in the core registry (Decision 6). No reader behavior changes; the readers keep parsing via `parse_frontmatter` (`lifecycle_board.py:246-259`). The registry documents them so the surfaces and the lint test see them.

5. **A lint test** — `tests/config-registry.test.ts`, mirroring `tests/flagless-gh.test.ts`, scans every `plugins/*/scripts/*.py` for frontmatter-key reads and fails CI if a key is read but not registered (Decision 5).

6. **`setup` delegation** — `setup` is refactored to write `issue_tracker` / `review_agents` / `plan_review_agents` / `nudge_todowrite` through the shared local-config writer and to point users at `/…:config` for later changes (Decision 3).

## Technical Approach

### Architecture

Data flow (single read, multiple renders):

```
plugins/*/scripts/config_registry.py   (per-plugin CONFIG_FLAGS declarations)
        │  BUILD TIME ONLY: generator scans core-first (generate-docs.ts:39-45
        │  pattern) and bakes siblings into a committed generated file inside
        │  the core plugin (Phase 2). Runtime never walks siblings.
        ▼
core:  scripts/config_registry.py  ── verbs ──▶  --inventory  (read-only JSON)
                                                 --get <key>   (read-only JSON)
                                                 --set <key> v (validated write)
        │                                              │
        │ writes route by flag.file:                   │
        │   local  → write_local_config_keys (NEW)     │
        │   committed/identity → NOT writable here     │
        ▼                                              ▼
   upsert_frontmatter_keys + atomic write     tracked-file guard + .gitignore ensure
   (reuse lifecycle_board.py:262-339)         (reuse setup Step 4.5 recipe / _is_tracked)
        ▲                                              ▲
        │ --inventory                                  │ AskUserQuestion + --set
   ┌────┴─────────────────┐                    ┌───────┴──────────┐
   │ lifecycle-doctor.md  │                    │   config.md      │
   │ "Configuration" sect │                    │ browse + flip    │
   │ SET/UNSET (+WARN inv) │                    │ toggleable only  │
   └──────────────────────┘                    └──────────────────┘
```

**Why a Python module and not JSON/YAML data:** the existing readers are stdlib-only Python (`lifecycle_board.py`, `workflow-repo-preflight.py`, `nudge-todowrite-to-tracker.py`), the write path (`upsert_frontmatter_keys`) is Python, and the reverse-check in the lint test wants to name an owning script. A Python `CONFIG_FLAGS` list keeps the registry in the same language and import graph as everything it describes (`nudge-todowrite-to-tracker.py:30-39` already demonstrates the `importlib.util.spec_from_file_location` cross-script import idiom the registry loader reuses).

**The runtime-root constraint (load-bearing, drives phasing).** `generate-docs.ts` runs at *build time in the marketplace repo*, so `plugins/` is right there (`scripts/generate-docs.ts:29`). `config`/`doctor` run at *user time in a target repo against installed plugins*, where `${CLAUDE_PLUGIN_ROOT}` points only at *this* plugin's install dir. Enumerating sibling installed plugins at runtime would require walking `dirname(CLAUDE_PLUGIN_ROOT)` (an installed-plugins root) — but this is **not merely unverified, it is confirmed unsupported by design**: Claude Code's Hooks documentation states plainly that *"Hooks cannot discover other installed plugins,"* and no env var, settings field, or API exposes a stable sibling/parent layout (`${CLAUDE_PLUGIN_ROOT}` resolves only to the plugin's own directory). A running command therefore can never see another plugin's files. This is the load-bearing fact of the whole cross-plugin story: because runtime discovery is impossible, the only place aggregation *can* happen is **at repo build time**, where `plugins/` is directly walkable. Phase 1 restricts the loader to the core plugin's own registry via the rock-solid `${CLAUDE_PLUGIN_ROOT}` (no cross-plugin need yet); Phase 2 adds a build-time generator that bakes the marketplace-wide aggregate into a committed file shipped *inside* the core plugin, so runtime still only ever reads files under its own root (see Implementation Phases and Risk Analysis).

### Registry descriptor schema (Decision 1)

Each entry in `CONFIG_FLAGS` is a `dataclass ConfigFlag`:

```python
@dataclass(frozen=True)
class ConfigFlag:
    key: str            # frontmatter key, e.g. "nudge_todowrite"
    kind: str           # "boolean" | "enum" | "list" | "identity"
    default: str        # effective value when unset (or "auto-detect" sentinel)
    description: str     # human-readable effect
    owner: str          # plugin-relative path of the script that READS it
    file: str           # "local" (agentic-engineering.local.md) | "committed" (agentic-engineering.md)
    choices: tuple[str, ...] = ()   # for kind=="enum"
    toggleable: bool = True          # False ⇒ inventory-only, never offered in config's flip UI
```

`kind="identity"` (implies `toggleable=False`, `file="committed"`) is the carve-out that lets `github_project_owner`/`github_project_number` be *inventoried* without ever appearing as a flip — the exact requirement the human called out. `config` never writes a `committed`/`identity` flag; those are managed by the board bootstrap and health-checked by doctor already.

### Registry CLI verbs (the shared engine)

- `config_registry.py --inventory` → `{"flags": [{key, kind, default, effective, set, source, valid, toggleable, file, owner, description, plugin}], "ok": true}`. Pure read. `effective` is the resolved value (explicit value if set, else `default`); `set` is whether an explicit value exists; `source` is `local`/`committed`/`default`; `valid` is `false` when an explicit value fails its kind/choices check (e.g. a stale `issue_tracker: linear`, exactly the case `read_local_config_tracker` already surfaces at `workflow-repo-preflight.py:196-204`).
- `config_registry.py --get <key>` → one flag's state.
- `config_registry.py --set <key> <value>` → validate against kind/choices; refuse `identity`/`committed` writes; for `local` flags run the tracked-file guard + `.gitignore`-ensure (reuse the setup Step 4.5 recipe / `_is_tracked`, `lifecycle_board.py:342-347`) then write via `upsert_frontmatter_keys` + `_atomic_write` (`lifecycle_board.py:262-339`). Emits `{ok, key, value, previous, file, path}` or the standard `{ok:false, error_code, error, fix}` contract (`lifecycle_board.py:129-138`).

`--set` is deterministic and non-interactive by design: the *command* owns consent (AskUserQuestion); the *script* just executes what it's told, exactly as `lifecycle_board.py`'s verbs do.

### Implementation Phases

#### Phase 1: Core-plugin registry + surfaces (prove the mechanism)

- Add `plugins/agentic-engineering/scripts/config_registry.py`:
  - `ConfigFlag` dataclass + core `CONFIG_FLAGS` (six entries, Decision 6).
  - A loader that, in Phase 1, loads **only** `${CLAUDE_PLUGIN_ROOT}/scripts/config_registry.py` (this plugin) — no sibling scan yet.
  - Config-file resolution reusing `lifecycle_board.repo_context()` (`lifecycle_board.py:229-240`) for `root`/`main_root`, `parse_frontmatter` for reads.
  - `verb_inventory`, `verb_get`, `verb_set`; a new `write_local_config_keys(root, keys)` helper (parallels `write_config_keys`, `lifecycle_board.py:327-339`, but targets `LOCAL_CONFIG` at `ctx.root` and runs the tracked/gitignore guard first).
  - `argparse` CLI mirroring `lifecycle_board.py:1559-1597`.
- Add `plugins/agentic-engineering/commands/config.md` (Decision 2).
- Extend `plugins/agentic-engineering/commands/lifecycle-doctor.md` with the Configuration section step (Decision 4).
- Refactor `skills/setup/SKILL.md` Steps 3.5 / 4 / 4.5 to delegate flag writes (Decision 3).
- Tests: `tests/config-registry.test.ts` (grep lint, Decision 5) + `plugins/agentic-engineering/tests/config_registry_test.py` (unit: inventory shape, enum/boolean/list validation, invalid-value flagged, tracked-guard refusal, byte-preservation via `upsert_frontmatter_keys`, identity-write refusal).
- Versioning + docs (Decision 7): command count 26→27 across `plugin.json`/`marketplace.json`/both READMEs/`docs/index.html`; `bun run docs:build`; CHANGELOG "Added" entry; bump 3.7.0→3.8.0 in both manifests.
- **Success criteria:** `/…:config` lists all six flags with correct current/default; flipping `nudge_todowrite` writes `.local.md` (never when tracked); doctor shows the Configuration section; `bun test` + the Python suite green.
- **Estimated effort:** ~1–2 sessions (one module, one command, one skill edit, two test files, the version/docs checklist).

#### Phase 2: Marketplace-wide discovery via build-time aggregation (NOT runtime discovery)

**Hard constraint that shapes this phase:** runtime cross-plugin discovery is *impossible*, not merely unverified — Claude Code's Hooks docs state *"Hooks cannot discover other installed plugins,"* and `${CLAUDE_PLUGIN_ROOT}` resolves only to the plugin's own directory (see "The runtime-root constraint" above). A running `config`/`doctor` can therefore never walk a sibling plugin's files. So Phase 2 does **not** generalize the *runtime* loader; it moves the every-plugin scan to **repo build time** (the only place `plugins/` is walkable) and ships the result to runtime as data.

- **Build-time generator** (the runtime analogue is impossible; this is the real analogue of `generate-docs.ts`): a generator walks every in-repo plugin's `scripts/config_registry.py` — `pluginDirs()`-style, core-first (`generate-docs.ts:39-45`) — and emits a **committed, generated** aggregate module shipped *inside* the core plugin, e.g. `plugins/agentic-engineering/scripts/config_registry_marketplace.generated.py`. Because it imports Python `CONFIG_FLAGS` lists, the generator is naturally a small Python script (or a `config_registry.py --build-aggregate` verb) invoked from the same build entrypoint as `docs:build`; it need not live in the TS generator. Non-core flags are namespaced by plugin in the emitted data (mirroring how `collectSkills` namespaces non-core skills, `generate-docs.ts:79-91`, and how `plugin-consistency.test.ts:173-204` treats non-core plugins uniformly).
- **Runtime stays root-local.** With the aggregate baked in, the core plugin's `--inventory` loads *only* two files, both under its own `${CLAUDE_PLUGIN_ROOT}`: its hand-written `config_registry.py` (core's live flags) and `config_registry_marketplace.generated.py` (the sibling flags, already resolved at commit time). **Zero** runtime cross-plugin filesystem access — the aggregation already happened at build time.
- **Staleness enforced the same way docs are.** The generated file is checked for drift by the existing `bun run docs:check` / `bun test` discipline that already guards `docs/pages/*.html` — extend the same build script and check command rather than inventing a separate mechanism (`plugin-consistency.test.ts` and `generate-docs.ts` are the model). A registry edit that isn't re-baked fails CI.
- **Consuming-surface caveat (important, and a real limit):** the aggregate is a *catalogue* of every flag declared across plugins **in this repo**, resolved at build time — it reflects what is committed, not what the user has installed. Since only the core plugin ships a `config`/`doctor` surface (`marketing` has **no** commands — verified: its only component is the `seo-audit` skill, `plugins/marketing/skills/seo-audit/`), cross-plugin flags are discoverable **only when the core plugin is installed**, and a flag whose owning plugin is *not* installed will still appear as read-only catalogue inventory (its reader script never runs, so flipping it is inert). This is acceptable because the core plugin is universally installed (`docs/dependency-policy.md:70-74`) and the surface is a discovery aid, but the plan must state it rather than imply per-install runtime accuracy.
- **Scope limit — state it plainly (this is the "sibling vs. 3rd-party" answer):** build-time aggregation can only ever include plugins committed to **this** git repo's `plugins/`. A genuinely third-party plugin from a *different* marketplace that a user happens to install alongside this one can **never** be aggregated — there is no shared build process, and (per the hard constraint) no runtime discovery either. "Sibling/3p plugins" resolves to two cases: **(a) other plugins within this marketplace** (`marketing`, future domain plugins) — solved by this build-time approach; **(b) truly foreign plugins from other marketplaces** — *unsolvable by design*, by Claude Code's own documented limitation. There is no future runtime generalization coming for (b); the plan does not promise one.
- **Deferred deliberately** (the ECC "maiden run" bulk-deferral pattern, `docs/plans/2026-07-02-feat-upstream-source-adoption-tracking-plan.md:133-138`): `marketing` ships zero config flags today, so Phase 2 has no consumer yet. Prove the mechanism against one plugin in Phase 1, then build the generator when a second **in-repo** plugin actually ships a flag.
- **Success criteria:** a second in-repo plugin with a `config_registry.py` surfaces in `config`/`doctor` (via the baked aggregate) with **no** edit to any hardcoded list, and `bun run docs:check` fails if the aggregate is stale.
- **Estimated effort:** ~1 session (a build-time generator + a staleness check), un-gated — no runtime-layout unknown remains, because runtime discovery is designed-out and this approach avoids it entirely.

#### Phase 3: Polish (optional, evidence-driven)

- `config --json` for scripting; a `config reset <key>` (remove the key, fall back to default); richer list-flag editing (multiselect for `review_agents` instead of "re-run /setup"). Deferred until asked for.

## Alternative Approaches Considered

1. **One mega-command / bolt onto doctor.** Rejected: a config browser must print everything regardless of state, which directly violates doctor's "silent unless something's wrong / never print on all-PASS" tenet (issue #68 grooming notes). Merging them would either corrupt doctor's health semantics or bury the browser. Kept as separate surfaces sharing only the `--inventory` read.

2. **Single *hand-maintained* central registry file** (a shared `scripts/config_registry.py` that every plugin edits to list its flags). Rejected: it re-introduces the exact hand-wiring `generate-docs.ts` deleted — every new plugin would have to edit a shared file, and plugins are independently distributable (dependency-policy invariants 5–6, `docs/dependency-policy.md:69-79`). A plugin should own its own flags the way it owns its own agents/commands/skills. **Note the distinction from Phase 2:** Phase 2's `config_registry_marketplace.generated.py` is *also* a central file, but a **generated** one — each plugin still owns its own declarations in its own `config_registry.py`, and the aggregate is derived (and drift-checked) mechanically, exactly as `docs/pages/*.html` are generated from per-plugin sources. Generated central aggregation is fine; hand-maintained central aggregation is what is rejected.

3. **A JSON/YAML data file per plugin** instead of a Python module. Rejected: the readers, the writer (`upsert_frontmatter_keys`), and the reverse-check are all Python; a data file adds a parser and severs the registry from the import graph that `nudge-todowrite-to-tracker.py:30-39` already uses to compose scripts. YAML would also need `js-yaml`/`PyYAML`, and the whole subsystem is deliberately stdlib-only (`lifecycle_board.py:19`).

4. **`config` as a skill** (like `setup`). Rejected: `setup` is a `disable-model-invocation` linear wizard with model-driven stack detection and branching (`skills/setup/SKILL.md:1-6`); `config` is a thin deterministic front-door over a JSON-emitting verb, structurally identical to `lifecycle-doctor` (a command). Matching doctor's form keeps the "report vs. act, both over one engine" symmetry legible.

5. **`config` as an agent.** Rejected: no autonomous multi-step reasoning is required; it is a render-then-prompt loop over a deterministic script. An agent would add nondeterminism to a task whose whole value is deterministic discoverability.

## System-Wide Impact

### Interaction Graph

`/…:config` invoked → command runs `config_registry.py --inventory` → loader resolves `repo_context()` (`lifecycle_board.py:229-240`) and reads `agentic-engineering.local.md` (+ committed `agentic-engineering.md` for identity rows) via `parse_frontmatter` → renders table → `AskUserQuestion` selects a toggleable flag → command runs `config_registry.py --set <key> <value>` → `verb_set` validates → for a `local` flag runs the tracked-file guard (`git ls-files --error-unmatch`, the same predicate as `_is_tracked`, `lifecycle_board.py:342-347`) and the `.gitignore`-ensure recipe (setup Step 4.5, `skills/setup/SKILL.md:423-497`) → `upsert_frontmatter_keys` (`lifecycle_board.py:262-314`) → `_atomic_write` (`:317-325`). Downstream, the *next* invocation of whichever hook/script owns the flag observes the new value — e.g. flipping `nudge_todowrite` changes the behavior of the PreToolUse hook `nudge-todowrite-to-tracker.py` on the next `TodoWrite` (`plugin.json` hooks → `nudge_opted_in`, `nudge-todowrite-to-tracker.py:63-85`); changing `issue_tracker` changes `resolve_issue_tracker` on the next `/workflows:*` preflight (`workflow-repo-preflight.py:207-238`). `doctor`'s new section is a pure read of the same `--inventory`, firing no writes.

### External System Wiring

**No external wiring required.** Config flags are local repo state read from `.local.md`/`.md`; `config` and the new registry make no network calls (unlike `lifecycle-doctor`, whose *board* checks need `gh`). The only external system anywhere near this feature is GitHub Projects, and only via the pre-existing identity keys, which `config` treats as read-only inventory and never writes. `config.md`'s `allowed-tools` therefore need no `gh` grant: `Read, Bash(python3 *), Bash(git *)` (git only for the tracked-file/gitignore guard).

### Error & Failure Propagation

The registry adopts `lifecycle_board.py`'s error contract verbatim (`:129-138`): every verb returns `{ok, ...}` or `{ok:false, error_code, error, fix}` and exits 1. Specific classes:
- **Invalid value on `--set`** → `error_code: invalid_value` with the allowed choices in `fix` (mirrors `verb_set_status`'s `STAGES` guard, `lifecycle_board.py:977-980`).
- **Attempt to `--set` an `identity`/`committed` flag** → `error_code: not_toggleable` — config refuses to touch board identity, keeping the owner-mismatch attack surface (`lifecycle_board.py:392-398`) entirely out of this path.
- **`.local.md` is tracked** → `--set` refuses with `error_code: local_config_tracked` and the untrack fix, the same invariant `read_board_config` (`:375-378`), `read_local_config_tracker` (`workflow-repo-preflight.py:180-186`), and `nudge_opted_in` (`nudge-todowrite-to-tracker.py:74-79`) all enforce. A tracked file is *ignored for reads and refused for writes*, never written through.
- **Malformed/absent config file** → inventory degrades to all-UNSET (defaults), never raises; matches the "unset degrades to default" posture of `read_binding_config` (`lifecycle_board.py:416-451`).
- **Symlinked `.gitignore`** → the setup recipe already refuses to write through it (`skills/setup/SKILL.md:435,451-453`); `verb_set` inherits that refusal and reports `gitignore=failed` in its result rather than following the link.

The doctor Configuration section is best-effort read-only: if `--inventory` fails, the section renders "configuration inventory unavailable" and does **not** flip doctor's overall `ready` verdict (config state is not board health).

### State Lifecycle Risks

Writes are single-key and atomic (`_atomic_write`, `lifecycle_board.py:317-325`: tmp + `os.replace`), so a crash mid-write can never truncate `.local.md`. `upsert_frontmatter_keys` preserves every other byte and updates *every* occurrence of a duplicated key (`:295-301`) so a `--set` is never a silent last-wins no-op. Ordering hazard: the `.gitignore`-ensure must run **before** the file write so a later `git add -A` cannot immediately re-track a freshly created `.local.md` — the setup recipe already sequences it this way (`skills/setup/SKILL.md:429-447`) and `verb_set` reuses that order. No multi-file transaction exists (config only ever writes one local file), so there is no partial-commit orphan risk.

### API Surface Parity

The registry is consumed by **three** surfaces that must agree on the same flag vocabulary: `config` (writes), `doctor` (reports), and `setup` (delegated writes). All three go through the one `config_registry.py` engine, so they cannot drift — the same "one writer, many callers" discipline `lifecycle_board.py` enforces for the board (`:5-11`). The lint test (Decision 5) is the fourth guard: it makes the *reader* population (every script that consumes a frontmatter key) parity-checked against the registry.

### Integration Test Scenarios

(Cross-layer; unit mocks would miss these.)

1. **Tracked-file refusal end to end.** Create a `.local.md`, `git add` it, run `config_registry.py --set nudge_todowrite true` as a subprocess in a temp git repo; assert exit 1, `error_code: local_config_tracked`, and that the file on disk is **unchanged** — proves the guard is enforced at the write boundary, not just advertised. (Mirrors the subprocess-driven rigor of `plan_tracker_guard_test.py`.)
2. **Byte-preservation with real frontmatter.** Seed a `.local.md` with `issue_tracker`, a `review_agents` list, and a hand-written "Review Context" body; `--set issue_tracker github`; assert only that line changed and the body is byte-identical (exercises `upsert_frontmatter_keys` against a realistic file, not a synthetic one).
3. **Doctor ↔ config agreement.** With a known `.local.md`, assert `lifecycle_board.py --doctor` rendering + `config_registry.py --inventory` report the same effective values for the same keys — the shared-read invariant.
4. **Invalid stale value surfaced, not crashed.** Seed `issue_tracker: linear`; assert `--inventory` reports that row `valid:false` and doctor's Configuration section WARNs (parity with `workflow-repo-preflight.py:196-204`), while `/workflows:*` resolution still falls back to auto-detect (no regression).
5. **Setup delegation writes identical bytes.** Run the refactored setup path and a direct `--set` for the same flag; assert both produce the same frontmatter, proving setup no longer has an independent serializer.

## Acceptance Criteria

### Functional Requirements

- [ ] `plugins/agentic-engineering/scripts/config_registry.py` exists, exports `ConfigFlag` + `CONFIG_FLAGS` with the six retrofit entries (Decision 6), and provides `--inventory`/`--get`/`--set` honoring the `{ok,...}`/`{ok:false,error_code,error,fix}` contract.
- [ ] `--inventory` reports per flag: `key, kind, default, effective, set, source, valid, toggleable, file, owner, description, plugin`.
- [ ] `/…:config` renders a plugin-grouped (core first) table and flips a toggleable flag via `AskUserQuestion`, writing through `--set`; non-interactive/pipeline mode prints the inventory and makes no writes.
- [ ] `--set` refuses `identity`/`committed` flags and refuses any write to a **tracked** `.local.md`; ensures the `.gitignore` entry before writing; writes via `upsert_frontmatter_keys` + `_atomic_write`.
- [ ] `lifecycle-doctor.md` gains a read-only **Configuration** section rendered from `--inventory` with SET/UNSET status (and WARN for `valid:false`), not altering the board `ready` verdict.
- [ ] `setup` writes `issue_tracker`/`review_agents`/`plan_review_agents`/`nudge_todowrite` through the shared local writer and points users at `/…:config`; setup no longer hand-templates those keys.
- [ ] The four existing toggles plus the two identity keys are all inventoried; identity keys are shown but never offered as flips.

### Non-Functional Requirements

- [ ] **Security:** the tracked-`.local.md` invariant is enforced on write (not just read); `config` never writes committed board identity; no self-referential in-file allowlist is introduced.
- [ ] **Performance:** `--inventory` and doctor's new section make **zero** network calls; runtime is bounded by reading two local files.
- [ ] **Determinism:** `--inventory`/`--get`/`--set` are pure functions of filesystem + args (stdlib-only, Python ≥ 3.9), unit-testable with an injected root — same seam discipline as `lifecycle_board.py:19`.
- [ ] **Accessibility:** table output uses the existing glyph/vocabulary conventions of `lifecycle-doctor.md:32` so the two sections read consistently.

### Quality Gates

- [ ] `tests/config-registry.test.ts` (grep lint) green and scanning a non-trivial surface (guard against a broken scanner finding nothing, like `flagless-gh.test.ts:116-119`).
- [ ] `plugins/agentic-engineering/tests/config_registry_test.py` covers: inventory shape, each `kind`'s validation, invalid-value flagging, tracked-guard refusal, identity-write refusal, byte-preservation, absent-file degradation.
- [ ] `bun test` (`plugin-consistency.test.ts`) green with the command count bumped everywhere it is enforced (`plugin.json`, `marketplace.json`, both READMEs, `docs/index.html`).
- [ ] `bun run docs:check` green (docs rebuilt for the new command card).
- [ ] Version bumped 3.7.0 → 3.8.0 in `plugin.json` **and** `marketplace.json`; CHANGELOG "Added" entry.

## Success Metrics

- **Discoverability:** a user can enumerate 100% of the opt-in flags (currently four toggles + two identity keys) from one command, with current-vs-default, without reading any Python. Today that number is 0%.
- **Invisibility prevented:** adding a seventh flag that a script reads but that is not registered **fails CI** via the lint test. The `nudge_todowrite`-style silent addition becomes impossible.
- **De-duplication:** `setup` has exactly one serializer for local-config flags (the shared writer); grep for hand-written `issue_tracker:`/`review_agents:` YAML templating in `SKILL.md` returns only the shared-writer call site.
- **Forward-compatibility:** in Phase 2, a second **in-repo** plugin's `config_registry.py` surfaces in `config`/`doctor` with zero edits to any hardcoded plugin list — the `generate-docs.ts` property, achieved via **build-time** aggregation baked into the core plugin (not a runtime scan, which Claude Code designs out). Truly foreign third-party plugins from other marketplaces are out of scope by that same design limit.

## Dependencies & Prerequisites

- **Reuses, does not re-implement:** `upsert_frontmatter_keys`, `_atomic_write`, `write_config_keys`, `parse_frontmatter`, `repo_context`, `_is_tracked`, the `{ok,...}` error contract (all in `lifecycle_board.py`); the `.gitignore`-ensure/tracked recipe (`skills/setup/SKILL.md:423-497`); the per-plugin scan pattern (`generate-docs.ts:39-45`); the grep-lint-with-allowlist pattern (`flagless-gh.test.ts`).
- **No new third-party dependencies** — stdlib Python + bun test, consistent with the subsystem's stdlib-only rule (`lifecycle_board.py:19`) and the core plugin's dependency-free mandate (`docs/dependency-policy.md:69-74`).
- **Prerequisite for Phase 2 only:** a second in-repo plugin that actually ships a config flag (there is none today — `marketing` has zero). Phase 2 needs **no** runtime-layout confirmation: runtime cross-plugin discovery is designed-out by Claude Code, so Phase 2 sidesteps it entirely with a build-time generator + `docs:check`-style staleness enforcement. Phase 1 has no cross-plugin dependency at all (`${CLAUDE_PLUGIN_ROOT}` is guaranteed).
- **Claude Code version:** none beyond what the plugin already targets; this adds a command + a script, no new host capabilities.

## Risk Analysis & Mitigation

- **⚠️ Runtime cross-plugin discovery is impossible by design (drives phasing).** This is *not* an open question — Claude Code's Hooks docs confirm *"Hooks cannot discover other installed plugins,"* and `${CLAUDE_PLUGIN_ROOT}` exposes only the plugin's own directory. `generate-docs.ts` can scan `plugins/` only because it runs at build time. **Mitigation:** Phase 1 loads only the core plugin's own registry (zero cross-plugin surface); Phase 2 achieves marketplace-wide discovery **without any runtime scan** — a build-time generator bakes the aggregate into a committed file inside the core plugin, and runtime reads only that root-local file. No install-layout assumption is ever made. The residual limitation (foreign plugins from other marketplaces can never be aggregated) is inherent and documented in Phase 2, not a risk to mitigate.
- **Command-name collision with the built-in `/config`.** Claude Code ships a built-in `/config`; the plugin CLAUDE.md notes the `workflows:` prefix exists precisely to dodge built-in collisions (`plugins/agentic-engineering/CLAUDE.md:47-53`). **Mitigation (Decision 2):** ship `name: config` but invoke plugin-qualified as `/agentic-engineering:config`, and say so in the command doc; if the qualified form proves awkward, fall back to a distinct top-level name like `/config-flags` (the `lifecycle-doctor` precedent of a descriptive, collision-free name).
- **Lint test false positives/negatives** (detailed in Decision 5). **Mitigation:** curated accessor-pattern set + key ALLOWLIST with a stale-entry check, plus a reverse check (every registered flag's `owner` script exists and contains the key literal). Residual false-negative (a bespoke reader avoiding both idioms) is documented and bounded — the one existing bespoke reader, `read_local_config_tracker`, contains the literal `issue_tracker` and is caught by the reverse/key-literal check.
- **Writing to a shared/tracked `.local.md`.** Enforced-on-write refusal (above) closes the PR-carries-config hole; identity keys are never writable via `config`.
- **Version/count drift.** A new command touches five count sites; `plugin-consistency.test.ts:76-109` fails loudly if any is missed — that is the safety net, not a risk if the checklist (Decision 7) is followed.

### Deferred (out of scope, noted for follow-up)

- Phase 2 sibling-plugin discovery (build-time aggregation; gated only on a second in-repo plugin actually shipping a flag, not on any runtime-layout question — runtime discovery is designed-out and avoided entirely).
- `config --json`, `config reset <key>`, rich multiselect editing of list flags.
- Folding the Configuration section into a future `/doctor --subsystem config` if #71 lands (this plan ships it as a self-contained producer that #71 can absorb).

## Resource Requirements

Single engineer, ~2–3 focused sessions total (Phase 1 ~1–2, Phase 2 ~1 once a second in-repo plugin needs it). No infrastructure, no secrets, no external accounts. Reviewers: one code review (the write-path security invariant is the load-bearing bit worth a careful read). No design open question remains: the former "runtime plugins-root" unknown is resolved — runtime cross-plugin discovery is impossible by Claude Code's design, and Phase 2 avoids it via build-time aggregation. The only decision left for the human is confirming which sense of "sibling/3p plugins" was intended (see Phase 2's scope-limit bullet); if truly foreign plugins from other marketplaces were meant, that is unachievable by design and should be dropped from the goal.

## Future Considerations

- **`generate-docs.ts` could render a "Config Flags" reference page** from the registry, giving the docs site a marketplace-wide flag catalogue with zero hand-maintenance — the registry is already the single source, and `generate-docs.ts` already owns the "scan plugins, render cards" machinery.
- **`#71` alignment:** when `lifecycle-doctor` generalizes to `/doctor --subsystem X`, the `config_registry.py --inventory` producer is already the right shape to be one such subsystem.
- **Per-flag validation hooks:** a future `ConfigFlag.validate` callable could let a flag reject values with domain logic (e.g. `review_agents` names that don't exist as agents), reusing the agent-file enumeration `plugin-consistency.test.ts` already does.
- **Marketing / domain plugins:** once a domain plugin ships its first flag, Phase 2's build-time aggregation makes it visible after the next `docs:build`-style rebuild — no per-plugin runtime wiring, matching how `collectSkills` (`generate-docs.ts:79-91`) already treats non-core skills. Since domain plugins like `marketing` ship no `config`/`doctor` surface of their own, their flags surface through the **core** plugin's baked aggregate, and only when the core plugin is installed.

## Documentation Plan

- `plugins/agentic-engineering/commands/config.md` — the command itself (user-facing).
- `plugins/agentic-engineering/README.md` — add `/config` to the commands table/list and bump the `| Commands | 27 |` row (enforced by `plugin-consistency.test.ts:90-95`).
- Root `README.md` — bump `| Commands | 27 |` (`plugin-consistency.test.ts:97-102`).
- `plugins/agentic-engineering/CHANGELOG.md` — "Added" entry (style: the 3.2.0 `link_repo`/backfill bullet in `docs/plans/2026-07-06-...-plan.md:122`); `docs/pages/changelog.html` regenerates via `bun run docs:build` (never hand-edited, per `CLAUDE.md:253`).
- `docs/index.html` + `docs/pages/commands.html` — regenerated by `bun run docs:build` (the new command card + landing stat).
- `plugins/agentic-engineering/CLAUDE.md` — a short "Config flags" note: new flags go in `scripts/config_registry.py`, and the lint test enforces it. This is the "Codify" step of the compounding loop (`CLAUDE.md:37-46`).
- `skills/setup/SKILL.md` — updated Steps 3.5/4/4.5 delegation + a pointer to `/…:config`.

## Sources & References

### Origin

- **Origin issue:** [#91](https://github.com/aagnone3/agentic-engineering/issues/91) — discoverable config surface across the marketplace.

### Internal References — the flags being unified

- `plugins/agentic-engineering/scripts/workflow-repo-preflight.py:160-238` — `read_local_config_tracker` / `resolve_issue_tracker` (`issue_tracker`).
- `plugins/agentic-engineering/scripts/plan-tracker-guard.py:135-137` — `issue_tracker: none` carve-out.
- `plugins/agentic-engineering/scripts/nudge-todowrite-to-tracker.py:63-85` — `nudge_todowrite` (PR #90, the freshest invisible-flag example).
- `plugins/agentic-engineering/skills/setup/SKILL.md:126-141,403-421,423-497` — `review_agents`/`plan_review_agents` writers + the tracked-file/gitignore recipe.
- `plugins/agentic-engineering/scripts/lifecycle_board.py:358-400` — `read_board_config` (`github_project_owner`/`github_project_number`, identity, security invariant).

### Internal References — reused mechanisms

- `plugins/agentic-engineering/scripts/lifecycle_board.py:246-259` (`parse_frontmatter`), `:262-314` (`upsert_frontmatter_keys`), `:317-339` (`_atomic_write`/`write_config_keys`), `:342-347` (`_is_tracked`), `:129-138` (error contract), `:229-240` (`repo_context`), `:1442-1552` (`verb_doctor`, the health-check vocabulary to sit beside), `:1385-1429` (`evaluate_forward_binding_check`, precedent for WARN-on-unrecognized), `:1559-1597` (argparse CLI shape).
- `plugins/agentic-engineering/scripts/nudge-todowrite-to-tracker.py:30-39` — cross-script `importlib` composition idiom the loader reuses.
- `scripts/generate-docs.ts:39-45` (`pluginDirs`, the per-plugin-scan precedent), `:79-102` (`collectSkills`/`collectMcp`, uniform per-plugin collection, non-core namespacing).
- `commands/lifecycle-doctor.md:14-44` — the command shape `config` mirrors and the section this plan extends.

### Internal References — test prior art

- `tests/flagless-gh.test.ts` — the grep-scan-with-allowlist + stale-entry-check pattern the lint test mirrors.
- `tests/plugin-consistency.test.ts:76-109,173-204` — the enforced count sites and non-core-plugin uniform checks.
- `plugins/agentic-engineering/tests/plan_tracker_guard_test.py:1-40` — the subprocess-driven, schema-shaped hook-test rigor bar for the Python unit tests.
- `docs/plans/2026-07-06-feat-explicit-repo-board-binding-decision-plan.md` — house style for the numbered-decisions table and the `upsert_frontmatter_keys`/`--doctor` integration this builds on.
- `docs/plans/2026-07-02-feat-upstream-source-adoption-tracking-plan.md:133-138,196-198` — the "maiden run / bulk-defer, prove-then-generalize" phasing pattern adopted here.

### Related Work

- **Related (distinct):** [#71](https://github.com/aagnone3/agentic-engineering/issues/71) — generalize `lifecycle-doctor` into `/doctor --subsystem X` (health composability; forward-compatible, not a dependency).
- **Design tenet:** issue #68 grooming notes — "silent unless something's wrong / never print on all-PASS" (the reason `config` is a separate surface).
- **Policy:** `docs/dependency-policy.md:69-79` — core plugin stays dependency-free; plugins own their own surface.

---

## Appendix: Decisions Table (the open questions this plan closes)

| # | Question | Decision | Grounding |
|---|----------|----------|-----------|
| 1 | Registry data shape + per-plugin vs central location | `ConfigFlag{key, kind, default, description, owner, file, choices, toggleable}` in a per-plugin `scripts/config_registry.py`; discovered core-first by directory convention | Mirrors `generate-docs.ts:39-45`; plugins own their surface (`dependency-policy.md:69-79`); stdlib-only like `lifecycle_board.py:19` |
| 2 | `config` = command / skill / agent | **Command** (`commands/config.md`), plugin-qualified invocation `/agentic-engineering:config` to dodge built-in `/config`; interactive via `AskUserQuestion`, read-only in pipeline mode | Structurally identical to `lifecycle-doctor` (a command); `setup` is a wizard skill; collision note per `CLAUDE.md:47-53` |
| 3 | `config` ↔ `setup` relationship | Build `config`+registry **first**, then refactor `setup` to **delegate** flag serialization to the shared writer and point users at `/…:config`; independent-with-duplication explicitly rejected | Compounding "don't duplicate" (`CLAUDE.md:37-46`); today's hand-templated `SKILL.md:403-421` |
| 4 | Doctor Configuration section format | New **SET/UNSET** informational vocabulary (distinct from PASS/WARN/FAIL/SKIP), with **WARN** only for `valid:false`; does not change `ready` | Health vs. inventory are different judgments (#68 tenet); WARN-on-invalid parity with `workflow-repo-preflight.py:196-204` and `evaluate_forward_binding_check` |
| 5 | The lint test | `tests/config-registry.test.ts`: forward grep (accessor idioms + key ALLOWLIST w/ stale-entry check) that every read frontmatter key is registered, **plus** reverse check that each flag's `owner` exists and contains the key literal; documented residual FN | Mirrors `flagless-gh.test.ts`; reverse check catches the one bespoke reader (`read_local_config_tracker`) |
| 6 | Retrofit the four existing flags | Declare `issue_tracker`(enum), `review_agents`/`plan_review_agents`(list), `nudge_todowrite`(bool) + `github_project_owner`/`_number`(identity, inventory-only) in the core registry; no reader behavior change | The four toggles + two identity keys enumerated above |
| 7 | Version / counted-component call | **MINOR 3.7.0→3.8.0** (new command); command count 26→27 across all enforced sites; config flags are **NOT** a counted component type (the registry+lint are their consistency mechanism), matching hooks-not-counted precedent | `plugin CLAUDE.md:12-15`; `plugin-consistency.test.ts` counts agents/commands/skills/mcp only |
| 8 | Phasing + cross-plugin mechanism | **Yes**, maiden-run deferral: Phase 1 core-plugin-only (proves mechanism vs. guaranteed `${CLAUDE_PLUGIN_ROOT}`). Phase 2 marketplace-wide discovery is done by **build-time aggregation** — a generator bakes every in-repo plugin's flags into a committed `config_registry_marketplace.generated.py` inside the core plugin, drift-checked by `docs:check` — **not** a runtime sibling scan, which Claude Code designs out (*"Hooks cannot discover other installed plugins"*). Deferred only until a second in-repo plugin ships a flag. Foreign plugins from other marketplaces are permanently out of scope | Runtime discovery confirmed impossible (Claude Code Hooks docs); build-time precedent = `generate-docs.ts` + `docs:check`; ECC deferral pattern (`2026-07-02-...-plan.md:133-138`); `marketing` has zero flags and no command surface today |
