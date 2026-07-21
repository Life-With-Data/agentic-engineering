# Adopt the GitHub Projects lifecycle

This is the authoritative setup journey for the seven-value GitHub Projects
lifecycle. Run it only after the repository capability contract passes. The
commands use scripts bundled with `wf-setup`; resolve `<skill-directory>` to the
directory containing its `SKILL.md`.

## 1. Establish access and ownership

The integration supports `github.com`, not GitHub Enterprise Server, and
requires `gh` 2.94.0 or newer. Start from a feature branch, unset CLI overrides
that could redirect writes, authenticate as the intended Project operator, and
verify the `project` OAuth scope:

```bash
git switch -c codex/adopt-agentic-lifecycle
unset GH_REPO GH_HOST
gh --version
gh auth status --hostname github.com
gh auth refresh --hostname github.com --scopes project
```

For an organization repository, the authenticated identity must also be
allowed by that organization to create a Project when no configured Project
exists, and to update the selected Project, its fields, workflows, and linked
repositories. Organizations can restrict PAT access and require administrator
approval of fine-grained PATs. Complete that approval before setup; when using
a classic PAT with a SAML-protected organization, explicitly authorize it for
SSO. A denied or pending credential must be fixed with the organization owner,
then doctor and the live probe must be rerun. Setup cannot bypass an
organization policy that prevents Project creation or mutation. Doctor's
Project write-access check is the final read-only confirmation that the current
viewer can update the selected Project.

Projects are owned by a user or organization, not by a repository. The
bootstrap derives the owner from the origin remote and creates or reuses that
owner's Project. One owner-level Project may be shared by several repositories;
runtime reads and writes still filter to the current origin repository. The
workflow scaffold uses the corresponding URL shape:

- user: `https://github.com/users/<owner>/projects/<number>`;
- organization: `https://github.com/orgs/<owner>/projects/<number>`.

Normally the Project owner must match the origin owner. Bootstrap run from a
personal fork creates only for that fork's owner; it must never infer authority
to create a Project for the canonical owner. To operate an existing canonical
Project from a trusted fork, first configure its exact
`github_project_owner` and `github_project_number` in `agentic-engineering.md`,
then verify the owner out of band and record the local trust decision:

```bash
git config agentic.trustedBoardOwners <canonical-owner>
```

This trust entry lives in the repository's Git config rather than a tracked
file, so an incoming pull request cannot authorize its own Project owner. Rerun
bootstrap only after both steps; it must resolve and verify that existing
Project, not create a canonical-owner Project from the fork's origin.

## 2. Choose how new issues reach the Project

Choose one forward binding before running bootstrap:

- `workflow-only` — recommended when the plugin workflows create and groom the
  work. The lifecycle engine adds items as it writes Status; no Actions secret
  is needed.
- `auto-add` — every newly opened issue should reach the Project, including
  issues created outside the plugin. Bootstrap scaffolds
  `.github/workflows/add-to-project.yml` and, when absent,
  `.github/dependabot.yml`; credential setup and a new-issue test remain manual.
- `none` — issues are placed on the Project manually. This is an explicit
  operating choice, not an unconfigured state.

The choice is committed as `github_project_forward_binding` and can be changed
by re-running bootstrap with a different value. Backfill is separate: a forward
binding affects new issues, never silently imports existing ones.

## 3. Bootstrap or safely migrate the Project

Run the bundled bootstrap with the selected binding:

```bash
python3 "<skill-directory>/scripts/bootstrap_lifecycle_board.py" \
  --forward-binding workflow-only
```

Replace `workflow-only` with `auto-add` or `none` when that was the deliberate
choice. The default probe is part of bootstrap; use `--no-probe` only to defer
live verification to a known later step.

This initial probe verifies Project writes and the Item-closed automation. It
does not prove a newly scaffolded `auto-add` binding: an issue-event workflow
cannot run until the scaffold is committed to the default branch and its secret
exists. Treat the later doctor `--live` run as the binding verification.

The command supports these inputs:

- no configured Project: create one for the origin owner;
- a fresh Project with GitHub's default Status options: convert it to the
  canonical seven values;
- an already canonical Project: verify and repair it idempotently;
- the plugin's legacy nine-value lifecycle or an interrupted migration from it:
  migrate items to `done` with a rollback snapshot in Git's common directory.

It deliberately refuses an unrelated customized Status schema rather than
overwriting a team's board. Stop on that error and choose a fresh dedicated
Project or obtain an explicit human decision about the existing board; do not
weaken or bypass the guard.

Read the complete JSON result before continuing. Require `ok: true`; inspect
`project`, `status_options`, `resulting_options`, `workflows`, `repo_link`,
`forward_binding`, `auto_add_scaffold`, `adoption_ready`, and every `warnings`
entry. The board-mechanics probe must report `PASS`, including successful
close and Project-item removal. For a newly scaffolded `auto-add` binding,
`adoption_ready: false` with forward-binding evidence `PENDING` is expected at
this point and is resolved only by the post-merge live probe. Any other false
result or warning remains unresolved work, not permission to declare setup
complete.

Bootstrap writes tracked repository configuration and may scaffold workflow
files. Review those diffs, run the repository's mapped test and security checks,
and commit and merge them through its normal branch and pull-request workflow.
For `auto-add`, merge the scaffold to the default branch and provision its
secret before running doctor `--live`. Never put a token value in configuration,
a workflow, an issue, command history, or a test fixture.

## 4. Provision auto-add credentials

Skip this section unless the forward binding is `auto-add`. The repository's
ordinary `GITHUB_TOKEN` cannot write a user- or organization-owned Project.
Provision `ADD_TO_PROJECT_PAT` as a GitHub Actions repository secret, or as an
organization Actions secret restricted to the selected repositories. Enter the
value only through the secret UI or an interactive command such as:

```bash
gh secret set ADD_TO_PROJECT_PAT --repo <owner>/<repo>
```

Use the least-privileged viable credential for the Project's owner type:

1. For an organization-owned Project, a fine-grained personal access token is
   the default: select the organization as resource owner, grant organization
   **Projects: Read and write**, restrict repository access to the consumer
   repository, and grant only **Issues: Read-only** and
   **Pull requests: Read-only** there (plus GitHub's implicit metadata read).
   Wait for organization approval when policy requires it.
2. A GitHub App installation token is the hardened organization option. Limit
   the installation to selected repositories and declare only the equivalent
   organization-Project write and repository read permissions. Its short-lived
   installation token must be minted for each run; adapt the scaffold's token
   input without broadening `GITHUB_TOKEN`.
3. For a user-owned Project, use the official action's classic PAT path with
   `project` and, for a private repository, `repo`. The same classic PAT is an
   account-wide fallback for an organization whose policies prevent the finer
   options. Prefer a dedicated machine account and explicitly authorize the PAT
   for organization SSO where SAML enforcement applies.

Set an expiry and an owner for rotation (about 90 days for a PAT). Doctor cannot
read a write-only secret or its expiry. An expired or revoked credential appears
as a red `add-to-project` workflow run; rotate the secret and re-run the failed
workflow rather than changing Project state by hand.

After the scaffold is merged and the secret exists, doctor `--live` creates one
disposable new issue. Verify its `add-to-project` workflow run succeeds and that
the issue appears on the configured Project without a direct `item-add`; the
probe then closes it, observes `done`, and removes and verifies the Project item.
Permanent issue deletion is not attempted because GitHub reserves it for
repository administrators/owners and organizations may disable it. The closed
probe issue remains as evidence unless an authorized operator optionally deletes
it later; live readiness never requires those elevated permissions. Failure to
verify the issue is closed or to remove and re-read the exact Project item still
fails readiness. This verifies the binding itself, not merely the workflow
file's presence. If live mode is unavailable, perform the same new-issue
verification manually and record its cleanup.

## 5. Deliberately backfill existing issues

Bootstrap never imports existing issues. If open issues should join the board,
run the idempotent backfill separately:

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --backfill
```

Review `counts`, `added`, `already_present`, `failed`, `flags`, and the advisory
high-water marker in its JSON. Any failed item or `backfill_truncated` flag means
the import is incomplete; correct the reported access or enumeration problem
and re-run. Backfill recomputes the open-issue difference every time, so it is
safe recovery after a partial run. It does not assign readiness: newly added
items still require the appropriate lifecycle Status.

## 6. Create the ready-work view

In the Project UI, create and save a view filtered by:

```text
status:planned no:assignee
```

Sort it by `Priority`. GitHub's view filter cannot express "has no open
blocked-by dependency," so treat it as a candidate queue: the engine's
`--ready-work` and `--claim` checks remain authoritative before work starts.

## 7. Verify and finish

Run the read-only engine check, then invoke the `wf-setup` doctor route with
`--live` (the route performs the second command below) as described in
[lifecycle doctor](lifecycle-doctor.md):

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --doctor
python3 "<skill-directory>/scripts/bootstrap_lifecycle_board.py" --probe-only
```

Live verification must test the chosen
forward binding before checking the close-to-`done` automation and must clean up
its scratch issue. A failed probe or cleanup makes the final verdict not ready,
even if the earlier read-only checks passed.

Lifecycle setup is complete only when:

1. bootstrap returned `ok: true`, its probe passed and cleaned up, and every
   warning has been resolved or explicitly accepted by the operator;
2. the canonical seven Status options, Priority field, repository link, and
   built-in Item-closed workflow pass doctor;
3. the chosen forward binding is configured and live-verified (`none` requires
   an explicit manual-operating decision);
4. tracked config and scaffolds have passed the repository's normal review and
   delivery process and reached the default branch before `auto-add` live
   verification, while credentials exist only in the approved secret store;
5. any requested backfill completed without failures or truncation, and the
   ready-work saved view exists; and
6. both read-only doctor and `--live` finish with
   `Ready for first work item: yes`.

## Day-two operation and recovery

Re-run doctor after plugin upgrades, board-field or Project-workflow changes,
repository transfers, forward-binding changes, authentication or secret
rotation, and before the first real item in a newly configured repository. Run
it during investigation whenever lifecycle commands hard-error.

For `auto-add`, a red workflow is the primary signal for an expired token,
missing secret, organization approval change, or Project permission loss.
Inspect the failed run without exposing secret values, restore the credential,
verify with a new disposable issue, and run backfill to recover any open issues
missed while the workflow was broken. Backfill reports partial failures and is
safe to repeat; its high-water marker is advisory, not proof of completeness.

If bootstrap or legacy migration stops, preserve its JSON and rollback snapshot,
fix the named permission or schema problem, and re-run the idempotent command.
Do not manually rename options mid-recovery or delete the snapshot before the
canonical board and live probe are verified.
