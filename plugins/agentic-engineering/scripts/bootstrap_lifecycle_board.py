#!/usr/bin/env python3
"""Bootstrap the unified lifecycle GitHub Projects v2 board (Phase 4).

Hosted by the setup skill, but a *script* so it is testable. Creates (or
idempotently re-configures) the Projects v2 board that
`lifecycle_board.py` reads and writes, then wires the built-in automations
that make `shipped` a zero-UI stamp.

The whole flow, in order (see the plan's Phase 4 bootstrap bullet):
  1. Preconditions — refuse `GH_REPO`/`GH_HOST` overrides; gh >= 2.94.0;
     gh authenticated; derive `--owner` from the ORIGIN remote owner (never
     `@me`, which on an org repo makes a user-owned project the plugin's own
     owner-check then rejects).
  2. Resolve-or-create the project. If the committed config already names a
     project, operate on it (idempotent re-run); else `gh project create`.
  3. Read the Status field + current options.
  4. Fresh-project guard: hard-stop with a printed diff unless the option set
     is exactly GitHub's defaults {Todo, In Progress, Done} or exactly the
     canonical 9 — never mutate a customized team board.
  5. ONE `updateProjectV2Field` mutation sending ALL 9 options with existing
     option IDs attached (Todo->stub, In Progress->in_progress, Done->shipped
     keep their ids; new options are id-less; on a canonical re-run every
     option keeps its id). Sending options without ids silently disables the
     five pre-enabled Status workflows and orphans item values — verified
     destructive, hence the idempotency rule.
  6. Create the Priority single-select field (p1/p2/p3) if absent.
  7. Disable the "Item reopened" workflow (`deleteProjectV2Workflow`) — it
     would stamp `stub` on reopen, erasing lifecycle position. Verify
     "Item closed" is enabled (WARN if not).
  7b. Link the board to the origin repo (idempotent; non-fatal) so it appears
     on the repo's Projects tab. Projects v2 boards are owned by a user/org —
     linking is the only repo-level association there is. NOTE: linking does not
     auto-add issues; how NEW issues reach the board is the explicit forward-
     binding decision recorded in step 8 (issue #64).
  8. Write/refresh the COMMITTED `agentic-engineering.md` — board identity (two
     keys) AND the forward-binding decision (`--forward-binding`, default
     workflow-only) in ONE write, so identity is never recorded without policy.
     Existing content is preserved byte-for-byte. Backfilling EXISTING issues
     (decision B) is the SEPARATE `lifecycle_board.py --backfill` command — it
     is never run here, so bootstrap never mutates issues onto the board
     unattended.
  9. Scripted probe (--probe, default ON): scratch issue -> board-add ->
     Status=stub -> close -> poll <=60s for the automation to stamp shipped
     -> report PASS/FAIL -> delete the scratch issue.
 10. Emit a JSON summary.

Conventions mirror lifecycle_board.py exactly: the {ok, error_code, error,
fix} error contract, an injected `run_gh` seam for tests, stdlib-only,
Python >= 3.9. lifecycle_board is imported (never modified) for STAGES,
BoardError, repo_context, parse_frontmatter, and the run_gh pattern.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

# --------------------------------------------------------------------------
# Import lifecycle_board (sibling module) — never modify it. Mirrors the
# importlib pattern the tests use so this works whether or not `scripts/` is
# on sys.path.
# --------------------------------------------------------------------------

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import lifecycle_board as lb  # noqa: E402

BoardError = lb.BoardError
STAGES = lb.STAGES
COMMITTED_CONFIG = lb.COMMITTED_CONFIG
MIN_GH_VERSION = lb.MIN_GH_VERSION
GhRunner = lb.GhRunner


# --------------------------------------------------------------------------
# Canonical option shape: name -> (color, description). Order is the STAGES
# order (the mutation preserves it). Colors per the plan's mapping.
# --------------------------------------------------------------------------

_STAGE_COLOR = {
    "stub": "GRAY",
    "brainstormed": "BLUE",
    "planned": "BLUE",
    "in_progress": "YELLOW",
    "in_review": "ORANGE",
    "shipped": "GREEN",
    "deployed": "GREEN",
    "compounded": "PURPLE",
    "abandoned": "RED",
}
_STAGE_DESCRIPTION = {
    "stub": "New/un-groomed work item",
    "brainstormed": "Requirements explored",
    "planned": "Plan doc written; ready to work",
    "in_progress": "Claimed and being implemented",
    "in_review": "PR open, under review",
    "shipped": "Merged to the default branch",
    "deployed": "Reached production (high-water mark)",
    "compounded": "Learnings captured",
    "abandoned": "Closed as not planned",
}

# GitHub's fresh-project defaults, and how they map onto our canonical stages
# (ID-preserving). Any option NOT in this map that survives from a default
# project simply gets a new, id-less canonical option appended.
_DEFAULT_TO_CANONICAL = {
    "Todo": "stub",
    "In Progress": "in_progress",
    "Done": "shipped",
}
_DEFAULT_OPTION_NAMES = frozenset(_DEFAULT_TO_CANONICAL)          # {Todo, In Progress, Done}
_CANONICAL_OPTION_NAMES = frozenset(STAGES)                       # the 9 stages

PRIORITY_FIELD_NAME = "Priority"
PRIORITY_OPTIONS = ("p1", "p2", "p3")

REOPENED_WORKFLOW = "Item reopened"
CLOSED_WORKFLOW = "Item closed"

# Auto-add scaffold (issue #63). When the forward binding is `auto-add`, write a
# GitHub Actions workflow using the official actions/add-to-project so new issues
# reach the board (the built-in auto-add has no create API). Pinned to a full
# commit SHA (supply-chain: a moving @v2 tag runs with ADD_TO_PROJECT_PAT in
# scope) — resolved live at scaffold time, falling back to this known-good SHA.
ADD_TO_PROJECT_REPO = "actions/add-to-project"
ADD_TO_PROJECT_PINNED_SHA = "5afcf98fcd03f1c2f92c3c83f58ae24323cc57fd"  # v2.0.0
ADD_TO_PROJECT_PINNED_REF = "v2.0.0"
ADD_TO_PROJECT_SECRET = "ADD_TO_PROJECT_PAT"
WORKFLOW_FILENAME = ".github/workflows/add-to-project.yml"
DEPENDABOT_FILENAME = ".github/dependabot.yml"

PROBE_TITLE = "[lifecycle-bootstrap probe]"
PROBE_POLL_SECONDS = 60
PROBE_POLL_INTERVAL = 3


# --------------------------------------------------------------------------
# Effect seam (injected in tests) — the two scripts share one subprocess
# implementation and one gh-missing error via lifecycle_board.run_gh directly.
# --------------------------------------------------------------------------

def _check(result: "subprocess.CompletedProcess[str]", code: str, what: str, fix: str) -> dict:
    """Assert a gh call succeeded, else raise the board error contract, and
    parse its stdout as JSON (empty -> {})."""
    if result.returncode != 0:
        raise BoardError(code, f"{what} failed: {result.stderr.strip()[:200]}", fix)
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise BoardError(code, f"{what}: could not parse gh JSON output", fix) from exc


# --------------------------------------------------------------------------
# 1. Preconditions
# --------------------------------------------------------------------------

def check_env_overrides(environ: "Optional[dict]" = None) -> None:
    """Refuse to run with GH_REPO/GH_HOST set — they would silently redirect
    every gh call away from the origin-derived owner and host."""
    environ = environ if environ is not None else os.environ
    present = [name for name in ("GH_REPO", "GH_HOST") if environ.get(name)]
    if present:
        raise BoardError(
            "env_override_present",
            f"Refusing to bootstrap with {', '.join(present)} set — these override "
            "the origin-derived owner/host and can redirect writes to the wrong board",
            f"Unset {' and '.join(present)} (e.g. `unset {' '.join(present)}`), then re-run",
        )


def check_gh_version(runner: GhRunner) -> "tuple[int, ...]":
    result = runner(["--version"])
    m = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", result.stdout or "")
    version = tuple(int(g) for g in m.groups()) if m else (0, 0, 0)
    if version < MIN_GH_VERSION:
        raise BoardError(
            "gh_too_old",
            f"gh {'.'.join(map(str, version))} is older than the required "
            f"{'.'.join(map(str, MIN_GH_VERSION))}",
            "Upgrade gh (e.g. `brew upgrade gh`)",
        )
    return version


def check_gh_authenticated(runner: GhRunner) -> None:
    auth = runner(["auth", "status"])
    if auth.returncode != 0:
        raise BoardError("gh_unauthenticated", "gh is not authenticated",
                         "Run `gh auth login`, then `gh auth refresh -s project`")


_PROJECT_SCOPE_HINT = "Grant the project scope: `gh auth refresh -s project`"


# --------------------------------------------------------------------------
# 2. Resolve-or-create the project
# --------------------------------------------------------------------------

@dataclass
class Project:
    number: int
    id: str
    created: bool


def resolve_or_create_project(ctx: "lb.RepoContext", runner: GhRunner) -> Project:
    """If the committed config already names a project, operate on it
    (idempotent). Else create a new one owned by the ORIGIN owner."""
    owner = ctx.origin_owner
    if not owner:
        raise BoardError("origin_unresolved",
                         "Could not derive the project owner from the origin remote",
                         "Add an `origin` remote pointing at your GitHub repo")

    existing = lb.read_board_config(ctx)  # enforces owner==origin / allowlist
    if existing is not None:
        view = runner(["project", "view", str(existing.number), "--owner", existing.owner,
                       "--format", "json"])
        payload = _check(view, "project_not_found",
                         f"reading existing project {existing.owner}/{existing.number}",
                         "Verify the project still exists, or remove its entry from "
                         f"{COMMITTED_CONFIG} to create a fresh one; " + _PROJECT_SCOPE_HINT)
        return Project(number=existing.number, id=payload.get("id", ""), created=False)

    title = f"{ctx.origin_repo} lifecycle"
    create = runner(["project", "create", "--owner", owner, "--title", title, "--format", "json"])
    payload = _check(create, "project_create_failed", f"creating project {title!r} under {owner}",
                     "Verify the `project` scope and that you can create projects under "
                     f"{owner}; " + _PROJECT_SCOPE_HINT)
    number = payload.get("number")
    if number is None:
        raise BoardError("project_create_failed", "project create returned no number",
                         "Retry; if persistent, create the project manually and record it "
                         f"in {COMMITTED_CONFIG}")
    return Project(number=int(number), id=payload.get("id", ""), created=True)


# --------------------------------------------------------------------------
# 3. Read the Status field + current options
# --------------------------------------------------------------------------

@dataclass
class StatusField:
    field_id: str
    options: "list[dict]"   # each {id, name} in board order


def read_status_field(project: Project, ctx: "lb.RepoContext", runner: GhRunner) -> StatusField:
    result = runner(["project", "field-list", str(project.number), "--owner", ctx.origin_owner,
                     "--format", "json"])
    payload = _check(result, "project_not_found",
                     f"reading fields of project {ctx.origin_owner}/{project.number}",
                     "Verify the project exists and gh has the `project` scope; " + _PROJECT_SCOPE_HINT)
    status, _priority = lb.parse_field_list(payload)
    if not status:
        raise BoardError("option_missing", "Project has no built-in Status field",
                         "Recreate the project (the built-in Status field is created automatically)")
    options = [{"id": o.get("id", ""), "name": o.get("name", "")} for o in status.get("options", [])]
    return StatusField(field_id=status.get("id", ""), options=options)


# --------------------------------------------------------------------------
# 4. Fresh-project guard
# --------------------------------------------------------------------------

def assert_fresh_or_canonical(status: StatusField) -> str:
    """Return "default" or "canonical". Hard-stop with a printed diff on any
    other option set — never mutate a customized team board."""
    names = [o["name"] for o in status.options]
    nameset = frozenset(names)
    if nameset == _DEFAULT_OPTION_NAMES:
        return "default"
    if nameset == _CANONICAL_OPTION_NAMES:
        return "canonical"
    diff = _option_diff(names)
    raise BoardError(
        "unrecognized_project",
        "Refusing to reconfigure this board: its Status options are neither GitHub's "
        "fresh-project defaults nor the canonical lifecycle set, so the replace-all "
        "mutation would silently destroy existing options/automations.\n" + diff,
        "Point the bootstrap at a fresh project (empty/default Status options) or at a "
        "board previously bootstrapped by this tool; never adopt a customized team board",
    )


def _option_diff(names: "list[str]") -> str:
    have = sorted(names)
    expected_default = sorted(_DEFAULT_OPTION_NAMES)
    expected_canonical = list(STAGES)
    return (
        f"  current options : {have}\n"
        f"  expected (fresh): {expected_default}\n"
        f"  expected (ours) : {expected_canonical}"
    )


# --------------------------------------------------------------------------
# 5. The ID-preserving updateProjectV2Field mutation
# --------------------------------------------------------------------------

# NOTE: the options list is inlined into the mutation document as a GraphQL
# literal rather than passed as a variable — `gh api graphql -f` can only carry
# string variables, and there is no flag for a nested list-of-objects (verified
# live: the string form is rejected as an invalid ProjectV2SingleSelectFieldOptionInput).
# json.dumps escaping is valid GraphQL string escaping; enum colors are unquoted.
UPDATE_FIELD_MUTATION = (
    "mutation($fieldId: ID!) {\n"
    "  updateProjectV2Field(input: {fieldId: $fieldId, singleSelectOptions: __OPTIONS__}) {\n"
    "    projectV2Field {\n"
    "      ... on ProjectV2SingleSelectField {\n"
    "        id\n"
    "        options { id name }\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "}"
)


def build_option_mapping(status: StatusField, kind: str) -> "list[dict]":
    """The full 9-option list in STAGES order, each carrying an existing
    option id where one can be preserved.

    - kind == "default": map Todo->stub, In Progress->in_progress, Done->shipped
      (those three keep their ids); the other six are new and id-less.
    - kind == "canonical": every option already exists by its canonical name,
      so every one keeps its id (idempotent re-run — never a partial/id-less list).
    """
    if kind == "canonical":
        by_name = {o["name"]: o["id"] for o in status.options}
    else:  # default
        by_name = {}
        for o in status.options:
            canonical = _DEFAULT_TO_CANONICAL.get(o["name"])
            if canonical:
                by_name[canonical] = o["id"]

    mapping: "list[dict]" = []
    for stage in STAGES:
        option: "dict[str, str]" = {}
        existing_id = by_name.get(stage)
        if existing_id:
            option["id"] = existing_id
        option["name"] = stage
        option["color"] = _STAGE_COLOR[stage]
        option["description"] = _STAGE_DESCRIPTION[stage]
        mapping.append(option)
    return mapping


def _options_graphql_literal(options: "list[dict]") -> str:
    """Serialize the options as a GraphQL input literal. `id` is included only
    where preserved (the destructive id-less list is the one foot-gun); colors
    are enum literals (unquoted); strings use json.dumps escaping (a valid
    GraphQL string escape)."""
    parts = []
    for o in options:
        fields = []
        if o.get("id"):
            fields.append(f'id: {json.dumps(o["id"])}')
        fields.append(f'name: {json.dumps(o["name"])}')
        fields.append(f'color: {o["color"]}')
        fields.append(f'description: {json.dumps(o.get("description", ""))}')
        parts.append("{" + ", ".join(fields) + "}")
    return "[" + ", ".join(parts) + "]"


def apply_status_options(status: StatusField, options: "list[dict]", runner: GhRunner) -> "list[dict]":
    """ONE updateProjectV2Field call, with the options inlined as a GraphQL
    literal (gh api graphql has no transport for list-of-object variables)."""
    document = UPDATE_FIELD_MUTATION.replace("__OPTIONS__", _options_graphql_literal(options))
    result = runner([
        "api", "graphql",
        "-f", f"query={document}",
        "-f", f"fieldId={status.field_id}",
    ])
    payload = _check(result, "board_write_failed", "updateProjectV2Field (Status options)",
                     "Verify the `project` scope and board write permission (viewerCanUpdate); "
                     + _PROJECT_SCOPE_HINT)
    field = (((payload.get("data") or {}).get("updateProjectV2Field") or {})
             .get("projectV2Field") or {})
    return field.get("options", [])


# --------------------------------------------------------------------------
# 6. Priority field
# --------------------------------------------------------------------------

def ensure_priority_field(project: Project, ctx: "lb.RepoContext", runner: GhRunner) -> dict:
    """Create the Priority single-select field (p1/p2/p3) if absent. Returns
    {created: bool, field_id: str|None}."""
    listing = runner(["project", "field-list", str(project.number), "--owner", ctx.origin_owner,
                      "--format", "json"])
    payload = _check(listing, "project_not_found", "re-reading fields for Priority check",
                     "Verify the project exists and the `project` scope; " + _PROJECT_SCOPE_HINT)
    _status, priority = lb.parse_field_list(payload)
    if priority:
        return {"created": False, "field_id": priority.get("id")}

    create = runner(["project", "field-create", str(project.number), "--owner", ctx.origin_owner,
                     "--name", PRIORITY_FIELD_NAME, "--data-type", "SINGLE_SELECT",
                     "--single-select-options", ",".join(PRIORITY_OPTIONS), "--format", "json"])
    created = _check(create, "board_write_failed", "creating the Priority field",
                     "Verify the `project` scope and board write permission; " + _PROJECT_SCOPE_HINT)
    return {"created": True, "field_id": created.get("id")}


# --------------------------------------------------------------------------
# 7. Workflows: disable "Item reopened", verify "Item closed"
# --------------------------------------------------------------------------

# repositoryOwner resolves BOTH User and Organization logins — querying
# organization(login:) for a user account is a hard GraphQL error (verified
# live: "Could not resolve to an Organization"), so a two-holder query fails
# for every user-owned project.
WORKFLOWS_QUERY = (
    "query($owner: String!, $number: Int!) {\n"
    "  repositoryOwner(login: $owner) {\n"
    "    ... on User {\n"
    "      projectV2(number: $number) {\n"
    "        workflows(first: 20) { nodes { id name enabled } }\n"
    "      }\n"
    "    }\n"
    "    ... on Organization {\n"
    "      projectV2(number: $number) {\n"
    "        workflows(first: 20) { nodes { id name enabled } }\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "}"
)

DELETE_WORKFLOW_MUTATION = (
    "mutation($workflowId: ID!) {\n"
    "  deleteProjectV2Workflow(input: {workflowId: $workflowId}) { clientMutationId }\n"
    "}"
)


def query_workflows(project: Project, ctx: "lb.RepoContext", runner: GhRunner) -> "list[dict]":
    """Query the project's workflows. The owner may be a User or an
    Organization; we ask for both and take whichever resolved."""
    result = runner([
        "api", "graphql",
        "-f", f"query={WORKFLOWS_QUERY}",
        "-F", f"owner={ctx.origin_owner}", "-F", f"number={project.number}",
    ])
    payload = _check(result, "board_read_failed", "querying project workflows",
                     "Verify the `project` scope; " + _PROJECT_SCOPE_HINT)
    data = payload.get("data") or {}
    node = ((data.get("repositoryOwner") or {}).get("projectV2") or {})
    nodes = (node.get("workflows") or {}).get("nodes")
    if nodes:
        return [{"id": w.get("id", ""), "name": w.get("name", ""),
                 "enabled": bool(w.get("enabled"))} for w in nodes]
    return []


def configure_workflows(project: Project, ctx: "lb.RepoContext", runner: GhRunner) -> dict:
    """Disable "Item reopened" (deleteProjectV2Workflow) if present+enabled;
    WARN if "Item closed" is not enabled."""
    workflows = query_workflows(project, ctx, runner)
    by_name = {w["name"]: w for w in workflows}

    reopened_disabled = False
    reopened = by_name.get(REOPENED_WORKFLOW)
    if reopened and reopened["enabled"] and reopened["id"]:
        result = runner([
            "api", "graphql",
            "-f", f"query={DELETE_WORKFLOW_MUTATION}",
            "-f", f"workflowId={reopened['id']}",
        ])
        _check(result, "board_write_failed", f"disabling the {REOPENED_WORKFLOW!r} workflow",
               "Verify the `project` scope and board write permission; " + _PROJECT_SCOPE_HINT)
        reopened_disabled = True

    closed = by_name.get(CLOSED_WORKFLOW)
    closed_enabled = bool(closed and closed["enabled"])
    warnings: "list[str]" = []
    if not closed_enabled:
        warnings.append(
            f"{CLOSED_WORKFLOW!r} workflow is not enabled — the automation that stamps "
            "`shipped` on issue close is off; enable it in the project UI (Workflows) "
            "or `shipped` will require a manual/scripted Status write on every merge"
        )
    return {
        "reopened_present": reopened is not None,
        "reopened_disabled": reopened_disabled,
        "closed_enabled": closed_enabled,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# 7.5 Link the board to the origin repo. Projects v2 boards are owned by a
# user/org and *linked* to repos; the link surfaces the board on the repo's
# Projects tab and enables auto-add-from-repo. Board resolution never needs it
# (owner+number is enough), so a link failure is a non-fatal warning, not an
# abort. Idempotent: query the current links and skip the mutation if present.
# --------------------------------------------------------------------------

def link_repo(project: Project, ctx: "lb.RepoContext", runner: GhRunner) -> dict:
    """Link the board to the origin repo unless it already is. Returns
    {linked, already_linked, warning}. Never raises — the board is fully usable
    unlinked, so failures degrade to a warning surfaced in the summary."""
    linked = lb.project_linked_repos(ctx.origin_owner, project.number, runner)
    if linked is not None and ctx.slug in linked:
        return {"linked": False, "already_linked": True, "warning": None}
    result = runner(["project", "link", str(project.number), "--owner", ctx.origin_owner,
                     "--repo", ctx.slug])
    if result.returncode != 0:
        return {
            "linked": False, "already_linked": False,
            "warning": (
                f"could not link the board to {ctx.slug}: {result.stderr.strip()[:200]} — the board "
                f"still works unlinked; link it manually with "
                f"`gh project link {project.number} --owner {ctx.origin_owner} --repo {ctx.slug}`"
            ),
        }
    return {"linked": True, "already_linked": False, "warning": None}


# --------------------------------------------------------------------------
# 7.6 Auto-add scaffold (issue #63). Only runs when forward_binding == "auto-add".
# The built-in auto-add workflow has no create API; actions/add-to-project
# reproduces it. Mirrors link_repo: idempotent (never clobber an existing file)
# and non-fatal (failures degrade to a summary warning). The scaffolded file is
# what lifecycle_board.find_auto_add_workflow greps for, flipping the doctor's
# board_forward_binding check WARN -> PASS.
# --------------------------------------------------------------------------

def _resolve_owner_url_segment(ctx: "lb.RepoContext", runner: GhRunner) -> str:
    """`users` for a user-owned board, `orgs` for an org-owned one — the
    add-to-project project-url segment must match the owner type exactly (the
    action does not normalize). The /users/{login} REST endpoint resolves BOTH
    account types and returns a `type` discriminator, so one call covers both;
    default to `users` if the type can't be read."""
    result = runner(["api", f"users/{ctx.origin_owner}", "--jq", ".type"])
    if result.returncode == 0 and result.stdout.strip() == "Organization":
        return "orgs"
    return "users"


def _resolve_action_ref(runner: GhRunner) -> "tuple[str, str]":
    """(sha, human_ref) for the pinned action. Resolve the v2 tag to its commit
    SHA live so scaffolds stay current across plugin releases; fall back to the
    known-good constant when the call fails (offline/CI). Always a full SHA — a
    moving tag would run with ADD_TO_PROJECT_PAT in scope."""
    result = runner(["api", f"repos/{ADD_TO_PROJECT_REPO}/commits/v2", "--jq", ".sha"])
    sha = result.stdout.strip() if result.returncode == 0 else ""
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        return sha, "v2"
    return ADD_TO_PROJECT_PINNED_SHA, ADD_TO_PROJECT_PINNED_REF


def render_add_to_project_workflow(project_url: str, action_sha: str, action_ref: str) -> str:
    """The hardened workflow YAML: permissions:{} at both levels (the PAT does
    the write, GITHUB_TOKEN needs nothing), SHA-pinned action, and an inline
    guardrail forbidding future run: steps that interpolate issue content."""
    return f"""\
# Auto-adds newly opened issues to the lifecycle Projects v2 board.
# Scaffolded by agentic-engineering bootstrap (forward binding = auto-add).
# One manual step: add a repo secret {ADD_TO_PROJECT_SECRET} (see the setup skill).
# SECURITY: do NOT add `run:` steps that interpolate ${{{{ github.event.issue.* }}}}
# — that reintroduces script injection. This job runs no untrusted code.
name: Add issues to project
on:
  issues:
    types: [opened]

permissions: {{}}   # the PAT does the Projects write; GITHUB_TOKEN needs nothing

jobs:
  add-to-project:
    runs-on: ubuntu-latest
    permissions: {{}}
    steps:
      - uses: {ADD_TO_PROJECT_REPO}@{action_sha}  # {action_ref}
        with:
          project-url: {project_url}
          github-token: ${{{{ secrets.{ADD_TO_PROJECT_SECRET} }}}}
          # Optional filter: labeled: bug,needs-triage / label-operator: OR|AND|NOT
"""


DEPENDABOT_GITHUB_ACTIONS = """\
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
"""


def _ensure_dependabot(ctx: "lb.RepoContext") -> dict:
    """Create .github/dependabot.yml (github-actions ecosystem) if absent so the
    pinned action SHA gets auto-bumped. If a dependabot config already exists,
    never parse/merge arbitrary user YAML — return a warning to add the ecosystem
    by hand. Non-fatal."""
    path = pathlib.Path(ctx.root) / DEPENDABOT_FILENAME
    if path.exists():
        text = ""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            pass
        if "github-actions" in text:
            return {"created": False, "already_covers_actions": True, "warning": None}
        return {"created": False, "already_covers_actions": False,
                "warning": (f"{DEPENDABOT_FILENAME} exists but has no github-actions ecosystem — "
                            "add one so the pinned add-to-project SHA stays current: "
                            "a `- package-ecosystem: \"github-actions\"` update entry")}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEPENDABOT_GITHUB_ACTIONS, encoding="utf-8")
    except OSError as exc:
        return {"created": False, "already_covers_actions": False,
                "warning": f"could not write {DEPENDABOT_FILENAME}: {exc}"}
    return {"created": True, "already_covers_actions": True, "warning": None}


def scaffold_add_to_project_workflow(project: Project, ctx: "lb.RepoContext",
                                     runner: GhRunner) -> dict:
    """Write .github/workflows/add-to-project.yml (+ ensure dependabot) unless the
    workflow already exists. Idempotent + non-fatal, mirroring link_repo."""
    path = pathlib.Path(ctx.root) / WORKFLOW_FILENAME
    if path.exists():
        return {"scaffolded": False, "already_exists": True, "path": str(path),
                "dependabot": {"created": False, "already_covers_actions": None, "warning": None},
                "warning": None}

    segment = _resolve_owner_url_segment(ctx, runner)
    project_url = f"https://github.com/{segment}/{ctx.origin_owner}/projects/{project.number}"
    action_sha, action_ref = _resolve_action_ref(runner)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_add_to_project_workflow(project_url, action_sha, action_ref),
                        encoding="utf-8")
    except OSError as exc:
        return {"scaffolded": False, "already_exists": False, "path": str(path),
                "dependabot": {"created": False, "already_covers_actions": None, "warning": None},
                "warning": (f"could not scaffold {WORKFLOW_FILENAME}: {exc} — add it by hand "
                            f"(actions/add-to-project) and set the {ADD_TO_PROJECT_SECRET} secret")}
    dependabot = _ensure_dependabot(ctx)
    return {"scaffolded": True, "already_exists": False, "path": str(path),
            "project_url": project_url, "action_ref": f"{action_sha} ({action_ref})",
            "secret_name": ADD_TO_PROJECT_SECRET, "dependabot": dependabot, "warning": None}


# --------------------------------------------------------------------------
# 8. Committed config write (byte-for-byte preservation of unrelated content)
# --------------------------------------------------------------------------

def write_committed_config(main_root: str, owner: str, number: int,
                           forward_binding: "Optional[str]" = None) -> str:
    """Create agentic-engineering.md with the board keys if it is missing;
    otherwise update ONLY those keys inside the frontmatter, preserving every
    other byte. Board identity and the forward-binding decision (issue #64) are
    written in ONE call, so a crash can never leave identity without policy.
    Returns the path written. Delegates to lifecycle_board's shared writer (the
    single write path for committed config keys)."""
    keys = {"github_project_owner": owner, "github_project_number": str(number)}
    if forward_binding is not None:
        keys[lb.CONFIG_KEY_FORWARD_BINDING] = forward_binding
    return lb.write_config_keys(main_root, keys)


# --------------------------------------------------------------------------
# 9. Scripted probe
# --------------------------------------------------------------------------

def run_probe(project: Project, ctx: "lb.RepoContext", runner: GhRunner,
              *, sleep: "Callable[[float], None]" = time.sleep,
              now: "Callable[[], float]" = time.monotonic) -> dict:
    """Create a scratch issue, add it to the board at Status=stub, close it,
    poll <=60s for the "Item closed" automation to stamp shipped, then delete
    the scratch issue. Returns PASS/FAIL evidence."""
    board = lb.BoardConfig(owner=ctx.origin_owner, number=project.number, source="bootstrap")
    issue_number: Optional[int] = None
    try:
        create = runner(["issue", "create", "--repo", ctx.slug, "--title", PROBE_TITLE,
                         "--body", "Automated bootstrap verification probe. Safe to delete."])
        if create.returncode != 0:
            return {"result": "FAIL", "reason": "could not create the scratch issue",
                    "detail": create.stderr.strip()[:200]}
        issue_number = _parse_issue_number(create.stdout)
        if issue_number is None:
            return {"result": "FAIL", "reason": "could not parse the scratch issue number",
                    "detail": create.stdout.strip()[:200]}

        # board-add + Status=stub via lifecycle_board's sanctioned verb.
        lb.verb_set_status(issue_number, "stub", ctx, runner)

        close = runner(["issue", "close", str(issue_number), "--repo", ctx.slug,
                        "--reason", "completed"])
        if close.returncode != 0:
            return {"result": "FAIL", "issue": issue_number,
                    "reason": "could not close the scratch issue",
                    "detail": close.stderr.strip()[:200]}

        deadline = now() + PROBE_POLL_SECONDS
        observed = None
        while now() < deadline:
            state = lb.fetch_issue_state(issue_number, board, ctx, runner)
            observed = state.stage if state else None
            if observed == "shipped":
                return {"result": "PASS", "issue": issue_number,
                        "observed_stage": observed,
                        "detail": "Item closed automation stamped shipped"}
            sleep(PROBE_POLL_INTERVAL)
        return {"result": "FAIL", "issue": issue_number, "observed_stage": observed,
                "reason": f"automation did not stamp shipped within {PROBE_POLL_SECONDS}s",
                "detail": "verify the 'Item closed' workflow is enabled in the project UI"}
    finally:
        if issue_number is not None:
            runner(["issue", "delete", str(issue_number), "--repo", ctx.slug, "--yes"])


def _parse_issue_number(stdout: str) -> Optional[int]:
    m = re.search(r"/issues/(\d+)", stdout or "")
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def bootstrap(ctx: "lb.RepoContext", runner: GhRunner, *, probe: bool = True,
              forward_binding: "Optional[str]" = None,
              environ: "Optional[dict]" = None) -> dict:
    check_env_overrides(environ)
    version = check_gh_version(runner)
    check_gh_authenticated(runner)

    # Preserve a previously-recorded forward binding on re-bootstrap: only
    # overwrite it when the caller passed --forward-binding explicitly. First
    # run with nothing recorded falls back to the workflow-only default. Key off
    # the RAW recorded value, not the validated enum — a typo'd binding
    # (`auto_add`) reads back as an invalid enum, and defaulting on it would
    # silently erase the operator's (malformed but intentional) decision, the
    # exact thing this preservation exists to prevent. The doctor WARNs on the
    # malformed value instead.
    if forward_binding is None:
        forward_binding = lb.read_binding_config(ctx).forward_raw or lb.DEFAULT_FORWARD_BINDING

    project = resolve_or_create_project(ctx, runner)
    status = read_status_field(project, ctx, runner)
    kind = assert_fresh_or_canonical(status)
    options = build_option_mapping(status, kind)
    resulting_options = apply_status_options(status, options, runner)
    priority = ensure_priority_field(project, ctx, runner)
    workflows = configure_workflows(project, ctx, runner)
    repo_link = link_repo(project, ctx, runner)
    # Step 8: board identity + the forward-binding decision (A) in one write.
    # Backfill (B) is a separate, deliberate `lifecycle_board.py --backfill`
    # command — never run here, so bootstrap never mutates issues onto the board
    # unattended (CI-safe by construction).
    config_path = write_committed_config(ctx.main_root, ctx.origin_owner, project.number,
                                         forward_binding)

    # Step 8b: scaffold the auto-add workflow ONLY when that forward binding was
    # chosen — this is the mechanism (issue #63) that makes `auto-add` functional
    # and flips the doctor's board_forward_binding check WARN -> PASS.
    auto_add = None
    if forward_binding == "auto-add":
        auto_add = scaffold_add_to_project_workflow(project, ctx, runner)

    option_mapping = _summarize_mapping(status, options, kind)

    summary = {
        "ok": True,
        "gh_version": ".".join(map(str, version)),
        "project": {"owner": ctx.origin_owner, "number": project.number,
                    "id": project.id, "created": project.created,
                    "source_option_set": kind},
        "status_options": option_mapping,
        "resulting_options": [o.get("name") for o in resulting_options],
        "priority_field": priority,
        "workflows": workflows,
        "repo_link": repo_link,
        "config_path": config_path,
        "forward_binding": forward_binding,
        "auto_add_scaffold": auto_add,
    }
    warnings = list(workflows.get("warnings") or [])
    if repo_link.get("warning"):
        warnings.append(repo_link["warning"])
    if auto_add:
        if auto_add.get("warning"):
            warnings.append(auto_add["warning"])
        if (auto_add.get("dependabot") or {}).get("warning"):
            warnings.append(auto_add["dependabot"]["warning"])
    if warnings:
        summary["warnings"] = warnings
    if probe:
        summary["probe"] = run_probe(project, ctx, runner)
    else:
        summary["probe"] = {"result": "SKIPPED", "reason": "--no-probe"}
    return summary


def _summarize_mapping(status: StatusField, options: "list[dict]", kind: str) -> "list[dict]":
    """Human-readable old-name -> new-name with preserved id, per option."""
    id_to_old = {o["id"]: o["name"] for o in status.options if o.get("id")}
    out: "list[dict]" = []
    for opt in options:
        old = id_to_old.get(opt.get("id", "")) if opt.get("id") else None
        out.append({"old_name": old, "new_name": opt["name"],
                    "id_preserved": bool(opt.get("id"))})
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: "list[str]") -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", dest="probe", action="store_true", default=True,
                        help="run the scratch-issue verification probe (default ON)")
    parser.add_argument("--no-probe", dest="probe", action="store_false",
                        help="skip the verification probe")
    parser.add_argument("--probe-only", action="store_true",
                        help="run ONLY the verification probe against the already-configured "
                             "board (no project mutations) — used by /lifecycle-doctor --live")
    parser.add_argument("--forward-binding", choices=lb.FORWARD_BINDINGS, default=None,
                        help="how NEW issues reach the board, recorded in committed config "
                             "(decision A, issue #64). Omitted: preserve the recorded choice on "
                             f"re-run, else default {lb.DEFAULT_FORWARD_BINDING}. Backfill of "
                             "EXISTING issues is the separate `lifecycle_board.py --backfill`.")
    args = parser.parse_args(argv)
    try:
        ctx = lb.repo_context()
        if args.probe_only:
            board = lb.read_board_config(ctx)
            if board is None:
                raise BoardError("board_not_configured",
                                 "No committed board config — run the full bootstrap first",
                                 "python3 .../bootstrap_lifecycle_board.py")
            project = Project(number=board.number, id="", created=False)
            print(json.dumps({"ok": True, "probe": run_probe(project, ctx, lb.run_gh)}, indent=2))
            return 0
        summary = bootstrap(ctx, lb.run_gh, probe=args.probe, forward_binding=args.forward_binding)
        print(json.dumps(summary, indent=2))
        return 0
    except BoardError as err:
        return lb._emit_error(err)
    except Exception as exc:  # noqa: BLE001 — edge-of-CLI belt-and-braces
        print(json.dumps({"ok": False, "error_code": "internal", "error": str(exc),
                          "fix": "report this — gh emitted an unexpected shape"}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
