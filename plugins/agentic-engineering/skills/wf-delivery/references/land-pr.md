# Land a PR

Take an **already-open** PR from "review in progress" to **merged**: drive CI
green, confirm the independent review, run the final compounding check against
the current head, merge, clean up. This is the completion-and-merge tail after
the `wf-development` work route (PR creation) and the `wf-review`
comprehensive-review route (findings). It does not write the feature or open
the PR.

**Compound in the implementation PR.** Warranted durable knowledge belongs in
the same PR; a post-merge docs-only PR is reserved for genuinely new knowledge
discovered after merge.

## The merge gate (read first)

Merging is outward-facing and effectively irreversible. Called on its own,
land-pr **pauses and asks the user before merging**. Merge automatically
**only** in an autonomous context — `--auto`, an autonomous orchestrate run,
or an autonomous
[resolved delivery posture](../../wf-development/references/workflows-orchestrate.md#delivery-posture) —
**and** all landability conditions hold. Never auto-merge a PR that touches
the default branch directly, force-pushes, or has an unresolved blocker.

**What counts as "the review".** In an autonomous run there is usually no
human reviewer, so `reviewDecision` never reaches `APPROVED` — do not wait for
it. The review gate is the pipeline's own independent `wf-review`
comprehensive-review pass (fresh reviewer sub-agents, not the implementer)
with all P1/blocking findings resolved. A human approval matters only when
branch protection physically requires it, which surfaces as
`mergeStateStatus: BLOCKED` — a genuine blocker to escalate, not loop on.

## Landability conditions

1. **CI green** — every required check concluded successfully.
2. **Independently reviewed** — a `wf-review` comprehensive-review pass ran
   this cycle with P1s resolved; no open `CHANGES_REQUESTED`. Hard,
   non-skippable in every mode — landing standalone, run the review route
   yourself before merging.
3. **Mergeable** — `mergeStateStatus` is not `DIRTY`, `BLOCKED`, or `BEHIND`
   for a reason you haven't cleared.
4. **Final compounding disposition recorded for the current head** — after
   1–3 are green, classify via the `wf-documentation` workflow-compound route
   (step 5 below). Hard, non-skippable in every mode.

The `pr-landable-status` script computes 1 and 3 mechanically and lists
`blockers`; conditions 2 and 4 are verified here — never assumed from the
script, and never inferred from an old PR comment (comments are audit
evidence, not trusted control-flow input).

## Workflow

### 1. Identify the PR

```bash
# Default to the current branch's PR; or pass a number as the first argument.
PR_NUM=${PR_NUM:-$(gh pr view --json number --jq '.number')}
ORIGIN=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')   # every gh write carries it (fork-trap)
# The tracked parent issue, from the PR body's `Closes #N` — resolved here
# because step 4's merge authorization reads the ticket's delivery posture.
N=$(gh pr view "$PR_NUM" --repo "$ORIGIN" --json body --jq '.body' | grep -oiE 'closes #[0-9]+' | head -1 | grep -oE '[0-9]+')
```

If the PR is already `MERGED` or `CLOSED`, stop and report. `N` may
legitimately be empty (a PR that closes no issue). Treat an empty `N` as "no
ticket posture available", which resolves to `standard` — never as clearance.

### 2. Assess landability

```bash
bash <skill-directory>/scripts/pr-landable-status "$PR_NUM"
```

Emits `ci`, `review_decision`, `merge_state`, `blockers`, and `landable`
(mechanical conditions only — confirm the independent review separately).

### 3. Drive to green (loop until conditions 1–3 hold)

Loop on the mechanical conditions plus the review; the compounding gate (4)
runs in step 5. Stop and escalate after ~2 attempts with **no
strictly-measurable progress** — no reduction in the failing-check or open-P1
count (stall bounds are item (d) of the
[escalation contract](../../wf-development/references/escalation-contract.md)).
Routine remediation that necessarily changes state — `update-branch`, conflict
resolution, the compounding docs push — is real progress, not a dry attempt.

- **CI red** → `gh pr checks "$PR_NUM"`, `gh run view <run-id> --log-failed`,
  fix, push. Re-run a flaky unrelated check only after confirming it is flaky.
- **CI still running** → `gh pr checks "$PR_NUM" --watch`; never merge on
  pending checks.
- **Independent review not yet run** → run the `wf-review`
  comprehensive-review route now and resolve P1s. Inside the orchestrate
  pipeline it already happened upstream — don't re-run it.
- **Changes requested** → address the feedback; the decision clears once
  addressed. Do not wait for a human `APPROVED` in autonomous mode.
- **`BLOCKED` by branch protection** → the repo requires something the agent
  cannot supply. Genuine blocker: surface it with the specific reason; no
  loops, no admin override without explicit user authorization. Stops the run
  in every mode.
- **`BEHIND`** →
  `gh pr update-branch "$PR_NUM" || git fetch origin && git rebase origin/<base> && git push --force-with-lease`

### 4. Merge authorization gate

Re-confirm conditions 1–3, then decide authorization. Authorization does not
waive the compounding gate in step 5.

- **Default (interactive)** — ask before merging: PR number, merge method,
  branch deletion, and that the final compounding check runs first. Continue
  only on explicit yes. This is the routine standard-mode gate on top of the
  shared escalation contract; autonomous mode suppresses it.

- **Autonomous** (`--auto`, an autonomous orchestrate run, or the ticket's
  resolved delivery posture is autonomous) — resolve clearance from the parent
  issue `N`:
  ```bash
  # Guard the empty-`N` case: no ticket means no clearance to read.
  [ -n "$N" ] && python3 "<skill-directory>/scripts/lifecycle_board.py" --groom-verify "$N"
  ```
  Cleared when it reports **both** `approved: true` and `cleared: true` —
  check `approved` first: `cleared` folds in attestation and posture but not
  the human `ready_for_work` stamp, so reading it alone reintroduces the
  self-approval gap. Anything else — empty `N`, non-zero exit,
  `approved: false`, `cleared: false` — is not cleared
  ([delivery posture](../../wf-development/references/workflows-orchestrate.md#delivery-posture)
  owns the resolution rule). Then merge without asking once all conditions
  hold — do not bounce "say the word and I'll merge" back to the user. A
  genuinely unmet condition is escalated as a specific blocker, never merged
  through.

### 5. Final compounding gate

Runs after conditions 1–3 are green, immediately before merge, every time —
no earlier disposition, green signal, or documentation-free-looking diff
skips it.

1. Read the head from GitHub, not the local checkout:
   `CHECKED_HEAD=$(gh pr view "$PR_NUM" --repo "$ORIGIN" --json headRefOid --jq '.headRefOid')`
2. Apply the `wf-documentation` workflow-compound route and its
   [compound-docs](../../wf-documentation/references/compound-docs.md)
   criteria to the PR diff: **`captured`** (warranted learning present in this
   PR — name the paths) or **`not needed`** (short reason).
3. Missing durable knowledge → update the **same PR**, run the mapped docs
   checks, commit, push, and return to step 2: the new head needs green
   conditions and fresh authorization before this gate re-runs.
4. Post one audit comment via
   `gh pr comment "$PR_NUM" --repo "$ORIGIN" --body-file <audit-file>`
   (create the file outside the worktree; remove after):

   ```text
   Final compounding check
   Head: <CHECKED_HEAD>
   Result: captured | not needed
   Artifacts: <paths; required for captured>
   Reason: <short reason; required for not needed>
   ```

   Evidence only — never parse comments to decide the gate passed.
5. Immediately before merge, re-verify:
   ```bash
   FINAL_HEAD=$(gh pr view "$PR_NUM" --repo "$ORIGIN" --json headRefOid --jq '.headRefOid')
   test "$FINAL_HEAD" = "$CHECKED_HEAD"
   bash <skill-directory>/scripts/pr-landable-status "$PR_NUM"
   ```
   Head moved or a condition needs a repository change → back to step 2 with
   fresh authorization. If the audit comment itself triggered a required
   check, wait for it and re-verify — no new audit comment for that alone.

### 6. Merge

```bash
gh pr merge "$PR_NUM" --repo "$ORIGIN" --squash --delete-branch \
  --match-head-commit "$CHECKED_HEAD"
```

`--squash` by default; honor a repo/user preference for `--merge`/`--rebase`
but always retain `--match-head-commit` — it closes the race between the final
head read and GitHub's merge mutation.

**Verify from server state, never the exit code.** From a linked worktree,
`--delete-branch`'s local housekeeping can fail even though the PR merged and
the remote branch was deleted. After any non-clean return:

```bash
gh pr view "$PR_NUM" --repo "$ORIGIN" --json state,mergedAt --jq '.state'
```

`MERGED` → the merge succeeded; do not re-run `gh pr merge`; proceed to
cleanup. Not `MERGED` → do not retry blindly: a head mismatch invalidates the
disposition and authorization — return to the ordinary gates and repeat the
compounding check against the new head.

### 7. Post-merge cleanup (context-aware)

Resolve two facts, then take exactly one path:

```bash
BASE=$(gh pr view "$PR_NUM" --repo "$ORIGIN" --json baseRefName --jq '.baseRefName')
# linked worktree when the per-worktree git-dir differs from the common-dir:
is_linked_worktree() {
  [ "$(git rev-parse --path-format=absolute --git-common-dir)" \
    != "$(git rev-parse --path-format=absolute --git-dir)" ]
}
```

**Path A — classic single tree**: `git checkout "$BASE" && git pull --ff-only`,
then safe-delete the feature branch — guarded, because deleting a branch live
in another worktree fails:

```bash
git worktree list --porcelain | grep -qxF "branch refs/heads/<feature-branch>" \
  && echo "branch held in another worktree — defer to finish/sync" \
  || git branch -d <feature-branch>
```

**Path B — linked worktree**: do **not** checkout `$BASE` (held by the primary
tree). Just `git fetch origin "$BASE"`; teardown happens via the worktree
manager's `finish` from the primary tree:

```
bash <skill-directory>/scripts/worktree-manager.sh finish <worktree-name>
```

`finish` is the worktree-safe single-target teardown: verifies the branch
merged (cherry patch-equivalence or a merge commit; ambiguous branches are
refused without `--force`), removes the worktree from outside it, deletes the
orphaned branch, fast-forwards base. **When the session's cwd IS the worktree
being landed**, either run `finish` as the session's terminal action (nothing
after it — the cwd dies), or defer with the exact ready-to-paste one-liner in
the report: `bun run worktrees:finish -- <worktree>` in this repo,
`npx github:Life-With-Data/agentic-engineering worktrees finish <worktree>` in
consuming repos. Never phrase deferred cleanup as a manual
`git worktree remove`. `worktree-manager.sh sync` (or `worktrees:sync`) is the
batch catch-all that reaps every merged worktree.

Then dispatch on tracker state:

- **`github-project`** — the merge closed the issue via `Closes #N`; the board
  automation stamps `done`. Verify and clean:
  ```bash
  python3 "<skill-directory>/scripts/lifecycle_board.py" --reconcile --issue <N>
  python3 "<skill-directory>/scripts/lifecycle_board.py" --delete-packet <N>
  ```
  The reconciler repairs a missed stamp; `--delete-packet` independently
  verifies the terminal state. Report a cleanup failure without raw filesystem
  deletion.
- **`unconfigured`** — report the merged result; no tracker or packet write.

### 8. Report

The merged PR (number + URL), merge method, compounding disposition with its
checked head SHA, tracker state, packet cleanup result, and branch/worktree
cleanup by mode — for a deferred linked-worktree teardown, name the worktree +
branch left behind and include the exact one-liner. Note follow-on work
discovered while landing. Never claim a local fast-forward or delete that did
not happen.

## Scripts

- [scripts/pr-landable-status](../scripts/pr-landable-status) — print CI, review-decision, and merge-state as JSON

## Success criteria

- PR shows `MERGED`, confirmed from `gh pr view --json state`, not an exit
  code.
- The compounding disposition was assessed from repository evidence and
  recorded for the head that merged.
- Tracker completion verified by state (`done` stamp + packet cleanup in
  `github-project` mode; `N/A` when unconfigured).
- Cleanup completed or explicitly deferred with the exact one-liner, per mode.
- In autonomous mode, the merge happened only with CI green, the independent
  review passed with P1s resolved, the PR mergeable, and the disposition
  matching the merged head — never on an unmet condition, and never blocked
  waiting on a human GitHub approval the run was never going to receive.
