#!/usr/bin/env python3
"""
Claude Code hook to check the active Node.js version before running
package-manager commands, and suggest the fix when it doesn't match the
project's declared requirement.

Node/JS projects commonly pin a required major version via `.nvmrc` or
`package.json`'s `engines.node` field, because a mismatched runtime produces
cryptic, hard-to-diagnose failures (module interop issues, native addon
mismatches, etc.) rather than a clear version error. This hook only acts when
the project declares a required version AND the active `node` differs from
it — it is a no-op for non-Node projects (no `.nvmrc`/`engines` found) and for
projects already on the right version.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


# Commands that require Node.js version check
PACKAGE_MANAGER_PATTERNS = [
    r"\bpnpm\s+(dev|build|start|test|run|exec)\b",
    r"\bnpm\s+(run|test|start|exec)\b",
    r"\byarn\s+(dev|build|start|test|run)\b",
    r"\bnpx\s+",
    r"\bturbo\s+(run|dev|build|test)\b",
]


def get_current_node_version():
    """Get the currently active Node.js version."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_required_node_version():
    """Get the required Node.js version from .nvmrc or package.json."""
    # Try .nvmrc first
    nvmrc_path = Path(".nvmrc")
    if nvmrc_path.exists():
        content = nvmrc_path.read_text().strip()
        if content.startswith("v"):
            content = content[1:]
        match = re.match(r"(\d+)", content)
        if match:
            return int(match.group(1))

    # Try package.json engines field
    package_json_path = Path("package.json")
    if package_json_path.exists():
        try:
            with open(package_json_path) as f:
                pkg = json.load(f)
            engines = pkg.get("engines", {})
            node_constraint = engines.get("node", "")
            match = re.search(r">=?\s*(\d+)", node_constraint)
            if match:
                return int(match.group(1))
        except Exception:
            pass

    return None


def parse_node_version(version_str):
    """Parse a version string like 'v24.2.0' into major version number."""
    if not version_str:
        return None
    match = re.match(r"v?(\d+)", version_str)
    if match:
        return int(match.group(1))
    return None


def is_package_manager_command(command):
    """Check if the command is a package manager command that runs Node.js code."""
    # Skip if already using a ./run wrapper script (it's expected to handle
    # version switching itself).
    if command.strip().startswith("./run "):
        return False

    for pattern in PACKAGE_MANAGER_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


def get_nvm_dir():
    """Get NVM directory."""
    nvm_dir = os.environ.get("NVM_DIR")
    if nvm_dir and Path(nvm_dir).exists():
        return nvm_dir
    # Common default locations
    home = Path.home()
    for candidate in [home / ".nvm", home / ".config/nvm"]:
        if candidate.exists():
            return str(candidate)
    return None


def check_fnm_available():
    """Check if fnm is available."""
    try:
        result = subprocess.run(
            ["which", "fnm"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    input_data = json.load(sys.stdin)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if tool_name != "Bash":
        sys.exit(0)

    if not is_package_manager_command(command):
        sys.exit(0)

    current_version = get_current_node_version()
    required_major = get_required_node_version()

    if not current_version or not required_major:
        sys.exit(0)

    current_major = parse_node_version(current_version)
    if current_major is None:
        sys.exit(0)

    if current_major == required_major:
        sys.exit(0)  # Already on correct version

    # Version mismatch - suggest the fix
    nvm_dir = get_nvm_dir()
    has_fnm = check_fnm_available()

    run_wrapper = Path("./run")
    if run_wrapper.exists() and os.access(run_wrapper, os.X_OK):
        corrected_command = f"./run {command}"
        msg = f"""⚠️  Node.js v{current_major} detected, but v{required_major} required.

Use the wrapper script to auto-switch:
  {corrected_command}"""
        print(msg, file=sys.stderr)
        sys.exit(2)
    elif nvm_dir or has_fnm:
        if nvm_dir:
            switch_cmd = f'source "{nvm_dir}/nvm.sh" && nvm use {required_major}'
        else:
            switch_cmd = f"fnm use {required_major}"

        msg = f"""⚠️  Node.js v{current_major} detected, but v{required_major} required.

Switch version first:
  {switch_cmd}

Then retry:
  {command}"""
        print(msg, file=sys.stderr)
        sys.exit(2)
    else:
        msg = f"""❌ Node.js v{current_major} detected, but v{required_major} required.

Install nvm to enable version switching:
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
  nvm install {required_major}"""
        print(msg, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
