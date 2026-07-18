---
name: land-docs
description: Ship compounded knowledge (docs-only markdown) as its own pull request, submitted with auto-merge enabled so it lands on green unattended. Use after a code PR has merged and the compound step has written docs/solutions or other markdown — this opens the "data PR", arms GitHub auto-merge, follows its checks, and lets it merge when green without another user turn. Triggers on "land the docs PR", "ship the compound knowledge", "open a data PR for these docs".
argument-hint: "[optional: issue number the knowledge came from — e.g. 92]"
allowed-tools: Bash(gh *), Bash(git *), Read
---

# Land a docs-only knowledge PR

Take the markdown a compound step just wrote — `docs/solutions/**`, patterns, CLAUDE.md
learnings, a memory pointer — and ship it as its **own** pull request, then drive that PR to
merge without a human turn. This is the autonomous "data lane": it exists so a session can close
out cleanly after the code PR merges, instead of leaving compounded knowledge uncommitted on the
working tree and turning back to ask the user what to do.

It is the counterpart to [`land-pr`](../land-pr/SKILL.md): `land-pr` lands the **code** PR (full
independent review gate); `land-docs` lands the **knowledge** PR (no in-agent review gate — the
repo's GitHub Actions own review; this skill only follows the checks). `land-pr` references this
skill for its docs tail.

## The one safety property: docs-only

This skill merges unattended, so it is allowed to run **only on a diff that is 100% documentation**.
Before opening the PR — and again before merging — verify every changed path matches the
docs allowlist:

- `*.md` anywhere,
- `docs/**` (any extension — the docs site is data, not code),
- memory-pointer files the compound step touches.

Explicitly **not** docs: anything under `plugins/**/scripts/`, `tests/**`, `*.ts`/`*.js`/`*.py`,
`*.json` manifests (`plugin.json`, `marketplace.json`), `.claude/**` config, hooks. If **any**
changed path falls outside the allowlist, this skill **stops and hands back to the user** — a
stray non-doc change must never auto-merge. This scope check is what licenses the no-human merge.

```bash
# Every changed path must match the allowlist, or STOP.
git diff --name-only "$BASE"...HEAD | grep -vE '(\.md$|^docs/)' && \
  echo "NON-DOC CHANGES PRESENT — do not auto-merge; escalate to user" || \
  echo "docs-only ✓"
```

## Auto-merge is armed at creation, not merged by hand

**The knowledge PR is always submitted with GitHub-native auto-merge enabled** (`gh pr merge --auto
--squash --delete-branch`), armed in the same step that opens it. This is a hard rule for the data
lane: the merge is pre-committed the moment the PR is created, so the docs land the instant CI goes
green **even if this session has already ended**. The skill never blocks on a manual merge and never
depends on staying alive to watch the checks.

The docs-only scope check (below) is the gate that licenses arming auto-merge unattended — it must
pass *before* the PR is opened.

## Reacting to checks (the whole decision tree)

The repo's GitHub Actions are the reviewer. This skill does **not** run its own multi-agent review,
style pass, or findings triage — it submits the PR with auto-merge armed and follows the checks:

| Check outcome | Action |
|---------------|--------|
| **All required checks pass** | GitHub auto-merges (squash, delete branch) on its own — nothing to do but confirm. No user turn. |
| **A check fails and the fix is simple** | Fix it (a broken relative link, a frontmatter typo, a failed docs build, a count that needs regenerating), push, re-check. Auto-merge stays armed and re-evaluates on the new commit. Bounded to ~2 attempts that make measurable progress. |
| **A check fails and the fix warrants user input** | Pause and ask. Auto-merge stays armed but harmless (GitHub won't merge a red PR). Ambiguous content, a schema/enum choice, a failure you can't resolve in ~2 attempts, or anything that would change *what the knowledge says* → surface it in one message and wait. Don't guess on content. |

"Simple" = mechanical and self-evident from the failure log (link/anchor fix, whitespace, rebuild
a generated artifact). "Warrants input" = a judgment about the knowledge itself.

## Workflow

### 1. Resolve context

```bash
ORIGIN=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')   # owner/repo of origin
BASE=$(gh repo view --repo "$ORIGIN" --json defaultBranchRef --jq '.defaultBranchRef.name')  # default branch — via the API; local origin/HEAD is often unset in a fresh worktree
N="${1:-}"                                                           # source issue number, if any

# true (linked worktree) when the per-worktree git-dir differs from the shared common-dir.
# Absolute path-format avoids relative-vs-absolute false matches across git versions.
is_linked_worktree() {
  [ "$(git rev-parse --path-format=absolute --git-common-dir)" \
    != "$(git rev-parse --path-format=absolute --git-dir)" ]
}
```

Every `gh` write carries an explicit `--repo "$ORIGIN"` (fork-trap guardrail).

### 2. Confirm there is docs-only work to ship

```bash
git status --porcelain
```

If the working tree is clean, there is nothing to land — report and stop. Otherwise run the
**docs-only scope check** above against the uncommitted changes (`git diff --name-only` /
`git status --porcelain`). If any non-doc path appears, **stop and escalate** — do not branch,
commit, or merge.

### 3. Branch from a synced default

The compound step wrote into the working tree of the (post-merge) default branch. Move that work
onto its own branch so the default branch stays clean. This branches on worktree context — a linked
worktree cannot check out `$BASE` (the primary tree holds it):

**Classic single tree** (`is_linked_worktree` false):

```bash
git stash push -u -- docs                # park the doc changes (adjust paths to what compound wrote)
git checkout "$BASE" && git pull --ff-only
git checkout -b "docs/${N:-compound}-knowledge"
git stash pop
```

**Linked worktree** (`is_linked_worktree` true) — do **not** `git checkout "$BASE"`. Branch in place
from the current `HEAD` (already on the default branch with the freshly-written docs) and refresh the
remote ref; GitHub diffs the docs-only PR against `$BASE` regardless:

```bash
git fetch origin "$BASE"                          # refresh origin/<base>; do not check it out
git checkout -b "docs/${N:-compound}-knowledge"   # branch in place from HEAD
```

If a stash is awkward (many scattered paths), an equivalent is to create the branch first, then
commit only the doc paths with an explicit `git add <doc paths>` — never `git add .`.

### 4. Commit and open the PR

```bash
git add docs/ '*.md'                     # only the doc paths — never a blanket add
git commit -m "$(cat <<'EOF'
docs: compound learnings from #<N>

Knowledge captured from the just-shipped change. Markdown only — no code.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

git push -u origin "docs/${N:-compound}-knowledge"

gh pr create --repo "$ORIGIN" --base "$BASE" \
  --title "docs: compound learnings from #<N>" \
  --body "$(cat <<'EOF'
Compounded knowledge from #<N>. **Docs-only — no code changes.**

## What this captures
- <one line: the solution doc / pattern / learning written>

## Scope
Markdown only (`docs/**`, `*.md`). Reviewed by CI; auto-merged on green per the `land-docs` skill.

---
[![Compound Engineered](https://img.shields.io/badge/Compound-Engineered-6366f1)](https://github.com/aagnone3/agentic-engineering) 🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"

PR_NUM=$(gh pr view --repo "$ORIGIN" --json number --jq '.number')
```

Do **not** put `Closes #<N>` in the body — the source issue was already closed by the code PR's
merge; this data PR must not reopen/retouch its lifecycle.

### 5. Arm auto-merge immediately

The moment the PR exists, enable GitHub-native auto-merge — this is the whole point of the data lane:
the merge is pre-committed and will fire on green with no further session turn.

```bash
gh pr merge "$PR_NUM" --repo "$ORIGIN" --squash --delete-branch --auto
```

If this errors because auto-merge is not enabled on the repo, that is a repo-settings blocker, not a
content problem — report it to the user (they must enable "Allow auto-merge" in the repo's settings)
and fall back to the watch-then-merge path in step 6. Do **not** silently skip arming it.

### 6. Follow the checks to close-out

With auto-merge armed, GitHub merges on green by itself. This step only exists to catch and fix a
failing check before it strands the PR:

```bash
gh pr checks "$PR_NUM" --watch          # follow GitHub Actions to their conclusion
```

Then branch on the outcome per the decision tree above:

- **Green** → GitHub auto-merges. Confirm with `gh pr view "$PR_NUM" --repo "$ORIGIN" --json state`
  (expect `MERGED`), then sync locally — context-aware, since a linked worktree cannot check out
  `$BASE`:
  ```bash
  if is_linked_worktree; then
    git fetch origin "$BASE"    # refresh origin/<base>; primary tree FFs on its next checkout — defer worktree/branch teardown to gc
  else
    git checkout "$BASE" && git pull --ff-only
    git branch -D "docs/${N:-compound}-knowledge" 2>/dev/null || true   # branch auto-deleted on merge
  fi
  ```
  In a worktree, local branch + worktree teardown is **deferred to `gc`** (see the
  [`git-worktree`](../git-worktree/SKILL.md) gc note — it can't self-reap the active worktree and only
  covers `$GIT_ROOT/.worktrees/`; `.claude/worktrees/` needs a manual `git worktree remove` from the
  primary tree).
- **Red + simple** → read the failing job (`gh run view <run-id> --log-failed`), fix, `git push`,
  re-watch. Auto-merge stays armed and re-evaluates the new commit. Max ~2 attempts that make
  measurable progress (fewer failing checks each time).
- **Red + warrants input**, or still red after 2 dry attempts → **stop and ask the user** with the
  specific failure. The docs PR stays open with auto-merge armed (harmless while red); the session
  does not silently drop it.

No lifecycle stamp here — the source issue is already `compounded` (the compound step stamped it
when it wrote the doc). This skill only delivers the artifact; it is not a lifecycle writer.

### 7. Report

One line: the docs PR (number + URL), that it was docs-only and submitted with auto-merge armed —
merged on green (or still open with auto-merge pending a check, with the reason). This is the
session's clean close-out — no further user turn needed on a green run.

## Success criteria

- Docs PR was **submitted with auto-merge enabled** (`--auto`) in the same step it was opened.
- Docs PR reaches `MERGED` (by GitHub auto-merge on green), branch deleted, local default branch
  fast-forwarded.
- The merged diff was **100% documentation** (the scope check held at open and at merge).
- No in-agent review was run — CI (GitHub Actions) was the reviewer; the skill only followed checks.
- The user was involved **only** if a check failure warranted their input, or if the repo lacks
  auto-merge permission — never for a green run.
