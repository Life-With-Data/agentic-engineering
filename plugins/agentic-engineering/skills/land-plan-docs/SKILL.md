---
name: land-plan-docs
description: Commit and open a docs-only PR for one or more join-keyed plan docs (docs/plans/**) written in a single groom/plan run, with auto-merge armed at creation so they land on green unattended. Use after /workflows-groom or /workflows-plan writes plan doc(s) carrying a github_issue join key — this batches a simple item (1 doc) or an epic plus its children (N+1 docs) into one branch, one commit, one PR. The pre-work, possibly-multi-doc counterpart to land-docs (which ships post-merge compound knowledge); the two are parallel but distinct. Triggers on "land the plan docs", "open the plan PR", "ship these groomed plans".
argument-hint: "[batch of {issue_number, plan_doc_path} pairs — the join-keyed docs/plans/** files for this run]"
allowed-tools: Bash(gh *), Bash(git *), Read
---

# Land plan docs as a docs-only PR

Take the plan doc(s) a groom/plan run just wrote under `docs/plans/**` — each carrying a
`github_issue: N` frontmatter join key — and ship them as a **single** docs-only pull request,
then arm GitHub auto-merge so they land on green without another user turn. This closes the gap
where plan docs are left untracked in the worktree and lost to a `git clean`, a worktree prune, or
grooming in one worktree and implementing in another.

This is the **pre-work, batched** counterpart to [`land-docs`](../land-docs/SKILL.md): `land-docs`
ships **post-merge compound knowledge** (`docs/solutions/**`, single-issue, referenced by
`/workflows-compound`); `land-plan-docs` ships **pre-work plan artifacts** (`docs/plans/**`,
1..N docs in one batch, referenced by the groom/plan wiring). The two surfaces stay parallel but
distinct — do not reuse the `land-docs` name or merge them. It also shares frontmatter and
fork-trap conventions with [`land-pr`](../land-pr/SKILL.md).

This skill is **not** a lifecycle writer. The board-`planned` stamp is owned by the caller
(`/workflows-plan`), which runs before this step. This skill only persists the plan artifact(s)
and reports the PR status — it never claims `planned` and stamps no board state.

## Input: a batch of join-keyed plan docs

The invocation supplies a batch of `{issue_number, plan_doc_path}` pairs (1..N):

- **1 pair** for a simple, crisp item → one plan doc.
- **N+1 pairs** for an epic plus N children groomed in the same run → N+1 plan docs, all landed in
  **one** PR.

Every `plan_doc_path` must be under `docs/plans/**`. Treat the set of these paths as **this run's
join keys** — the scope check, commit, and idempotency check are all defined against exactly this
set.

## Scope check (narrower than land-docs)

`git add` only the exact join-keyed `docs/plans/**` paths for this run — never a blanket
`git add .` or `git add docs/`. Unlike `land-docs` (which requires the *whole* diff to be
docs-only), a plan run legitimately coexists with dirty product code, so:

- **Tolerate** unrelated dirty files anywhere else in the tree (product code, other dirs) — do not
  abort on them, and never stage them.
- **Abort only** when a *different* `docs/plans/**` file — one **outside** this run's join-key
  paths — is also dirty. That is ambiguous ownership: another run's plan doc is in flight and this
  skill must not sweep it up. Stop and surface it; do not branch, commit, or merge.

```bash
# The exact join-keyed paths for this run (one per plan doc in the batch):
RUN_DOCS=( docs/plans/<doc-1>.md docs/plans/<doc-2>.md )   # fill from the input batch

# List every dirty docs/plans/** path, then drop this run's own paths. Anything left is a
# *different* plan doc in flight = ambiguous ownership → STOP. The pipeline leads with `git` so
# the Bash(git *) allow-list covers it (same convention as land-docs — do not widen allowed-tools).
git status --porcelain -- 'docs/plans/**' | sed 's/^...//' \
  | grep -vFxf <(printf '%s\n' "${RUN_DOCS[@]}") \
  | grep . && echo "OTHER docs/plans CHANGES PRESENT — ambiguous ownership; escalate to user" \
           || echo "plan-doc scope clean ✓"
```

## Idempotency: detect an existing PR before branching

Before creating a branch, check whether this batch's join key(s) already have an open **or** merged
PR — a re-run on an already-`planned` item must **no-op**, not re-branch. Detect via the recognizable
branch-name prefix (`plan-docs/<primary-issue>-...`) and/or a label, checking all states:

```bash
PRIMARY="<lowest or epic issue number in the batch>"

# Existing PR from a prior run of this skill for the same primary join key? Our branches are
# named plan-docs/<PRIMARY>-<suffix>, so filter on the prefix client-side. Do NOT use a
# `--search "head:plan-docs/${PRIMARY}"` query — GitHub's `head:` qualifier matches the ref
# *exactly* and would never match the suffixed branch, silently re-branching on every re-run.
EXISTING=$(gh pr list --repo "$ORIGIN" --state all \
  --json number,url,state,headRefName \
  --jq '[.[] | select(.headRefName | startswith("plan-docs/'"${PRIMARY}"'-"))][0]')

if [ -n "$EXISTING" ] && [ "$EXISTING" != "null" ]; then
  # No-op: report the existing PR link and status; do NOT re-branch.
  echo "$EXISTING"    # → report "skipped: existing PR" with its number/URL and state
fi
```

If an existing PR is found (open or merged), report it and stop — the plan docs are already landed
or in flight. Only proceed to branch/commit/PR when no such PR exists.

## Auto-merge is armed at creation

The plan-docs PR is submitted with GitHub-native auto-merge enabled
(`gh pr merge --auto --squash --delete-branch`) in the same step that opens it, so the docs land the
instant CI goes green even if this session has already ended. The scope check above is the gate that
licenses arming it unattended.

If the repo disallows auto-merge, that is a repo-settings blocker (Settings → General → Pull Requests
→ "Allow auto-merge"), not a content problem — report it plainly and fall back to the
watch-then-report path. **Never silently skip arming auto-merge.**

## Reacting to hook/CI failures (the decision tree)

The repo's git hooks and GitHub Actions are the reviewer. This skill runs no in-agent review — it
submits the PR with auto-merge armed and reacts to the checks. Do **not** assume any specific
link-check or lint hook exists; handle failures generically from the failure log.

| Outcome | Action |
|---------|--------|
| **All required checks pass** | GitHub auto-merges (squash, delete branch) on its own — confirm and report. No user turn. |
| **A check/hook fails and the fix is mechanical** | Fix it (a broken relative link, a frontmatter typo, a failed docs build, a count to regenerate), commit, push, re-check. Auto-merge stays armed and re-evaluates. Bounded to ~2 attempts that make measurable progress. |
| **A failure warrants user input** | Pause and ask, with the specific failure. Auto-merge stays armed but harmless while red. Anything that would change *what a plan says*, a failure unresolved after ~2 attempts, or an ambiguous fix → surface it and wait. |

Never `--no-verify`. Never push directly to the default branch. Never self-merge without an armed
auto-merge or explicit human approval.

## Workflow

### 1. Resolve context

```bash
ORIGIN=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')   # owner/repo of origin
BASE=$(gh repo view --repo "$ORIGIN" --json defaultBranchRef --jq '.defaultBranchRef.name')  # default branch — resolve via the API; local origin/HEAD is often unset in a fresh worktree (exactly this skill's context)
PRIMARY="<epic or lowest issue number in the batch>"                 # names the branch
RUN_DOCS=( docs/plans/<doc-1>.md docs/plans/<doc-2>.md )             # this run's join-key paths

# true (linked worktree) when the per-worktree git-dir differs from the shared common-dir.
# Absolute path-format avoids relative-vs-absolute false matches across git versions.
is_linked_worktree() {
  [ "$(git rev-parse --path-format=absolute --git-common-dir)" \
    != "$(git rev-parse --path-format=absolute --git-dir)" ]
}
```

Every `gh` write carries an explicit `--repo "$ORIGIN"` (fork-trap guardrail) — resolve `ORIGIN`
once, here, and reuse it.

### 2. Confirm work to land, then run the scope check

```bash
git status --porcelain -- "${RUN_DOCS[@]}"
```

If none of the batch's plan docs are dirty (already committed/clean), there is nothing to land —
report and stop. Otherwise run the **scope check** above; abort if a `docs/plans/**` file outside
`RUN_DOCS` is dirty.

### 3. Idempotency check

Run the **existing-PR detection** above. If an open or merged PR already covers this primary join
key, no-op — report its link and status (`skipped: existing PR #<n>`) and stop. Do not re-branch.

### 4. Branch for the plan docs

Create the branch directly from the current `HEAD` and stage only the join-keyed paths. Branch
**in place** rather than switching to `$BASE` first: at groom/plan time `HEAD` already sits on the
default branch with only the freshly-written (untracked) plan docs, and a `git checkout "$BASE"`
would *abort* the moment any unrelated tracked product file is dirty — the very coexistence this
skill is built to tolerate. Forking from `HEAD` sidesteps that strand entirely.

```bash
git checkout -b "plan-docs/${PRIMARY}-$(date +%s)-$RANDOM"   # unique suffix for race-retry (step 6)
```

A docs-only PR forked from `HEAD` is diffed against `$BASE` by GitHub regardless; auto-merge
(step 7) squashes onto the current default at merge time. Only if `HEAD` carries unrelated *commits*
ahead of `$BASE` (not the groom/plan case) sync first — `git fetch origin "$BASE"` and branch from
`origin/$BASE`.

### 5. Commit and open one PR for the whole batch

One branch, one commit, one PR covering all docs in the batch. Use a conventional `docs:` message
enumerating every issue number in the batch:

```bash
git add "${RUN_DOCS[@]}"                          # only the join-keyed plan docs
git commit -m "$(cat <<'EOF'
docs: land plan docs for #<issue-a>, #<issue-b>, #<issue-c>

Plan artifacts groomed in one run. Markdown only — no code.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push -u origin "$BRANCH"

gh pr create --repo "$ORIGIN" --base "$BASE" \
  --title "docs: land plan docs for #<issue-a>, #<issue-b>, #<issue-c>" \
  --body "$(cat <<'EOF'
Plan docs groomed/planned in one run. **Docs-only — no code changes.**

## What this lands
- `docs/plans/<doc-1>.md` — plan for #<issue-a>
- `docs/plans/<doc-2>.md` — plan for #<issue-b>

## Scope
Markdown under `docs/plans/**` only. Reviewed by CI; auto-merged on green per the `land-plan-docs` skill.

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"

PR_NUM=$(gh pr view --repo "$ORIGIN" "$BRANCH" --json number --jq '.number')
```

Do **not** put `Closes #<N>` in the body — these are pre-work plan artifacts; landing them must not
touch the issues' lifecycle. The board-`planned` stamp is the caller's job.

### 6. Handle a push race

If `git push` is rejected because a concurrent run raced to the same branch name, retry with a
**fresh** branch-name suffix — bounded to ~2 attempts:

```bash
git checkout -b "plan-docs/${PRIMARY}-$(date +%s)-$RANDOM-retry"   # new unique suffix (fresh entropy)
git push -u origin "$(git rev-parse --abbrev-ref HEAD)"
```

After ~2 failed attempts that make no progress, stop and surface the race to the user rather than
looping.

### 7. Arm auto-merge immediately

```bash
gh pr merge "$PR_NUM" --repo "$ORIGIN" --squash --delete-branch --auto
```

If this errors because auto-merge is not enabled on the repo, report the repo-settings blocker
plainly and fall back to the watch-then-report path in step 8 — never silently skip arming it.

### 8. Follow the checks to close-out

```bash
gh pr checks "$PR_NUM" --watch          # follow the checks to their conclusion
```

Then branch on the outcome per the decision tree above:

- **Green** → GitHub auto-merges. Confirm `gh pr view "$PR_NUM" --repo "$ORIGIN" --json state`
  (expect `MERGED`), then sync locally. Pick the path by evaluating `is_linked_worktree` — a linked
  worktree (this skill's usual context) cannot check out `$BASE` (the primary tree holds it):

  **Classic single tree:**
  ```bash
  git checkout "$BASE" && git pull --ff-only
  git branch -D "$BRANCH" 2>/dev/null || true    # branch auto-deleted on merge
  ```

  **Linked worktree** — do **not** check out `$BASE`:
  ```bash
  git fetch origin "$BASE"    # refresh origin/<base>; primary tree FFs on its next checkout
  ```
  In a worktree, local branch + worktree teardown is **deferred to `gc`** (see the
  [`git-worktree`](../git-worktree/SKILL.md) gc note — it can't self-reap the active worktree and only
  covers `$GIT_ROOT/.worktrees/`; `.claude/worktrees/` needs a manual `git worktree remove` from the
  primary tree).
- **Red + mechanical** → read the failing job (`gh run view <run-id> --log-failed`), fix, `git push`,
  re-watch. Auto-merge stays armed and re-evaluates. Max ~2 attempts that make measurable progress.
- **Red + warrants input**, or still red after 2 dry attempts → **stop and ask the user** with the
  specific failure. The PR stays open with auto-merge armed (harmless while red).

No lifecycle stamp here — this skill only delivers the plan artifact(s) and reports PR status.

### 9. Report

Emit **one line** — never silent — stating the PR number/URL and its status:

- `landed` — merged on green.
- `pending` — open with auto-merge armed, waiting on a check.
- `needs approval` — open, auto-merge unavailable (repo-settings blocker or branch protection);
  names the blocker.
- `skipped: <reason>` — no-op (e.g. existing PR #<n>, nothing dirty to land, ambiguous scope).

## Success criteria

- A batch of N plan docs produces **exactly one** branch, one commit, and one PR.
- Only the join-keyed `docs/plans/**` paths were staged; unrelated dirty files were left untouched;
  a dirty `docs/plans/**` file outside the batch aborted the run.
- A re-run on an already-landed/in-flight join key **no-ops** with the existing PR link.
- The PR was submitted with auto-merge armed (`--auto`) where allowed; where not, the blocker was
  reported and the run fell back to watch-then-report — never a silent skip.
- Hook/CI failures were fixed mechanically (bounded) or surfaced — never `--no-verify`, never a
  direct push to the default branch, never an unapproved self-merge.
- Exactly one status line was reported.
