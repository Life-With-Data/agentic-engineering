#!/usr/bin/env python3
"""
Claude Code / Cursor / Codex hook to catch a Node.js MAJOR-version mismatch
before a package-manager command runs.

A repo that pins its Node version (`.nvmrc`, or `package.json` `engines.node`)
expects every `pnpm`/`npm`/`yarn`/`npx`/`turbo` invocation to run on that
version. When the active shell is on a different major — a common failure when
the login shell defaults to an older/newer Node than the project needs — the
command fails cryptically (native-module ABI mismatches, `engines` refusals,
tooling that quietly misbehaves), the agent burns a turn diagnosing it, and the
same break resurfaces in CI. This guard turns that late, confusing failure into
an early, actionable one: it stops the command and tells the agent exactly how
to switch versions first.

It is the DX sibling of the `block-db-push` / `prevent-main-commit` guards: a
PreToolUse/Bash check that fires only on the exact footgun and otherwise costs
nothing. It NO-OPS entirely unless ALL of these hold, so a repo that does not
pin a Node version — or a non-Node repo — pays only a cheap regex:

  1. the tool call is Bash,
  2. the command actually runs a package manager (not `install`; those are
     more version-tolerant and matching them would over-block), and
  3. the repo declares a required Node major (`.nvmrc` / `engines.node`), and
  4. the active Node major differs from it.

Only when all four hold does it spawn `node --version` and block (exit 2) with
switch instructions. Advisory, never destructive — it rewrites nothing and
mutates nothing; it just refuses the run and explains the one-line fix.

Config is by ENVIRONMENT VARIABLE (matching `worktree-session` / `sdd-cache`):
a per-machine opt-out, not a per-clone frontmatter flag.

  AGENTIC_NODE_VERSION_CHECK=0   skip this hook entirely

Design notes:
- Pure logic lives in `evaluate()` so it can be unit tested without spawning a
  subprocess or driving the hook through stdin. `evaluate()` takes the current
  and required majors as arguments; the I/O (reading `node --version` and the
  repo's pin) lives in thin, separately testable helpers.
- Cross-harness payloads are normalized through `hook_payload.py`, same as the
  other guards.
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

# Package-manager subcommands that execute project/JS code and therefore care
# about the Node major. `install` is deliberately excluded: it is far more
# version-tolerant, and blocking it would over-fire on the most common command.
PACKAGE_MANAGER_PATTERNS = (
    r"\bpnpm\s+(?:dev|build|start|test|run|exec)\b",
    r"\bnpm\s+(?:run|test|start|exec)\b",
    r"\byarn\s+(?:dev|build|start|test|run)\b",
    r"\bnpx\s+",
    r"\bturbo\s+(?:run|dev|build|test)\b",
)


def is_package_manager_command(command: str) -> bool:
    """True if the command runs a package manager that executes Node code."""
    cleaned = _strip_quotes(command)
    return any(re.search(pat, cleaned) for pat in PACKAGE_MANAGER_PATTERNS)


def _strip_quotes(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    return command


def parse_major(version: str | None) -> int | None:
    """Parse a version string like 'v22.2.0' or '22' into its major int."""
    if not version:
        return None
    match = re.match(r"v?(\d+)", version.strip())
    return int(match.group(1)) if match else None


def current_node_major() -> int | None:
    """Major version of the Node.js currently on PATH, or None if unknown."""
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return parse_major(result.stdout)


def required_node_major(cwd: Path | None = None) -> int | None:
    """Required Node major from `.nvmrc`, else `package.json` engines.node."""
    root = cwd or Path.cwd()

    nvmrc = root / ".nvmrc"
    if nvmrc.exists():
        major = parse_major(nvmrc.read_text().strip())
        if major is not None:
            return major

    pkg = root / "package.json"
    if pkg.exists():
        try:
            engines = json.loads(pkg.read_text()).get("engines", {})
        except Exception:
            return None
        match = re.search(r">=?\s*(\d+)", str(engines.get("node", "")))
        if match:
            return int(match.group(1))

    return None


def evaluate(current_major: int | None, required_major: int | None) -> bool:
    """Return True if the command should be blocked as a version mismatch.

    A mismatch requires both majors to be known and different. Any unknown
    (no Node on PATH, no pin in the repo) means "don't get in the way".
    """
    if current_major is None or required_major is None:
        return False
    return current_major != required_major


def _switch_hint(required_major: int) -> str:
    """Best-available switch instruction for the host's version manager."""
    nvm_dir = os.environ.get("NVM_DIR")
    if not (nvm_dir and Path(nvm_dir).exists()):
        for candidate in (Path.home() / ".nvm", Path.home() / ".config" / "nvm"):
            if candidate.exists():
                nvm_dir = str(candidate)
                break
        else:
            nvm_dir = None

    if nvm_dir:
        return f'source "{nvm_dir}/nvm.sh" && nvm use {required_major}'

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
        return f"fnm use {required_major}"

    return (
        "install a Node version manager (e.g. nvm), then "
        f"`nvm install {required_major} && nvm use {required_major}`"
    )


def main() -> None:
    if os.environ.get("AGENTIC_NODE_VERSION_CHECK") == "0":
        emit_allow()

    input_data = normalize(json.load(sys.stdin))

    if input_data.get("tool_name") != "Bash":
        emit_allow()

    command = input_data.get("tool_input", {}).get("command", "")

    # Cheapest checks first: skip non-package-manager commands and repos with no
    # pin BEFORE spawning `node --version`, so non-Node repos pay nothing.
    if not is_package_manager_command(command):
        emit_allow()

    required = required_node_major()
    if required is None:
        emit_allow()

    current = current_node_major()
    if evaluate(current, required):
        print(_error_message(current, required, command), file=sys.stderr)
        sys.exit(2)

    emit_allow()


def _error_message(current_major: int, required_major: int, command: str) -> str:
    return "\n".join(
        [
            f"⚠️  Node.js v{current_major} is active, but this repo requires "
            f"v{required_major} (.nvmrc / package.json engines).",
            "",
            "Running package-manager commands on the wrong major fails "
            "cryptically here and again in CI. Switch first:",
            f"  {_switch_hint(required_major)}",
            "",
            "Then retry:",
            f"  {command}",
        ]
    )


if __name__ == "__main__":
    main()
