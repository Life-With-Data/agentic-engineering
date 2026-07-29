# Adopt the GitHub Projects lifecycle

The authoritative setup journey for the eight-value GitHub Projects lifecycle.
Run it only after the repository capability contract passes. Scripts are
bundled with `wf-setup`; resolve `<skill-directory>` to its directory.

## 1. Establish access and ownership

Requires `github.com` (not GHES) and `gh` 2.94.0+. From a feature branch:

```bash
git switch -c codex/adopt-agentic-lifecycle
unset GH_REPO GH_HOST
gh --version
gh auth status --hostname github.com
gh auth refresh --hostname github.com --scopes project
```

For an organization repository the identity must be allowed to create/update
the Project; complete any PAT approval (and SAML SSO authorization for classic
PATs) before setup — bootstrap cannot bypass organization policy. Doctor's
Project write-access check is the final read-only confirmation.

Projects are owned by a user or organization, not a repository; bootstrap
derives the owner from the origin remote. Normally the Project owner must
match the origin owner — bootstrap from a fork creates only for the fork's
owner. To operate a canonical Project from a trusted fork, configure its exact
`github_project_owner`/`github_project_number` in `agentic-engineering.md`,
verify the owner out of band, and record the trust decision locally (so an
incoming PR cannot authorize its own Project owner):

```bash
git config agentic.trustedBoardOwners <canonical-owner>
```

## 2. Choose how new issues reach the Project

Pick one forward binding:

- `workflow-only` — recommended; the lifecycle engine adds items as it writes
  Status. No Actions secret needed.
- `auto-add` — every new issue reaches the Project, including ones created
  outside the plugin. Bootstrap scaffolds
  `.github/workflows/add-to-project.yml`; credentials and a new-issue test
  remain manual.
- `none` — issues are placed manually. An explicit operating choice, not an
  unconfigured state.

Committed as `github_project_forward_binding`; change it by re-running
bootstrap. Backfill is separate — a forward binding affects new issues, never
silently imports existing ones.

## 3. Bootstrap or safely migrate the Project

```bash
python3 "<skill-directory>/scripts/bootstrap_lifecycle_board.py" \
  --forward-binding workflow-only
```

The default probe is part of bootstrap; `--no-probe` only defers live
verification to a known later step. The probe verifies Project writes and the
Item-closed automation — it cannot prove a newly scaffolded `auto-add`
binding (the workflow can't run until merged to the default branch with its
secret provisioned); doctor `--live` is that binding's verification.

The command idempotently handles: no Project (creates one), a fresh default
Project (converts to the canonical eight values), an already-canonical or
pre-`ready_for_work` board (repairs, adding missing options without
renumbering), and the legacy nine-value lifecycle (migrates with a rollback
snapshot). It deliberately refuses an unrelated customized Status schema —
stop on that error and get an explicit human decision; never weaken the guard.

Read the full JSON result. Require `ok: true`; the board-mechanics probe must
report `PASS`. For a newly scaffolded `auto-add` binding,
`adoption_ready: false` with forward-binding evidence `PENDING` is the
expected result at this point — that one pending item is resolved by the
post-merge live probe. Any *other* false result or warning is unresolved work,
not permission to declare setup complete.

Bootstrap writes tracked config and may scaffold workflow files: review the
diffs, run the mapped checks, and merge through the normal PR workflow. Never
put a token value in configuration, a workflow, an issue, or a fixture.

## 4. Provision auto-add credentials

Skip unless the binding is `auto-add`. `GITHUB_TOKEN` cannot write a user- or
org-owned Project. Provision `ADD_TO_PROJECT_PAT` as an Actions secret, via
the secret UI or:

```bash
gh secret set ADD_TO_PROJECT_PAT --repo <owner>/<repo>
```

Least-privileged options, in order:

1. Org-owned Project: fine-grained PAT — org **Projects: Read and write**,
   repository access restricted to the consumer repo with Issues/PRs
   read-only. Wait for org approval where required.
2. Hardened org option: a GitHub App installation token, limited to selected
   repositories with the equivalent permissions.
3. User-owned Project: the official action's classic PAT path (`project`,
   plus `repo` for private repositories); also the fallback for restrictive
   orgs. Prefer a machine account; authorize for SSO where SAML applies.

Set an expiry and rotation owner (~90 days). An expired credential shows as a
red `add-to-project` run — rotate the secret and re-run the workflow rather
than changing Project state by hand.

After the scaffold merges and the secret exists, doctor `--live` creates one
disposable issue, verifies the workflow adds it to the Project without a
direct `item-add`, closes it, observes `done`, and removes and verifies the
item. Permanent issue deletion is not attempted (admin-reserved); the closed
probe issue remains as evidence. If live mode is unavailable, perform the same
new-issue verification manually and record its cleanup.

## 5. Deliberately backfill existing issues

Bootstrap never imports existing issues:

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --backfill
```

Review its JSON (`counts`, `added`, `skipped_sub_issues`, `failed`, `flags`).
Sub-issues are excluded by design — only parents belong on the board. Any
failure or `backfill_truncated` flag means an incomplete import; fix and
re-run (it recomputes the difference each time). Backfill does not assign
readiness.

## 6. Create the ready-work view

In the Project UI, save a view filtered by:

```text
status:ready_for_work no:assignee
```

sorted by `Priority`. The filter cannot express "no open blocked-by", so it is
a candidate queue — `--ready-work` and `--claim` remain authoritative.

## 7. Verify and finish

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --doctor
python3 "<skill-directory>/scripts/bootstrap_lifecycle_board.py" --probe-only
```

Run doctor `--live` per [lifecycle doctor](lifecycle-doctor.md); it must test
the chosen forward binding, check the close-to-`done` automation, and clean up
its scratch issue. Setup is complete only when:

1. bootstrap returned `ok: true`, its probe passed, and every warning is
   resolved or explicitly accepted;
2. the eight Status options, Priority field, repo link, and Item-closed
   workflow pass doctor;
3. the forward binding is configured and live-verified (`none` requires the
   explicit manual-operating decision);
4. tracked config and scaffolds reached the default branch through normal
   review before `auto-add` live verification, with credentials only in the
   secret store;
5. any requested backfill completed without failures or truncation, and the
   ready-work view exists; and
6. both read-only doctor and `--live` finish with
   `Ready for first work item: yes`.

## Day-two operation and recovery

**A plugin upgrade that adds a lifecycle stage:** `resolve_schema` refuses a
board missing the new option (`option_missing`) — deliberate, not a
regression. Re-run the idempotent bootstrap (adds only missing options,
preserves IDs, moves nothing), then confirm with `--doctor`. The
`ready_for_work` stage was added this way.

Re-run doctor after plugin upgrades, board or Project-workflow changes,
repository transfers, binding changes, auth/secret rotation, before the first
real item, and whenever lifecycle commands hard-error.

For `auto-add`, a red workflow is the primary signal for an expired token or
permission loss: restore the credential, verify with a disposable issue, and
run backfill to recover missed issues. If bootstrap or migration stops,
preserve its JSON and rollback snapshot, fix the named problem, and re-run;
never manually rename options mid-recovery or delete the snapshot before the
board and live probe verify.
