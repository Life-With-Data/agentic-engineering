# Config Flags

Discoverability front door for the plugin's opt-in, per-repo configuration flags (`issue_tracker`, `nudge_todowrite`, etc.). Complements the [`lifecycle-doctor`](lifecycle-doctor.md) reference: doctor reports the health of what's *currently* configured; this command shows *everything that could be* configured and lets you change it. Unlike doctor, it is not silent by design — every flag is always listed, regardless of state.

## Step 1: Run the inventory verb

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/config_registry.py" --inventory
```

Returns JSON: `{"flags": [...], "ok": true}`. Each entry has `key`, `kind` (`boolean`/`enum`/`list`/`identity`), `default`, `effective`, `set`, `valid`, `source` (`local`/`committed`/`default`), `toggleable`, `file`, `owner`, `description`, `plugin`.

## Step 2: Render the table

Group rows by `plugin` (core plugin — `agentic-engineering` — first; today it is the only plugin with a registry). Within a plugin, list `identity` rows separately from toggleable ones — identity rows (e.g. `github_project_owner`) are board identity, not feature toggles, and are shown for completeness only.

Columns: Key, Kind, Current (`effective`, with a note if `set` is false — "(default)"), Toggleable, Description. If a row's `valid` is `false`, flag it inline (e.g. "⚠️ invalid — falling back to default") — this means the repo has a stale or malformed override.

## Step 3: Non-interactive mode

If `$ARGUMENTS` supplies exactly two tokens (`<key> <value>`), skip the interactive browser: run `--set <key> <value>` directly and report the result (success with old/new value, or the error JSON's `error`/`fix` verbatim on failure). This is the scripting/pipeline path — never prompt in this mode.

If `$ARGUMENTS` is empty and the session is non-interactive (no way to ask a question and wait for an answer), stop after Step 2 — print the table and take no further action. Never guess at a write in non-interactive mode.

## Step 4: Interactive browse-and-toggle

Otherwise, use the AskUserQuestion tool:

**Question 1: Which flag to change?**
- Options: every row where `toggleable` is `true` and `kind` is `boolean` or `enum` (label each option with its key and current value). Include an explicit "Nothing — just browsing" option to exit cleanly.
- Rows with a non-editable kind are shown for inventory only and are never
  offered as interactive choices.
- Rows with `kind: identity` are never offered — they aren't feature toggles (Step 2 already explains why).

**Question 2: New value?** (only if Question 1 selected a flag)
- For a `boolean` flag: options `true` / `false`.
- For an `enum` flag: options are exactly its `choices` from the inventory row, plus nothing else — never invent a value not in the row's `choices`.

Then run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/config_registry.py" --set <key> <value>
```

On success (`ok: true`), confirm the new value and mention the previous one (`previous`) if it was set. On failure (`ok: false`), render `error` and `fix` verbatim — do not paraphrase, especially for `local_config_tracked` (the fix is an exact `git rm --cached` command the user must run themselves) and `invalid_value` (the fix lists the exact allowed values).

## Notes

- Writes go through `config_registry.py`'s `--set`, which enforces the same tracked-file security invariant every other local-config writer in this codebase does (`agentic-engineering.local.md` is per-machine; a tracked copy is refused, never silently written through) and ensures `.gitignore` covers it before the first write.
- This command never writes `agentic-engineering.md` (committed board identity) — those rows are inventory-only. Board identity is managed by the lifecycle bootstrap, not here.
- Adding a new flag: declare it in the relevant plugin's `scripts/config_registry.py`; `tests/config-registry.test.ts` fails CI if a script reads a frontmatter key with no matching entry, so a flag can't ship invisibly.
