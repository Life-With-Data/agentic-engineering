#!/usr/bin/env python3
"""Lifecycle board engine: the single implementation of every lifecycle
predicate and board verb for the unified work-item lifecycle on GitHub
Projects v2 (see docs/plans/2026-07-05-feat-unified-lifecycle-github-projects-plan.md).

Design rules (enforced here, relied on everywhere):
  - Pure decision core: every predicate (gate evaluation, claim decision,
    reconciler repairs, ready-work merge) is a pure function over parsed gh
    JSON with an injected runner/clock — unit-testable with zero network.
  - One writer per transition: commands invoke exactly one verb for their
    owned transition; nothing else mutates the board.
  - The reconciler's repair set is CLOSED (five rules) plus report-only
    flags; it never fights a human's manual drag.
  - Board reads are repo-scoped: items whose content lives in another repo
    are dropped before any decision or write (shared boards are
    read-tolerated, never foreign-written).
  - Error contract: failures emit {ok, error_code, error, fix} on stdout and
    exit 1. A failed ready-work query hard-errors — it never returns [].
  - stdlib-only, Python >= 3.9. gh JSON is parsed with `json`; never jq/yq.

CLI verbs (used by workflow commands; humans/CI may call them directly):
  --gate <command> [--issue N]   entry-gate verdict for a workflow command
  --claim <N>                    race-safe claim (assign -> confirm sole ->
                                 blocked-by check -> Status=in_progress)
  --set-status <N> <stage>       the four-ID item-edit flow (sanctioned
                                 operator primitive for deliberate moves)
  --ready-work                   planned ∧ unassigned ∧ unblocked, Priority-
                                 sorted, <= 2 API calls at any board size
  --reconcile [--issue N] [--force]  scoped drift repair (TTL-cached)
  --doctor                       all A/B-class checks, report-everything mode
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# --------------------------------------------------------------------------
# Lifecycle vocabulary (the sole definition — the lifecycle skill documents
# these; commands reference them verbatim).
# --------------------------------------------------------------------------

STAGES = (
    "stub",
    "brainstormed",
    "planned",
    "in_progress",
    "in_review",
    "shipped",
    "deployed",
    "compounded",
    "abandoned",
)
# Total order for gate comparisons. `deployed` and `compounded` are
# order-independent terminal refinements of `shipped`; both compare as
# "at least shipped". `abandoned` is an off-ramp, not part of the order.
_ORDER = {
    "stub": 0,
    "brainstormed": 1,
    "planned": 2,
    "in_progress": 3,
    "in_review": 4,
    "shipped": 5,
    "deployed": 5,
    "compounded": 5,
    "abandoned": -1,
}
TERMINAL_STAGES = {"shipped", "deployed", "compounded"}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
PRIORITY_ORDER = {"p1": 0, "p2": 1, "p3": 2}

VERDICTS = (
    "proceed",
    "already_done",
    "route_to_plan",
    "route_to_work",
    "claim_conflict",
    "repair_needed",
    "no_board",
)

READY_WORK_LIMIT = 50
RECONCILE_TTL_SECONDS = 600
GH_TIMEOUT_SECONDS = 30
MIN_GH_VERSION = (2, 94, 0)

COMMITTED_CONFIG = "agentic-engineering.md"
LOCAL_CONFIG = "agentic-engineering.local.md"
CACHE_FILENAME = "agentic_engineering_cache.json"

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
_JOIN_KEY_RE = re.compile(r"^(?:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)#)?(?P<number>\d+)$")


# --------------------------------------------------------------------------
# Error contract
# --------------------------------------------------------------------------

class BoardError(Exception):
    def __init__(self, code: str, message: str, fix: str) -> None:
        super().__init__(message)
        self.code = code
        self.fix = fix


def _emit_error(err: BoardError) -> int:
    print(json.dumps({"ok": False, "error_code": err.code, "error": str(err), "fix": err.fix}, indent=2))
    return 1


def _emit(data: dict) -> int:
    data.setdefault("ok", True)
    print(json.dumps(data, indent=2))
    return 0


# --------------------------------------------------------------------------
# Effect seams (injected in tests)
# --------------------------------------------------------------------------

GhRunner = Callable[..., "subprocess.CompletedProcess[str]"]


def run_gh(args: "list[str]", timeout: int = GH_TIMEOUT_SECONDS) -> "subprocess.CompletedProcess[str]":
    """Default gh runner. Every board read/write flows through this seam.

    Fork-trap discipline: PreToolUse hooks cannot see this subprocess, so
    callers of this module MUST pass explicit --repo/--owner in `args`
    (asserted by unit tests via the argv-validating fake).
    """
    if shutil.which("gh") is None:
        raise BoardError("gh_missing", "GitHub CLI (gh) is not installed",
                         "Install gh >= 2.94.0: https://cli.github.com")
    try:
        return subprocess.run(["gh", *args], text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise BoardError("gh_timeout", f"gh timed out after {timeout}s: gh {' '.join(args[:4])}…",
                         "Check network connectivity / GitHub status, then retry") from exc


def _run_gh_retry(runner: GhRunner, args: "list[str]") -> "subprocess.CompletedProcess[str]":
    """One jittered retry on secondary-limit responses (403/429 text)."""
    result = runner(args)
    if result.returncode != 0 and ("HTTP 403" in result.stderr or "HTTP 429" in result.stderr):
        time.sleep(1.0 + (time.monotonic() % 1.0))
        result = runner(args)
    return result


def _git(args: "list[str]") -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else ""


# --------------------------------------------------------------------------
# Repo / config resolution
# --------------------------------------------------------------------------

@dataclass
class BoardConfig:
    owner: str
    number: int
    source: str  # committed | local


@dataclass
class RepoContext:
    root: str            # worktree root (artifact scans)
    main_root: str       # main repository root (committed config, cache)
    origin_owner: str
    origin_repo: str
    default_branch: str

    @property
    def slug(self) -> str:
        return f"{self.origin_owner}/{self.origin_repo}"


def parse_origin(url: str) -> "tuple[str, str]":
    """Parse owner/repo from https or ssh git remote URLs."""
    m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return ("", "")
    return (m.group(1), m.group(2))


def repo_context() -> RepoContext:
    root = _git(["rev-parse", "--show-toplevel"])
    if not root:
        raise BoardError("not_a_repo", "Not inside a git repository", "cd into the repository and retry")
    common = _git(["rev-parse", "--git-common-dir"])
    common_path = pathlib.Path(common) if pathlib.Path(common).is_absolute() else pathlib.Path(root) / common
    main_root = str(common_path.resolve().parent)
    owner, repo = parse_origin(_git(["remote", "get-url", "origin"]))
    head = _git(["symbolic-ref", "refs/remotes/origin/HEAD"])
    default_branch = head.rsplit("/", 1)[-1] if head else "main"
    return RepoContext(root=root, main_root=main_root, origin_owner=owner,
                       origin_repo=repo, default_branch=default_branch)


_FLAT_KEY_RE = re.compile(r"^\s*([A-Za-z_][\w-]*)\s*:\s*(.+?)\s*$")


def parse_frontmatter(text: str) -> "dict[str, str]":
    """Flat key: value scalars from a leading --- fenced block."""
    if not text.startswith("---"):
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not m:
        return {}
    out: "dict[str, str]" = {}
    for line in m.group(1).splitlines():
        line = re.sub(r"\s+#.*$", "", line)
        km = _FLAT_KEY_RE.match(line)
        if km:
            out[km.group(1)] = km.group(2).strip().strip('"').strip("'")
    return out


def read_board_config(ctx: RepoContext) -> Optional[BoardConfig]:
    """Committed config wins identity; .local may override for testing.

    Security invariant: the configured owner must match the origin owner
    unless it appears in `github_project_owner_allowlist` (comma-separated)
    in the same file — a PR must not be able to redirect agents to an
    attacker-owned board.
    """
    for name, source_root, source in (
        (LOCAL_CONFIG, ctx.root, "local"),
        (COMMITTED_CONFIG, ctx.main_root, "committed"),
    ):
        path = pathlib.Path(source_root) / name
        if not path.is_file():
            continue
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        owner = meta.get("github_project_owner", "")
        number = meta.get("github_project_number", "")
        if not owner and not number:
            continue
        if not _OWNER_RE.match(owner):
            raise BoardError("board_config_invalid",
                             f"{name}: github_project_owner {owner!r} is not a valid owner slug",
                             f"Fix github_project_owner in {name}")
        if not number.isdigit():
            raise BoardError("board_config_invalid",
                             f"{name}: github_project_number {number!r} is not an integer",
                             f"Fix github_project_number in {name}")
        allow = {a.strip() for a in meta.get("github_project_owner_allowlist", "").split(",") if a.strip()}
        if ctx.origin_owner and owner != ctx.origin_owner and owner not in allow:
            raise BoardError(
                "owner_mismatch",
                f"Configured board owner {owner!r} does not match origin owner {ctx.origin_owner!r}",
                f"Point github_project_owner at {ctx.origin_owner!r}, or add {owner!r} to "
                f"github_project_owner_allowlist in {name} after confirming it is trusted",
            )
        return BoardConfig(owner=owner, number=int(number), source=source)
    return None


def resolve_mode(board: Optional[BoardConfig], gh_authenticated: bool) -> str:
    """github-project | github | none. Lifecycle features require a board."""
    if board is not None:
        return "github-project"
    if gh_authenticated:
        return "github"
    return "none"


# --------------------------------------------------------------------------
# Session cache (git-common-dir: untracked by construction, worktree-shared)
# --------------------------------------------------------------------------

def _cache_path(ctx: RepoContext) -> pathlib.Path:
    common = _git(["rev-parse", "--git-common-dir"])
    base = pathlib.Path(common) if pathlib.Path(common).is_absolute() else pathlib.Path(ctx.root) / common
    return base / CACHE_FILENAME


def load_cache(ctx: RepoContext) -> dict:
    try:
        return json.loads(_cache_path(ctx).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(ctx: RepoContext, cache: dict) -> None:
    try:
        _cache_path(ctx).write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass  # cache is an optimization, never correctness


# --------------------------------------------------------------------------
# Board schema resolution (IDs by name, per entry; cached within TTL)
# --------------------------------------------------------------------------

@dataclass
class BoardSchema:
    project_id: str
    status_field_id: str
    status_options: "dict[str, str]"      # stage name -> option id
    priority_field_id: Optional[str] = None
    priority_options: "dict[str, str]" = field(default_factory=dict)


def parse_field_list(payload: dict) -> "tuple[Optional[dict], Optional[dict]]":
    status = priority = None
    for f in payload.get("fields", []):
        if f.get("name") == "Status":
            status = f
        elif f.get("name") == "Priority":
            priority = f
    return status, priority


def resolve_schema(board: BoardConfig, ctx: RepoContext, runner: GhRunner,
                   cache: Optional[dict] = None) -> BoardSchema:
    cache = cache if cache is not None else {}
    cached = cache.get("schema", {})
    if cached and time.time() - cached.get("fetched_at", 0) < RECONCILE_TTL_SECONDS:
        return BoardSchema(**{k: v for k, v in cached.items() if k != "fetched_at"})

    result = _run_gh_retry(runner, ["project", "field-list", str(board.number),
                                    "--owner", board.owner, "--format", "json"])
    if result.returncode != 0:
        raise BoardError("project_not_found",
                         f"Cannot read project {board.number} under {board.owner}: {result.stderr.strip()[:200]}",
                         "Verify the project exists and gh has the `project` scope "
                         "(gh auth refresh -s project); run the setup skill's bootstrap if missing")
    payload = json.loads(result.stdout or "{}")
    status, priority = parse_field_list(payload)
    if not status:
        raise BoardError("option_missing", "Project has no Status field", "Re-run the setup bootstrap")
    options = {o["name"]: o["id"] for o in status.get("options", [])}
    missing = [s for s in STAGES if s not in options]
    if missing:
        raise BoardError(
            "option_missing",
            f"Status field is missing lifecycle options: {', '.join(missing)}",
            "Re-run the setup bootstrap (it updates options ID-preservingly); "
            "someone may have renamed options in the project UI",
        )
    project_id = payload.get("projectId") or status.get("projectId") or ""
    if not project_id:
        view = _run_gh_retry(runner, ["project", "view", str(board.number),
                                      "--owner", board.owner, "--format", "json"])
        if view.returncode == 0:
            project_id = json.loads(view.stdout or "{}").get("id", "")
    if not project_id:
        raise BoardError("project_not_found", f"Cannot resolve project node ID for {board.owner}/{board.number}",
                         "Verify the project exists and the `project` scope is granted")
    schema = BoardSchema(
        project_id=project_id,
        status_field_id=status["id"],
        status_options=options,
        priority_field_id=priority["id"] if priority else None,
        priority_options={o["name"]: o["id"] for o in (priority or {}).get("options", [])},
    )
    cache["schema"] = {**dataclasses.asdict(schema), "fetched_at": time.time()}
    return schema


# --------------------------------------------------------------------------
# Issue state (one batched GraphQL read per issue)
# --------------------------------------------------------------------------

ISSUE_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      number title state stateReason url
      authorAssociation
      assignees(first: 10) { nodes { login } }
      closedByPullRequestsReferences(first: 5) {
        nodes { number state merged baseRefName author { login } }
      }
      subIssues(first: 100) { nodes { number state } }
      projectItems(first: 10) {
        nodes {
          id
          project { id number owner { ... on User { login } ... on Organization { login } } }
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}
"""


@dataclass
class IssueState:
    number: int
    state: str                      # OPEN | CLOSED
    state_reason: Optional[str]     # COMPLETED | NOT_PLANNED | REOPENED | None
    assignees: "list[str]"
    author_association: str
    stage: Optional[str]            # Status option name on the configured board
    item_id: Optional[str]
    closing_prs: "list[dict]"       # {number,state,merged,baseRefName,author}
    open_sub_issues: "list[int]"
    blocked_by_count: int
    url: str = ""
    title: str = ""


def parse_issue_state(data: dict, board: BoardConfig) -> Optional[IssueState]:
    issue = (data.get("data") or {}).get("repository", {}).get("issue")
    if not issue:
        return None
    stage = item_id = None
    for node in issue.get("projectItems", {}).get("nodes", []):
        proj = node.get("project") or {}
        if proj.get("number") == board.number and (proj.get("owner") or {}).get("login") == board.owner:
            item_id = node.get("id")
            fv = node.get("fieldValueByName") or {}
            stage = fv.get("name")
    return IssueState(
        number=issue["number"],
        state=issue.get("state", "OPEN"),
        state_reason=issue.get("stateReason"),
        assignees=[n["login"] for n in issue.get("assignees", {}).get("nodes", [])],
        author_association=issue.get("authorAssociation", "NONE"),
        stage=stage,
        item_id=item_id,
        closing_prs=[
            {"number": n["number"], "state": n["state"], "merged": n["merged"],
             "baseRefName": n.get("baseRefName", ""), "author": (n.get("author") or {}).get("login", "")}
            for n in issue.get("closedByPullRequestsReferences", {}).get("nodes", [])
        ],
        open_sub_issues=[n["number"] for n in issue.get("subIssues", {}).get("nodes", [])
                         if n.get("state") == "OPEN"],
        blocked_by_count=_blocked_count(issue),
        url=issue.get("url", ""),
        title=issue.get("title", ""),
    )


def _blocked_count(issue: dict) -> int:
    # gh >= 2.94 exposes blockedBy via `gh issue view --json blockedBy`; in the
    # GraphQL read we derive it separately (see fetch_issue_state).
    return issue.get("_blocked_by_count", 0)


def fetch_issue_state(number: int, board: BoardConfig, ctx: RepoContext,
                      runner: GhRunner) -> Optional[IssueState]:
    result = _run_gh_retry(runner, [
        "api", "graphql",
        "-f", f"query={ISSUE_QUERY}",
        "-F", f"owner={ctx.origin_owner}", "-F", f"repo={ctx.origin_repo}", "-F", f"number={number}",
    ])
    if result.returncode != 0:
        return None
    state = parse_issue_state(json.loads(result.stdout or "{}"), board)
    if state is not None:
        blocked = _run_gh_retry(runner, [
            "issue", "view", str(number), "--repo", ctx.slug, "--json", "blockedBy",
        ])
        if blocked.returncode == 0:
            try:
                state.blocked_by_count = len(json.loads(blocked.stdout).get("blockedBy", []))
            except (json.JSONDecodeError, TypeError):
                pass
    return state


# --------------------------------------------------------------------------
# Pure decision core
# --------------------------------------------------------------------------

def stage_at_least(stage: Optional[str], floor: str) -> bool:
    if stage is None:
        return False
    return _ORDER.get(stage, -2) >= _ORDER[floor]


@dataclass
class GateResult:
    verdict: str
    route: str
    reason: str
    stage: Optional[str]
    provenance: str = "trusted"


def evaluate_gate(command: str, stage: Optional[str], has_issue: bool,
                  plan_doc: Optional[str], brainstorm_doc: Optional[str],
                  author_association: str = "OWNER") -> GateResult:
    """The idempotent entry-gate decision table. Stage + artifact, never
    stage alone (humans drag cards arbitrarily)."""
    provenance = "trusted" if author_association in TRUSTED_ASSOCIATIONS else "untrusted"

    def gr(verdict: str, route: str, reason: str) -> GateResult:
        return GateResult(verdict=verdict, route=route, reason=reason, stage=stage, provenance=provenance)

    if command == "brainstorm":
        if not has_issue or stage in (None, "stub"):
            return gr("proceed", "brainstorm", "un-groomed item")
        if stage_at_least(stage, "brainstormed") and brainstorm_doc:
            return gr("already_done", "route_to_plan", "brainstormed with doc — groom no further, plan next")
        return gr("repair_needed", "brainstorm", "stage says brainstormed but no doc — re-groom (this run repairs it)")

    if command == "plan":
        if stage == "abandoned":
            return gr("already_done", "none", "item abandoned")
        if stage_at_least(stage, "planned") and plan_doc:
            return gr("already_done", "route_to_work", f"plan exists: {plan_doc}")
        if stage_at_least(stage, "planned") and not plan_doc:
            return gr("repair_needed", "plan", "stage says planned but no join-keyed plan doc — treat as un-groomed")
        return gr("proceed", "plan", "ready for planning")

    if command == "work":
        if stage == "abandoned":
            return gr("already_done", "none", "item abandoned")
        if stage in TERMINAL_STAGES:
            return gr("already_done", "none", f"already {stage}")
        if not stage_at_least(stage, "planned"):
            return gr("route_to_plan", "plan", "work requires >= planned; groom first (hotfixes bypass the board)")
        if not plan_doc:
            return gr("route_to_plan", "plan", "Status says planned but no plan doc with this join key exists — un-groomed")
        return gr("proceed", "work", "planned with plan doc — claim next")

    if command == "compound":
        if not has_issue:
            return gr("proceed", "compound", "no board item (hotfix path) — skip the Status write")
        if stage == "compounded":
            return gr("already_done", "none", "already compounded")
        if stage in ("shipped", "deployed"):
            return gr("proceed", "compound", "shipped — compound and stamp")
        return gr("repair_needed", "compound", f"stage {stage} is pre-merge; compound anyway but do not stamp")

    if command == "orchestrate":
        # Orchestrate consumes raw state and applies its own ladder.
        return gr("proceed", "orchestrate", "state read for orchestrator")

    return gr("no_board", "none", f"unknown command {command!r}")


@dataclass
class ClaimDecision:
    action: str  # proceed | conflict | blocked
    reason: str


def decide_claim(assignees: "list[str]", me: str, blocked_by_count: int) -> ClaimDecision:
    """Post-assignment confirmation: sole assignee, unblocked. GitHub has no
    CAS on assignment — two winners are legal, so the sole-assignee re-read
    is load-bearing."""
    if blocked_by_count > 0:
        return ClaimDecision("blocked", f"issue has {blocked_by_count} open blocking issue(s); dependencies are advisory — do not claim")
    if assignees == [me]:
        return ClaimDecision("proceed", "sole assignee confirmed")
    if me in assignees:
        return ClaimDecision("conflict", f"multiple assignees {assignees}; back off (self-unassign) — loser yields")
    return ClaimDecision("conflict", f"assigned to {assignees}; not ours to claim")


@dataclass
class Repair:
    issue: int
    rule: str
    from_stage: Optional[str]
    to_stage: Optional[str]        # None => non-status action (sub-issue cascade)
    comment: str
    close_sub_issues: "list[int]" = field(default_factory=list)


@dataclass
class Flag:
    issue: int
    flag: str
    comment: str


def plan_repairs(states: "list[IssueState]", default_branch: str) -> "tuple[list[Repair], list[Flag]]":
    """The CLOSED five-repair set + report-only flags. Anything not matched
    here is never auto-repaired — the reconciler must not fight human drags."""
    repairs: "list[Repair]" = []
    flags: "list[Flag]" = []
    for s in states:
        merged_pr = next((p for p in s.closing_prs if p["merged"]), None)
        assignee_prs = [p for p in s.closing_prs if p["author"] in s.assignees] if s.assignees else []

        # Rule 1: merged close missed by automation -> shipped
        if s.state == "CLOSED" and s.state_reason == "COMPLETED" and merged_pr \
                and not stage_at_least(s.stage, "shipped") and s.stage != "abandoned":
            repairs.append(Repair(s.number, "merged_close_missed", s.stage, "shipped",
                                  f"reconciler: PR #{merged_pr['number']} merged and issue closed — Status → shipped"))
            continue

        # Rule 2: closed as not planned -> abandoned (fixes the any-close automation mislabel)
        if s.state == "CLOSED" and s.state_reason == "NOT_PLANNED" and s.stage != "abandoned":
            repairs.append(Repair(s.number, "not_planned_close", s.stage, "abandoned",
                                  "reconciler: issue closed as not-planned — Status → abandoned",
                                  close_sub_issues=list(s.open_sub_issues)))
            continue

        # Rule 3: assignee's PR closed without merge -> regress to in_progress
        if s.state == "OPEN" and s.stage == "in_review" and assignee_prs \
                and all(p["state"] == "CLOSED" and not p["merged"] for p in assignee_prs):
            repairs.append(Repair(s.number, "pr_closed_unmerged", s.stage, "in_progress",
                                  "reconciler: linked PR closed without merging — Status → in_progress"))
            continue

        # Rule 4: abandoned parent with open sub-issues -> cascade close
        if s.stage == "abandoned" and s.open_sub_issues:
            repairs.append(Repair(s.number, "abandoned_cascade", s.stage, None,
                                  f"reconciler: parent abandoned — closing sub-issues {s.open_sub_issues} as not planned",
                                  close_sub_issues=list(s.open_sub_issues)))
            continue

        # Rule 5: assignee's PR (re)opened while item regressed -> in_review
        if s.state == "OPEN" and s.stage == "in_progress" \
                and any(p["state"] == "OPEN" for p in assignee_prs):
            repairs.append(Repair(s.number, "pr_reopened", s.stage, "in_review",
                                  "reconciler: linked PR is open — Status → in_review"))
            continue

        # Flag (never repaired): merged off the default branch — the git-flow stall
        if s.state == "OPEN" and merged_pr and merged_pr["baseRefName"] != default_branch \
                and s.stage in ("in_progress", "in_review"):
            flags.append(Flag(s.number, "merged_to_non_default_branch",
                              f"reconciler: PR #{merged_pr['number']} merged into "
                              f"'{merged_pr['baseRefName']}' (not '{default_branch}') so GitHub will not "
                              "auto-close this issue — add the issue-closer workflow from the docs, "
                              "or close it manually when it lands on the default branch"))
    return repairs, flags


@dataclass
class ReadyItem:
    number: int
    title: str
    priority: Optional[str]
    repo: str


def merge_ready_legs(board_items: "list[dict]", blocked_counts: "dict[int, int]",
                     origin_slug: str) -> "tuple[list[ReadyItem], bool]":
    """Leg 1 (item-list, server-filtered) x leg 2 (batched blockedBy counts).
    Repo-scoped: foreign-repo items are dropped, never acted on."""
    truncated = len(board_items) >= READY_WORK_LIMIT
    ready: "list[ReadyItem]" = []
    for item in board_items:
        content = item.get("content") or {}
        if content.get("type") not in ("Issue", None):
            continue
        repo = (content.get("repository") or "")
        if isinstance(repo, dict):
            repo = repo.get("nameWithOwner", "")
        if repo and repo != origin_slug:
            continue  # shared/portfolio board: read-tolerated, never written
        number = content.get("number")
        if number is None:
            continue
        if blocked_counts.get(number, 0) > 0:
            continue
        ready.append(ReadyItem(number=number, title=content.get("title", item.get("title", "")),
                               priority=(item.get("priority") or None), repo=repo or origin_slug))
    ready.sort(key=lambda r: PRIORITY_ORDER.get((r.priority or "").lower(), 99))
    return ready, truncated


# --------------------------------------------------------------------------
# Artifact scans (docs are content; the join key is the identity)
# --------------------------------------------------------------------------

def normalize_join_key(value: str, origin_slug: str) -> Optional[str]:
    m = _JOIN_KEY_RE.match(value.strip())
    if not m:
        return None
    owner, repo, number = m.group("owner"), m.group("repo"), m.group("number")
    slug = f"{owner}/{repo}" if owner and repo else origin_slug
    return f"{slug}#{number}"


def find_docs_for_issue(number: int, ctx: RepoContext) -> "tuple[Optional[str], Optional[str]]":
    """(plan_doc, brainstorm_doc) whose github_issue join key resolves to
    origin#number. Bare integers are repo-local by definition."""
    want = f"{ctx.slug}#{number}"
    plan = brainstorm = None
    for sub, current in (("docs/plans", "plan"), ("docs/brainstorms", "brainstorm")):
        directory = pathlib.Path(ctx.root) / sub
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md"), reverse=True):
            try:
                meta = parse_frontmatter(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            raw = meta.get("github_issue", "")
            if raw and normalize_join_key(raw, ctx.slug) == want:
                rel = str(path.relative_to(ctx.root))
                if current == "plan" and plan is None:
                    plan = rel
                elif current == "brainstorm" and brainstorm is None:
                    brainstorm = rel
                break
    return plan, brainstorm


# --------------------------------------------------------------------------
# Effectful verbs
# --------------------------------------------------------------------------

def _require_board(ctx: RepoContext) -> BoardConfig:
    board = read_board_config(ctx)
    if board is None:
        raise BoardError(
            "board_not_configured",
            f"No board configured: add github_project_owner/github_project_number to {COMMITTED_CONFIG}",
            "Run the setup skill's bootstrap to create the project and write the committed config",
        )
    return board


def _gh_me(runner: GhRunner) -> str:
    result = _run_gh_retry(runner, ["api", "user", "--jq", ".login"])
    if result.returncode != 0:
        raise BoardError("gh_unauthenticated", "gh is not authenticated",
                         "Run `gh auth login`, then `gh auth refresh -s project`")
    return result.stdout.strip()


def verb_gate(command: str, issue: Optional[int], ctx: RepoContext, runner: GhRunner) -> dict:
    board = read_board_config(ctx)
    gh_ok = shutil.which("gh") is not None
    mode = resolve_mode(board, gh_ok)
    if mode != "github-project":
        return {"mode": mode, "verdict": "no_board", "route": "none",
                "reason": "lifecycle gates require a configured board; degrading to legacy behavior",
                "stage": None, "issue": issue, "flags": []}

    flags: "list[dict]" = []
    stage = None
    has_issue = issue is not None
    plan_doc = brainstorm_doc = None
    author_association = "OWNER"
    if issue is not None:
        state = fetch_issue_state(issue, board, ctx, runner)  # type: ignore[arg-type]
        if state is None:
            flags.append({"issue": issue, "flag": "stale_join_key",
                          "comment": f"github_issue: {issue} does not resolve in {ctx.slug} "
                                     "(deleted or transferred?) — update the doc frontmatter"})
            return {"mode": mode, "verdict": "repair_needed", "route": "none",
                    "reason": "join key does not resolve", "stage": None,
                    "issue": issue, "flags": flags}
        stage = state.stage
        author_association = state.author_association
        plan_doc, brainstorm_doc = find_docs_for_issue(issue, ctx)
    result = evaluate_gate(command, stage, has_issue, plan_doc, brainstorm_doc, author_association)
    return {"mode": mode, "verdict": result.verdict, "route": result.route,
            "reason": result.reason, "stage": result.stage, "issue": issue,
            "plan_doc": plan_doc, "brainstorm_doc": brainstorm_doc,
            "author_association": author_association, "provenance": result.provenance,
            "flags": flags}


def verb_set_status(issue: int, stage: str, ctx: RepoContext, runner: GhRunner) -> dict:
    if stage not in STAGES:
        raise BoardError("invalid_stage", f"{stage!r} is not a lifecycle stage",
                         f"Use one of: {', '.join(STAGES)}")
    board = _require_board(ctx)
    cache = load_cache(ctx)
    schema = resolve_schema(board, ctx, runner, cache)
    save_cache(ctx, cache)
    state = fetch_issue_state(issue, board, ctx, runner)
    if state is None:
        raise BoardError("issue_not_found", f"Issue #{issue} not found in {ctx.slug}",
                         "Check the issue number / join key")
    item_id = state.item_id
    if item_id is None:
        add = _run_gh_retry(runner, ["project", "item-add", str(board.number),
                                     "--owner", board.owner, "--url", state.url, "--format", "json"])
        if add.returncode != 0:
            raise BoardError("board_write_failed", f"item-add failed: {add.stderr.strip()[:200]}",
                             "Verify the `project` scope and board permissions (viewerCanUpdate)")
        item_id = json.loads(add.stdout or "{}").get("id")
    edit = _run_gh_retry(runner, [
        "project", "item-edit", "--id", item_id,
        "--project-id", schema.project_id,
        "--field-id", schema.status_field_id,
        "--single-select-option-id", schema.status_options[stage],
    ])
    if edit.returncode != 0:
        raise BoardError("board_write_failed", f"item-edit failed: {edit.stderr.strip()[:200]}",
                         "Verify the `project` scope and board permissions")
    return {"issue": issue, "stage": stage, "previous_stage": state.stage, "item_id": item_id}


def verb_claim(issue: int, ctx: RepoContext, runner: GhRunner) -> dict:
    board = _require_board(ctx)
    me = _gh_me(runner)
    state = fetch_issue_state(issue, board, ctx, runner)
    if state is None:
        raise BoardError("issue_not_found", f"Issue #{issue} not found in {ctx.slug}",
                         "Check the issue number")
    if state.assignees and me not in state.assignees:
        decision = decide_claim(state.assignees, me, state.blocked_by_count)
        return {"issue": issue, "claimed": False, "verdict": "claim_conflict", "reason": decision.reason}
    if state.blocked_by_count > 0:
        decision = decide_claim(state.assignees, me, state.blocked_by_count)
        return {"issue": issue, "claimed": False, "verdict": "blocked", "reason": decision.reason}

    if not state.assignees:
        assign = _run_gh_retry(runner, ["issue", "edit", str(issue), "--repo", ctx.slug,
                                        "--add-assignee", "@me"])
        if assign.returncode != 0:
            raise BoardError("claim_failed", f"assign failed: {assign.stderr.strip()[:200]}",
                             "Verify triage permission on the repo")
    confirm = fetch_issue_state(issue, board, ctx, runner)  # ALWAYS a fresh read
    decision = decide_claim(confirm.assignees if confirm else [], me,
                            confirm.blocked_by_count if confirm else 0)
    if decision.action != "proceed":
        if confirm and me in confirm.assignees and len(confirm.assignees) > 1:
            _run_gh_retry(runner, ["issue", "edit", str(issue), "--repo", ctx.slug,
                                   "--remove-assignee", "@me"])  # loser yields visibly
        return {"issue": issue, "claimed": False,
                "verdict": "claim_conflict" if decision.action == "conflict" else "blocked",
                "reason": decision.reason}
    status = verb_set_status(issue, "in_progress", ctx, runner)
    return {"issue": issue, "claimed": True, "verdict": "proceed",
            "assignee": me, "previous_stage": status["previous_stage"]}


def _item_list(board: BoardConfig, runner: GhRunner, query: str) -> "list[dict]":
    result = _run_gh_retry(runner, ["project", "item-list", str(board.number),
                                    "--owner", board.owner, "--format", "json",
                                    "--limit", str(READY_WORK_LIMIT), "--query", query])
    if result.returncode != 0:
        raise BoardError("ready_work_failed",
                         f"item-list failed ({query!r}): {result.stderr.strip()[:200]}",
                         "Verify gh >= 2.94.0, the `project` scope, and that the board exists — "
                         "a failed query must never read as an empty work list")
    return json.loads(result.stdout or "{}").get("items", [])


BLOCKED_QUERY_HEADER = "query($owner: String!, $repo: String!) {\n  repository(owner: $owner, name: $repo) {\n"


def _batched_blocked_counts(numbers: "list[int]", ctx: RepoContext, runner: GhRunner) -> "dict[int, int]":
    if not numbers:
        return {}
    body = "".join(
        f"    i{n}: issue(number: {n}) {{ blockedBy(first: 1) {{ totalCount }} }}\n" for n in numbers
    )
    query = BLOCKED_QUERY_HEADER + body + "  }\n}"
    result = _run_gh_retry(runner, ["api", "graphql", "-f", f"query={query}",
                                    "-F", f"owner={ctx.origin_owner}", "-F", f"repo={ctx.origin_repo}"])
    if result.returncode != 0:
        raise BoardError("ready_work_failed",
                         f"blockedBy batch query failed: {result.stderr.strip()[:200]}",
                         "Retry; if persistent, check GraphQL availability — "
                         "never treat a failed query as an empty work list")
    repo_data = (json.loads(result.stdout or "{}").get("data") or {}).get("repository") or {}
    return {n: ((repo_data.get(f"i{n}") or {}).get("blockedBy") or {}).get("totalCount", 0)
            for n in numbers}


def verb_ready_work(ctx: RepoContext, runner: GhRunner) -> dict:
    board = _require_board(ctx)
    items = _item_list(board, runner, "status:planned no:assignee")   # call 1
    numbers = [i.get("content", {}).get("number") for i in items
               if i.get("content", {}).get("number") is not None]
    blocked = _batched_blocked_counts(numbers, ctx, runner)           # call 2
    ready, truncated = merge_ready_legs(items, blocked, ctx.slug)
    out = {"items": [dataclasses.asdict(r) for r in ready], "truncated": truncated, "flags": []}
    if truncated:
        out["flags"].append({"flag": "truncated_ready_work",
                             "comment": f"board leg hit the {READY_WORK_LIMIT}-item cap; "
                                        "Priority ordering may be incomplete"})
    return out


def verb_reconcile(ctx: RepoContext, runner: GhRunner, issue: Optional[int] = None,
                   force: bool = False, now: Optional[float] = None) -> dict:
    board = _require_board(ctx)
    cache = load_cache(ctx)
    now = now if now is not None else time.time()
    if not force and issue is None:
        last = cache.get("last_reconciled_at", 0)
        if now - last < RECONCILE_TTL_SECONDS:
            return {"skipped_ttl": True, "repairs_applied": [], "repairs_failed": [], "flags": []}

    numbers: "list[int]" = []
    if issue is not None:
        numbers = [issue]
    else:
        for query in ("status:in_progress", "status:in_review"):
            for item in _item_list(board, runner, query):
                content = item.get("content") or {}
                repo = content.get("repository", "")
                if isinstance(repo, dict):
                    repo = repo.get("nameWithOwner", "")
                if repo and repo != ctx.slug:
                    continue  # foreign items: never examined, never written
                if content.get("number") is not None:
                    numbers.append(content["number"])

    states = [s for s in (fetch_issue_state(n, board, ctx, runner) for n in dict.fromkeys(numbers))
              if s is not None]
    repairs, flags = plan_repairs(states, ctx.default_branch)

    applied, failed = [], []
    for repair in repairs:
        try:
            if repair.to_stage:
                verb_set_status(repair.issue, repair.to_stage, ctx, runner)
            for sub in repair.close_sub_issues:
                _run_gh_retry(runner, ["issue", "close", str(sub), "--repo", ctx.slug,
                                       "--reason", "not planned",
                                       "--comment", f"reconciler: parent #{repair.issue} abandoned"])
            _run_gh_retry(runner, ["issue", "comment", str(repair.issue), "--repo", ctx.slug,
                                   "--body", repair.comment])
            applied.append(dataclasses.asdict(repair))
        except BoardError as exc:
            failed.append({**dataclasses.asdict(repair), "error_code": exc.code, "error": str(exc)})
    for flag in flags:
        _run_gh_retry(runner, ["issue", "comment", str(flag.issue), "--repo", ctx.slug,
                               "--body", flag.comment])

    if issue is None:
        cache["last_reconciled_at"] = now
        save_cache(ctx, cache)
    return {"skipped_ttl": False, "repairs_applied": applied, "repairs_failed": failed,
            "flags": [dataclasses.asdict(f) for f in flags]}


# --------------------------------------------------------------------------
# Doctor (report-everything mode over the same checks the hard-error paths use)
# --------------------------------------------------------------------------

def _gh_version(runner: GhRunner) -> "tuple[int, ...]":
    result = runner(["--version"])
    m = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", result.stdout)
    return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)


def verb_doctor(ctx: RepoContext, runner: GhRunner) -> dict:
    checks: "list[dict]" = []

    def check(name: str, status: str, detail: str, fix: str = "") -> None:
        checks.append({"check": name, "status": status, "detail": detail, "fix": fix})

    # Local toolchain
    if sys.version_info >= (3, 9):
        check("python", "PASS", f"python {sys.version_info.major}.{sys.version_info.minor}")
    else:
        check("python", "FAIL", "python < 3.9", "Install Python 3.9+")
    if shutil.which("gh") is None:
        check("gh_installed", "FAIL", "gh not on PATH", "Install gh >= 2.94.0")
        return {"checks": checks, "ready": False}
    check("gh_installed", "PASS", "gh on PATH")
    version = _gh_version(runner)
    if version >= MIN_GH_VERSION:
        check("gh_version", "PASS", ".".join(map(str, version)))
    else:
        check("gh_version", "FAIL", ".".join(map(str, version)), "Upgrade gh to >= 2.94.0 (brew upgrade gh)")
    auth = runner(["auth", "status"])
    authed = auth.returncode == 0
    check("gh_auth", "PASS" if authed else "FAIL", "authenticated" if authed else "not authenticated",
          "" if authed else "gh auth login")
    combined = auth.stdout + auth.stderr
    if authed and "github.com" not in combined:
        check("host", "FAIL", "not github.com", "GHES is unsupported — use github.com")
    elif authed:
        check("host", "PASS", "github.com")
    scope_ok = authed and "project" in combined
    check("project_scope", "PASS" if scope_ok else ("WARN" if authed else "SKIP"),
          "project scope present" if scope_ok else "project scope not visible in auth status",
          "" if scope_ok else "gh auth refresh -s project")

    # Repo shape
    check("origin", "PASS" if ctx.origin_owner else "FAIL",
          ctx.slug if ctx.origin_owner else "cannot parse origin remote",
          "" if ctx.origin_owner else "Add an origin remote")
    if authed and ctx.origin_owner:
        repo_info = runner(["api", f"repos/{ctx.slug}", "--jq", ".has_issues"])
        if repo_info.returncode == 0:
            issues_on = repo_info.stdout.strip() == "true"
            check("issues_enabled", "PASS" if issues_on else "FAIL",
                  "issues enabled" if issues_on else "issues disabled",
                  "" if issues_on else "Enable Issues in repo settings")
        else:
            check("issues_enabled", "SKIP", "could not read repo settings")

    # Board schema
    try:
        board = read_board_config(ctx)
    except BoardError as exc:
        board = None
        check("board_config", "FAIL", str(exc), exc.fix)
    if board is None:
        if not any(c["check"] == "board_config" for c in checks):
            check("board_config", "WARN", f"no board configured in {COMMITTED_CONFIG}",
                  "Run the setup bootstrap (Phase 4) to create the project and committed config")
    else:
        check("board_config", "PASS", f"{board.owner}/projects/{board.number} ({board.source})")
        try:
            schema = resolve_schema(board, ctx, runner, {})
            check("status_options", "PASS", "all 9 lifecycle options present")
            check("priority_field", "PASS" if schema.priority_field_id else "WARN",
                  "Priority field present" if schema.priority_field_id else "no Priority field",
                  "" if schema.priority_field_id else "Re-run bootstrap to add it")
        except BoardError as exc:
            check("status_options", "FAIL", str(exc), exc.fix)

    # Delivery topology (detection, not enforcement)
    if authed and ctx.origin_owner:
        merged = runner(["pr", "list", "--repo", ctx.slug, "--state", "merged",
                         "--limit", "10", "--json", "baseRefName"])
        if merged.returncode == 0:
            try:
                bases = {p["baseRefName"] for p in json.loads(merged.stdout or "[]")}
                off_default = bases - {ctx.default_branch}
                if off_default:
                    check("default_branch_merges", "WARN",
                          f"recent PRs merged into {sorted(off_default)} (not {ctx.default_branch})",
                          "Git-flow topology: add the issue-closer workflow from the docs or items stall at in_review")
                else:
                    check("default_branch_merges", "PASS", f"recent merges target {ctx.default_branch}")
            except json.JSONDecodeError:
                check("default_branch_merges", "SKIP", "unparseable pr list")
        deployments = runner(["api", f"repos/{ctx.slug}/deployments?per_page=1", "--jq", "length"])
        if deployments.returncode == 0 and deployments.stdout.strip() not in ("", "0"):
            check("deployments", "PASS", "GitHub Deployment records exist — the deployed adapter can hook deployment_status/promotion events")
        else:
            check("deployments", "SKIP", "no Deployment records — ignore the deployed stage or use a promotion-event adapter")

    hard_fail = any(c["status"] == "FAIL" for c in checks)
    return {"checks": checks, "ready": not hard_fail}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: "list[str]") -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gate", metavar="COMMAND")
    group.add_argument("--claim", type=int, metavar="N")
    group.add_argument("--set-status", nargs=2, metavar=("N", "STAGE"))
    group.add_argument("--ready-work", action="store_true")
    group.add_argument("--reconcile", action="store_true")
    group.add_argument("--doctor", action="store_true")
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        ctx = repo_context()
        if args.gate:
            return _emit(verb_gate(args.gate, args.issue, ctx, run_gh))
        if args.claim is not None:
            return _emit(verb_claim(args.claim, ctx, run_gh))
        if args.set_status:
            number, stage = args.set_status
            return _emit(verb_set_status(int(number), stage, ctx, run_gh))
        if args.ready_work:
            return _emit(verb_ready_work(ctx, run_gh))
        if args.reconcile:
            return _emit(verb_reconcile(ctx, run_gh, issue=args.issue, force=args.force))
        if args.doctor:
            return _emit(verb_doctor(ctx, run_gh))
    except BoardError as err:
        return _emit_error(err)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
