# Lifecycle Doctor

Setup-verification front door for the unified GitHub Projects v2 lifecycle. Run
it after install, after bootstrap, and before the first real work item. Its
default mode is read-only. `--live` creates a scratch issue, closes it, and must
remove its Project item.

## Step 1: Run the doctor verb

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --doctor
```

This returns JSON: `{"checks": [...], "ready": bool}`. Each entry in `checks`
has `check`, `status` (`PASS`/`WARN`/`FAIL`/`SKIP`), `detail`, and `fix` (empty
when not applicable). The checks share runtime validation helpers; a doctor
failure predicts a runtime hard error without making a trial write.

## Step 2: Render the report

Group the `checks` array into a table (columns: Check, Status, Detail, Fix) under these headings, in this order:

**Local toolchain** — `python`, `gh_installed`, `gh_version`, `gh_auth`, `host`, `project_scope`

**Repo shape** — `origin`, `issues_enabled`

**Board schema** — `board_config`, `board_write_access`, `status_options`,
`priority_field`, `item_closed_workflow`, `board_repo_link`,
`board_forward_binding`

**Delivery topology** — `default_branch_merges`

Use a status glyph per row (PASS ✅ / WARN ⚠️ / FAIL ❌ / SKIP ⏭️). Only checks actually present in the JSON are rendered — a check group may be short (e.g. board-schema checks are skipped entirely if `board_config` failed first).

Every row whose status is `FAIL` or `WARN` and carries a non-empty `fix` must have that fix rendered verbatim in the Fix column — never paraphrased or omitted.

## Step 3: Verdict

End the report with:

```
**Ready for first work item: yes/no**
```

sourced directly from the JSON's `ready` field (`ready: true` -> yes,
`ready: false` -> no). If `no`, list the specific FAIL rows again directly
beneath the verdict as the blocking punch list.

Readiness is strict for lifecycle adoption. A missing board, missing or unknown
`project` scope, unknown Project write access, invalid Status schema, disabled
Item-closed workflow, missing Priority field, missing canonical repository
link, or unconfigured forward binding blocks readiness. Do not reinterpret a
critical `WARN`, `SKIP`, or unknown result as ready; the JSON's `ready` value
already incorporates those critical checks.

## Step 4: `--live` (optional)

If `$ARGUMENTS` contains `--live`, after the read-only report above, also run the bootstrap probe:

```bash
python3 "<skill-directory>/scripts/bootstrap_lifecycle_board.py" --probe-only
```

This creates one scratch issue and verifies the configured forward binding
before checking close automation:

- `auto-add` waits for the issue to appear through the configured
  `add-to-project` workflow. It must not add the issue directly first; otherwise
  the secret, Project URL, event trigger, and workflow permission path would go
  untested. Run this only after the scaffold is merged to the default branch and
  its secret is provisioned; an earlier run fails safely rather than claiming
  the binding works.
- `workflow-only` exercises the lifecycle engine's normal item-add path.
- `none` records the explicit manual-binding limitation and exercises only the
  board automation that can be tested safely.

The probe closes the scratch issue, asserts that Status becomes `done`, removes
the exact item from the Project using the resolved Project owner and item ID,
then re-reads the issue to verify it is closed and no Project item remains.
Permanent issue deletion is not attempted: GitHub restricts it to repository
administrators or owners and an organization may disable it. The closed probe
issue remains as evidence unless an authorized operator optionally deletes it
later; readiness does not require that authority. Append the binding path,
issue number, observed Status transition, verified closed state, removed item
ID, re-read result, and pass/fail under a **Live probe** section. A failed probe,
timeout, close, or Project-item
removal/verification overrides an earlier read-only `ready: true`: render the
final **Ready for first work item: no** and return a failing result. Never report
`ok: true` for a failed mandatory probe step.

## Step 5: Configuration section (read-only)

```bash
python3 "<skill-directory>/scripts/config_registry.py" --inventory
```

Render a **Configuration** section beneath the board-health report, one row per flag: **SET** (`set: true`) or **UNSET** (`set: false`, showing the default in use). This is a different judgment from the PASS/WARN/FAIL/SKIP checks above — it reports what a repo has *chosen*, not whether the repo is healthy — so use the SET/UNSET vocabulary here, not the health glyphs. The one exception: a row whose `valid` is `false` (a stale or malformed override, e.g. `issue_tracker: linear`) renders as **⚠️ WARN — invalid, falling back to default** — this is the sole place WARN appears in this section, and it never changes the overall `ready` verdict from Step 3 (configuration state is not board health).

If `config_registry.py` is missing or `--inventory` fails, render "Configuration inventory unavailable" and continue — this section is best-effort and must never block the rest of the report.

To change a flag, run the `wf-setup` configuration route — this section is read-only.

## Step 6: Guidance — when to re-run

- After installing or upgrading the plugin
- After running or re-running [lifecycle bootstrap](lifecycle-bootstrap.md)
- After changing GitHub authentication or Project credentials
- After changing Project fields, workflows, links, or the forward binding
- After rotating `ADD_TO_PROJECT_PAT`, or when the auto-add workflow is red
- Before picking up the first real work item on a newly configured repo (this is the runbook's step 0)

The **forward binding** (how new issues reach the board) is a recorded decision,
so `board_forward_binding` validates the selected branch. `workflow-only`
requires no orphaned auto-add workflow. `auto-add` structurally validates the
issue-open trigger, exact configured user/org Project URL, pinned
`actions/add-to-project` action, and `ADD_TO_PROJECT_PAT` reference. A
write-only secret's value and expiry cannot be checked read-only, so only the
live probe proves the binding. `none` records a deliberate manual workflow; an
unrecognized or unrecorded value blocks readiness.

The ready-work saved view has no creation API and remains a manual verification
in [lifecycle bootstrap](lifecycle-bootstrap.md). Backfill is a one-time action,
not standing state: inspect its `failed` and `flags` results and rerun it after
any auto-add outage or newly discovered un-added open issues.

## Notes

- This command is read-only in its default (non-`--live`) form; it makes no board writes and creates nothing. The Configuration section (Step 5) is also read-only, always — it never writes, even under `--live`.
- `--live` is successful only when the chosen binding, close-to-`done`
  automation, issue close, and exact Project-item removal/verification all
  succeed. A mandatory cleanup failure leaves the issue and item identifiers in
  the evidence for safe, targeted recovery. Permanent deletion is not attempted
  and does not affect the verdict.
- The doctor's checks and runtime entry gates share validation helpers, so a
  clean doctor run is a reliable predictor of command behavior. The live probe
  adds the external Actions and automation behavior that reads alone cannot
  establish.
- The Configuration section shares its data source (`config_registry.py --inventory`) with the `wf-setup` configuration route — the two surfaces can never disagree about what's currently set, only about whether they report or let you act on it.
