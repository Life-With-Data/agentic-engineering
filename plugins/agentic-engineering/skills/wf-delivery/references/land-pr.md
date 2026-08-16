# Land a pull request

Take an open PR to merged state without adding ceremony that does not change the
decision.

## Landability

A PR is landable when:

1. required CI checks for the current head passed;
2. the branch is mergeable and not behind by repository policy;
3. no unresolved review finding blocks correctness, security, data integrity,
   or an explicit acceptance criterion; and
4. the run has merge authority.

Independent review is risk-based, not universal. Require it for high-risk or
broad changes, when repository policy requires it, or when the user asks. Do not
manufacture fresh reviewer agents for a routine localized change.
When independent review is required, a reviewed SHA that differs from the
current head is stale and must be refreshed.

Documentation is not a merge gate. If the change revealed a durable,
non-obvious lesson, capture it in the implementation PR when practical. If it
did not, move on without an audit comment.

## Procedure

1. Resolve the PR and repository explicitly:

   ```bash
   PR_NUM=${PR_NUM:-$(gh pr view --json number --jq '.number')}
   ORIGIN=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
   ```

2. Read the current head, state, mergeability, review threads, and required
   checks. If the PR is already merged or closed, report that state.
3. Fix failing required checks and blocking findings. Do not wait on optional
   checks unless repository policy makes them required.
4. Reconcile with the base branch using repository guidance and rerun invalidated
   checks.
5. Update the PR description with a concise summary and actual verification
   evidence. Do not land a UI/UX-changing PR that lacks the screenshot
   evidence `wf-review`'s visual evidence gate requires — fix that before
   merging, not after. Add operational validation only when the change has
   operational impact.
6. Ask before merging when invoked standalone. Merge without another prompt only
   when the user selected an autonomous/unattended run or already granted merge
   authority.
7. Read back the merged PR. In Project mode, also verify the closing issue and
   `Status = done`; run `lifecycle_board.py --reconcile` once if automation is
   delayed, then `lifecycle_board.py --delete-packet <N>` to remove the work
   packet.
8. Clean up as the session's own final act — never hand the user a cleanup
   command. In a classic single tree, check out the base, fast-forward, and
   delete the merged feature branch. In a linked worktree, run
   `worktree-manager.sh finish <worktree-name>` from the primary tree as the
   terminal shell action, after the completion report; see the
   [git worktree](../../wf-development/references/git-worktree.md) reference
   for the fallback commands.

Never use admin override, force-push, or a direct default-branch write without
explicit authority. Surface an externally blocked branch with the concrete
reason instead of looping.

## Completion

Report the PR URL, merged commit, required checks, any blocking findings that
were resolved, and verified tracker/deployment state relevant to the request.
