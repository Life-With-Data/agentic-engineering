"""Tests for ``scripts/check-node-version.py``.

`evaluate()` holds all the pure decision logic (command matching, reading the
required version from `.nvmrc` / `package.json`, comparing against the active
`node`); it's exercised directly via `importlib` (the script's hyphenated
filename isn't a valid module name) so tests can monkeypatch
`current_major_version()` instead of depending on whatever Node happens to be
installed on the machine running the suite. The stdin/exit-code contract is
covered separately with real subprocess calls for the no-op fast paths, which
don't require a real `node` binary.

Run with: ``python3 -m unittest tests.check_node_version_test``.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-node-version.py"

_spec = importlib.util.spec_from_file_location("check_node_version", SCRIPT)
check_node_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_node_version)


def _run(payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


class EvaluateLogicTest(unittest.TestCase):
    """Direct-import tests for the pure decision logic."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)
        self._orig_current = check_node_version.current_major_version

    def tearDown(self) -> None:
        check_node_version.current_major_version = self._orig_current
        self._tmp.cleanup()

    def _fake_current(self, major: int) -> None:
        check_node_version.current_major_version = lambda: major

    def test_blocks_on_nvmrc_mismatch(self) -> None:
        (self.cwd / ".nvmrc").write_text("v22\n", encoding="utf-8")
        self._fake_current(24)
        message = check_node_version.evaluate("pnpm run build", cwd=str(self.cwd))
        self.assertIn("v24", message)
        self.assertIn("v22", message)
        self.assertIn("nvm use 22", message)

    def test_passes_on_nvmrc_match(self) -> None:
        (self.cwd / ".nvmrc").write_text("22\n", encoding="utf-8")
        self._fake_current(22)
        message = check_node_version.evaluate("pnpm run build", cwd=str(self.cwd))
        self.assertEqual(message, "")

    def test_blocks_on_package_json_engines_mismatch(self) -> None:
        (self.cwd / "package.json").write_text(
            json.dumps({"engines": {"node": ">=22.0.0 <23.0.0"}}), encoding="utf-8"
        )
        self._fake_current(24)
        message = check_node_version.evaluate("npm run test", cwd=str(self.cwd))
        self.assertIn("v24", message)
        self.assertIn("v22", message)

    def test_noop_when_no_version_declared(self) -> None:
        self._fake_current(24)
        message = check_node_version.evaluate("pnpm run build", cwd=str(self.cwd))
        self.assertEqual(message, "")

    def test_noop_for_non_package_manager_command(self) -> None:
        (self.cwd / ".nvmrc").write_text("22\n", encoding="utf-8")
        self._fake_current(24)
        message = check_node_version.evaluate("ls -la", cwd=str(self.cwd))
        self.assertEqual(message, "")

    def test_noop_when_command_only_mentions_npm_in_quotes(self) -> None:
        (self.cwd / ".nvmrc").write_text("22\n", encoding="utf-8")
        self._fake_current(24)
        message = check_node_version.evaluate(
            'echo "run npm run build later"', cwd=str(self.cwd)
        )
        self.assertEqual(message, "")

    def test_npx_always_matches_package_manager_pattern(self) -> None:
        (self.cwd / ".nvmrc").write_text("22\n", encoding="utf-8")
        self._fake_current(24)
        message = check_node_version.evaluate(
            "npx inngest-cli@latest dev", cwd=str(self.cwd)
        )
        self.assertIn("v24", message)


class HookContractTest(unittest.TestCase):
    """Subprocess-level tests for the stdin/exit-code contract."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_noop_for_non_bash_tool(self) -> None:
        result = _run(
            {"tool_name": "Write", "tool_input": {"command": "pnpm run build"}},
            self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_noop_without_nvmrc_or_engines(self) -> None:
        result = _run(
            {"tool_name": "Bash", "tool_input": {"command": "pnpm run build"}},
            self.cwd,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
