# Plugin Hooks

Installing the **agentic-engineering** plugin activates safety-net hooks that
keep the agentic-engineering workflow — plan → work → PR → review → merge —
from being short-circuited. They fire automatically once the harness loads the
plugin (Codex additionally requires reviewing and trusting plugin hooks).

Python implementations live in this directory and are shared across harnesses.
Skills-only installs via the [skills CLI](https://github.com/vercel-labs/skills)
(`npx skills add ...`) never read plugin-level hooks; for that channel the
[`install-hooks` skill](../skills/install-hooks/SKILL.md) bundles byte-identical
copies of the four portable safety guards (enforced by
`tests/install-hooks-skill-sync.test.ts` — update the copies when a canonical
script changes). Wiring differs per platform:

| Hook script | Claude | Cursor | Codex | Notes |
|-------------|--------|--------|-------|-------|
| `block-no-verify.py` | Ships (`PreToolUse` / Bash) | Ships (`beforeShellExecution`) | Ships (`PreToolUse` / Bash) | Safety net |
| `prevent-main-commit.py` | Ships | Ships | Ships | Safety net |
| `block-slack-webhook.py` | Ships (Bash + Write/Edit/MultiEdit) | Ships (shell + `preToolUse` Write) | Ships (Bash + `apply_patch`) | Safety net; Cursor has no MultiEdit matcher |
| `block-db-push.py` | Ships | Ships | Ships | Safety net |
| `check-node-version.py` | Ships | Claude-only | Claude-only | Left Claude-primary until verified elsewhere |
| `block-beads-jsonl-stage.py` | Ships | Claude-only | Claude-only | Claude-primary |
| `nudge-todowrite-to-tracker.py` | Ships (`TodoWrite`) | N/A | N/A | No TodoWrite equivalent on Cursor/Codex |
| `plan-tracker-guard.py` | Ships (`Stop`) | Claude-only | Claude-only | Claude-primary until verified |
| `sdd-cache-pre.py` / `sdd-cache-post.py` | Ships (`WebFetch`, opt-in) | N/A | N/A | WebFetch-specific; opt-in via `AGENTIC_SDD_CACHE=1` |

Harness config files:

| Harness | Config | Path root |
|---------|--------|-----------|
| Claude Code | inline `hooks` in [`.claude-plugin/plugin.json`](../.claude-plugin/plugin.json) | `${CLAUDE_PLUGIN_ROOT}` |
| Cursor | [`hooks/hooks-cursor.json`](../hooks/hooks-cursor.json) | relative `./scripts/...` (plugin root cwd) |
| Codex | [`hooks/hooks-codex.json`](../hooks/hooks.json) | `${PLUGIN_ROOT}` (also sets `CLAUDE_PLUGIN_ROOT` for compatibility) |

`hook_payload.py` normalizes Cursor `beforeShellExecution` (`{command}`) and
`tool_name: "Shell"` into `{tool_name:"Bash", tool_input:{command}}`. Codex's
canonical `apply_patch` name is preserved; `block-slack-webhook.py` inspects the
added lines in its `tool_input.command` patch directly.

## `block-no-verify.py` — PreToolUse (Bash) / beforeShellExecution

**Blocks** `git commit`/`git push` that carry `--no-verify` (or the `-n` short
form on commit).

**Why:** Pre-commit / pre-push hooks catch formatting, lint, and test failures
before they reach CI. Bypassing them trades a few seconds now for a red CI run,
extra fix-up commits, and wasted CI minutes later. The plugin's value compounds
through quality gates that run every time — `--no-verify` breaks that chain.

**Precision:** It fires only when `git commit`/`git push` is the actual command
verb bypassing verification. Commands that merely *mention* the flag — a quoted
commit message, a shell comment, `grep -- --no-verify`, `echo` — are **not**
blocked. It is also segment-aware: the flag must sit in the same command segment
as the git verb, so `git commit -m ok && echo --no-verify` is allowed.

**If checks are failing:** fix the root cause, or fix the hook — don't bypass.

## `prevent-main-commit.py` — PreToolUse (Bash) / beforeShellExecution

**Blocks** a `git commit` while the current branch is `main`/`master`, and an
explicit `git push` whose refspec targets `main`/`master`
(`git push origin main`, `git push origin HEAD:main`, …).

**Why:** Work should land via a feature branch and a PR, so code review, CI, and
the `land-pr` flow apply. Committing straight to `main` skips all three.

**Precision:** Quoted commit messages can't false-trigger it (a message
mentioning "merge main" is fine), and a branch merely *named* like `main`
(e.g. `main-feature`) is not treated as the protected branch.

**Correct alternative:** `git checkout -b <type>/<description>`, then open a PR.

## `block-slack-webhook.py` — PreToolUse (Bash, Write, Edit, MultiEdit, apply_patch) / beforeShellExecution + Write

**Blocks** introducing a Slack *incoming webhook* URL
(`hooks.slack.com/services/...`) into a Bash command (a `curl`/fetch that posts
to it) or into a file (Write/Edit/MultiEdit that writes the URL into code or
config). On Codex, it scans only added `apply_patch` lines in non-exempt files;
removed lines and patch context do not false-trigger the guard.

**Why:** A Slack incoming-webhook URL **is a live credential** — anyone holding
it can post to the channel. Hardcoding one leaks a secret into git history and
build logs, where it is hard to fully revoke, and it fragments notification
wiring away from a single authenticated code path. This is the plugin's
secret-hygiene guardrail.

**Precision:** It fires only on the unambiguous incoming-webhook host+path, so
the Slack *app* (`api.slack.com`, `chat.postMessage`, the Slack MCP tooling) is
never blocked. Documentation files (`.md`, `.mdx`, `.markdown`, `.txt`, `.rst`)
and files under `hooks/`/`scripts/` may *name* the host — prose that describes
the anti-pattern is exempt, mirroring the other guards here.

**Correct alternative:** read the webhook from an environment variable / secret
manager instead of inlining it, or send through a connected Slack app / the
Slack MCP tooling (`chat.postMessage`).

## `block-db-push.py` — PreToolUse (Bash) / beforeShellExecution

**Blocks** `prisma db push` in its wrapper forms (`npx`/`pnpm`/`dotenv`
prefixes, and `pnpm --filter <pkg> push` script aliases).

**Why:** `db push` mutates the live database to match `schema.prisma` *without*
writing a migration, so the schema silently drifts from the migration history.
That breaks the workflows migrations are the source of truth for: tests that
apply migrations from scratch diverge from a `push`ed dev DB, and CI/CD and
production (which deploy by running migrations) never receive the change. This
is the DB-safety sibling of the `prevent-main-commit` / `block-no-verify` git
guards.

**Precision:** It fires only when `prisma db push` is the actual command verb.
Commands that merely *mention* the phrase — a quoted commit message, a shell
comment, `grep`, `echo` — are **not** blocked (same quote-stripping as the
other guards). Legitimate `prisma migrate dev` / `migrate deploy` / `generate`
commands are untouched.

**No-op unless relevant:** like `check-node-version.py`, it never fires unless a
project actually runs `prisma db push`, so a non-Prisma repo pays nothing.

**Correct alternative:** `prisma migrate dev --name <migration-name>` (or the
repo's wrapper), which records a migration that keeps the DB and history in sync.

## `nudge-todowrite-to-tracker.py` — PreToolUse (TodoWrite) — Claude-only

**Never blocks** (`exit 0` always). Opt-in only: silent unless the repo sets
`nudge_todowrite: true` in `agentic-engineering.local.md` frontmatter. When
enabled, reminds the agent (via `systemMessage` + `additionalContext`) that
this repo has a durable issue tracker, so cross-session work should be filed
there rather than left in `TodoWrite`'s ephemeral, in-session list.

**Why:** `TodoWrite` is legitimate for throwaway in-session steps, but it's
easy to reach for out of habit for work that should outlive the session.
Repos that have committed to a durable tracker want a lightweight reminder
without a hard block — `TodoWrite` has a real ephemeral role and shouldn't be
fought.

**Tracker resolution:** reuses `workflow-repo-preflight.py`'s
`resolve_issue_tracker()` chain verbatim (local override > committed board
config -> `github-project` -> `gh auth` -> `github` -> `none`), so the
reminder always names the same tracker the rest of the lifecycle tooling
agrees on. Resolves to `none` → silent (nothing to nudge toward). Beads is
intentionally not a nudge target: under the unified lifecycle GitHub is the
sole authoritative tracker and beads is a non-authoritative scratchpad (see
`plan-tracker-guard.py` above).

**Enable it:** add `nudge_todowrite: true` to `agentic-engineering.local.md`'s
frontmatter (same file the `setup` skill writes `issue_tracker:` into). A
*tracked* copy of that file is ignored (security invariant shared with the
other local-config reads), so the flag only takes effect from an untracked,
per-machine copy.

## `plan-tracker-guard.py` — Stop — Claude-primary

**Blocks** turn termination if a plan file (`docs/plans/*.md`) modified during
the session lacks a tracker ID (`bead_id` / `linear_issue` / `github_issue`) in
its YAML frontmatter — unless the plan opts out with `issue_tracker: none`.

**Why:** Plans that aren't linked to a tracked issue get orphaned. This keeps
`/workflows-plan` output connected to whatever issue tracker the repo uses.

## `sdd-cache-pre.py` / `sdd-cache-post.py` — PreToolUse / PostToolUse (WebFetch), opt-in — Claude-only

**Off by default.** Unlike the guards above, this pair is a *performance* hook,
not a safety net, and it is **inert unless the environment sets
`AGENTIC_SDD_CACHE=1`**. When enabled it caches `WebFetch` results on disk under
`.claude/sdd-cache/` (gitignored) and serves a page back to the agent instead of
re-fetching it — but **only** after the origin server confirms the page is
unchanged. Adapted from
[`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills)'s
`sdd-cache` hooks, ported from bash to python3 (stdlib only).

**The 304-only guarantee:** there is **no TTL**. On a `WebFetch`, the pre hook
looks up the cached entry by `sha256(url)` and, if it stored an `ETag` /
`Last-Modified`, sends a conditional `HEAD` (`If-None-Match` / `If-Modified-Since`,
5s timeout, follows redirects) to that same URL. The cached body is served (and
the fetch blocked via exit 2, the same deny signal `block-no-verify.py` uses)
**only** when the origin answers `304 Not Modified` — a live re-verification, not
a memory read. Any other answer (`200` = changed, an error, a timeout, or an
entry with no validator) lets the real `WebFetch` proceed. So the "verify against
current docs" property that `WebFetch` gives you is never weakened; you only skip
the byte transfer when the server itself says nothing moved.

**Why:** agents that consult the same official docs across many sessions re-fetch
identical pages constantly. A naive TTL cache would speed that up at the cost of
silently serving stale docs — the opposite of what a docs-verification workflow
wants. Delegating freshness to the origin's own validators keeps every served
hit as trustworthy as a fresh fetch.

**The post hook** records the result after a fetch: it `HEAD`s the URL to capture
the current `ETag` / `Last-Modified` from the final redirect hop and writes
`{url, prompt, etag, last_modified, content, fetched_at}` atomically. A response
with **no** validator is never cached (it could never be revalidated), and any
stale entry for that URL is removed.

**Fail-open:** any error in either hook (bad stdin, unreadable cache, network
failure) resolves to "let the fetch proceed" — a broken cache can never block a
legitimate `WebFetch`.

This cache-only policy is intentionally different from the four Cursor safety
gates above, which set `failClosed: true` so a hook process failure cannot allow
a prohibited shell or write action.

**Enable it:** export `AGENTIC_SDD_CACHE=1` in the environment you launch Claude
Code from (a per-machine choice — an env var, unlike a committed config flag,
can't ride a PR and flip caching on for every clone). Unset it to disable.

## Testing hooks

Each PreToolUse / beforeShellExecution hook reads a JSON payload on stdin and
signals its decision via exit code (`0` allows, `2` blocks). Drive one directly:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify"}}' \
  | python3 scripts/block-no-verify.py; echo "exit: $?"   # exit: 2 (blocked)

# Cursor beforeShellExecution shape:
echo '{"command":"git commit --no-verify"}' \
  | python3 scripts/block-no-verify.py; echo "exit: $?"   # exit: 2 (blocked)
```

Automated regression tests live in [`../tests/`](../tests) and run in CI via
`python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'`:

- [`block_no_verify_test.py`](../tests/block_no_verify_test.py)
- [`prevent_main_commit_test.py`](../tests/prevent_main_commit_test.py)
- [`block_slack_webhook_test.py`](../tests/block_slack_webhook_test.py)
- [`block_db_push_test.py`](../tests/block_db_push_test.py)
- [`plan_tracker_guard_test.py`](../tests/plan_tracker_guard_test.py)
- [`nudge_todowrite_to_tracker_test.py`](../tests/nudge_todowrite_to_tracker_test.py)
- [`sdd_cache_pre_test.py`](../tests/sdd_cache_pre_test.py)
- [`sdd_cache_post_test.py`](../tests/sdd_cache_post_test.py)
- [`hook_payload_test.py`](../tests/hook_payload_test.py)

These pin the tricky false-positive / false-negative edges (prose that mentions
a flag, chained command segments, branches named like `main`) so the regex
guards can't silently regress.

## Disabling a hook

These hooks are intentionally conservative and should rarely need disabling. If
one is genuinely in the way (e.g. a hook itself is broken), override it in your
project's harness-local settings rather than editing the plugin, so your change
survives plugin updates:

- Claude Code: `.claude/settings.local.json`
- Cursor: project/user hooks override or disable the plugin hook entry
- Codex: `/hooks` to untrust or disable the plugin-bundled hook
