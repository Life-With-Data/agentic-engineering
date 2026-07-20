# gh recipes

Concrete `gh` invocations behind the lifecycle verbs, plus the external-wiring snippets for consumer repos. Every command names its repo explicitly (`--repo owner/repo`, `--owner`) — hooks cannot see subprocess `gh` calls, so implicit-repo invocations are forbidden. **All recipes require `gh` ≥ 2.94.0** (`--parent`, `--blocked-by`, and the dependency JSON fields do not exist before it).

## Sub-issue creation

Create a decomposed task as a native sub-issue of a parent work item:

```bash
gh issue create --repo owner/repo \
  --title "Implement the claim verb" \
  --body-file /tmp/body.md \
  --parent 39
```

`--parent` attaches the new issue under issue #39 (native sub-issues: GA, 100 per parent, 8 levels deep). Pass the body via `--body-file`, never inline (shell hardening).

## Sub-issue status (the `--sub-status` verb)

`lifecycle_board.py --sub-status <N> <status>` is the one writer of a sub-issue's `status:*` label (see the reference's *Sub-issue status* section). It is board-free — pure `gh issue`/`gh label` — so it needs no `project` scope and runs in `github` mode. The gh calls it makes, for transparency:

```bash
# 1. read current labels + open/closed state (one call)
gh issue view <N> --repo owner/repo --json labels,state

# 2a. open states (in_progress | in_review | blocked): upsert the label, then swap
gh label create status:in-progress --repo owner/repo \
  --color 1D76DB --description "Sub-issue: actively being implemented" --force
gh issue edit <N> --repo owner/repo \
  --add-label status:in-progress --remove-label status:in-review   # any prior status:* label

# 2b. done (terminal): strip every status:* label, then close as completed
gh issue edit <N> --repo owner/repo --remove-label status:in-review
gh issue close <N> --repo owner/repo --reason completed
```

Do not hand-roll these — call the verb, which enforces the at-most-one-label invariant and idempotency. Writing a `status:*` label needs only `issues: write` (plain `GITHUB_TOKEN` suffices in CI), unlike a board Status write.

## Dependencies (blocked-by)

Create an issue already blocked by another, or add the dependency after the fact:

```bash
# at creation
gh issue create --repo owner/repo --title "Wire the gate" --blocked-by 40

# after the fact
gh issue edit 41 --repo owner/repo --add-blocked-by 40
```

Read dependency and parent fields as JSON:

```bash
gh issue view 41 --repo owner/repo --json blockedBy,blocking,parent
```

`blockedBy` is a list; a non-empty list means the issue is not claimable. The claim verb enforces this.

## Ready-work saved view

The ready-work board leg filters server-side:

```
status:planned no:assignee
```

Create this as a saved view in the Projects UI (there is no API for view creation), sorted by Priority. **The filter over-shows blocked items** — it cannot express "unblocked," so the engine computes the unblocked leg agent-side with a batched `blockedBy` query. Before starting any card from this view, check its Blocked-by list.

## Consumer `deployed` adapter

The `deployed` writer runs in the **consumer repo's** deploy workflow, not the plugin. Its contract is **comment-always / Status-best-effort**:

- **Always** post a deploy-evidence issue comment (`deployed to production at <sha>, <ts>`) — the comment trail is the durable deploy record.
- **Best-effort** advance Status to `deployed` only if the item is currently `shipped`, using a bounded poll (**≤ 90s**) for the async close automation; skip and log if already `compounded`. Under normal pipeline timing compound often lands first, so the Status write alone would silently never fire — the comment is what survives.

Map a deployed SHA to the issues it closes, iterating over every SHA in the deploy range (a deploy carries several PRs, not one):

```bash
gh api "repos/OWNER/REPO/commits/${SHA}/pulls" \
  --jq '.[].number' \
| while read pr; do
    gh pr view "$pr" --repo OWNER/REPO \
      --json closingIssuesReferences \
      --jq '.closingIssuesReferences[].number'
  done
```

Each resulting issue number is a `deployed` candidate.

### Trigger variants

- **`on: deployment_status`** (build-success adapter) — for external CD systems that create GitHub **Deployment records**. Filter to `state == success && environment == Production` so staging/dev jobs never stamp.
  - Deployment records exist for **Vercel** and **Cloudflare Pages**. They generally do **not** exist for **Netlify, Railway, or Fly** — those repos should ignore the `deployed` stage.
- **`vercel.deployment.promoted` via `vercel/repository-dispatch`** (promotion adapter) — Vercel fires `deployment_status: success` at **build** time, NOT at promotion. Repos that stage builds and promote manually must instead trigger on the promotion event, or the stamp lies by hours/days:

  ```yaml
  on:
    repository_dispatch:
      types: ['vercel.deployment.promoted']
  ```

  Wire it with Vercel's official `vercel/repository-dispatch` integration.

### Credentials

- The **comment-only** adapter (comment-always, no Status write) needs only `GITHUB_TOKEN` (issues-write) — zero extra secrets. Promotion-flow repos where compound usually wins the race can ship this and nothing else.
- The **Status write** requires a **GitHub App installation token** (recommended — repo-scoped, 1-hour expiry) or a dedicated-machine-account PAT in an environment-scoped secret. `GITHUB_TOKEN` **cannot write the board** — fail loudly when the secret is missing (Status-write variant only). Never place the token in the repo, config, or issue bodies.

## Git-flow issue-closer workflow

When PRs merge into a non-default integration branch, GitHub's `Closes #N` auto-close does not fire and items stall at `in_review` (the `merged_to_non_default_branch` reconciler flag surfaces this). The escape hatch is a ~10-line consumer-repo workflow — **plain `GITHUB_TOKEN` suffices** (closing issues is repo-scoped; the board automation does the rest):

```yaml
name: close-issues-on-integration-merge
on:
  pull_request:
    types: [closed]
    branches: ['develop', 'release/**']   # non-default integration branches
jobs:
  close:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    permissions: { issues: write }
    steps:
      - env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh pr view "${{ github.event.pull_request.number }}" \
            --repo "${{ github.repository }}" \
            --json closingIssuesReferences \
            --jq '.closingIssuesReferences[].number' \
          | while read n; do
              gh issue close "$n" --repo "${{ github.repository }}" \
                --reason completed
            done
```

Closing the issue then triggers the built-in "Item closed" automation, which stamps `shipped`.

## Parent → `in_review` (no custom workflow needed)

`→ shipped` is already zero-UI (the built-in "Item closed" automation fires on the merge's `Closes #N`). The **opening** edge — parent → `in_review` — is covered by two existing mechanisms, so **no committed Actions workflow is required** (an earlier `lifecycle-pr-in-review.yml` was removed as redundant):

1. **Command-opened PRs** — the `wf-development` work route Phase 4 writes `--set-status <N> in_review` directly, immediately, and **through the `open_sub_issues` seam gate** (a PR opened with unfinished sub-issues is refused). This is the primary, deterministic, enforced path.
2. **Out-of-band PRs by the assignee** — the reconciler's **rule 5** (`assignee's open PR on an in_progress item → in_review`) advances them at the next command entry. No token, no Actions minutes, no extra file.

A non-assignee PR is deliberately **not** auto-advanced (the yield/security model flags it for human review rather than trusting it to drive state) — which is why a blanket "any linked PR → in_review" Actions job was the wrong tool.

**On GitHub's native "Pull request linked to issue" workflow:** it is enabled by default and *does* set a linked issue's Status when a `Closes #N` PR opens against the **default branch** — but its default target is **In progress** (= our `in_progress`), a harmless no-op since the issue is already `in_progress` during work. We deliberately **leave it at that default** rather than pointing it at `in_review`: a native stamp would bypass the `open_sub_issues` seam gate (built-in workflows write Status directly, never through the engine), and its config is UI-only and unverifiable via API (`ProjectV2Workflow` exposes only `name`/`enabled`; the sole mutation is `deleteProjectV2Workflow`). The `in_review_with_open_subissues` reconciler flag remains the detector for any parent that reaches `in_review` with open sub-issues by a native or out-of-band path.

Sub-issues need no PR-linked analogue: they have no PR of their own, so their status is engine-written by the owning agent at dispatch/hand-back (`--sub-status`), never by a PR event.
