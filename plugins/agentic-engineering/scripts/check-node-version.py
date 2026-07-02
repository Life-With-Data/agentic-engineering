#!/usr/bin/env python3
"""
Claude Code hook to catch Node.js version mismatches before running package
manager commands.

Node/JS projects often pin a required Node major version via `.nvmrc` or
`package.json`'s `engines.node` field. Running package-manager commands under
the wrong major version produces cryptic, hard-to-diagnose failures (native
module ABI mismatches, ESM/CJS interop breaks, etc.) that look like code bugs
but are actually environment drift. This hook compares the active `node`
version against the project's declared requirement before letting a
package-manager command (npm/pnpm/yarn/npx/turbo) run, and blocks with the
exact switch command if they disagree.

No-ops entirely for non-Node projects (no `.nvmrc` / `engines.node` declared)
and for any tool call that isn't Bash — it never fires unless a project has
opted into a required Node version.

Design notes:
- Segment-aware: reuses the same quote-stripping approach as the other
  PreToolUse hooks so commands that merely *mention* npm/pnpm (e.g. inside a
  quoted string or comment) aren't mistaken for package-manager invocations.
- Pure logic lives in `evaluate()` so it can be unit tested without shelling
  out to a real `node` binary or driving the hook through stdin.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

PACKAGE_MANAGER_PATTERNS = [
    re.compile(r"\bpnpm\s+(?:run\s+)?(dev|build|start|test|exec)\b"),
    re.compile(r"\bnpm\s+(?:run\s+)?(run|test|start|exec)\b"),
    re.compile(r"\byarn\s+(dev|build|start|test|run)\b"),
    re.compile(r"\bnpx\s+"),
    re.compile(r"\bturbo\s+(run|dev|build|test)\b"),
]

ERROR_TEMPLATE = """
❌ BLOCKED: Node.js v{current} detected, but this project requires v{required}.

Running package-manager commands under the wrong Node major version produces
cryptic failures (native module ABI mismatches, ESM/CJS interop breaks) that
look like code bugs but are actually environment drift.

Switch first, then retry:
  nvm use {required}   (or: fnm use {required} / volta pin node@{required})
  {command}
""".strip()


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    message = evaluate(command)
    if message:
        print(message, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


def evaluate(command: str, cwd: str = ".") -> str:
    """Return an error message if `command` should be blocked, else "" ."""
    if not is_package_manager_command(strip_quotes(command)):
        return ""

    required = required_major_version(cwd)
    if required is None:
        return ""

    current = current_major_version()
    if current is None or current == required:
        return ""

    return ERROR_TEMPLATE.format(
        current=current, required=required, command=command.strip()
    )


def strip_quotes(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    return command


def is_package_manager_command(command: str) -> bool:
    return any(pattern.search(command) for pattern in PACKAGE_MANAGER_PATTERNS)


def required_major_version(cwd: str = "."):
    base = Path(cwd)

    nvmrc = base / ".nvmrc"
    if nvmrc.exists():
        major = parse_major(nvmrc.read_text(encoding="utf-8").strip())
        if major is not None:
            return major

    package_json = base / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        constraint = pkg.get("engines", {}).get("node", "")
        match = re.search(r">=?\s*(\d+)", constraint)
        if match:
            return int(match.group(1))

    return None


def current_major_version():
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return parse_major(result.stdout.strip())


def parse_major(version: str):
    match = re.match(r"v?(\d+)", version)
    return int(match.group(1)) if match else None


if __name__ == "__main__":
    main()
