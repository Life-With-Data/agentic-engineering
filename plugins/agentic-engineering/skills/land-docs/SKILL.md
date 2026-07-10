---
name: land-docs
description: Ship compounded knowledge (docs-only markdown) as its own pull request and drive it to merge unattended. Use after a code PR has merged and the compound step has written docs/solutions or other markdown — this opens the "data PR", follows its checks, and merges when green without another user turn. Triggers on "land the docs PR", "ship the compound knowledge", "open a data PR for these docs".
argument-hint: "[optional: issue number the knowledge came from — e.g. 92]"
disable-model-invocation: true
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

## Reacting to checks (the whole decision tree)

The repo's GitHub Actions are the reviewer. This skill does **not** run its own multi-agent review,
style pass, or findings triage — it submits the PR and follows the checks:

| Check outcome | Action |
|---------------|--------|
| **All required checks pass** | Merge (squash, delete branch). No user turn. |
| **A check fails and the fix is simple** | Fix it (a broken relative link, a frontmatter typo, a failed docs build, a count that needs regenerating), push, re-check. Bounded to ~2 attempts that make measurable progress. |
| **A check fails and the fix warrants user input** | Pause and ask. Ambiguous content, a schema/enum choice, a failure you can't resolve in ~2 attempts, or anything that would change *what the knowledge says* → surface it in one message and wait. Don't guess on content. |

"Simple" = mechanical and self-evident from the failure log (link/anchor fix, whitespace, rebuild
a generated artifact). "Warrants input" = a judgment about the knowledge itself.

## Workflow

### 1. Resolve context

```bash
ORIGIN=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')   # owner/repo of origin
BASE=$(git rev-parse --abbrev-ref origin/HEAD | sed 's@^origin/@@')  # default branch
N="${1:-}"                                                           # source issue number, if any
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
onto its own branch so the default branch stays clean:

```bash
git stash push -u -- docs                # park the doc changes (adjust paths to what compound wrote)
git checkout "$BASE" && git pull --ff-only
git checkout -b "docs/${N:-compound}-knowledge"
git stash pop
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

### 5. Follow the checks

```bash
gh pr checks "$PR_NUM" --watch          # wait for GitHub Actions to conclude
```

Then branch on the outcome per the decision tree above:

- **Green** → step 6.
- **Red + simple** → read the failing job (`gh run view <run-id> --log-failed`), fix, `git push`,
  re-watch. Max ~2 attempts that make measurable progress (fewer failing checks each time).
- **Red + warrants input**, or still red after 2 dry attempts → **stop and ask the user** with the
  specific failure. The docs PR stays open; the session does not silently merge or silently drop it.

### 6. Merge and clean up

```bash
gh pr merge "$PR_NUM" --repo "$ORIGIN" --squash --delete-branch
git checkout "$BASE" && git pull --ff-only
git branch -d "docs/${N:-compound}-knowledge"   # safe-delete; already merged
```

No lifecycle stamp here — the source issue is already `compounded` (the compound step stamped it
when it wrote the doc). This skill only delivers the artifact; it is not a lifecycle writer.

### 7. Report

One line: the merged docs PR (number + URL), that it was docs-only and auto-merged on green (or
paused, with the reason). This is the session's clean close-out — no further user turn needed on a
green run.

## Success criteria

- Docs PR shows `MERGED`, branch deleted, local default branch fast-forwarded.
- The merged diff was **100% documentation** (the scope check held at open and at merge).
- No in-agent review was run — CI (GitHub Actions) was the reviewer; the skill only followed checks.
- The user was involved **only** if a check failure warranted their input — never for a green run.
