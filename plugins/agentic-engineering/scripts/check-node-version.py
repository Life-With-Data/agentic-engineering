#!/usr/bin/env python3
"""
Claude Code hook to block package-manager RUN commands when the active Node.js
major is outside the version this repository declares.

Running `pnpm dev` / `npm test` / `turbo build` / `npx …` under the wrong Node
major is a classic source of cryptic, hard-to-diagnose failures: native-addon
ABI mismatches, ESM/CJS interop breaks (e.g. Zod v4 on Node >= 24), and
lockfile/engine warnings that surface as unrelated stack traces three layers
deep. The command usually *fails*, but slowly and confusingly, after the agent
has already spent a turn on it. This hook stops the doomed run before it starts
and hands back the one-line version switch.

It is the toolchain sibling of the `block-db-push` guard: it reads only files
that already exist in the repo (`.nvmrc`, `package.json` `engines.node`), so a
repository that declares no Node constraint — or any non-JS repo — pays nothing.

Design notes, mirroring the other PreToolUse guards:
- Pure logic lives in `decide()` / `allowed_range()` so it can be unit tested
  without a filesystem, subprocess, or stdin.
- **Fail-open on every ambiguity.** The declared constraint is parsed as a
  *range*, not an equality (a repo with `engines.node: ">=18"` must NOT be
  blocked while on Node 20). Anything this parser cannot resolve with certainty
  — an `.nvmrc` alias like `lts/*`, a `||` union, a `*` wildcard, a missing
  `node` binary, unreadable files — resolves to "allow". A version guard that
  false-blocks a valid command is worse than one that occasionally lets a
  mismatch through, so every unknown biases toward allow.
- Only package-manager *run/exec* verbs are considered. `install`/`add` are not
  gated (installing under a slightly-off major is usually fine, and blocking it
  would trap the user before they can fix anything), and a command that already
  switches Node in the same line (`nvm use …`, `fnm use …`) is skipped.
- Claude-only: this uses no Cursor/Codex-specific payload shape beyond the
  shared normalizer, but it is wired only into the Claude plugin hooks. It is
  not part of the portable safety-guard bundle.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import emit_allow, normalize

# Package-manager verbs that execute project JS under the active Node runtime.
# Deliberately excludes install/add/remove — those are gated by neither the
# original tool nor this one (see module docstring). Anchored to the START of a
# command segment so a mention mid-command (`echo pnpm test`, `grep npx`) does
# not fire.
PACKAGE_MANAGER_PATTERNS = [
    re.compile(r"^pnpm\s+(?:dev|build|start|test|run|exec)\b"),
    re.compile(r"^npm\s+(?:run|test|start|exec)\b"),
    re.compile(r"^yarn\s+(?:dev|build|start|test|run)\b"),
    re.compile(r"^npx\s+\S"),
    re.compile(r"^turbo\s+(?:run|dev|build|test)\b"),
]

# A command that already performs a Node switch in the same line is left alone.
ALREADY_SWITCHES = re.compile(r"\b(?:nvm|fnm)\s+use\b|\bvolta\s+run\b")

# Segment separators (`&&`, `||`, `;`, `|`, newline) so `cd app && pnpm dev`
# tests the `pnpm dev` segment, and leading env assignments are stripped.
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")
LEADING_ENV = re.compile(r"^(?:\w+=\S*\s+)+")


def _strip_quotes(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    return command


def is_package_manager_command(command: str) -> bool:
    cleaned = _strip_quotes(command)
    if ALREADY_SWITCHES.search(cleaned):
        return False
    for segment in SEGMENT_SPLIT.split(cleaned):
        stripped = LEADING_ENV.sub("", segment.strip())
        if any(pattern.match(stripped) for pattern in PACKAGE_MANAGER_PATTERNS):
            return True
    return False


def major_of(version: str | None) -> int | None:
    """Parse a version-ish string ('v22.3.0', '22', '22.x') into a major int."""
    if not version:
        return None
    match = re.match(r"v?(\d+)", version.strip())
    return int(match.group(1)) if match else None


def parse_nvmrc(text: str | None) -> int | None:
    """An `.nvmrc` pins an exact intended major, or is an unresolvable alias."""
    if not text:
        return None
    content = text.strip()
    if not content:
        return None
    # Aliases (lts/*, node, stable, ...) cannot be resolved offline → no-op.
    return major_of(content)


def parse_engines(constraint: str | None) -> tuple[int | None, int | None] | None:
    """Reduce an `engines.node` range to inclusive (lo_major, hi_major) bounds.

    Returns None when the constraint cannot be resolved with confidence — a
    union (`||`), a pure wildcard, or an empty string — so the caller allows.
    A None bound on either side means "open" (no lower / no upper limit).
    Every rule biases toward a WIDER allowed set than the true semver range, so
    the guard never blocks a version the range actually permits.
    """
    if not constraint:
        return None
    text = constraint.strip()
    if not text or "||" in text:
        return None

    lo: int | None = None
    hi: int | None = None
    saw_bound = False

    for token in text.split():
        m = re.match(r"^(>=|<=|>|<|\^|~|=)?\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", token)
        if not m:
            # A bare `*` / `x` / `latest` / unparseable token → give up (allow).
            if token in ("*", "x", "latest", "node"):
                return None
            return None
        op = m.group(1) or "="
        major = int(m.group(2))
        minor = int(m.group(3)) if m.group(3) not in (None, "x", "*") else None
        patch = int(m.group(4)) if m.group(4) not in (None, "x", "*") else None

        if op in (">=", ">"):
            # `>16.0.0` still allows 16.x, so the major floor is `major` either way.
            lo = major if lo is None else max(lo, major)
            saw_bound = True
        elif op == "<":
            # `<23.0.0` excludes all of major 23 → ceiling 22. `<23.5.0` allows
            # 23.x → ceiling 23. Only tighten to major-1 on a clean `.0.0`.
            ceil = major - 1 if (minor in (0, None) and patch in (0, None)) else major
            hi = ceil if hi is None else min(hi, ceil)
            saw_bound = True
        elif op == "<=":
            hi = major if hi is None else min(hi, major)
            saw_bound = True
        else:
            # `=`, `^`, `~`, or a bare `20` / `20.x` all pin a single major
            # (caret/tilde keep the major fixed for major >= 1).
            lo = major if lo is None else max(lo, major)
            hi = major if hi is None else min(hi, major)
            saw_bound = True

    return (lo, hi) if saw_bound else None


def allowed_range(
    nvmrc: str | None, engines_node: str | None
) -> tuple[int | None, int | None] | None:
    """Resolve the repo's allowed major range. `.nvmrc` wins when it pins one."""
    pinned = parse_nvmrc(nvmrc)
    if pinned is not None:
        return (pinned, pinned)
    return parse_engines(engines_node)


def decide(
    command: str,
    nvmrc: str | None,
    engines_node: str | None,
    current_version: str | None,
) -> int | None:
    """Return the major to switch to if `command` should be blocked, else None."""
    if not is_package_manager_command(command):
        return None
    allowed = allowed_range(nvmrc, engines_node)
    if allowed is None:
        return None
    current = major_of(current_version)
    if current is None:
        return None
    lo, hi = allowed
    if lo is not None and current < lo:
        return lo
    if hi is not None and current > hi:
        return hi
    return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except Exception:
        return None


def _engines_node() -> str | None:
    text = _read_text(Path("package.json"))
    if not text:
        return None
    try:
        node = json.loads(text).get("engines", {}).get("node", "")
    except Exception:
        return None
    return node if isinstance(node, str) and node else None


def _current_node_version() -> str | None:
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _switch_command(required: int) -> str:
    """Best-effort version-manager hint for the local machine."""
    try:
        has_fnm = (
            subprocess.run(
                ["which", "fnm"], capture_output=True, text=True, timeout=5
            ).returncode
            == 0
        )
    except Exception:
        has_fnm = False
    if has_fnm:
        return f"fnm use {required}"
    nvm_dir = os.environ.get("NVM_DIR") or str(Path.home() / ".nvm")
    if Path(nvm_dir).exists():
        return f"nvm use {required}"
    return f"nvm install {required} && nvm use {required}"


def _error(required: int, current: str | None) -> str:
    current_label = current or "an unsupported version"
    return (
        f"❌ BLOCKED: this repo targets Node.js {required}, but {current_label} "
        "is active.\n\n"
        "Package-manager run commands under the wrong Node major fail in "
        "confusing ways — native ABI mismatches, ESM/CJS interop breaks, engine "
        "warnings surfacing as unrelated stack traces.\n\n"
        "Switch first, then re-run your command:\n"
        f"  {_switch_command(required)}\n\n"
        "(This guard only reads `.nvmrc` / `package.json` engines; a repo with "
        "no Node constraint is never affected.)"
    )


def main() -> None:
    try:
        input_data = normalize(json.load(sys.stdin))
    except Exception:
        emit_allow()

    if input_data.get("tool_name") != "Bash":
        emit_allow()

    command = input_data.get("tool_input", {}).get("command", "")

    required = decide(
        command,
        nvmrc=_read_text(Path(".nvmrc")),
        engines_node=_engines_node(),
        current_version=_current_node_version(),
    )
    if required is not None:
        print(_error(required, _current_node_version()), file=sys.stderr)
        sys.exit(2)

    emit_allow()


if __name__ == "__main__":
    main()
