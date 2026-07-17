---
title: "Three gh/git boundary gotchas when authoring a land-* skill: head: is exact-match, origin/HEAD is unset in worktrees, and allowed-tools matches the pipeline's first token"
category: integration-issues
tags: [skills, gh-cli, git, idempotency, worktree, allowed-tools, permissions, unattended, land-docs, bash-recipes]
module: skills
symptom: "A new land-* skill was written by faithfully mirroring land-docs, passed bun test and typecheck, and read clean — yet three of its adapted gh/git snippets would misbehave at runtime: the idempotency check re-branches on every re-run, default-branch resolution silently empties in a fresh worktree, and the scope-check pipeline stalls an unattended run on a permission prompt."
root_cause: "The bugs live in the deltas from the mirrored skill, not the mirrored parts: GitHub's `head:` search qualifier matches a ref exactly (never as a prefix) so it misses timestamp-suffixed branches; `git rev-parse --abbrev-ref origin/HEAD` depends on a local symbolic ref that is unset in fresh clones/CI/worktrees; and a skill's `allowed-tools` allow-list matches a bash pipeline by its first token, so a pipeline that leads with `comm`/`sed` rather than `git`/`gh` is not covered and prompts for permission."
---

# Three gh/git boundary gotchas when authoring a `land-*` skill

From PR [#173](https://github.com/Life-With-Data/agentic-engineering/pull/173) (issue #147): creating
the [`land-plan-docs`](../../../plugins/agentic-engineering/skills/land-plan-docs/SKILL.md) skill by
adapting [`land-docs`](../../../plugins/agentic-engineering/skills/land-docs/SKILL.md). The skill was a
faithful mirror of a proven sibling, passed `bun test` / `bun run typecheck`, and read clean — but the
independent review found three runtime bugs, **all in the parts that were *changed* rather than
copied.** Each is a git/gh boundary assumption that a green test suite cannot catch because the snippets
are prompt guidance, not executed code. Companion doc: [[skills-mutating-user-repos-git-gotchas]].

The meta-lesson: **when you adapt a working skill, the review budget belongs on the deltas.** The copied
scaffolding is already battle-tested; the new behaviors (here: batching, idempotency, worktree-origin)
are where the boundary semantics bite.

## 1. GitHub's `head:` search qualifier is exact-match, not a prefix

**Trap.** The idempotency no-op ("has this join key already been landed?") was written as:

```bash
gh pr list --repo "$ORIGIN" --state all --search "head:plan-docs/${PRIMARY}" --json number --jq '.[0]'
```

with a comment claiming it matched "the recognizable branch-name **prefix**." But the branches the skill
actually creates carry a uniqueness suffix — `plan-docs/${PRIMARY}-$(date +%s)`. GitHub's `head:` search
qualifier matches the head **ref name exactly**; `head:plan-docs/147` never equals
`plan-docs/147-1699999999`. So the query always returns `[]`, the `!= "null"` guard passes, and the skill
**re-branches and opens a duplicate PR on every re-run** — the precise failure the idempotency check
exists to prevent.

**Fix.** Don't lean on `head:` for prefix intent. Pull the candidate PRs and filter client-side on the
prefix:

```bash
EXISTING=$(gh pr list --repo "$ORIGIN" --state all \
  --json number,url,state,headRefName \
  --jq '[.[] | select(.headRefName | startswith("plan-docs/'"${PRIMARY}"'-"))][0]')
```

(Or drive idempotency off a label instead of the branch name.) The null-handling was already correct;
the *predicate* was wrong.

## 2. `origin/HEAD` is frequently unset — resolve the default branch via `gh`, not `git rev-parse`

**Trap.** Default-branch resolution was copied verbatim from the sibling:

```bash
BASE=$(git rev-parse --abbrev-ref origin/HEAD | sed 's@^origin/@@')
```

`refs/remotes/origin/HEAD` is a *local* symbolic ref that only exists if it was set at clone time. It is
routinely absent in fresh clones, CI checkouts, and — critically — **freshly-created git worktrees.**
When unset, `git rev-parse` fails to stdout, the substitution captures an empty string, and `BASE=""`
propagates silently until `git checkout ""` or `gh pr create --base ""` fails late, after the tree has
already been mutated. This matters far more for `land-plan-docs` than for `land-docs`, because its whole
motivation is the multi-worktree case ("grooming in one worktree and implementing in another").

**Fix.** Resolve the default branch from the API, which does not depend on a local symbolic ref:

```bash
BASE=$(gh repo view --repo "$ORIGIN" --json defaultBranchRef --jq '.defaultBranchRef.name')
```

(`git remote set-head origin -a` also repairs the local ref, but the API call is one line and has no
local-state precondition.) A copied idiom is only as portable as its *most degenerate* target
environment — here, the fresh worktree the feature exists to serve.

## 3. A skill's `allowed-tools` allow-list matches a bash pipeline by its FIRST token

**Trap.** The scope check was written to lead with `comm` against two process substitutions:

```bash
comm -23 <(git status --porcelain -- 'docs/plans/**' | sed 's/^...//' | sort -u) \
         <(printf '%s\n' "${RUN_DOCS[@]}" | sort -u) | grep .
```

The skill's frontmatter declares `allowed-tools: Bash(gh *), Bash(git *), Read` — an allow-list the
acceptance criteria require to stay exactly that. Claude Code matches a `Bash(...)` permission rule
against the **first token of the command**. A pipeline whose first token is `comm` (not `git`/`gh`) is
not covered, so an unattended run **stalls on a permission prompt** — a hidden human-only step that
defeats the "arms auto-merge and lands unattended" contract the scope check is supposed to license.

**Fix.** Restructure the pipeline to **lead with an allow-listed command**, the same way `land-docs`
leads its scope check with `git diff ... | grep`:

```bash
git status --porcelain -- 'docs/plans/**' | sed 's/^...//' \
  | grep -vFxf <(printf '%s\n' "${RUN_DOCS[@]}") | grep .
```

Now the first token is `git`, `Bash(git *)` covers it, and the allow-list stays untouched. Note the
inverse also holds: a `$(date +%s)` or `$(...)` **inside** a `git`/`gh` command is fine — it expands as
an argument of the already-allowed outer command; only a *standalone leading* non-allowlisted command
trips the gate.

**Lesson.** When a skill is meant to run unattended, every bash recipe must be executable under its own
declared `allowed-tools` — the allow-list is part of the behavior, not just metadata. Widening the
allow-list is the wrong fix when the criteria pin it; restructure the command instead.

## Prevention

- **Budget review on the deltas.** For a skill authored by mirroring another, diff against the sibling
  and scrutinize exactly what changed — the copied parts are already proven.
- **Read gh/git snippets as if hostile.** For each, ask: does this qualifier mean what the comment
  claims (`head:` = exact, not prefix)? Does this local ref always exist (`origin/HEAD` — no)? Would
  this command pass the skill's own `allowed-tools`?
- **These are prompt files, so tests won't catch them.** `bun test` validates counts and frontmatter,
  not runtime behavior of illustrative bash. The independent multi-agent review (integration-boundary +
  agent-native reviewers) is the gate that does — keep it non-skippable for skill changes too.

## Resources

- PR [#173](https://github.com/Life-With-Data/agentic-engineering/pull/173) · issue #147
- Sibling skills: [`land-docs`](../../../plugins/agentic-engineering/skills/land-docs/SKILL.md),
  [`land-pr`](../../../plugins/agentic-engineering/skills/land-pr/SKILL.md)
- Companion learnings: [[skills-mutating-user-repos-git-gotchas]]
