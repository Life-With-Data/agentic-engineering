---
title: "Skills that mutate a user's repo: six git-boundary gotchas (check-ignore --no-index, symlink write-through, cross-process state, whole-unit references, verbatim-extraction tests, core.hooksPath redirection)"
category: integration-issues
tags: [skills, gitignore, check-ignore, symlink, security, idempotency, live-verification, bash-recipes, user-repo, git-hooks, core-hookspath]
module: setup
symptom: "A skill's bash recipe must idempotently edit .gitignore, detect a tracked file, or install a git hook in an arbitrary USER repo — what breaks that research, mocks, and a green review won't catch?"
root_cause: "git's ignore/index/hook semantics diverge from intuition (tracked files are never 'ignored'; symlinked .gitignore is read-refused but write-followed; core.hooksPath replaces rather than extends the hook search path), and skill recipes execute cross-process in hostile, unknown repos — assumptions valid in this repo's happy path fail exactly on the legacy/adversarial population the fix targets"
---

# Six Git-Boundary Gotchas for Skills That Mutate a User's Repo

Lessons 1–5 come from PR [#72](https://github.com/aagnone3/agentic-engineering/pull/72) (issue #62, v3.5.3): teaching the `setup` skill to gitignore `agentic-engineering.local.md` on write and detect/untrack an already-committed copy. A ~20-line bash recipe in a SKILL.md produced five durable lessons — one found only by live execution after **four research passes missed it and one asserted its opposite**. Fills the gap flagged at plan time: no prior solution doc covered skills performing git operations in the *user's* repo (vs. this repo).

Lesson 6 was added later, from the graphify integration — a different feature, the same family of trap, and caught the same way (a live probe, not research). Companion docs: [[idempotent-backfill-and-recorded-config-design]], [[recorded-fixtures-must-be-load-bearing]].

## 1. `git check-ignore` NEVER reports a tracked file as ignored — `--no-index` is load-bearing

**Trap.** The idempotence gate "is this file already ignored?" was implemented as `git check-ignore -q <file>`. Correct-sounding, endorsed by spec-flow analysis ("authoritative and unaffected by tracking status" — **false**), and it passes every fresh-repo test. But tracked files aren't subject to exclude rules, so plain `check-ignore` exits 1 for a tracked file *even when a matching pattern exists*. Against a legacy tracked copy — **the exact population the fix targets** — the gate fails on every re-run and appends a duplicate entry each time.

**Fix.** `git check-ignore -q --no-index` evaluates the exclude rules purely, ignoring the index. Prefer it over exact-line grep too (grep misses broader patterns like `*.local.md`, other ignore sources, and is defeated by negations).

**Lesson.** The failure was invisible to research (3 agents + spec-flow) and visible to a 30-second live run. For anything touching git edge semantics, execute the actual command against the actual state — including the *degenerate* state (here: file already tracked) — before shipping. See lesson 5 for the harness shape that caught it.

## 2. git refuses to READ a symlinked `.gitignore`, but shell `>>` happily WRITES through it

**Trap.** git ≥ ~2.32 opens in-worktree `.gitignore` with `O_NOFOLLOW` — a symlinked `.gitignore` is never read, so the check-ignore gate permanently reports "not ignored." Meanwhile `printf ... >> "$ROOT/.gitignore"` follows the symlink. Combined: a hostile repo committing `.gitignore -> ~/.zshrc` redirects the skill's one *autonomous* (non-consent-gated) mutation to a file **outside the repo tree**, unprompted; benign dotfile-manager users accumulate one duplicate line per setup re-run. Live-verified both ways by two independent reviewers.

**Fix.** `[ -L "$ROOT/.gitignore" ]` → refuse the append, report `gitignore=failed`, let the rest of the skill proceed. Re-verify after a performed append so "added" is never claimed when the write didn't take effect (also catches read-only `.gitignore`).

**Lesson.** A skill runs in repos it doesn't control, cloned from people the user doesn't know. Treat every autonomous filesystem mutation as attacker-reachable: guard symlinks before writing, and never claim success you didn't re-observe. Consent-gated actions get their guard "for free" (a human sees the ask); autonomous ones don't.

## 3. Skill bash recipes are cross-process — state the next instruction needs must be echoed, not stored

**Trap.** The recipe computed `TRACKED=1` and later instructions said "If `TRACKED=1`, warn and offer…" — but the shell variable dies when the Bash tool call exits, and every branch of the recipe was silent (`-q` flags, `>/dev/null`). The executing agent sees empty output + exit 0 and reads it as "nothing to do": the consent gate never fires, and the confirmation step's status lines get fabricated. The feature fails silently in exactly its target scenario.

**Fix.** End the recipe with one machine-readable line — `echo "root=… gitignore=… tracked=…"` — and key every downstream instruction ("if the status line reports `tracked=1`…", Step 5's display values) off that observable output. Corollary: a later instruction must not reference `"$ROOT"` either; it reads the `root=` field.

**Lesson.** In agent-executed docs, each fenced block is a separate process. Any recipe whose downstream prose consumes its state must self-report on stdout; silent-success recipes are only acceptable when nothing later depends on what happened.

## 4. Reference whole idempotent units, not halves of them

**Trap.** Step 1 (existing-config path) pulled forward *only* the tracked-check + untrack offer from Step 4.5 — not the gitignore-ensure — while Step 4.5's own comment declared the ordering invariant "ignore entry always BEFORE any untrack offer." On the View/Cancel branches (which exit before Step 4.5), an accepted untrack left the file unignored; the next `git add -A` re-tracked it, resurrecting the bug the user was just told was fixed. Three review agents independently converged on this.

**Fix.** Step 1 runs the full Step 4.5 block (safe because the whole unit is idempotent: the append no-ops via check-ignore) plus one no-re-ask clause for the Reconfigure path.

**Lesson.** When one instruction references another step, reference the whole idempotent unit. A partial import silently drops the invariants the unit maintains internally — and idempotence is what makes whole-unit reuse free.

## 5. Test the doc, not a transcription: verbatim-extraction harnesses

**Pattern that caught lesson 1.** The verification harness never hand-copied the recipe; it extracted it from the shipped SKILL.md by anchor and executed it in scratch repos:

```bash
awk '/^## Step 4\.5/{s=1} s && /^```bash$/{b=1; next} b && /^```$/{exit} b{print}' "$SKILL" > recipe.sh
```

Scenarios that mattered: fresh repo *run from a subdirectory* (root-anchoring), legacy tracked copy (warning before/after untrack, staged deletion, `git add -A` re-track blocked, **re-run while still tracked** — the case that exposed `--no-index`), broader `*.local.md` pattern, `.gitignore` without trailing newline, non-git dir, symlinked `.gitignore` (no write-through, no duplicates).

**Lesson.** For executable documentation, extraction-by-anchor makes the doc itself the tested artifact — a transcribed copy can drift and silently test nothing (the [[recorded-fixtures-must-be-load-bearing]] trap in another costume). One-shot harnesses rot, so the follow-up commits it as a bun test with the same verbatim extraction (todos/004; spawned task).

## 6. `core.hooksPath` REPLACES the hook search path — an installed git hook can be a silent no-op

**Trap.** Offering "install a git hook" (here: graphify's `graphify hook install`, which writes a `post-commit` that rebuilds the knowledge graph) assumes hooks live in `.git/hooks`. `core.hooksPath` breaks that assumption: it does not *add* a search location, it *replaces* it. Any tool that sets it — beads, husky, lefthook, pre-commit — silently redirects git's entire hook lookup away from `.git/hooks`, so a hook installed there never fires. No error, no warning; the install reports success.

The live probe found the degenerate case, which is worse than a conflict. In this repo:

```
core.hooksPath = <repo>/.beads/hooks   (set in .git/config, local scope)
.beads/hooks   → DOES NOT EXIST
```

Beads had pointed the lookup at a directory that wasn't there, so **no git hook fired in the repo at all**, from any tool. A graph-rebuild hook installed into that repo would have reported success and then quietly never run — leaving the graph permanently stale with zero signal. Note the scope trap too: `core.hooksPath` lives in `.git/config`, which is **shared across worktrees**, so a per-clone setting silently governs every worktree of it.

**Fix.** Preflight before offering any git-hook install: read `git config --get core.hooksPath`, and treat "unset" as the only trivially safe state. When it *is* set, the offer is only sound if the target directory exists **and** the installing tool writes *there* rather than to `.git/hooks` — two facts most tools don't document. If that can't be proven, don't offer the hook. The `setup` skill therefore offers graphify's CLI but **not** its hook, and the refresh runs as an explicit step inside `/workflows-compound` instead.

**Lesson.** Two, and the second is the general one. First: same shape as lesson 1 — a 10-second `git config --get` against the real repo beat any amount of reasoning about what "install a hook" does. Second, and reusable beyond git: **prefer an explicit in-loop step over a hook whenever the failure mode is invisible.** A hook that doesn't fire and a hook that isn't needed look identical from the outside. For anything maintaining a derived artifact (a graph, an index, a cache), staleness is silent by construction — so put the refresh somewhere its absence is observable, and reserve hooks for work whose omission announces itself.

## Cross-references

- Fix: PR [#72](https://github.com/aagnone3/agentic-engineering/pull/72) (issue #62, v3.5.3) — plan at `docs/plans/2026-07-07-fix-setup-gitignore-local-config-plan.md`
- Lesson 6: the graphify integration — `graphify_refresh` flag (`scripts/config_registry.py`), the install offer (`skills/setup/SKILL.md` Step 3.10), and the refresh step (`skills/workflows-compound/SKILL.md` Phase 2 step 8). That step also gates on `graphify-out/` being gitignored: a refresh rewrites non-doc artifacts, and [`land-docs`](../../../plugins/agentic-engineering/skills/land-docs/SKILL.md) scope-checks the **working tree**, so a tracked `graphify-out/` would escalate every autonomous compound run.
- Review-spawned siblings, merged same day: #73 (worktree-manager adopts the canonical idiom — its grep gate + bare `echo >>` had lesson-1 and newline bugs latent), #75 (preflight now ignores a tracked `.local.md` tracker override, closing the runtime-parity hole)
- Runtime invariant this protects: `plugins/agentic-engineering/scripts/lifecycle_board.py` `read_board_config` (tracked `.local.md` ignored — a PR must not carry board identity)
