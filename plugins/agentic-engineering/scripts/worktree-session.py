#!/usr/bin/env python3
"""SessionStart(startup) hook: bootstrap and advise on Claude Code worktrees.

Claude Code creates session worktrees under `<repo>/.claude/worktrees/<name>`
with a bare `git worktree add` — no dependency install, no gitignored-file copy.
The `wf-development` worktree route only helps when a human invokes its manager script by
hand; it does nothing for the worktrees the harness spins up itself (parallel /
web sessions and `isolation:"worktree"` subagents). This hook fills that gap so a
fresh harness-created worktree is usable immediately, and warns when the current
worktree is stale.

It does three things, each a no-op outside a linked `.claude/worktrees/*` tree:

  1. Copy gitignored env files git can't bring into a worktree (`.env`, `.env.local`,
     and one/two levels of `*/.env*`) from the main tree.
  2. Run an OPT-IN bootstrap command (`$AGENTIC_WORKTREE_BOOTSTRAP_CMD`, e.g.
     "pnpm install") once, gated on a marker so a bootstrapped worktree pays nothing.
  3. Emit a staleness advisory (non-destructive) when the worktree's branch is
     already merged into the default branch — it won't receive further changes.

Config is by ENVIRONMENT VARIABLE, not `agentic-engineering.local.md` frontmatter
— matching the `sdd-cache` precedent: a per-machine choice (which command installs
deps, whether to bootstrap at all) should not ride a PR and flip behavior for every
clone.

  WORKTREE_BOOTSTRAP=0            skip this hook entirely
  AGENTIC_WORKTREE_BOOTSTRAP_CMD  shell command to install deps in a fresh worktree
  AGENTIC_WORKTREE_ENV_GLOBS      ':'-separated globs (relative to the main tree) to
                                  copy, overriding the built-in defaults

Never blocks and never fails the session — always exits 0. Output, when there is
anything to say, is a SessionStart `additionalContext` JSON note to the model.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ENV_GLOBS = (
    ".env",
    ".env.local",
    "*/.env",
    "*/.env.local",
    "*/*/.env",
    "*/*/.env.local",
)
BOOTSTRAP_MARKER = ".claude-worktree-bootstrap-ok"


def _run(args: list[str], cwd: str | None = None, timeout: int = 20):
    """Run a git/shell command, returning (rc, stdout). Never raises."""
    try:
        p = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout.strip()
    except Exception:
        return 1, ""


def _emit(note: str) -> None:
    """Feed a note back to the model as SessionStart additionalContext."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": note,
        }
    }
    print(json.dumps(payload))


def _read_cwd() -> str:
    """SessionStart payload carries `.cwd`; fall back to project dir / PWD."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    cwd = (data.get("cwd") or "").strip()
    if not cwd:
        cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return cwd


def _main_root(cwd: str) -> str | None:
    """Absolute path of the main working tree, or None if cwd isn't in a repo."""
    rc, common = _run(["git", "rev-parse", "--git-common-dir"], cwd=cwd)
    if rc != 0 or not common:
        return None
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = Path(cwd) / common_path
    try:
        return str(common_path.parent.resolve())
    except Exception:
        return None


def _default_branch(main_root: str) -> str:
    """Best-effort remote default branch (origin/HEAD), falling back to main."""
    rc, ref = _run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        cwd=main_root,
    )
    if rc == 0 and ref:
        return ref  # e.g. "origin/main"
    for cand in ("main", "master"):
        rc, _ = _run(
            ["git", "rev-parse", "--verify", "--quiet", f"origin/{cand}"],
            cwd=main_root,
        )
        if rc == 0:
            return f"origin/{cand}"
    return "origin/main"


def _copy_env_files(cwd: str, main_root: str) -> int:
    """Copy missing gitignored env files from the main tree. Returns count copied."""
    globs = os.environ.get("AGENTIC_WORKTREE_ENV_GLOBS")
    patterns = globs.split(":") if globs else list(DEFAULT_ENV_GLOBS)
    root = Path(main_root)
    dest_root = Path(cwd)
    copied = 0
    for pattern in patterns:
        for src in root.glob(pattern):
            if not src.is_file():
                continue
            if src.name.endswith(".example") or src.name.endswith(".sample"):
                continue
            try:
                rel = src.relative_to(root)
            except ValueError:
                continue
            dst = dest_root / rel
            if dst.exists():
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
                copied += 1
            except Exception:
                continue
    return copied


def _bootstrap(cwd: str) -> str | None:
    """Run the opt-in bootstrap command once. Returns a note, or None if nothing ran."""
    cmd = os.environ.get("AGENTIC_WORKTREE_BOOTSTRAP_CMD")
    if not cmd:
        return None
    marker = Path(cwd) / BOOTSTRAP_MARKER
    if marker.exists():
        return None
    rc, _ = _run(["/bin/sh", "-c", cmd], cwd=cwd, timeout=900)
    if rc == 0:
        try:
            marker.write_text("ok\n")
        except Exception:
            pass
        return f"Worktree bootstrap ran: `{cmd}` succeeded. Ready for typecheck/build."
    return (
        f"Worktree bootstrap: `{cmd}` FAILED (exit {rc}). Run it manually and fix "
        "before typecheck/build."
    )


def _stale_note(cwd: str, main_root: str) -> str | None:
    """Advisory when this worktree's branch is already merged into the default branch."""
    rc, branch = _run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=cwd)
    if rc != 0 or not branch:
        return None  # detached HEAD → nothing to advise
    base = _default_branch(main_root)
    _run(["git", "fetch", "-q", "origin", base.split("/", 1)[-1]], cwd=main_root)
    rc, cherry = _run(["git", "cherry", base, branch], cwd=main_root)
    if rc != 0:
        return None
    lines = [ln for ln in cherry.splitlines() if ln.strip()]
    plus = sum(1 for ln in lines if ln.startswith("+"))
    merged = sum(1 for ln in lines if ln.startswith("-"))
    # Stale = had commits, all patches now in base (all '-'). Fresh branch (0 commits)
    # or any '+' (unmerged work) is NOT stale.
    if plus != 0 or merged < 1:
        return None
    rc, dirty = _run(["git", "status", "--porcelain"], cwd=cwd)
    dirty_note = (
        " It has uncommitted changes — commit or discard them first."
        if dirty
        else ""
    )
    return (
        f"⚠ This worktree is on '{branch}', already merged into {base} — it's stale "
        f"and won't receive further changes.{dirty_note} For new work, start a fresh "
        "session/worktree."
    )


def main() -> int:
    if os.environ.get("WORKTREE_BOOTSTRAP") == "0":
        return 0
    cwd = _read_cwd()
    try:
        if not Path(cwd).is_dir():
            return 0
    except Exception:
        return 0

    main_root = _main_root(cwd)
    if not main_root:
        return 0
    try:
        cwd_abs = str(Path(cwd).resolve())
    except Exception:
        cwd_abs = cwd
    if cwd_abs == main_root:
        return 0  # main tree → nothing to do

    # Only act inside a harness-created worktree.
    wt_prefix = str(Path(main_root) / ".claude" / "worktrees")
    if not cwd_abs.startswith(wt_prefix + os.sep):
        return 0

    notes: list[str] = []
    copied = _copy_env_files(cwd, main_root)
    if copied:
        notes.append(f"Copied {copied} gitignored env file(s) from the main tree.")

    boot = _bootstrap(cwd)
    if boot:
        notes.append(boot)
    elif not os.environ.get("AGENTIC_WORKTREE_BOOTSTRAP_CMD"):
        notes.append(
            "Fresh worktree: dependencies are not installed. Set "
            "AGENTIC_WORKTREE_BOOTSTRAP_CMD (e.g. \"pnpm install\") to auto-bootstrap, "
            "or install them manually before typecheck/build."
        )

    stale = _stale_note(cwd, main_root)
    if stale:
        notes.append(stale)

    if notes:
        _emit("\n".join(notes))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open: a broken bootstrap hook must never block a session start.
        sys.exit(0)
