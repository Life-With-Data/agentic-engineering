---
name: lifecycle-doctor
description: Verify lifecycle-board setup and repo compatibility before the first work item — checks toolchain, repo shape, board schema, and delivery topology
argument-hint: "[--live]"
allowed-tools: Read, Bash(gh *), Bash(python3 *), Bash(git *), Bash(jq *)
---

# Lifecycle Doctor

Setup-verification front door for the unified GitHub Projects v2 lifecycle. Run it after install, after bootstrap, and any time before the first real work item — it never mutates the board (except under `--live`, which cleans up after itself).

## Step 1: Run the doctor verb

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --doctor
```

This returns JSON: `{"checks": [...], "ready": bool}`. Each entry in `checks` has `check`, `status` (`PASS`/`WARN`/`FAIL`/`SKIP`), `detail`, and `fix` (empty when not applicable). These are the **same check functions the runtime hard-error paths call** — doctor and commands can never disagree about repo readiness.

## Step 2: Render the report

Group the `checks` array into a table (columns: Check, Status, Detail, Fix) under these headings, in this order:

**Local toolchain** — `python`, `gh_installed`, `gh_version`, `gh_auth`, `host`, `project_scope`

**Repo shape** — `origin`, `issues_enabled`

**Board schema** — `board_config`, `status_options`, `priority_field`

**Delivery topology** — `default_branch_merges`, `deployments`

Use a status glyph per row (PASS ✅ / WARN ⚠️ / FAIL ❌ / SKIP ⏭️). Only checks actually present in the JSON are rendered — a check group may be short (e.g. board-schema checks are skipped entirely if `board_config` failed first).

Every row whose status is `FAIL` or `WARN` and carries a non-empty `fix` must have that fix rendered verbatim in the Fix column — never paraphrased or omitted.

## Step 3: Verdict

End the report with:

```
**Ready for first work item: yes/no**
```

sourced directly from the JSON's `ready` field (`ready: true` → yes, `ready: false` → no). If `no`, list the specific FAIL rows again directly beneath the verdict as the blocking punch list.

## Step 4: `--live` (optional)

If `$ARGUMENTS` contains `--live`, after the read-only report above, also run the bootstrap probe:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap_lifecycle_board.py" --probe-only
```

This creates one scratch issue, adds it to the board, closes it, asserts the Status flips to `shipped`, then deletes the scratch issue — it needs `project` scope (see `project_scope` above). Append its evidence (issue number created/deleted, observed Status transition, pass/fail) to the report under a **Live probe** section. If the script is not yet present in this checkout, report that plainly (`--live probe unavailable: bootstrap_lifecycle_board.py not found`) rather than failing the whole command — the base report from Step 1–3 still stands on its own.

## Step 5: Guidance — when to re-run

- After installing or upgrading the plugin
- After running the setup bootstrap (Phase 4) or re-running it
- After changing tokens, PAT/App credentials, or CD/deploy wiring
- Before picking up the first real work item on a newly configured repo (this is the runbook's step 0)

For any `SKIP` row (auto-add config, saved view), point at the manual checklist in the setup skill — these two steps have no API and must be verified by hand in the Project's UI. Secrets are unreadable by design: a `SKIP` on deploy-credential-shaped checks means "verify in repo settings," not a failure.

## Notes

- This command is read-only in its default (non-`--live`) form; it makes no board writes and creates nothing.
- The doctor's checks and the runtime commands' entry-gate hard errors share one implementation (`lifecycle_board.py`), so a clean doctor run is a reliable predictor of command behavior — there is no separate "doctor logic" to drift out of sync.
