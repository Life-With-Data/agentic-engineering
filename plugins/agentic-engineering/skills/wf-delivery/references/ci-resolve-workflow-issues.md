# Fix CI — Diagnose and Resolve Failing Checks

When CI checks fail on a PR, follow this workflow to identify the root cause and ship a fix. Works with GitHub Actions and any common CI provider.

## Step 1: Identify the PR and Failed Checks

Locate the PR and its check status. If a PR number or URL was provided as an argument, use it directly. Otherwise detect from the current branch:

```bash
gh pr view --json number,url,headRefName,statusCheckRollup
```

List all checks and find which ones failed:

```bash
gh pr checks
```

## Step 2: Fetch Failure Logs

For each failed check, retrieve the logs. First find the workflow run ID:

```bash
gh run list --branch <branch-name> --limit 5
```

Then fetch the failure output:

```bash
gh run view <run-id> --log-failed
```

Alternatively, use the GitHub MCP tools if available:
- `mcp__github__actions_list` to list runs
- `mcp__github__get_job_logs` to fetch logs for a specific job

## Step 3: Classify the Failure

Map the log output to a failure category:

| Category | Common indicators | First action |
|----------|-------------------|--------------|
| **Lint / format** | eslint, biome, rubocop, flake8, formatting errors | Run the project's linter locally with auto-fix |
| **Type errors** | tsc, mypy, sorbet, type-check | Run the type checker locally and fix errors |
| **Test failures** | assertion error, test suite failed, spec failed | Run the failing test file locally |
| **Build failures** | compilation error, module not found, next build | Run the build locally and fix import/syntax errors |
| **E2E / browser failures** | playwright, cypress, screenshot diff | Run the E2E suite locally; check trace artifacts |
| **Dependency / lockfile** | lockfile out of date, missing package | Re-run the package manager install and commit the lockfile |
| **Migration / schema** | schema drift, pending migrations | Apply and commit the pending migration |
| **Environment / secrets** | missing env var, auth failure | Check that required secrets are set in CI settings |

## Step 4: Reproduce Locally

Run the failing command in your local environment to confirm the failure and iterate quickly. Use whatever commands the project defines — check the CI config file (`.github/workflows/`) and the project's README or CLAUDE.md for the exact commands.

Common patterns:
```bash
# Read the CI workflow file to find the exact failing step
cat .github/workflows/<workflow>.yml

# Then run that step's command locally
```

## Step 5: Fix the Issue

Apply the fix in the affected files. Follow these principles:

- **Lint/format**: Run the formatter with auto-fix first, then manually address remaining issues
- **Type errors**: Read the error message precisely — fix the type, not just cast away the error
- **Test failures**: Determine whether the test is wrong (update it) or the code is wrong (fix it)
- **Build failures**: Fix the root import or syntax error; don't suppress the error
- **Lockfile conflicts**: Regenerate with the package manager; never manually edit lockfiles

## Step 6: Verify the Fix Locally

Run the same check that failed in CI to confirm the fix:

```bash
# Run whatever check was failing (from the CI config)
```

Then run the full local validation suite to catch any regressions:

```bash
# Project-specific — check CLAUDE.md or package.json scripts for the right command
```

## Step 7: Commit and Push

```bash
git add <affected files>
git commit -m "fix: resolve CI failure in <check-name>

- [describe what failed and why]
- [describe the fix]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

git push
```

## Step 8: Monitor the New CI Run

Watch for the checks to pass:

```bash
gh pr checks --watch
```

Or poll periodically:

```bash
gh pr checks
```

## Step 9: Report Status

**Success:**
- All CI checks passing
- Link to the PR

**Persistent failure:**
- Describe what was tried
- Show the remaining error output
- Recommend next steps (re-run flaky test, escalate environment issue, etc.)

---

## Quick Reference

```bash
# Full CI status overview
gh pr checks

# Recent workflow runs on this branch
gh run list --limit 5

# Logs for a specific run (failed steps only)
gh run view <run-id> --log-failed

# Re-run only the failed jobs (for flaky failures)
gh run rerun <run-id> --failed

# Watch checks update in real time
gh pr checks --watch
```

## Handling Flaky Failures

If the failure is intermittent (no code change caused it, and re-running locally passes), trigger a CI re-run before writing any code:

```bash
gh run rerun <run-id> --failed
```

If it fails again with the same error, it is not flaky — proceed with the fix workflow above.

## Next Step

Once all checks pass, return to the `wf-delivery` landing route to drive the PR
through review threads, approval, and merge.
