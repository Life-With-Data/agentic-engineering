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
  --backfill                     one-time idempotent add of every open repo
                                 issue not yet on the board (decision B, #64)
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

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

# Gate verdicts emitted by evaluate_gate. `route_to_work`/`route_to_plan` are
# routes, not verdicts; claim_conflict/blocked are claim-only outcomes.
VERDICTS = (
    "proceed",
    "already_done",
    "route_to_plan",
    "repair_needed",
    "no_board",
)
# Claim protocol outcomes (verb_claim), disjoint from the gate VERDICTS.
CLAIM_VERDICTS = ("proceed", "claim_conflict", "blocked")

# Sub-issue status vocabulary. Sub-issues roll up into the PARENT's PR, so
# they never earn their own `in_review`/`shipped` board stage — the board
# tracks the parent. Their finer-grained progress rides on mutually-exclusive
# `status:*` labels a stakeholder can read directly in the issues list, driven
# by this same engine (never a second writer). Labels are repo-scoped, so the
# verb needs NO board and works in `github` mode too. The invariant: an issue
# carries at most one `status:*` label; the terminal `done` closes the issue
# (an orchestrator close, not a PR auto-close) and strips the label, because
# CLOSED already means done. `in_progress`/`in_review`/`blocked` describe an
# OPEN sub-issue's live state.
SUB_STATUSES = ("in_progress", "in_review", "blocked", "done")
SUB_STATUS_LABELS = {
    "in_progress": "status:in-progress",
    "in_review": "status:in-review",
    "blocked": "status:blocked",
    "done": "status:done",
}
ALL_SUB_STATUS_LABELS = tuple(SUB_STATUS_LABELS.values())
# (color hex without '#', description) — colors mirror the board's stage
# palette so the two surfaces read as one system.
SUB_STATUS_LABEL_META = {
    "status:in-progress": ("1D76DB", "Sub-issue: actively being implemented"),
    "status:in-review": ("FBCA04", "Sub-issue: implemented, awaiting parent-level gates/PR"),
    "status:blocked": ("D93F0B", "Sub-issue: has an open blocked-by dependency"),
    "status:done": ("0E8A16", "Sub-issue: acceptance criteria met"),
}

READY_WORK_LIMIT = 50
RECONCILE_TTL_SECONDS = 600
GH_TIMEOUT_SECONDS = 30
MIN_GH_VERSION = (2, 94, 0)

COMMITTED_CONFIG = "agentic-engineering.md"
LOCAL_CONFIG = "agentic-engineering.local.md"
CACHE_FILENAME = "agentic_engineering_cache.json"

# Repo->board binding, recorded in the committed config as two orthogonal
# decisions (see issue #64): (A) how NEW issues reach the board going forward,
# and (B) a high-water mark of the last one-time backfill of EXISTING issues.
# Both are flat scalars (parse_frontmatter reads nothing else). Backfill is
# offered under ANY forward binding — the two are independent.
CONFIG_KEY_FORWARD_BINDING = "github_project_forward_binding"
CONFIG_KEY_BACKFILLED_THROUGH = "github_project_backfilled_through"
FORWARD_BINDINGS = ("workflow-only", "auto-add", "none")
DEFAULT_FORWARD_BINDING = "workflow-only"

# Backfill enumeration caps. These are deliberately NOT READY_WORK_LIMIT (50) —
# that cap is a ready-work UX bound; a backfill that silently dropped issues
# past 50 would leave the board permanently short. gh paginates internally up
# to --limit, so these are the true ceilings (truncation is flagged, never
# silent).
BACKFILL_ISSUE_LIMIT = 1000
BACKFILL_BOARD_LIMIT = 1000

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
    """Parse owner/repo from https or ssh git remote URLs.

    Repo-less URLs (`https://github.com/justowner`) must NOT parse — otherwise
    the host (`github.com`) is captured as the owner. The owner segment is
    required to follow the ``:``/``/`` that separates it from the authority, and
    the authority itself (host, optionally with a port) is consumed first.
    """
    url = url.strip()
    # SSH: git@host:owner/repo(.git)
    m = re.match(r"^[\w.-]+@[\w.-]+:([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    if m:
        return (m.group(1), m.group(2))
    # HTTPS/SSH-URL: scheme://[user@]host[:port]/owner/repo(.git)
    m = re.match(r"^[a-zA-Z][\w+.-]*://[^/]+/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    if m:
        return (m.group(1), m.group(2))
    return ("", "")


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


def upsert_frontmatter_keys(text: str, keys: "dict[str, str]") -> str:
    """Update the given keys inside a leading --- fenced frontmatter block,
    preserving all other content byte-for-byte. If a key is absent it is
    appended just before the closing fence; if the file has no frontmatter, one
    is prepended. The single writer for committed-config keys — the bootstrap
    (board identity + forward binding) and the backfill verb (its high-water
    mark) both go through it, so a crash between writes can never leave the file
    half-formed."""
    # Match the file's prevailing newline so rewritten lines don't flip a CRLF
    # file to mixed endings (byte-preservation).
    nl = "\r\n" if "\r\n" in text else "\n"

    def render(pairs: "list[tuple[str, str]]") -> str:
        return "".join(f"{k}: {v}{nl}" for k, v in pairs)

    # Empty frontmatter (`---\n---\n`) has no inner content, so the general
    # regex below (which requires a `\n---` before the closing fence) misses it.
    # Insert the keys between the two fences rather than prepending a 2nd block.
    empty = re.match(r"^(---[ \t]*\r?\n)(---[ \t]*(?:\r?\n|$))", text)
    if empty:
        return empty.group(1) + render(list(keys.items())) + empty.group(2) + text[empty.end():]

    m = re.match(r"^(---[ \t]*\r?\n)(.*?)(\r?\n---[ \t]*(?:\r?\n|$))", text, re.DOTALL)
    if not m:
        return "---" + nl + render(list(keys.items())) + "---" + nl + text

    open_fence, inner, close_fence = m.group(1), m.group(2), m.group(3)
    key_line = re.compile(r"^([ \t]*)([A-Za-z_][\w-]*)([ \t]*:[ \t]*).*$")

    seen: "set[str]" = set()
    out_lines: "list[str]" = []
    for line in inner.split("\n"):
        line = line[:-1] if line.endswith("\r") else line  # nl re-added on join
        km = key_line.match(line)
        if km and km.group(2) in keys:
            # Update EVERY occurrence, not just the first: parse_frontmatter is
            # last-wins, so leaving a later duplicate would make the write a
            # silent no-op for that key.
            out_lines.append(f"{km.group(1)}{km.group(2)}{km.group(3)}{keys[km.group(2)]}")
            seen.add(km.group(2))
        else:
            out_lines.append(line)

    appended = [f"{k}: {v}" for k, v in keys.items() if k not in seen]
    if appended:
        # Insert appended keys after the last non-empty inner line to avoid a
        # blank gap, preserving trailing blank lines the author had.
        insert_at = len(out_lines)
        while insert_at > 0 and out_lines[insert_at - 1].strip() == "":
            insert_at -= 1
        out_lines[insert_at:insert_at] = appended

    return open_fence + nl.join(out_lines) + close_fence + text[m.end():]


def _atomic_write(path: pathlib.Path, text: str) -> None:
    """Write `text` to `path` atomically (tmp + os.replace), so a crash or
    ENOSPC mid-write can never truncate the target. Unlike save_cache, OSError
    is NOT swallowed — the committed board config is load-bearing (losing it
    breaks all lifecycle resolution), so a write failure must surface."""
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX/NTFS: no partial/truncated config


def write_config_keys(main_root: str, keys: "dict[str, str]") -> str:
    """Create COMMITTED_CONFIG with `keys` if it is missing; otherwise upsert
    only those keys inside the frontmatter, preserving every other byte. The
    single write path for the committed board config — atomic so identity is
    never half-written. Returns the path."""
    path = pathlib.Path(main_root) / COMMITTED_CONFIG
    if not path.exists():
        body = "---\n" + "".join(f"{k}: {v}\n" for k, v in keys.items()) + "---\n"
        _atomic_write(path, body)
        return str(path)
    text = path.read_text(encoding="utf-8")
    _atomic_write(path, upsert_frontmatter_keys(text, keys))
    return str(path)


def _is_tracked(ctx: RepoContext, name: str) -> bool:
    """True if `name` at ctx.root is tracked in git (would ride a PR)."""
    result = subprocess.run(
        ["git", "-C", ctx.root, "ls-files", "--error-unmatch", name],
        text=True, capture_output=True)
    return result.returncode == 0


def _trusted_board_owners(ctx: RepoContext) -> "set[str]":
    """The out-of-band trust store: `git config agentic.trustedBoardOwners`
    (comma/space-separated). It lives in .git/config, unreachable by any PR —
    the human sets it once (`git config agentic.trustedBoardOwners <owner>`)."""
    raw = _git(["-C", ctx.root, "config", "--get", "agentic.trustedBoardOwners"])
    return {tok for tok in re.split(r"[,\s]+", raw) if tok}


def read_board_config(ctx: RepoContext) -> Optional[BoardConfig]:
    """Committed config wins identity; .local may override for testing.

    Security invariant: the configured owner must match the origin owner unless
    it appears in the out-of-band trust store `git config
    agentic.trustedBoardOwners` — a self-referential in-file allowlist would let
    an attacker PR set owner + allowlist together, so the allowlist is NOT read
    from the config file. A `.local.md` that is *tracked* in git (i.e. would
    ride a PR) is ignored: local config must never be committed.
    """
    for name, source_root, source in (
        (LOCAL_CONFIG, ctx.root, "local"),
        (COMMITTED_CONFIG, ctx.main_root, "committed"),
    ):
        path = pathlib.Path(source_root) / name
        if not path.is_file():
            continue
        if name == LOCAL_CONFIG and _is_tracked(ctx, name):
            print(f"warning: {name} is tracked in git — a PR must not carry it; "
                  "ignoring it and using committed config", file=sys.stderr)
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
        if ctx.origin_owner and owner != ctx.origin_owner and owner not in _trusted_board_owners(ctx):
            raise BoardError(
                "owner_mismatch",
                f"Configured board owner {owner!r} does not match origin owner {ctx.origin_owner!r}",
                f"Point github_project_owner at {ctx.origin_owner!r}, or — after confirming "
                f"{owner!r} is trusted — run: git config agentic.trustedBoardOwners {owner}",
            )
        return BoardConfig(owner=owner, number=int(number), source=source)
    return None


@dataclass
class BindingConfig:
    """The recorded repo->board binding decisions (issue #64). `forward_binding`
    is the validated enum (or None when unset / unrecognized); `forward_raw` is
    the value as written, so the doctor can WARN on an unrecognized string
    instead of silently treating it as unset. `backfilled_through` is the
    high-water issue number of the last one-time backfill (None when never run)."""
    forward_binding: Optional[str]
    forward_raw: str
    backfilled_through: Optional[int]
    source: Optional[str]  # local | committed | None (unset)


def read_binding_config(ctx: RepoContext) -> BindingConfig:
    """Read (A) forward binding + (B) backfill high-water from the committed
    config (a .local override is honored for testing, same precedence as
    read_board_config, and ignored when tracked). Never raises: an unset or
    unrecognized value degrades to None so the caller supplies the default.

    The two decisions are orthogonal, so each key is resolved independently:
    a .local override that sets only one of them must not mask the other in the
    committed file (a single first-hit-wins scan would, and would then make
    `verb_backfill` misread `prior` and spuriously re-write the marker)."""
    layers: "list[tuple[str, dict[str, str]]]" = []
    for name, source_root, source_label in (
        (LOCAL_CONFIG, ctx.root, "local"),
        (COMMITTED_CONFIG, ctx.main_root, "committed"),
    ):
        path = pathlib.Path(source_root) / name
        if not path.is_file():
            continue
        if name == LOCAL_CONFIG and _is_tracked(ctx, name):
            continue
        layers.append((source_label, parse_frontmatter(path.read_text(encoding="utf-8"))))

    def first(key: str) -> "tuple[Optional[str], str]":
        for source_label, meta in layers:  # local before committed
            if meta.get(key, ""):
                return source_label, meta[key]
        return None, ""

    fb_source, raw = first(CONFIG_KEY_FORWARD_BINDING)
    bt_source, through = first(CONFIG_KEY_BACKFILLED_THROUGH)
    return BindingConfig(
        forward_binding=raw if raw in FORWARD_BINDINGS else None,
        forward_raw=raw,
        backfilled_through=int(through) if through.isdigit() else None,
        source=fb_source or bt_source,
    )


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
        path = _cache_path(ctx)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        os.replace(tmp, path)  # atomic: no partial/truncated cache is ever read
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
    cache_key = f"{board.owner}/{board.number}"
    cached = cache.get("schema", {})
    if (cached and cached.get("board_key") == cache_key
            and time.time() - cached.get("fetched_at", 0) < RECONCILE_TTL_SECONDS):
        options = cached.get("status_options") or {}
        if all(s in options for s in STAGES):
            try:
                return BoardSchema(**{k: v for k, v in cached.items()
                                     if k not in ("fetched_at", "board_key")})
            except TypeError:
                pass  # cache record shape drifted — fall through to a fresh fetch

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
    )
    cache["schema"] = {**dataclasses.asdict(schema), "fetched_at": time.time(),
                       "board_key": cache_key}
    return schema


# --------------------------------------------------------------------------
# Issue state (one batched GraphQL read per issue)
# --------------------------------------------------------------------------

ISSUE_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      number state stateReason url
      authorAssociation
      blockedBy(first: 1) { totalCount }
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
        blocked_by_count=(issue.get("blockedBy") or {}).get("totalCount", 0),
        url=issue.get("url", ""),
    )


def fetch_issue_state(number: int, board: BoardConfig, ctx: RepoContext,
                      runner: GhRunner) -> Optional[IssueState]:
    """Return the parsed issue state, None on a genuine 404 (issue is null),
    or raise BoardError('gh_read_failed') on a transport/auth failure — the
    caller must not conflate a failed read with a missing issue."""
    result = _run_gh_retry(runner, [
        "api", "graphql",
        "-f", f"query={ISSUE_QUERY}",
        "-F", f"owner={ctx.origin_owner}", "-F", f"repo={ctx.origin_repo}", "-F", f"number={number}",
    ])
    if result.returncode != 0:
        raise BoardError("gh_read_failed",
                         f"reading issue #{number} in {ctx.slug} failed: {result.stderr.strip()[:200]}",
                         "retry; check network/auth (gh auth status)")
    return parse_issue_state(json.loads(result.stdout or "{}"), board)


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
        # Beyond brainstormed (planned+, terminal, or abandoned): the item legally
        # skipped stub→planned and has no brainstorm doc by construction — never
        # repair_needed (that would walk the board backwards).
        if stage == "planned":
            return gr("already_done", "route_to_plan", "already planned — brainstorming is behind us")
        if _ORDER.get(stage, -2) > _ORDER["brainstormed"] or stage == "abandoned":
            return gr("already_done", "none", f"already {stage} — brainstorming is behind us")
        # stage == brainstormed exactly.
        if brainstorm_doc:
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
            return gr("route_to_plan", "plan", f"Status is {stage} but no plan doc with this join key exists — un-groomed")
        return gr("proceed", "work", f"{stage} with plan doc — claim (or resume) next")

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

        # Flag (never repaired): parent is ready-for-review but decomposed work
        # is unfinished. The seam gate blocks the agent path from creating this;
        # this catches the forced/out-of-band paths (rule 5's reality-sync, an
        # operator `--force`, a human drag) so an incomplete parent can't quietly
        # merge → ship. Never auto-repaired: neither closing the sub-issues nor
        # regressing the parent is safe to do unattended.
        if s.state == "OPEN" and s.stage == "in_review" and s.open_sub_issues:
            flags.append(Flag(s.number, "in_review_with_open_subissues",
                              f"reconciler: issue is in_review but has open sub-issues "
                              f"{s.open_sub_issues} — finish/close them, or the parent may merge "
                              "and ship with decomposed work still incomplete"))
    return repairs, flags


@dataclass
class ReadyItem:
    number: int
    title: str
    priority: Optional[str]
    repo: str


def _origin_issue_number(item: dict, origin_slug: str) -> Optional[int]:
    """The single repo-scoping predicate + normalizer for board items.

    Returns the issue number only when the item is an origin-repo Issue:
      - content must not be JSON-null (a shared board can carry null content);
      - type must be "Issue" or absent (PR-typed items are dropped);
      - the repository (string or {nameWithOwner}) normalized must equal the
        origin slug or be empty (shared/portfolio boards: read-tolerated,
        never foreign-written).
    Everything else returns None so callers never emit a foreign `issue(number)`
    read or a foreign write."""
    content = item.get("content") or {}
    if content.get("type") not in ("Issue", None):
        return None
    repo = content.get("repository") or ""
    if isinstance(repo, dict):
        repo = repo.get("nameWithOwner", "")
    if repo and repo != origin_slug:
        return None
    number = content.get("number")
    return number if isinstance(number, int) else None


def merge_ready_legs(board_items: "list[dict]", blocked_counts: "dict[int, int]",
                     origin_slug: str) -> "tuple[list[ReadyItem], bool]":
    """Leg 1 (item-list, server-filtered) x leg 2 (batched blockedBy counts).
    Repo-scoped: foreign-repo items are dropped, never acted on."""
    truncated = len(board_items) >= READY_WORK_LIMIT
    ready: "list[ReadyItem]" = []
    for item in board_items:
        number = _origin_issue_number(item, origin_slug)
        if number is None:
            continue
        if blocked_counts.get(number, 0) > 0:
            continue
        content = item.get("content") or {}
        ready.append(ReadyItem(number=number, title=content.get("title", item.get("title", "")),
                               priority=(item.get("priority") or None), repo=origin_slug))
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
                if current == "plan":
                    plan = rel
                else:
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


def verb_set_status(issue: int, stage: str, ctx: RepoContext, runner: GhRunner,
                    force: bool = False) -> dict:
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
    # Seam gate: a parent must not declare itself ready-for-review while its
    # decomposed work is unfinished. Enforced here (not just in work.md prose)
    # so an agent that skips the Phase-4 check cannot advance the parent and
    # bury the unfinished sub-issues under the merge → shipped automation. The
    # data is already in `state`; the reconciler and deliberate operator moves
    # pass force=True. Only `in_review` is gated — the agent-driven transition
    # that precedes the burying merge.
    if stage == "in_review" and not force and state.open_sub_issues:
        raise BoardError(
            "open_sub_issues",
            f"Issue #{issue} has open sub-issues {state.open_sub_issues} — cannot enter "
            "in_review until they are terminal",
            "Finish and `--sub-status <sub> done` each open sub-issue (or re-parent/close "
            "out-of-scope ones), then retry. Deliberate override: --force")
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


def verb_sub_status(issue: int, status: str, ctx: RepoContext, runner: GhRunner) -> dict:
    """Set a sub-issue's `status:*` label (mutually exclusive), board-free.

    `in_progress`/`in_review`/`blocked` swap the single live label on an OPEN
    sub-issue. `done` is terminal: strip every `status:*` label and close the
    issue as completed (the orchestrator's close, distinct from a PR auto-close).
    Idempotent — re-setting the current status is a cheap no-op edit; re-running
    `done` on an already-closed issue only reconciles labels.
    """
    if status not in SUB_STATUSES:
        raise BoardError("invalid_sub_status", f"{status!r} is not a sub-issue status",
                         f"Use one of: {', '.join(SUB_STATUSES)}")
    # One read for both the current labels and the open/closed state. A genuine
    # 404 (issue absent) surfaces as issue_not_found; a transport failure raises.
    view = _run_gh_retry(runner, ["issue", "view", str(issue), "--repo", ctx.slug,
                                  "--json", "labels,state"])
    if view.returncode != 0:
        stderr = view.stderr.strip()
        if "Could not resolve" in stderr or "not found" in stderr.lower():
            raise BoardError("issue_not_found", f"Issue #{issue} not found in {ctx.slug}",
                             "Check the issue number")
        raise BoardError("gh_read_failed", f"reading issue #{issue} failed: {stderr[:200]}",
                         "retry; check network/auth (gh auth status)")
    payload = json.loads(view.stdout or "{}")
    current = {lbl.get("name", "") for lbl in payload.get("labels", [])}
    present_status = [lbl for lbl in ALL_SUB_STATUS_LABELS if lbl in current]
    is_open = payload.get("state", "OPEN").upper() == "OPEN"

    if status == "done":
        if present_status:
            edit = _run_gh_retry(runner, ["issue", "edit", str(issue), "--repo", ctx.slug,
                                          *sum((["--remove-label", lbl] for lbl in present_status), [])])
            if edit.returncode != 0:
                raise BoardError("label_write_failed", f"remove-label failed: {edit.stderr.strip()[:200]}",
                                 "Verify issues-write permission on the repo")
        closed_now = False
        if is_open:
            close = _run_gh_retry(runner, ["issue", "close", str(issue), "--repo", ctx.slug,
                                           "--reason", "completed"])
            if close.returncode != 0:
                raise BoardError("issue_close_failed", f"close failed: {close.stderr.strip()[:200]}",
                                 "Verify issues-write permission on the repo")
            closed_now = True
        return {"issue": issue, "sub_status": "done", "closed": closed_now,
                "removed_labels": present_status}

    target = SUB_STATUS_LABELS[status]
    # Upsert the label (idempotent; also self-heals color/description) before
    # attaching it — removing labels never requires them to pre-exist here.
    color, desc = SUB_STATUS_LABEL_META[target]
    ensure = _run_gh_retry(runner, ["label", "create", target, "--repo", ctx.slug,
                                    "--color", color, "--description", desc, "--force"])
    if ensure.returncode != 0:
        raise BoardError("label_write_failed", f"ensuring {target} failed: {ensure.stderr.strip()[:200]}",
                         "Verify issues-write (triage) permission on the repo")
    remove = [lbl for lbl in present_status if lbl != target]
    add = [] if target in current else ["--add-label", target]
    edit_args = ["issue", "edit", str(issue), "--repo", ctx.slug, *add,
                 *sum((["--remove-label", lbl] for lbl in remove), [])]
    if add or remove:
        edit = _run_gh_retry(runner, edit_args)
        if edit.returncode != 0:
            raise BoardError("label_write_failed", f"issue-edit failed: {edit.stderr.strip()[:200]}",
                             "Verify issues-write permission on the repo")
    return {"issue": issue, "sub_status": status, "label": target,
            "removed_labels": remove, "was_open": is_open}


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

    assigned_by_us = False
    if not state.assignees:
        assign = _run_gh_retry(runner, ["issue", "edit", str(issue), "--repo", ctx.slug,
                                        "--add-assignee", "@me"])
        if assign.returncode != 0:
            raise BoardError("claim_failed", f"assign failed: {assign.stderr.strip()[:200]}",
                             "Verify triage permission on the repo")
        assigned_by_us = True

    # ALWAYS a fresh read to confirm. If the confirming read fails or 404s,
    # never fabricate a conflict from empty data: undo our own assignment
    # (best-effort) and surface the read failure honestly.
    def _self_unassign() -> None:
        _run_gh_retry(runner, ["issue", "edit", str(issue), "--repo", ctx.slug,
                               "--remove-assignee", "@me"])

    try:
        confirm = fetch_issue_state(issue, board, ctx, runner)
    except BoardError:
        if assigned_by_us:
            try:
                _self_unassign()
            except BoardError:
                pass
        raise BoardError("claim_unverified", "assignment succeeded but the confirming read failed",
                         "retry --claim")
    if confirm is None:
        if assigned_by_us:
            try:
                _self_unassign()
            except BoardError:
                pass
        raise BoardError("claim_unverified", "assignment succeeded but the confirming read failed",
                         "retry --claim")

    decision = decide_claim(confirm.assignees, me, confirm.blocked_by_count)
    if decision.action != "proceed":
        if me in confirm.assignees and len(confirm.assignees) > 1:
            _self_unassign()  # loser yields visibly
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
    # Scope BEFORE the batch: only origin-repo issue numbers may enter the
    # per-number blockedBy query (foreign/PR items would hard-fail it).
    numbers = [n for n in (_origin_issue_number(i, ctx.slug) for i in items) if n is not None]
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
                number = _origin_issue_number(item, ctx.slug)  # foreign items: never examined
                if number is not None:
                    numbers.append(number)

    # A failed read of one issue must not abort the whole run — record it and
    # keep reconciling the rest (a 404 legitimately drops the issue).
    states: "list[IssueState]" = []
    read_failures: "list[dict]" = []
    for n in dict.fromkeys(numbers):
        try:
            state = fetch_issue_state(n, board, ctx, runner)
        except BoardError as exc:
            read_failures.append({"issue": n, "error_code": exc.code, "error": str(exc)})
            continue
        if state is not None:
            states.append(state)
    repairs, flags = plan_repairs(states, ctx.default_branch)

    applied, failed = [], []
    for repair in repairs:
        try:
            if repair.to_stage:
                # A repair is a deliberate reality-sync (e.g. rule 5: a PR is
                # open → in_review); bypass the open-sub-issues seam gate.
                verb_set_status(repair.issue, repair.to_stage, ctx, runner, force=True)
            cascade_failed = None
            for sub in repair.close_sub_issues:
                close = _run_gh_retry(runner, ["issue", "close", str(sub), "--repo", ctx.slug,
                                               "--reason", "not planned",
                                               "--comment", f"reconciler: parent #{repair.issue} abandoned"])
                if close.returncode != 0:
                    cascade_failed = sub
                    break
            if cascade_failed is not None:
                failed.append({**dataclasses.asdict(repair),
                               "error_code": "cascade_close_failed",
                               "error": f"could not close sub-issue #{cascade_failed}"})
                continue
            # Flag/repair comments are best-effort: a failed comment does not
            # undo the applied Status write, so its returncode is not checked.
            _run_gh_retry(runner, ["issue", "comment", str(repair.issue), "--repo", ctx.slug,
                                   "--body", repair.comment])
            applied.append(dataclasses.asdict(repair))
        except BoardError as exc:
            failed.append({**dataclasses.asdict(repair), "error_code": exc.code, "error": str(exc)})
    for flag in flags:
        # Best-effort: a failed flag comment is not a repair failure.
        _run_gh_retry(runner, ["issue", "comment", str(flag.issue), "--repo", ctx.slug,
                               "--body", flag.comment])

    if issue is None:
        # Re-load the cache right before saving so a concurrent writer's schema
        # cache is not clobbered — set only our own field.
        fresh = load_cache(ctx)
        fresh["last_reconciled_at"] = now
        save_cache(ctx, fresh)
    return {"skipped_ttl": False, "repairs_applied": applied, "repairs_failed": failed,
            "read_failures": read_failures, "flags": [dataclasses.asdict(f) for f in flags]}


# --------------------------------------------------------------------------
# Backfill (issue #64, decision B). Auto-add is forward-only — it never places
# pre-existing issues on the board. Backfill is the one-time, idempotent loop
# that does. It is independent of the forward binding (A): a repo on
# workflow-only or manual may still have a pile of open issues to track.
#
# Correctness rules baked in here (the SpecFlow surfaced each):
#   - Enumerate REPO issues via `gh issue list` (issues only — PRs excluded for
#     free; NEVER `_item_list`, whose 50-cap would silently drop issues 51+).
#   - Open issues only: a long-closed issue added at stub would contradict the
#     "Item closed -> shipped" automation, so closed issues are skipped.
#   - Idempotent via ONE board-membership read (a set of issue numbers already
#     on the board), not an N+1 per-issue read; `item-add` is itself idempotent
#     server-side, so a stale membership read at worst re-adds harmlessly.
#   - Partial-failure-tolerant: one failed add never aborts the loop (mirrors
#     verb_reconcile). Issues are processed in ascending number order and the
#     recorded high-water mark advances only over a failure-free prefix.
#
# The high-water mark is an ADVISORY watermark, not a completeness guarantee:
# it is never read to skip work (verb_backfill always re-enumerates the full
# open-vs-board difference, so running it is always complete and idempotent).
# It exists only to let setup decide whether to *re-offer* the backfill prompt.
# Do NOT build gap-skipping logic on it — issue numbers are inherently gappy
# (PRs and closed issues consume numbers), so "everything <= mark is present"
# does not hold; a reopened lower-numbered issue is picked up by the next full
# --backfill run, not by trusting the mark.
# --------------------------------------------------------------------------

def _board_issue_numbers(board: BoardConfig, ctx: RepoContext,
                         runner: GhRunner) -> "tuple[set[int], bool]":
    """The set of origin-repo issue numbers already on the board, plus a
    truncation flag. Repo-scoped and PR-dropped via _origin_issue_number — a
    foreign or PR item never counts as 'already present'."""
    result = _run_gh_retry(runner, ["project", "item-list", str(board.number),
                                    "--owner", board.owner, "--format", "json",
                                    "--limit", str(BACKFILL_BOARD_LIMIT)])
    if result.returncode != 0:
        raise BoardError("backfill_failed",
                         f"reading board membership failed: {result.stderr.strip()[:200]}",
                         "Verify gh >= 2.94.0, the `project` scope, and that the board exists")
    items = json.loads(result.stdout or "{}").get("items", [])
    numbers = {n for n in (_origin_issue_number(i, ctx.slug) for i in items) if n is not None}
    return numbers, len(items) >= BACKFILL_BOARD_LIMIT


def _repo_open_issues(ctx: RepoContext, runner: GhRunner) -> "tuple[list[dict], bool]":
    """Open origin-repo issues as [{number, url}], plus a truncation flag.
    `gh issue list` returns issues only — PRs are excluded for free."""
    result = _run_gh_retry(runner, ["issue", "list", "--repo", ctx.slug,
                                    "--state", "open", "--limit", str(BACKFILL_ISSUE_LIMIT),
                                    "--json", "number,url"])
    if result.returncode != 0:
        raise BoardError("backfill_failed",
                         f"listing repo issues failed: {result.stderr.strip()[:200]}",
                         "Verify gh auth and that Issues are enabled on the repo")
    issues = json.loads(result.stdout or "[]")
    return issues, len(issues) >= BACKFILL_ISSUE_LIMIT


def verb_backfill(ctx: RepoContext, runner: GhRunner) -> dict:
    """Add every open origin-repo issue not already on the board, idempotently,
    then record an advisory high-water mark (see the section comment — it gates
    re-offer only, never skips work). Reports added / already-present / failed
    counts. Safe to re-run: a second pass adds only what a partial first pass
    missed, recomputing the full difference each time."""
    board = _require_board(ctx)
    existing, board_truncated = _board_issue_numbers(board, ctx, runner)
    issues, issues_truncated = _repo_open_issues(ctx, runner)

    added: "list[int]" = []
    already_present: "list[int]" = []
    failed: "list[dict]" = []
    high_water = 0
    contiguous = True  # cleared at the first failure so the mark stays truthful

    # Drop malformed rows (missing/typed-wrong number) before ordering.
    valid = [i for i in issues if isinstance(i.get("number"), int)]
    for issue in sorted(valid, key=lambda i: i["number"]):
        number = issue["number"]
        if number in existing:
            already_present.append(number)
            if contiguous:
                high_water = number
            continue
        url = issue.get("url") or ""
        if not url:
            # A number-known / url-missing row is a data anomaly — record it and
            # break the prefix rather than shell out `item-add --url ""`.
            failed.append({"issue": number, "error": "issue has no url — cannot add to board"})
            contiguous = False
            continue
        add = _run_gh_retry(runner, ["project", "item-add", str(board.number),
                                     "--owner", board.owner, "--url", url,
                                     "--format", "json"])
        if add.returncode != 0:
            failed.append({"issue": number, "error": add.stderr.strip()[:200]})
            contiguous = False
            continue
        added.append(number)
        if contiguous:
            high_water = number

    # Persist the high-water mark only when it advances and enumeration was
    # complete — a truncated read means the sweep was partial, so the watermark
    # would overstate how far the backfill actually reached.
    marker_written = False
    prior = read_binding_config(ctx).backfilled_through or 0
    if high_water > prior and not issues_truncated and not board_truncated:
        write_config_keys(ctx.main_root, {CONFIG_KEY_BACKFILLED_THROUGH: str(high_water)})
        marker_written = True

    flags: "list[dict]" = []
    if issues_truncated or board_truncated:
        flags.append({"flag": "backfill_truncated",
                      "comment": f"enumeration hit a {BACKFILL_ISSUE_LIMIT}-item cap "
                                 "(issues and/or board) — re-run to continue; the high-water "
                                 "mark was not advanced past the truncation point"})
    return {
        "added": added,
        "already_present": already_present,
        "failed": failed,
        "counts": {"added": len(added), "already_present": len(already_present),
                   "failed": len(failed)},
        "high_water": high_water,
        "marker_written": marker_written,
        "flags": flags,
    }


# --------------------------------------------------------------------------
# Board <-> repo link. Projects v2 boards are owned by a user/org and *linked*
# to repos — the link is what surfaces the board on the repo's Projects tab and
# enables repo-scoped features (auto-add-from-repo). Board *resolution* only
# needs owner+number, so a missing link is a discoverability gap (WARN), never
# a hard error. Shared by the bootstrap link step and the doctor check.
# --------------------------------------------------------------------------

PROJECT_REPOS_QUERY = (
    "query($owner: String!, $number: Int!) {\n"
    "  repositoryOwner(login: $owner) {\n"
    "    ... on User { projectV2(number: $number) { repositories(first: 100) { nodes { nameWithOwner } } } }\n"
    "    ... on Organization { projectV2(number: $number) { repositories(first: 100) { nodes { nameWithOwner } } } }\n"
    "  }\n"
    "}"
)


def project_linked_repos(owner: str, number: int, runner: GhRunner) -> "Optional[list[str]]":
    """Return the `owner/repo` slugs linked to the board, or None if the query
    could not be read (callers treat None as 'unknown' — the doctor SKIPs, the
    bootstrap still attempts the link). Owner may be a User or an Organization;
    one repositoryOwner lookup covers both (organization(login:) on a user
    account is a hard GraphQL error, mirroring the workflows query)."""
    result = runner(["api", "graphql", "-f", f"query={PROJECT_REPOS_QUERY}",
                     "-F", f"owner={owner}", "-F", f"number={number}"])
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    node = ((payload.get("data") or {}).get("repositoryOwner") or {}).get("projectV2") or {}
    nodes = (node.get("repositories") or {}).get("nodes") or []
    return [n.get("nameWithOwner", "") for n in nodes if n.get("nameWithOwner")]


PROJECT_WORKFLOWS_QUERY = (
    "query($owner: String!, $number: Int!) {\n"
    "  repositoryOwner(login: $owner) {\n"
    "    ... on User { projectV2(number: $number) { workflows(first: 20) { nodes { name enabled } } } }\n"
    "    ... on Organization { projectV2(number: $number) { workflows(first: 20) { nodes { name enabled } } } }\n"
    "  }\n"
    "}"
)


def project_workflows(owner: str, number: int, runner: GhRunner) -> "Optional[dict[str, bool]]":
    """Return `{workflow_name: enabled}` for the board's built-in workflows, or
    None if the query could not be read. The GraphQL API exposes only name +
    enabled (never a workflow's trigger/action config, and there is no
    create/enable mutation — only `deleteProjectV2Workflow`), so `enabled` is
    the one bit the doctor can verify. Owner may be a User or an Organization."""
    result = runner(["api", "graphql", "-f", f"query={PROJECT_WORKFLOWS_QUERY}",
                     "-F", f"owner={owner}", "-F", f"number={number}"])
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    node = ((payload.get("data") or {}).get("repositoryOwner") or {}).get("projectV2") or {}
    nodes = (node.get("workflows") or {}).get("nodes") or []
    return {w.get("name", ""): bool(w.get("enabled")) for w in nodes if w.get("name")}


# --------------------------------------------------------------------------
# Auto-add workflow detection (for the forward-binding doctor check). The
# built-in auto-add workflow has no API, but the `actions/add-to-project`
# alternative (issue #63) is a committed file we CAN see — so the doctor
# verifies the recorded auto-add decision against the file's presence instead
# of printing an uncheckable "verify by hand" line.
# --------------------------------------------------------------------------

def find_auto_add_workflow(ctx: RepoContext) -> Optional[str]:
    """Repo-relative path of the first .github/workflows/*.y{a,}ml that wires
    `actions/add-to-project`, or None. Purely local (no gh) — deterministic and
    unit-testable."""
    wf_dir = pathlib.Path(ctx.root) / ".github" / "workflows"
    if not wf_dir.is_dir():
        return None
    paths = sorted({p for pat in ("*.yml", "*.yaml") for p in wf_dir.glob(pat)})
    for path in paths:
        try:
            if "actions/add-to-project" in path.read_text(encoding="utf-8"):
                return str(path.relative_to(ctx.root))
        except OSError:
            continue
    return None


def evaluate_forward_binding_check(binding: BindingConfig,
                                   auto_add_workflow: Optional[str]) -> "tuple[str, str, str]":
    """Pure per-branch verdict for the forward-binding doctor check: returns
    (status, detail, fix). What "verify concretely" means differs per branch —
    workflow-only asserts NO orphaned auto-add file; auto-add asserts the file
    IS present (its token secret is write-only, hence unverifiable and called
    out); none/unset are informational. Kept pure (no gh, no fs) so every branch
    is unit-tested; verb_doctor supplies auto_add_workflow via
    find_auto_add_workflow."""
    fb = binding.forward_binding
    if binding.forward_raw and fb is None:
        return ("WARN",
                f"recorded forward binding {binding.forward_raw!r} is not one of "
                f"{', '.join(FORWARD_BINDINGS)}",
                f"Set {CONFIG_KEY_FORWARD_BINDING} to one of "
                f"{', '.join(FORWARD_BINDINGS)} in {COMMITTED_CONFIG}")
    if fb is None:
        return ("WARN",
                f"no forward binding recorded in {COMMITTED_CONFIG} — how new issues reach "
                "the board is undecided",
                "Re-run the setup bootstrap to record it, or set "
                f"{CONFIG_KEY_FORWARD_BINDING}: {DEFAULT_FORWARD_BINDING} in {COMMITTED_CONFIG}")
    if fb == "workflow-only":
        if auto_add_workflow is not None:
            return ("WARN",
                    f"forward binding is workflow-only but an auto-add workflow exists "
                    f"({auto_add_workflow})",
                    f"Remove {auto_add_workflow}, or set {CONFIG_KEY_FORWARD_BINDING}: auto-add "
                    f"in {COMMITTED_CONFIG} if you do want auto-add")
        return ("PASS",
                "workflow-only — the /workflows:* commands add items themselves; no auto-add", "")
    if fb == "auto-add":
        if auto_add_workflow is None:
            return ("WARN",
                    "forward binding is auto-add but no actions/add-to-project workflow is present "
                    "— new issues will NOT auto-reach the board",
                    "Scaffold .github/workflows/add-to-project.yml (see issue #63) and add its "
                    f"PAT/App-token secret, or set {CONFIG_KEY_FORWARD_BINDING}: workflow-only "
                    f"in {COMMITTED_CONFIG}")
        return ("PASS",
                f"auto-add workflow present ({auto_add_workflow}) — note: its token secret is "
                "write-only and cannot be verified from here; send a test issue to confirm", "")
    # none
    return ("PASS",
            "manual — issues are added to the board by hand (and via one-time backfill)", "")


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
        # The one native automation the lifecycle DEPENDS ON: "Item closed" is
        # the sole writer of `→ shipped` (no engine verb owns it). If a human
        # disables it, merges silently stop stamping shipped — a pure snowball
        # source. The API can read `enabled` (not the action config), so verify
        # that one bit here; bootstrap only checks it once, the doctor re-checks.
        if authed:
            workflows = project_workflows(board.owner, board.number, runner)
            if workflows is None:
                check("item_closed_workflow", "SKIP",
                      "could not read the board's built-in workflows")
            elif workflows.get("Item closed"):
                check("item_closed_workflow", "PASS",
                      "'Item closed' automation enabled (stamps shipped on merge-close)")
            else:
                check("item_closed_workflow", "FAIL",
                      "'Item closed' workflow is disabled — merged PRs will close issues but "
                      "Status will never advance to shipped",
                      "Re-enable it in the Project → Workflows UI (there is no API to enable "
                      "a built-in workflow), then re-run the doctor")
        # Board <-> repo link (discoverability; a missing link never blocks work).
        if authed and ctx.origin_owner:
            linked = project_linked_repos(board.owner, board.number, runner)
            if linked is None:
                check("board_repo_link", "SKIP", "could not read the board's linked repositories")
            elif ctx.slug in linked:
                check("board_repo_link", "PASS", f"linked to {ctx.slug}")
            else:
                check("board_repo_link", "WARN",
                      f"board is not linked to {ctx.slug} — it won't appear on the repo's Projects tab",
                      f"gh project link {board.number} --owner {board.owner} --repo {ctx.slug}")

        # Forward binding (issue #64, decision A): verify the RECORDED choice
        # concretely, per branch — not a generic "verify by hand" line. Purely
        # local (config + workflow file), so it runs regardless of auth.
        fb_status, fb_detail, fb_fix = evaluate_forward_binding_check(
            read_binding_config(ctx), find_auto_add_workflow(ctx))
        check("board_forward_binding", fb_status, fb_detail, fb_fix)

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
    group.add_argument("--sub-status", nargs=2, metavar=("N", "STATUS"))
    group.add_argument("--ready-work", action="store_true")
    group.add_argument("--reconcile", action="store_true")
    group.add_argument("--doctor", action="store_true")
    group.add_argument("--backfill", action="store_true")
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
            return _emit(verb_set_status(int(number), stage, ctx, run_gh, force=args.force))
        if args.sub_status:
            number, status = args.sub_status
            return _emit(verb_sub_status(int(number), status, ctx, run_gh))
        if args.ready_work:
            return _emit(verb_ready_work(ctx, run_gh))
        if args.reconcile:
            return _emit(verb_reconcile(ctx, run_gh, issue=args.issue, force=args.force))
        if args.doctor:
            return _emit(verb_doctor(ctx, run_gh))
        if args.backfill:
            return _emit(verb_backfill(ctx, run_gh))
    except BoardError as err:
        return _emit_error(err)
    except Exception as exc:  # noqa: BLE001 — edge-of-CLI belt-and-braces
        print(json.dumps({"ok": False, "error_code": "internal", "error": str(exc),
                          "fix": "report this — gh emitted an unexpected shape"}, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
