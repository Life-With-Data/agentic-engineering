# Plugin Hooks

Installing the **agentic-engineering** plugin activates safety-net hooks that
keep the agentic-engineering workflow — plan → work → PR → review → merge —
from being short-circuited. They fire automatically once the harness loads the
plugin (Codex additionally requires reviewing and trusting plugin hooks).

Python implementations live in this directory and are shared across harnesses.
Skills-only installs via the [skills CLI](https://github.com/vercel-labs/skills)
(`npx skills add ...`) never read plugin-level hooks; for that channel the
[`wf-setup` install-hooks reference](../skills/wf-setup/references/install-hooks.md) bundles byte-identical
copies of the four portable safety guards (byte-identity enforced by the
`SCRIPT_BUNDLES` gate in `tests/workflow-skill-architecture.test.ts` — run
`bun run skills:sync` when a canonical script changes). Wiring differs per
platform:

| Hook script | Claude | Cursor | Codex | Notes |
|-------------|--------|--------|-------|-------|
| `block-no-verify.py` | Ships (`PreToolUse` / Bash) | Ships (`beforeShellExecution`) | Ships (`PreToolUse` / Bash) | Safety net |
| `prevent-main-commit.py` | Ships | Ships | Ships | Safety net |
| `block-slack-webhook.py` | Ships (Bash + Write/Edit/MultiEdit) | Ships (shell + `preToolUse` Write) | Ships (Bash + `apply_patch`) | Safety net; Cursor has no MultiEdit matcher |
| `block-db-push.py` | Ships | Ships | Ships | Safety net |
| `block-secret-commit.py` | Ships (Bash + Write/Edit/MultiEdit) | Ships (shell + `preToolUse` Write) | Ships (Bash + Write/Edit) | Safety net; portable (bundled for skills-only installs) |
| `nudge-test-suppression.py` | Ships (Bash + Write/Edit/MultiEdit) | N/A | N/A | Non-blocking nudge; Claude-only (advisory `systemMessage` channel) |
| `nudge-todowrite-to-tracker.py` | Ships (`TodoWrite`) | N/A | N/A | No TodoWrite equivalent on Cursor/Codex |
| `sdd-cache-pre.py` / `sdd-cache-post.py` | Ships (`WebFetch`, opt-in) | N/A | N/A | WebFetch-specific; opt-in via `AGENTIC_SDD_CACHE=1` |
| `worktree-session.py` | Ships (`SessionStart` / `startup`) | N/A | N/A | Worktree bootstrap + staleness advisory; no-op outside `.claude/worktrees/*` |
| `stale-conversation-guard.py` | Ships (`UserPromptSubmit`) | N/A | N/A | Pauses a conversation idle past the prompt-cache TTL |

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
form on commit), **and** the pre-commit framework's selective bypass env vars
`SKIP=<hooks>` / `PRE_COMMIT_ALLOW_NO_CONFIG=` when they prefix a
`git commit` / `pre-commit` invocation.

**Why:** Pre-commit / pre-push hooks catch formatting, lint, and test failures
before they reach CI. Bypassing them trades a few seconds now for a red CI run,
extra fix-up commits, and wasted CI minutes later. The plugin's value compounds
through quality gates that run every time — `--no-verify` breaks that chain.
`SKIP=` is the *partial* sibling: it silences only the hooks it names (e.g.
`SKIP=type-check git commit …`), slipping past a guard that only watches for
`--no-verify` while still shipping the exact problem the skipped hook exists to
catch. If a hook is genuinely broken, disable *that hook* visibly in
`.pre-commit-config.yaml` rather than routing around it per-commit.

**Precision:** It fires only when `git commit`/`git push`/`pre-commit` is the
actual command verb bypassing verification. Commands that merely *mention* the
flag or env var — a quoted commit message, a shell comment,
`grep -- --no-verify`, `echo` — are **not** blocked. It is also segment-aware:
the flag (or the `SKIP=` env prefix) must sit in the same command segment as the
verb, so `git commit -m ok && echo --no-verify` and `export SKIP=lint; git
commit` are allowed.

**If checks are failing:** fix the root cause, or fix the hook — don't bypass.

## `prevent-main-commit.py` — PreToolUse (Bash) / beforeShellExecution

**Blocks** a `git commit` while the current branch is `main`/`master`. That is
the only rule; nothing else is blocked.

**Why:** Work should land via a feature branch and a PR, so code review, CI, and
the `land-pr` flow apply. Committing straight to `main` skips all three.

**Precision:** Quoted commit messages can't false-trigger it (a message
mentioning "merge main" is fine), and a branch merely *named* like `main`
(e.g. `main-feature`) is not treated as the protected branch. The rule reads the
live branch from `git branch --show-current`, so rewording a command's target
cannot get around it — but the verb match itself is literal `git commit`, and
global git options between the words (`git -c x=y commit`) are not matched
today.

**Not blocked, deliberately:**

- **Every `git push` phrasing.** A client-side refspec check decides from the
  shape of the phrasing, not from what the push would do — `git push` and
  `git push --force origin HEAD` from `main` update remote `main` exactly as
  `git push origin main` does. Such a check also blocks `git push origin main`,
  a required step of the delivery lifecycle on forges without a PR flow. Push and
  force-push policy belongs on the server, where it binds every client,
  identity, and phrasing: `buzz repos protect set --ref refs/heads/main --push
  owner --no-force-push`, or a GitHub ruleset (`pull_request`,
  `non_fast_forward`, `deletion`, `required_linear_history`).
- **`git merge` / `cherry-pick` / `revert` / `am` on `main`.** These create
  commits, but merging into `main` is the delivery lifecycle, not a bypass.

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

**No-op unless relevant:** it never fires unless a project actually runs
`prisma db push`, so a non-Prisma repo pays nothing.

**Correct alternative:** `prisma migrate dev --name <migration-name>` (or the
repo's wrapper), which records a migration that keeps the DB and history in sync.

## `block-secret-commit.py` — PreToolUse (Bash, Write, Edit, MultiEdit, apply_patch) / beforeShellExecution + Write

**Blocks** introducing a *live credential* into a Bash command, a tracked file,
or a Codex patch. It scans for structurally unmistakable provider-secret shapes:
Stripe `sk_live_`/`rk_live_` keys, AWS `AKIA…` access keys, GitHub `ghp_`/`gho_`/
`ghu_`/`ghs_`/`ghr_` tokens, Google `AIza…` API keys, Slack `xox[baprs]-` tokens,
`sk-`/`sk-ant-`/`sk-proj-` model-provider keys, and PEM `PRIVATE KEY` headers.

**Why:** A provider secret is a bearer credential — whoever holds it can act as
you. Writing one into a tracked file bakes it into git history and build logs
(hard to fully revoke); passing one on a command line leaks it into shell
history and process listings. This is the broad sibling of `block-slack-webhook`
(which guards one specific live credential).

**Precision:** Precision over recall, like the other guards. It fires only on
provider-specific token shapes — never on a bare provider name or a
`DATABASE_URL`-style connection string that legitimately fills configs and docs.
Each alnum-run token additionally has to *look real* (mixed letters and digits,
no `EXAMPLE`/`xxxx`/`your…` placeholder body), so documented samples such as
AWS's `AKIAIOSFODNN7EXAMPLE` and a bare `sk_live_` prefix with no body do not
trip it. On the Bash path the raw command is scanned (quotes are **not**
stripped — a real secret almost always sits inside quotes).

**Exemptions:** documentation files (`.md`/`.mdx`/`.markdown`/`.txt`/`.rst`),
placeholder/fixture paths (`*.example`, `*.sample`, `fixtures/`, `__fixtures__/`),
and the plugin's own `/hooks/` and `/scripts/` (which name the patterns by
design). It is one of the portable safety guards bundled into the
[`wf-setup` install-hooks reference](../skills/wf-setup/references/install-hooks.md)
for skills-only installs.

**Correct alternative:** read the secret from an environment variable or a
secret manager and reference it by name; keep real values out of tracked files
and off the command line.

## `nudge-test-suppression.py` — PreToolUse (Bash, Write, Edit, MultiEdit) — Claude-only

**Nudges (never blocks)** away from suppressing test signal instead of fixing
it. Two green-washing moves get a one-line reminder: a Bash command that lets a
failing or empty run report success (`--passWithNoTests` / `--pass-with-no-tests`
/ `--allowEmptyTestSuite`, or `TESTCONTAINERS_RYUK_DISABLED=`), and a file
mutation that *adds* a skipped/focused test to a test file (`it.skip`,
`describe.only`, `xit`, a pytest/unittest skip decorator, Go `t.Skip(`, Rust
`#[ignore]`).

**Why:** Skipping, focusing, or passing-with-no-tests is the easy way to get a
suite green while hiding a real failure — the exact failure mode the workflow's
testing stage exists to prevent. Surfacing the tradeoff keeps the signal honest.

**Why a nudge and not a block:** each move has legitimate, reviewed uses (a spec
that genuinely cannot run in this environment, a temporary focus while
debugging). So this only ever exits `0`, emitting an advisory `systemMessage` +
`additionalContext` (a Claude-only channel, like `nudge-todowrite-to-tracker`);
Bash detection strips quotes/comments so a *mentioned* flag does not fire, and
the file path must match a test-file pattern.

**Correct alternative:** fix the root cause (make the test infra reachable, fix
the glob, repair the failing spec), or gate the skip explicitly and visibly (a
documented condition) rather than a bare `.skip`.

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
config -> `github-project`, otherwise `unconfigured`), so the reminder always
names the same tracker the rest of the lifecycle tooling agrees on. An
`unconfigured` repo (no board yet) → silent (nothing to nudge toward until
the wf-setup lifecycle bootstrap configures a board). Under the unified
lifecycle GitHub is the sole authoritative tracker, so the board is the only
nudge target.

**Enable it:** add `nudge_todowrite: true` to `agentic-engineering.local.md`'s
frontmatter (same file the `setup` skill writes `issue_tracker:` into). A
*tracked* copy of that file is ignored (security invariant shared with the
other local-config reads), so the flag only takes effect from an untracked,
per-machine copy.

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

## `worktree-session.py` — SessionStart (`startup`) — Claude-only

**Never blocks** (`exit 0` always). Bootstraps and advises on Claude Code
worktrees. Claude Code creates session worktrees under
`<repo>/.claude/worktrees/<name>` with a bare `git worktree add` — no dependency
install and no gitignored-file copy. The [`wf-development` git-worktree reference](../skills/wf-development/references/git-worktree.md)
skill only helps when a human runs its manager script by hand; it does nothing for
the worktrees the harness spins up itself (parallel / web sessions and
`isolation:"worktree"` subagents). This hook closes that gap so a fresh
harness-created worktree is usable immediately.

Inside a linked `.claude/worktrees/*` tree (a no-op everywhere else — the main
tree, a non-git dir, or a hand-made worktree elsewhere) it:

1. **Copies gitignored env files** (`.env`, `.env.local`, and one/two levels of
   `*/.env*`) from the main tree, which `git worktree add` can't carry over.
2. **Runs an opt-in bootstrap command** once — `$AGENTIC_WORKTREE_BOOTSTRAP_CMD`
   (e.g. `"pnpm install"`) — gated on a `.claude-worktree-bootstrap-ok` marker so a
   bootstrapped worktree pays nothing on later sessions. Unset → it just reminds
   the model that deps aren't installed.
3. **Emits a staleness advisory** (non-destructive) when the worktree's branch is
   already merged into the default branch — detected with `git cherry` so
   rebase/squash merges (different SHAs) are caught, while a fresh commit-less
   branch or one with unmerged work is left silent.

The advisory is deliberately this hook's ceiling: actually removing a merged
worktree and its branch is destructive, so no hook does it. Sweep merged
worktrees on demand with the
[`wf-development` worktree manager](../skills/wf-development/scripts/worktree-manager.sh):
`worktree-manager.sh sync` reaps merged `.claude/worktrees/` (and `.worktrees/`)
trees plus stale merged branches, `finish <name>` tears down one worktree, and
`gc` sweeps both roots unattended — all apply the same `git cherry`
merged-check before removing anything.

**Config is by environment variable, not frontmatter** — matching the
`sdd-cache` precedent: which command installs deps, and whether to bootstrap at
all, is a per-machine choice that shouldn't ride a PR and flip behavior for every
clone.

- `WORKTREE_BOOTSTRAP=0` — skip the hook entirely.
- `AGENTIC_WORKTREE_BOOTSTRAP_CMD` — shell command run once in a fresh worktree.
- `AGENTIC_WORKTREE_ENV_GLOBS` — `:`-separated globs (relative to the main tree)
  to copy, overriding the built-in defaults.

**Cursor/Codex:** N/A — neither exposes a `SessionStart` worktree-bootstrap event,
so this is Claude-only. Adapted and generalized
from the BlueStar monorepo's `setup-worktree.sh` / `check-stale-worktree.sh`.

## `stale-conversation-guard.py` — UserPromptSubmit — Claude-only

**Blocks the first prompt** submitted into a conversation whose newest
transcript entry is older than `AGENTIC_STALE_MINUTES` (default **60**), and
shows the user why. **Submitting again within 10 minutes is the approval** — the
guard records the wall-clock time of the block and stands down for the next
prompt. After that grace window (or once a resumed conversation goes cold again)
it re-arms. Note that blocking *erases* the prompt, so the user's text is not
preserved; the message says so.

**Why exit 0 + JSON, not exit 2:** on `UserPromptSubmit` the documented exit-2
behavior is "blocks prompt processing and erases the prompt", and exit-2 stderr
is fed back to *Claude* — the user would watch their prompt vanish with no
explanation. So the hook emits `{"decision": "block", "reason": …,
"systemMessage": …}` and exits 0; `systemMessage` is the documented
user-visible channel.

**Why the ack is wall-clock, not transcript-keyed:** the transcript is written
asynchronously and may lag the live conversation. An ack keyed to the newest
transcript timestamp desyncs if a pending entry flushes between the block and
the re-submit, re-blocking a prompt the user has no way to approve.

**Only blocks when a human is watching.** `UserPromptSubmit` also fires under
`claude -p`, scheduled agents, and SDK embeddings, where an erased prompt is a
silent no-op nobody can approve. So the guard runs only for a recognized
interactive entrypoint (`CLAUDE_CODE_ENTRYPOINT` in `cli`, `claude-desktop`,
`vscode`, `jetbrains`) with `CI` unset. The allowlist direction is deliberate:
an unknown entrypoint — a new automation surface, `mcp`, `sdk-*` — skips the
guard, so being wrong costs a missed warning rather than a lost prompt. A TTY
check can't stand in for it (the desktop app has no controlling terminal, and
`claude -p` inherits one).

**Why:** Anthropic's prompt cache expires minutes after the last turn. Resuming
an hour-cold conversation re-sends the entire context uncached — the same tokens
you already paid to cache, billed again at full write price, and the bigger the
conversation the worse the bill. After an idle hour a fresh session (or
`/clear`) with the task stated directly is usually cheaper than reheating stale
context. This hook makes that a deliberate choice rather than an accident.

**Config is by environment variable, not frontmatter** — matching the
`sdd-cache` / `worktree-session` precedent: cost tolerance is a per-machine
choice that shouldn't ride a PR and change behavior for every clone.

- `AGENTIC_STALE_MINUTES` — idle minutes before the guard fires (default `60`);
  `0` disables it.

**Ack file:** `<transcript>.stale-ack`, one ISO timestamp (the moment of the
block), written next to the transcript under `~/.claude/projects/…` — never in
the repo, and inert to session discovery, which looks for `*.jsonl`.

**Fail-open:** an unreadable transcript, an unparseable timestamp, a missing
payload, or an unwritable ack file all resolve to "allow the prompt". A broken
guard can never wedge a session.

**Cursor/Codex:** N/A — neither exposes a prompt-submission event.

## Testing hooks

Each PreToolUse / beforeShellExecution hook reads a JSON payload on stdin and
signals its decision via exit code — `2` blocks (with the reason on stderr), `0`
allows. The **allow** path additionally prints `{"permission": "allow"}` on
stdout via `emit_allow()`: Cursor's `failClosed: true` hooks treat an empty
stdout as a failure and block, so the exit code alone is not enough there. The
JSON is inert on Claude Code (stdout parsed only on exit 0, and the `permission`
field is outside its `hookSpecificOutput` schema, so it is ignored) and on Codex
(exit-code contract), so one shared emitter covers all three. Drive one directly:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify"}}' \
  | python3 scripts/block-no-verify.py; echo "exit: $?"   # exit: 2 (blocked)

# Cursor beforeShellExecution shape — allowed command emits the allow decision:
echo '{"command":"git status"}' \
  | python3 scripts/block-no-verify.py; echo " exit: $?"
  # {"permission": "allow"}  exit: 0

echo '{"command":"git commit --no-verify"}' \
  | python3 scripts/block-no-verify.py; echo "exit: $?"   # exit: 2 (blocked)
```

Automated regression tests live in [`../tests/`](../tests) and run in CI via
`python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'`:

- [`block_no_verify_test.py`](../tests/block_no_verify_test.py)
- [`prevent_main_commit_test.py`](../tests/prevent_main_commit_test.py)
- [`block_slack_webhook_test.py`](../tests/block_slack_webhook_test.py)
- [`block_db_push_test.py`](../tests/block_db_push_test.py)
- [`nudge_todowrite_to_tracker_test.py`](../tests/nudge_todowrite_to_tracker_test.py)
- [`sdd_cache_pre_test.py`](../tests/sdd_cache_pre_test.py)
- [`sdd_cache_post_test.py`](../tests/sdd_cache_post_test.py)
- [`worktree_session_test.py`](../tests/worktree_session_test.py)
- [`stale_conversation_guard_test.py`](../tests/stale_conversation_guard_test.py)
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
