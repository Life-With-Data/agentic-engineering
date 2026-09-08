# Resolve PR Comments

Resolve all unresolved PR review comments with one context build and one
suite run by default.

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

Create a TodoWrite list of all unresolved threads grouped by handling:
- Code-change threads (file, line, comment body, thread id) — fixed by a
  `pr-comment-resolver` agent
- Reply-only threads (questions, threads needing a reply rather than a code
  change) — answered by the orchestrator itself

### 3. Implement

Default: dispatch one `pr-comment-resolver` agent with the complete list of
code-change threads (file, line, comment body, thread id for each). One
context build, one suite run, one commit.

Dispatch one agent per thread in parallel only when threads are file-disjoint
and each is substantial enough to justify its own context build — see the
[dispatch contract](../../wf-orchestrate/references/subagent-delegation.md#dispatch-contract).

Reply-only threads are not sent to a fixer. The orchestrator posts the reply
itself; each thread is then resolved individually in step 4 like any other.

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

Should return an empty array `[]`. If threads remain, repeat from step 1 —
bounded at ~2 passes: a surviving thread (an unanswered reviewer question, a
product decision, a bot that re-opens on every push) is a blocker to escalate
to the user, not a reason to keep looping —
[escalation contract](../../wf-orchestrate/references/escalation-contract.md)
item (d) defines a dry attempt.

## Scripts

- [scripts/get-pr-comments](../scripts/get-pr-comments) - GraphQL query for unresolved review threads
- [scripts/resolve-pr-thread](../scripts/resolve-pr-thread) - GraphQL mutation to resolve a thread by ID

## Success Criteria

- All unresolved review threads addressed
- Changes committed and pushed
- Threads resolved via GraphQL (marked as resolved on GitHub)
- Empty result from get-pr-comments on verify

## Related

This reference is the **comment-resolution loop**, invoked on its own through
the `wf-review` router. To take a PR all the way to merged, use the
[`land-pr`](../../wf-delivery/references/land-pr.md) reference.
