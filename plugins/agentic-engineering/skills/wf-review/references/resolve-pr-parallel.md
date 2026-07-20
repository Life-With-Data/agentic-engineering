# Resolve PR Comments in Parallel

Resolve all unresolved PR review comments by spawning parallel agents for each thread.

## Context Detection

Claude Code automatically detects git context:
- Current branch and associated PR
- All PR comments and review threads
- Works with any PR by specifying the number

## Workflow

### 1. Analyze

Fetch unresolved review threads using the GraphQL script:

```bash
bash <skill-directory>/scripts/get-pr-comments PR_NUMBER
```

This returns only **unresolved, non-outdated** threads with file paths, line numbers, and comment bodies.

If the script fails, fall back to:
```bash
gh pr view PR_NUMBER --json reviews,comments
gh api repos/{owner}/{repo}/pulls/PR_NUMBER/comments
```

### 2. Plan

Create a TodoWrite list of all unresolved items grouped by type:
- Code changes requested
- Questions to answer
- Style/convention fixes
- Test additions needed

### 3. Implement (PARALLEL)

Spawn a `pr-comment-resolver` agent for each unresolved item in parallel.

If there are 3 comments, spawn 3 agents:

1. Task pr-comment-resolver(comment1)
2. Task pr-comment-resolver(comment2)
3. Task pr-comment-resolver(comment3)

Always run all in parallel subagents/Tasks for each Todo item.

### 4. Commit & Resolve

- Commit changes with a clear message referencing the PR feedback
- Resolve each thread programmatically:

```bash
bash <skill-directory>/scripts/resolve-pr-thread THREAD_ID
```

- Push to remote

### 5. Verify

Re-fetch comments to confirm all threads are resolved:

```bash
bash <skill-directory>/scripts/get-pr-comments PR_NUMBER
```

Should return an empty array `[]`. If threads remain, repeat from step 1.

## Scripts

- [scripts/get-pr-comments](../scripts/get-pr-comments) - GraphQL query for unresolved review threads
- [scripts/resolve-pr-thread](../scripts/resolve-pr-thread) - GraphQL mutation to resolve a thread by ID

## Success Criteria

- All unresolved review threads addressed
- Changes committed and pushed
- Threads resolved via GraphQL (marked as resolved on GitHub)
- Empty result from get-pr-comments on verify

## Related

This reference is the **comment-resolution loop**. To take a PR all the way to merged — waiting on CI,
resolving threads (via this reference), confirming approval, then merging and cleaning up — use the
[`land-pr`](../../wf-delivery/references/land-pr.md) reference, which calls this one as its thread-resolution step.
