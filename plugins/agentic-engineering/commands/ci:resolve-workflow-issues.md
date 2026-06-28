---
name: ci:resolve-workflow-issues
description: Diagnose and fix CI workflow failures by analyzing check logs and applying targeted fixes
argument-hint: "[PR number]"
---

# Fix CI — Diagnose and Resolve Workflow Failures

When CI checks are failing on a PR, follow this workflow to identify root causes and apply targeted fixes.

## Required Steps (IN THIS ORDER)

### 1. Identify the PR and Failed Checks

Get the current PR and its check status:

```bash
gh pr view --json number,url,headRefName,statusCheckRollup
```

If no PR exists for the current branch, check if a PR number was passed as an argument (`$ARGUMENTS`).

### 2. List All Checks and Their Status

```bash
gh pr checks --json name,state,conclusion,startedAt,completedAt
```

Identify which checks failed (`conclusion: "FAILURE"`) or are stuck (`state: "PENDING"`).

### 3. Fetch Failure Logs

Find the run ID and retrieve detailed failure output:

```bash
gh run list --branch <branch-name> --limit 5
gh run view <run-id> --log-failed
```

### 4. Analyze the Failure Type

| Failure Type | Indicators | General Approach |
| ------------ | ---------- | ---------------- |
| **Lint errors** | ESLint, Biome, Rubocop, Flake8, style violations | Run the project's lint/format command |
| **Type errors** | TypeScript `tsc`, mypy, Sorbet, Flow | Run the project's type-check command |
| **Test failures** | vitest, jest, rspec, pytest, assertion errors | Run failing tests locally; fix code or tests |
| **Build failures** | Compilation errors, missing imports, bundler errors | Fix locally, verify with a build command |
| **Dependency issues** | Lockfile conflicts, missing packages | Reinstall dependencies and commit updated lockfile |
| **Migration issues** | Schema drift, unapplied DB migrations | Apply pending migrations and commit |

### 5. Detect the Project Stack and Run Appropriate Fix Commands

Inspect the project to determine the right commands:

```bash
# Node.js / TypeScript
cat package.json | jq '.scripts' 2>/dev/null

# Ruby / Rails
ls Gemfile Gemfile.lock 2>/dev/null

# Python
ls setup.py pyproject.toml requirements.txt 2>/dev/null
```

**Common fix commands by project type:**

Node.js / TypeScript:
```bash
npm run lint        # or pnpm lint / yarn lint
npm run format      # or pnpm format
npm run type-check  # or npx tsc --noEmit
npm test            # or pnpm test / yarn test
npm run build
```

Ruby / Rails:
```bash
bundle exec rubocop --autocorrect
bundle exec rspec
bundle exec rails test
```

Python:
```bash
ruff check --fix .    # or flake8 / pylint
ruff format .         # or black .
mypy .
pytest
```

### 6. Reproduce Locally and Fix

Run the failing command locally to confirm the error, then apply the fix:

- **Lint/format**: Run the auto-fix command; review changes before committing
- **Type errors**: Read the error carefully; fix type issues in indicated files; re-run to verify
- **Test failures**: Read the test output; fix the code *or* the test as appropriate; run the specific test file to confirm
- **Build failures**: Check for missing imports/exports, syntax errors, or env vars; fix and rebuild
- **Dependencies**: Run the install command, commit the updated lockfile

### 7. Verify Locally Before Pushing

Run the full local validation suite to confirm nothing else broke:

```bash
# Check what the project uses (pre-commit, lint-staged, etc.)
cat .pre-commit-config.yaml 2>/dev/null || true
cat .husky/pre-commit 2>/dev/null || true

# Run the full check
pre-commit run --all-files  # if pre-commit is configured
# or run lint + type-check + tests individually
```

### 8. Commit and Push

```bash
git add <changed-files>
git commit -m "fix: resolve CI failures"
git push
```

### 9. Monitor CI

```bash
gh pr checks --watch
```

Or check periodically:

```bash
gh pr checks
```

### 10. Report Status

**Success:**
- ✅ Fixed: [list of issues fixed]
- ✅ CI checks now passing
- 🔗 PR URL

**Persistent Issues:**
- ❌ Remaining: [describe what's still failing]
- 📋 Next steps: [recommendations]

## Quick Diagnosis Commands

```bash
# Full CI status overview
gh pr checks

# Recent workflow runs
gh run list --limit 10

# View specific run
gh run view <run-id>

# Download logs for failed steps only
gh run view <run-id> --log-failed

# Re-run only the failed jobs (avoids re-running passing jobs)
gh run rerun <run-id> --failed
```

## Error Handling

- **Can't identify PR**: Ask for a PR number or URL; use `gh pr list` to find it
- **Logs unavailable**: Check the GitHub Actions UI tab on the PR directly
- **Fix unclear**: Report the raw failure output and ask for guidance before changing code
- **Flaky test**: Re-run CI without a code change first — `gh run rerun <run-id> --failed` — then investigate if it fails again
