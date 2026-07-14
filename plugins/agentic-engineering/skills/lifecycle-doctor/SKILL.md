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

**Board schema** — `board_config`, `status_options`, `priority_field`, `board_repo_link`, `board_forward_binding`

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

This creates one scratch issue, adds it to the board, closes it, asserts the Status flips to `shipped`, then deletes the scratch issue — it needs `project` scope (see `project_scope` above). Append its evidence (issue number created/deleted, observed Status transition, pass/fail) to the report under a **Live probe** section.

## Step 5: Configuration section (read-only)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/config_registry.py" --inventory
```

Render a **Configuration** section beneath the board-health report, one row per flag: **SET** (`set: true`) or **UNSET** (`set: false`, showing the default in use). This is a different judgment from the PASS/WARN/FAIL/SKIP checks above — it reports what a repo has *chosen*, not whether the repo is healthy — so use the SET/UNSET vocabulary here, not the health glyphs. The one exception: a row whose `valid` is `false` (a stale or malformed override, e.g. `issue_tracker: linear`) renders as **⚠️ WARN — invalid, falling back to default** — this is the sole place WARN appears in this section, and it never changes the overall `ready` verdict from Step 3 (configuration state is not board health).

If `config_registry.py` is missing or `--inventory` fails, render "Configuration inventory unavailable" and continue — this section is best-effort and must never block the rest of the report.

To change a flag, run `/config-flags` — this section is read-only.

## Step 6: Guidance — when to re-run

- After installing or upgrading the plugin
- After running the setup bootstrap (Phase 4) or re-running it
- After changing tokens, PAT/App credentials, or CD/deploy wiring
- Before picking up the first real work item on a newly configured repo (this is the runbook's step 0)

The **forward binding** (how new issues reach the board) is now a recorded decision, so the `board_forward_binding` check verifies it concretely per branch: `workflow-only` PASSes when no orphaned auto-add workflow exists; `auto-add` checks that `.github/workflows/add-to-project.yml` is present (bootstrap scaffolds it, SHA-pinned, when `auto-add` is chosen; its token secret is write-only, so that one bit stays unverifiable and is called out in the detail — and the separate `board_repo_link` row covers the link); `none` is informational; an unrecognized or unrecorded value WARNs. The one remaining no-API step is the **ready-work saved view** — verify it by hand in the Project's UI, following the setup skill. Backfill (a one-time action, not standing state) is not asserted here; re-run `lifecycle_board.py --backfill` when new un-added issues exist.

## Notes

- This command is read-only in its default (non-`--live`) form; it makes no board writes and creates nothing. The Configuration section (Step 5) is also read-only, always — it never writes, even under `--live`.
- The doctor's checks and the runtime commands' entry-gate hard errors share one implementation (`lifecycle_board.py`), so a clean doctor run is a reliable predictor of command behavior — there is no separate "doctor logic" to drift out of sync.
- The Configuration section shares its data source (`config_registry.py --inventory`) with `/config-flags` — the two surfaces can never disagree about what's currently set, only about whether they report or let you act on it.
