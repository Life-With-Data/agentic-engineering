#!/usr/bin/env python3
"""Config-flag registry: the single declared inventory of every opt-in,
per-repo configuration flag the agentic-engineering plugin reads from
agentic-engineering.local.md (or, for board identity, the committed
agentic-engineering.md). Two consuming surfaces read this module's
--inventory: the `config` command (browse/toggle) and `lifecycle-doctor`
(read-only health report). `setup` writes through --set instead of
hand-templating frontmatter.

Adding a new flag: declare it in CONFIG_FLAGS below, next to the script
that reads it. tests/config-registry.test.ts fails CI if a script reads a
frontmatter key that isn't declared here.

CLI verbs:
  --inventory            full flag inventory (read-only JSON)
  --get <key>             one flag's state (read-only JSON)
  --set <key> <value>     validate + write (toggleable local flags only)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

_LB_SPEC = importlib.util.spec_from_file_location(
    "lifecycle_board", pathlib.Path(__file__).resolve().with_name("lifecycle_board.py")
)
assert _LB_SPEC is not None and _LB_SPEC.loader is not None
lifecycle_board = importlib.util.module_from_spec(_LB_SPEC)
sys.modules["lifecycle_board"] = lifecycle_board
_LB_SPEC.loader.exec_module(lifecycle_board)


@dataclass(frozen=True)
class ConfigFlag:
    key: str
    kind: str            # "boolean" | "enum" | "list" | "identity"
    default: str          # effective value when unset ("auto-detect" is a valid sentinel)
    description: str
    owner: str            # plugin-relative path of the script that READS this key
    file: str              # "local" (agentic-engineering.local.md) | "committed" (agentic-engineering.md)
    choices: "tuple[str, ...]" = ()   # for kind == "enum"
    toggleable: bool = True            # False => inventory-only, never writable via --set


CONFIG_FLAGS = [
    ConfigFlag(
        key="issue_tracker",
        kind="enum",
        default="auto-detect",
        description=(
            "Override which issue tracker /workflows-* skills resolve to. "
            "github-project (a GitHub Project board) is currently the only "
            "supported tracker; more may be supported later. Unset "
            "auto-detects: committed board config -> github-project, "
            "otherwise the repo is unconfigured (run the wf-setup lifecycle "
            "bootstrap)."
        ),
        owner="scripts/workflow-repo-preflight.py",
        file="local",
        choices=("github-project",),
    ),
    ConfigFlag(
        key="nudge_todowrite",
        kind="boolean",
        default="false",
        description=(
            "Reminds the agent, via a PreToolUse hook, to file durable, "
            "cross-session work with the resolved issue tracker instead of "
            "leaving it in TodoWrite's ephemeral in-session list."
        ),
        owner="scripts/nudge-todowrite-to-tracker.py",
        file="local",
    ),
    ConfigFlag(
        key="github_project_owner",
        kind="identity",
        default="",
        description=(
            "GitHub Projects v2 board owner (org/user slug) this repo is "
            "bound to. Board identity, not a feature toggle — set by "
            "lifecycle board bootstrap, never by /…:config."
        ),
        owner="scripts/lifecycle_board.py",
        file="committed",
        toggleable=False,
    ),
    ConfigFlag(
        key="github_project_number",
        kind="identity",
        default="",
        description=(
            "GitHub Projects v2 board number this repo is bound to. Board "
            "identity, not a feature toggle — set by lifecycle board "
            "bootstrap, never by /…:config."
        ),
        owner="scripts/lifecycle_board.py",
        file="committed",
        toggleable=False,
    ),
]

_BY_KEY = {flag.key: flag for flag in CONFIG_FLAGS}


def _unknown_flag_error(key: str) -> "lifecycle_board.BoardError":
    return lifecycle_board.BoardError(
        "unknown_flag", f"No config flag named {key!r}",
        f"Known flags: {', '.join(sorted(_BY_KEY))}")


def _config_path(ctx: "lifecycle_board.RepoContext", flag: ConfigFlag) -> pathlib.Path:
    if flag.file == "local":
        return pathlib.Path(ctx.root) / lifecycle_board.LOCAL_CONFIG
    return pathlib.Path(ctx.main_root) / lifecycle_board.COMMITTED_CONFIG


def _read_value(ctx: "lifecycle_board.RepoContext", flag: ConfigFlag) -> "tuple[Optional[str], str]":
    """Return (raw_value_or_None, source); source is 'local'/'committed'/'default'.

    A tracked LOCAL_CONFIG is ignored entirely (same security invariant every
    other local-config reader in this codebase enforces: a committed copy
    would ride a PR), degrading to 'default' rather than raising.
    """
    if flag.file == "local" and lifecycle_board._is_tracked(ctx, lifecycle_board.LOCAL_CONFIG):
        return (None, "default")
    path = _config_path(ctx, flag)
    if not path.is_file():
        return (None, "default")
    meta = lifecycle_board.parse_frontmatter(path.read_text(encoding="utf-8"))
    value = meta.get(flag.key)
    if value is None:
        return (None, "default")
    return (value, flag.file)


def _validate(flag: ConfigFlag, value: str) -> bool:
    if flag.kind == "boolean":
        return value.strip().lower() in {"true", "false"}
    if flag.kind == "enum":
        return value.strip().lower() in flag.choices
    if flag.kind in ("list", "identity"):
        return True  # list values are free-form; identity values are never validated here (never written via --set)
    return False


def _inventory_row(ctx: "lifecycle_board.RepoContext", flag: ConfigFlag) -> dict:
    raw, source = _read_value(ctx, flag)
    is_set = raw is not None
    valid = _validate(flag, raw) if is_set else True
    effective = raw if (is_set and valid) else flag.default
    return {
        "key": flag.key,
        "kind": flag.kind,
        "default": flag.default,
        "effective": effective,
        "set": is_set,
        "valid": valid,
        "source": source,
        "toggleable": flag.toggleable,
        "file": flag.file,
        "owner": flag.owner,
        "description": flag.description,
        "plugin": "agentic-engineering",
    }


def verb_inventory(ctx: "lifecycle_board.RepoContext") -> dict:
    return {"flags": [_inventory_row(ctx, flag) for flag in CONFIG_FLAGS]}


def verb_get(ctx: "lifecycle_board.RepoContext", key: str) -> dict:
    flag = _BY_KEY.get(key)
    if flag is None:
        raise _unknown_flag_error(key)
    return _inventory_row(ctx, flag)


def write_local_config_keys(root: str, keys: "dict[str, str]") -> str:
    """Local-config analogue of lifecycle_board.write_config_keys: create
    LOCAL_CONFIG with `keys` if missing, else upsert only those keys,
    preserving every other byte. Callers MUST have already verified the file
    is untracked and .gitignore-ensured (verb_set does both, in that order,
    before calling this)."""
    path = pathlib.Path(root) / lifecycle_board.LOCAL_CONFIG
    if not path.exists():
        body = "---\n" + "".join(f"{k}: {v}\n" for k, v in keys.items()) + "---\n"
        lifecycle_board._atomic_write(path, body)
        return str(path)
    text = path.read_text(encoding="utf-8")
    lifecycle_board._atomic_write(path, lifecycle_board.upsert_frontmatter_keys(text, keys))
    return str(path)


def _ensure_gitignore(root: str) -> None:
    """Ensure LOCAL_CONFIG is git-ignored before it is ever written, mirroring
    the wf-setup route's Step 4.5 recipe. A symlinked
    .gitignore is refused rather than followed — git itself would not read
    one, and a write must never follow a link to a file outside the repo."""
    root_path = pathlib.Path(root)
    gitignore = root_path / ".gitignore"
    if gitignore.is_symlink():
        return
    check = subprocess.run(
        ["git", "-C", root, "check-ignore", "-q", "--no-index", lifecycle_board.LOCAL_CONFIG],
        capture_output=True)
    if check.returncode == 0:
        return
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    gitignore.write_text(existing + f"{lifecycle_board.LOCAL_CONFIG}\n", encoding="utf-8")


def verb_set(ctx: "lifecycle_board.RepoContext", key: str, value: str) -> dict:
    flag = _BY_KEY.get(key)
    if flag is None:
        raise _unknown_flag_error(key)
    if not flag.toggleable or flag.file != "local":
        fix = ("Board identity is managed by lifecycle board bootstrap, not /…:config"
               if flag.kind == "identity"
               else f"{key!r} is committed config; edit it directly and commit the change")
        raise lifecycle_board.BoardError(
            "not_toggleable",
            f"{key!r} is not a toggleable local flag (kind={flag.kind}, file={flag.file})",
            fix)
    if not _validate(flag, value):
        fix = (f"Allowed values: {', '.join(flag.choices)}" if flag.choices
               else "Boolean flags accept true/false")
        raise lifecycle_board.BoardError(
            "invalid_value", f"{value!r} is not valid for {key!r} (kind={flag.kind})", fix)
    if lifecycle_board._is_tracked(ctx, lifecycle_board.LOCAL_CONFIG):
        raise lifecycle_board.BoardError(
            "local_config_tracked",
            f"{lifecycle_board.LOCAL_CONFIG} is tracked in git — a PR must not carry it",
            f"git rm --cached {lifecycle_board.LOCAL_CONFIG}")
    previous, _ = _read_value(ctx, flag)
    _ensure_gitignore(ctx.root)  # before the write: a later `git add -A` must not immediately re-track it
    path = write_local_config_keys(ctx.root, {key: value})
    return {"key": key, "value": value, "previous": previous, "file": flag.file, "path": path}


def main(argv: "list[str]") -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inventory", action="store_true")
    group.add_argument("--get", metavar="KEY")
    group.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"))
    args = parser.parse_args(argv)

    try:
        ctx = lifecycle_board.repo_context()
        if args.inventory:
            return lifecycle_board._emit(verb_inventory(ctx))
        if args.get:
            return lifecycle_board._emit(verb_get(ctx, args.get))
        if args.set:
            key, value = args.set
            return lifecycle_board._emit(verb_set(ctx, key, value))
    except lifecycle_board.BoardError as err:
        return lifecycle_board._emit_error(err)
    except Exception as exc:  # noqa: BLE001 — edge-of-CLI belt-and-braces
        print(json.dumps({"ok": False, "error_code": "internal", "error": str(exc),
                          "fix": "report this"}, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
