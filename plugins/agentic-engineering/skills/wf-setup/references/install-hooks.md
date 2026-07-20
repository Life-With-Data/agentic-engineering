# Install Safety Hooks

Wire the agentic-engineering safety hooks into the current coding agent's hook
configuration. The hook scripts are bundled inside this skill's
[scripts/](../scripts/) directory, so this works even when the skill was
installed standalone (e.g. `npx skills@latest add Life-With-Data/agentic-engineering`),
where only skill directories are copied and plugin-level hooks do not ride along.

**Skip this skill entirely if the plugin was installed natively** — the Claude
Code, Cursor, and Codex plugin installs already activate these hooks. Check
first (step 1) and stop if they are already active.

## What gets installed

Four PreToolUse guards, shared across harnesses. Each reads a JSON payload on
stdin and signals its decision via exit code (`0` allows, `2` blocks); the allow
path also prints `{"permission": "allow"}` on stdout, which Cursor's
`failClosed: true` hooks require and which is inert on Claude Code / Codex:

| Script | Blocks |
|--------|--------|
| [block-no-verify.py](../scripts/block-no-verify.py) | `git commit`/`git push` carrying `--no-verify` (or `-n` on commit) |
| [prevent-main-commit.py](../scripts/prevent-main-commit.py) | committing on `main`/`master`, or pushing a refspec targeting them |
| [block-slack-webhook.py](../scripts/block-slack-webhook.py) | introducing a live Slack incoming-webhook URL into commands or files |
| [block-db-push.py](../scripts/block-db-push.py) | `prisma db push` (schema drift without a migration) |

[hook_payload.py](../scripts/hook_payload.py) is a shared normalizer imported by
the guards — it maps Cursor's `beforeShellExecution` (`{command}`) and
`tool_name: "Shell"` payload shapes onto the Claude-shaped
`{tool_name: "Bash", tool_input: {command}}` envelope. It must stay in the same
directory as the guards.

## Steps

### 1. Check whether the hooks are already active

Probe before wiring anything:

- If the full plugin is installed natively (Claude Code `/plugin` list, Cursor
  installed plugins, Codex `/plugins`), the hooks already fire — report that and
  stop.
- If the target hook config (identified per harness below) already references
  any of these script names, treat the run as an update: reuse the existing
  entries' locations rather than adding duplicates.

### 2. Resolve the script path

Resolve the installed `wf-setup` skill root from the `SKILL.md` that loaded this
reference; the scripts are direct children of that root's `scripts/` directory.
Do not assume a tool-specific project or user installation path. Confirm
`python3` is on PATH (the scripts are stdlib-only).

### 3. Wire the harness

Identify which coding agent is running and follow the matching subsection. Ask
the user whether to install at **project** scope (this repo only) or **user**
scope (all projects) when the harness supports both.

#### Claude Code

Merge into `.claude/settings.json` (project) or `~/.claude/settings.json`
(user) — create the file if missing, and deep-merge if it already has a
`hooks` key. Use the resolved absolute script path (for project scope,
`$CLAUDE_PROJECT_DIR`-relative is also fine when the skill lives inside the
project):

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "python3 <scripts>/block-no-verify.py" }] },
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "python3 <scripts>/prevent-main-commit.py" }] },
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "python3 <scripts>/block-slack-webhook.py" }] },
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "python3 <scripts>/block-db-push.py" }] },
      { "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type": "command", "command": "python3 <scripts>/block-slack-webhook.py" }] }
    ]
  }
}
```

#### Cursor

Merge into `.cursor/hooks.json` at the project root (or the user-level hooks
file if user scope was chosen). `failClosed: true` keeps the guards
fail-closed, matching the native plugin wiring:

```json
{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      { "command": "python3 <scripts>/block-no-verify.py", "failClosed": true },
      { "command": "python3 <scripts>/prevent-main-commit.py", "failClosed": true },
      { "command": "python3 <scripts>/block-slack-webhook.py", "failClosed": true },
      { "command": "python3 <scripts>/block-db-push.py", "failClosed": true }
    ],
    "preToolUse": [
      { "command": "python3 <scripts>/block-slack-webhook.py", "matcher": "Write", "failClosed": true }
    ]
  }
}
```

#### Codex

Prefer the native plugin install, which bundles these hooks with a trust
review (`codex plugin marketplace add Life-With-Data/agentic-engineering`,
then `codex plugin add agentic-engineering --marketplace agentic-engineering`,
then trust the hooks via `/hooks`). Only wire manually if the user declines
the plugin.

#### Other hook-supporting agents

For any other agent with a command-hook mechanism: register each guard as a
pre-tool-use / pre-shell command hook. The contract is: JSON payload on stdin
(Claude-shaped `{tool_name, tool_input}`, Cursor-shaped `{command}`, or
`tool_name: "Shell"` — all normalized by `hook_payload.py`), exit `0` to
allow, exit `2` to block with the message on stderr. Consult that agent's
hooks documentation for where command hooks are declared.

### 4. Verify

Drive one guard directly and confirm it blocks:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify"}}' \
  | python3 <scripts>/block-no-verify.py; echo "exit: $?"   # expect: exit: 2
```

Then confirm an innocuous payload passes (`{"command":"git status"}` → exit 0).
Finally, restate to the user which config file was modified and which guards
are now active.

## Notes

- **Idempotent:** re-running must not duplicate entries — check for each script
  name before appending.
- **Uninstall — unwire FIRST, then remove.** The guards are fail-closed: if a
  wired script goes missing, `python3` exits 2 on the unopenable file, and both
  Claude Code (`PreToolUse` exit 2) and Cursor (`failClosed: true`) treat that
  as a block — every guarded action (all Bash commands, and file writes for the
  webhook guard) is then blocked until the config is hand-edited. So when
  uninstalling: delete the hook entries from the settings file **before**
  running `skills remove install-hooks`. The same lockout applies to moving or
  renaming the skill directory after wiring — re-run this skill to re-point the
  paths.
- These bundled scripts are copies of the canonical plugin scripts
  (`plugins/agentic-engineering/scripts/` in the source repo); a repository
  test keeps them byte-identical, and `skills update` refreshes GitHub-sourced
  installs.
- The full hook set (Node version check, TodoWrite nudge, plan-tracker guard,
  SDD cache) ships only with the native Claude Code plugin install — those
  hooks depend on plugin-level modules that do not travel with this skill.
