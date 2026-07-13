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

`lifecycle_board.py --sub-status <N> <status>` is the one writer of a sub-issue's `status:*` label (see the skill's *Sub-issue status* section). It is board-free — pure `gh issue`/`gh label` — so it needs no `project` scope and runs in `github` mode. The gh calls it makes, for transparency:

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

## Native PR-opened → `in_review` (parent)

`→ shipped` is already zero-UI (the built-in "Item closed" automation fires on the merge's `Closes #N`). The **opening** edge — parent → `in_review` — is written by `/workflows:work` Phase 4 when the command opens the PR. That covers every PR the workflow opens, but **not** a PR opened out-of-band (a human, or an agent outside the command). GitHub Projects has **no enable-able built-in for "a linked PR opened,"** so the portable native cover is a committed Actions workflow that maps the PR's closing issues to a board write via the one engine. It is **opt-in** (a board Status write needs a non-`GITHUB_TOKEN` secret) and **self-skips** when that secret is absent, so it never reds-out a PR before wiring:

```yaml
name: lifecycle-pr-in-review
on:
  pull_request:
    types: [opened, reopened, ready_for_review]
jobs:
  in-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # the engine lives in-repo here
      - env:
          # A Projects-write token (App installation token or a machine-account
          # PAT with project+repo). GITHUB_TOKEN CANNOT write the board. Reuses
          # the same secret name as the lifecycle-smoke board-probe leg.
          GH_TOKEN: ${{ secrets.LIFECYCLE_BOARD_PAT }}
        run: |
          if [ -z "$GH_TOKEN" ]; then echo "::warning::no LIFECYCLE_BOARD_PAT — skipping"; exit 0; fi
          gh pr view "${{ github.event.pull_request.number }}" \
            --repo "${{ github.repository }}" \
            --json closingIssuesReferences \
            --jq '.closingIssuesReferences[].number' \
          | while read n; do
              python3 plugins/agentic-engineering/scripts/lifecycle_board.py \
                --set-status "$n" in_review
            done
```

The write is idempotent with the command's own Phase-4 write — both call `--set-status … in_review`, so belt-and-suspenders never double-stamps. Consumer repos that vendor the plugin elsewhere adjust the script path (or drop the checkout and call a vendored copy). Sub-issues need no analogue: they have no PR of their own, so their status is engine-written by the owning agent at dispatch/hand-back (`--sub-status`), never by a PR event.
