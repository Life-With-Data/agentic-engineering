"""Regression tests for ``scripts/check-node-version.py``.

This PreToolUse/Bash guard blocks a package-manager command when the active
Node.js MAJOR differs from the version the repo pins (`.nvmrc` /
`package.json` engines.node). Like the other guards, the tricky part is
precision: it must fire only on a real package-manager command in a repo that
actually pins a version, and stay quiet everywhere else (non-Node repos,
prose that merely mentions a command, matching majors, non-Bash tools).

Contract: exit code 2 blocks the command; exit code 0 allows it.

Run with: ``python3 -m unittest tests.check_node_version_test``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-node-version.py"

BLOCK = 2
ALLOW = 0


def _load_module():
    spec = importlib.util.spec_from_file_location("check_node_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cnv = _load_module()

NODE = shutil.which("node")


def _run_payload(
    payload: dict, cwd: str | None = None, env: dict | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        cwd=cwd,
        env=env,
    )


def _run(command: str, **kw) -> subprocess.CompletedProcess[str]:
    return _run_payload({"tool_name": "Bash", "tool_input": {"command": command}}, **kw)


class PureLogicTest(unittest.TestCase):
    def test_parse_major(self) -> None:
        self.assertEqual(cnv.parse_major("v22.2.0"), 22)
        self.assertEqual(cnv.parse_major("22"), 22)
        self.assertEqual(cnv.parse_major("v24"), 24)
        self.assertIsNone(cnv.parse_major(""))
        self.assertIsNone(cnv.parse_major(None))
        self.assertIsNone(cnv.parse_major("lts/hydrogen"))

    def test_is_package_manager_command(self) -> None:
        for cmd in [
            "pnpm build",
            "pnpm run test",
            "npm test",
            "npx tsc",
            "turbo run build",
            "cd apps/web && pnpm dev",
        ]:
            self.assertTrue(cnv.is_package_manager_command(cmd), cmd)

    def test_is_not_package_manager_command(self) -> None:
        for cmd in [
            "git status",
            "pnpm install",  # install is intentionally excluded
            "ls -la",
            "echo 'pnpm build'",  # quoted mention must not count
            'grep -r "pnpm dev" docs/',
        ]:
            self.assertFalse(cnv.is_package_manager_command(cmd), cmd)

    def test_evaluate(self) -> None:
        self.assertTrue(cnv.evaluate(24, 22))
        self.assertFalse(cnv.evaluate(22, 22))
        self.assertFalse(cnv.evaluate(None, 22))
        self.assertFalse(cnv.evaluate(24, None))
        self.assertFalse(cnv.evaluate(None, None))

    def test_required_from_nvmrc_and_engines(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".nvmrc").write_text("v20\n")
            self.assertEqual(cnv.required_node_major(root), 20)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "package.json").write_text(
                json.dumps({"engines": {"node": ">=22.0.0 <23.0.0"}})
            )
            self.assertEqual(cnv.required_node_major(root), 22)
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(cnv.required_node_major(Path(d)))


class HarnessContractTest(unittest.TestCase):
    def test_ignores_non_bash_tool(self) -> None:
        result = _run_payload(
            {"tool_name": "Write", "tool_input": {"command": "pnpm build"}}
        )
        self.assertEqual(result.returncode, ALLOW)

    def test_allows_non_package_manager_command(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".nvmrc").write_text("v99\n")  # pin present but command is inert
            self.assertEqual(_run("git status", cwd=d).returncode, ALLOW)

    def test_allows_when_repo_pins_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run("pnpm build", cwd=d).returncode, ALLOW)

    def test_env_opt_out_allows(self) -> None:
        if NODE is None:
            self.skipTest("node not installed")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".nvmrc").write_text("v99\n")  # would otherwise block
            env = dict(os.environ, AGENTIC_NODE_VERSION_CHECK="0")
            self.assertEqual(_run("pnpm build", cwd=d, env=env).returncode, ALLOW)

    def test_cursor_payload_shape_allows_when_no_pin(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            result = _run_payload({"command": "pnpm build"}, cwd=d)
            self.assertEqual(result.returncode, ALLOW)

    def test_blocks_on_major_mismatch(self) -> None:
        if NODE is None:
            self.skipTest("node not installed")
        current = cnv.current_node_major()
        if current is None:
            self.skipTest("could not resolve current node major")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".nvmrc").write_text(f"v{current + 1}\n")
            self.assertEqual(_run("pnpm build", cwd=d).returncode, BLOCK)

    def test_allows_on_matching_major(self) -> None:
        if NODE is None:
            self.skipTest("node not installed")
        current = cnv.current_node_major()
        if current is None:
            self.skipTest("could not resolve current node major")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".nvmrc").write_text(f"v{current}\n")
            self.assertEqual(_run("pnpm build", cwd=d).returncode, ALLOW)


if __name__ == "__main__":
    unittest.main()
