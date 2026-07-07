---
title: "Hardening a GitHub Actions workflow you scaffold into other repos"
category: security-issues
tags: [github-actions, supply-chain, sha-pinning, permissions, pat, projects-v2, scaffolding]
module: lifecycle-board-bootstrap
symptom: "Generating a .github/workflows/*.yml (with a third-party action + a PAT secret) that ships into many downstream repos — what's the hardened template?"
root_cause: "A scaffolded workflow's security posture propagates to every repo it lands in; a weak default (moving tag, ambient GITHUB_TOKEN scopes, run: interpolation) becomes a weak default everywhere"
---

# Hardening a Scaffolded GitHub Actions Workflow

When a tool *generates* a workflow file (here: `actions/add-to-project` for board auto-add, PR #67 / issue #63), the security posture **propagates** to every repo it touches — so the bar is higher than a one-off workflow. This is the reusable checklist, verified by a security + framework-docs deepening pass and a review.

## The hardened template (each line earns its place)

```yaml
name: Add issues to project
on:
  issues:
    types: [opened]          # NOT pull_request_target — no fork-controlled refs

permissions: {}              # (1) strip GITHUB_TOKEN to nothing

jobs:
  add-to-project:
    runs-on: ubuntu-latest
    permissions: {}          # (1) again at job level
    steps:
      - uses: actions/add-to-project@<40-hex-sha>  # (2) SHA-pin, tag in comment
        with:
          project-url: https://github.com/users/<owner>/projects/<n>
          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}   # (3) PAT, never echoed
```

### (1) `permissions: {}` — not `contents: read`
The write is done by the **PAT** (see below), so `GITHUB_TOKEN` does no work → give it *zero* scopes. `permissions: {}` sets every scope to `none` (GitHub: "any permission absent from the list is set to `none`"). An explicit empty block also **overrides a permissive org default** (many orgs still default the token to read/write). `contents: read` would over-grant. Put it at **top and job level**.

### (2) SHA-pin third-party actions — first-party `actions/*` is NOT an exemption
A moving `@v2` tag can be re-pointed (or the maintainer account compromised) to code that runs **with your secret in scope** — the tj-actions/changed-files (Mar 2025) class, amplified because a template fans the risk out to every scaffolded repo at once. Pin a full 40-char commit SHA with the human tag in a trailing comment. Two implementation details that made this robust:
- **Resolve the SHA at scaffold time** (`gh api repos/<owner>/<action>/commits/<tag> --jq .sha`) so the pin is current when written, with a **known-good constant fallback** for offline/CI. Gate the result through `re.fullmatch(r"[0-9a-f]{40}", sha)` so a tag, short SHA, or garbled response **fails to the constant, never emits a tag**. A test asserts the `uses:` line is a 40-hex SHA.
- **Ship `.github/dependabot.yml`** (`github-actions` ecosystem) alongside so the pin is auto-bumped — "pinned but not frozen." A static SHA with no Dependabot silently misses the action's own security patches.

### (3) PAT secret — least-privilege, and why `GITHUB_TOKEN` can't
`GITHUB_TOKEN` is *repository*-scoped; Projects v2 are *account*-owned (user/org) — a different ownership boundary no `permissions:` grant can cross. Document the token **least-privilege-first**: fine-grained PAT (org **Projects: R/W** + repo **Issues/PRs: Read**) → GitHub App installation token (org-hardened) → classic PAT (`project`+`repo`, account-wide) as the flagged fallback. Set an expiry + rotate (~90d); an expired token surfaces as a **red workflow run**, not a doctor check.

### Trigger safety
`issues: [opened]` is low-risk: no checkout of untrusted code, no `run:` steps. The one real injection vector for issue-triggered workflows is interpolating `${{ github.event.issue.title/body }}` into a `run:` shell step — this template has **no `run:` steps**, and a scaffolded inline comment forbids adding them, so the posture survives downstream edits. Never add `pull_request_target` to a file holding a write-scoped PAT (Pwn Request class).

### Injection at the generator, not just the template
The owner/repo interpolated into `project-url` and the file paths come from `git remote` — validate them at the parser (`parse_origin`'s `[\w.-]+` capture rejects newlines/`$`/`{`/quotes, so a hostile remote name can't break out of the YAML scalar). Keep scaffold **paths as fixed constants** joined to the repo root (no owner/repo in the filesystem path → no traversal). **Validate interpolated values at the render boundary** (the SHA must be 40-hex; a human ref that lands in a comment must be a single tame token) so safety doesn't depend on caller discipline.

## Two silent-degradation review patterns (reusable beyond workflows)

1. **A substring test is too loose for a structural guarantee.** `"github-actions" in dependabot_text` returned "already covered" when the string was only in a *comment* while the real ecosystem was npm — so the wiring silently never happened. Match the value **in key position** (`^\s*-?\s*package-ecosystem:\s*["']?github-actions`) when you're deciding whether to *skip* work. (Still not "merge their YAML" — just read more precisely before staying silent.)
2. **Don't default-guess on a transient failure — surface the ambiguity.** Resolving user-vs-org via `gh api users/<owner> --jq .type` and defaulting to `users` on failure silently scaffolds a wrong `users/…` URL for an **org** board (the action doesn't normalize; it fails days later in a downstream log). A *failed* lookup is indistinguishable from a user account, so return a **warning** alongside the default rather than guessing invisibly — matches the "verify concretely" ethos.

## References

- PR #67, issue #63 (scaffold); sibling PR #66, issue #64 (the recorded forward binding + the `board_forward_binding` doctor check this satisfies).
- Related config/idempotency lessons: [[idempotent-backfill-and-recorded-config-design]]. gh CLI shapes: [[gh-projects-v2-backfill-item-list-shapes]].
- GitHub — Security hardening for GitHub Actions; OpenSSF Scorecard (Token-Permissions, Pinned-Dependencies); `actions/add-to-project` README.
