"""Regression tests for ``scripts/check-node-version.py``.

This PreToolUse/Bash hook blocks package-manager *run* commands when the active
Node.js major is outside the version the repository declares (`.nvmrc` /
`package.json` engines). The tricky part is precision in two directions:

- it must fire only on package-manager run/exec verbs, never on install/add,
  prose, or a command that already switches Node in the same line; and
- it must treat ``engines.node`` as a *range*, never an equality — a repo on
  ``">=18"`` must not be blocked while running Node 20. Every parse ambiguity
  (an `.nvmrc` alias, a ``||`` union, a wildcard, a missing bound) resolves to
  ALLOW, because a false block is worse than a missed mismatch.

The pure decision logic (`decide`, `allowed_range`, `parse_engines`) is imported
directly so the range edge-cases are exercised without a real `node` binary or
filesystem. A couple of subprocess smoke tests cover the payload/allow path.

Contract: exit code 2 blocks the command; exit code 0 allows it.

Run with: ``python3 -m unittest tests.check_node_version_test``.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-node-version.py"

BLOCK = 2
ALLOW = 0


def _load_module():
    spec = importlib.util.spec_from_file_location("check_node_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


cnv = _load_module()


def _run_payload(payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


class CommandDetectionTest(unittest.TestCase):
    def test_detects_run_verbs(self) -> None:
        for cmd in (
            "pnpm dev",
            "pnpm build",
            "pnpm test",
            "pnpm run typecheck",
            "npm test",
            "npm run build",
            "yarn dev",
            "npx tsc",
            "turbo run build",
            "cd apps/web && pnpm dev",
        ):
            self.assertTrue(cnv.is_package_manager_command(cmd), cmd)

    def test_ignores_install_and_unrelated(self) -> None:
        for cmd in (
            "pnpm install",
            "pnpm add zod",
            "npm ci",
            "yarn add react",
            "git commit -m 'pnpm dev'",
            "echo pnpm test",
            "ls",
        ):
            self.assertFalse(cnv.is_package_manager_command(cmd), cmd)

    def test_skips_commands_that_already_switch_node(self) -> None:
        for cmd in (
            "nvm use 22 && pnpm dev",
            "fnm use 22 && npm test",
        ):
            self.assertFalse(cnv.is_package_manager_command(cmd), cmd)


class NvmrcParsingTest(unittest.TestCase):
    def test_exact_majors(self) -> None:
        self.assertEqual(cnv.parse_nvmrc("22"), 22)
        self.assertEqual(cnv.parse_nvmrc("v22.3.0\n"), 22)
        self.assertEqual(cnv.parse_nvmrc("18.19.0"), 18)

    def test_aliases_and_blank_are_unresolvable(self) -> None:
        for text in ("lts/*", "lts/hydrogen", "node", "stable", "", "   "):
            self.assertIsNone(cnv.parse_nvmrc(text), text)


class EnginesParsingTest(unittest.TestCase):
    def test_bounded_range(self) -> None:
        # ">=22 <23" → exactly major 22.
        self.assertEqual(cnv.parse_engines(">=22.0.0 <23.0.0"), (22, 22))

    def test_open_upper_bound(self) -> None:
        # ">=18" → floor 18, no ceiling.
        self.assertEqual(cnv.parse_engines(">=18.0.0"), (18, None))
        self.assertEqual(cnv.parse_engines(">=18"), (18, None))

    def test_lt_nonzero_minor_keeps_major(self) -> None:
        # "<23.5.0" still allows 23.x → ceiling stays 23.
        self.assertEqual(cnv.parse_engines(">=22 <23.5.0"), (22, 23))

    def test_caret_and_tilde_and_exact_pin_major(self) -> None:
        self.assertEqual(cnv.parse_engines("^20.0.0"), (20, 20))
        self.assertEqual(cnv.parse_engines("~20.1.0"), (20, 20))
        self.assertEqual(cnv.parse_engines("20.x"), (20, 20))
        self.assertEqual(cnv.parse_engines("20"), (20, 20))

    def test_ambiguous_constraints_are_unresolvable(self) -> None:
        for text in ("*", "", ">=16 || >=18", None):
            self.assertIsNone(cnv.parse_engines(text), text)


class DecideTest(unittest.TestCase):
    def _run(self, cmd, nvmrc, engines, current):
        return cnv.decide(cmd, nvmrc, engines, current)

    def test_blocks_too_new_via_nvmrc(self) -> None:
        # The Node-24-breaks-Zod-v4 case: repo pins 22, machine on 24.
        self.assertEqual(self._run("pnpm dev", "22", None, "v24.2.0"), 22)

    def test_blocks_too_old_via_nvmrc(self) -> None:
        self.assertEqual(self._run("pnpm dev", "22", None, "v20.0.0"), 22)

    def test_allows_matching_major(self) -> None:
        self.assertIsNone(self._run("pnpm dev", "22", None, "v22.9.0"))

    def test_allows_open_range_satisfied(self) -> None:
        # The regression the source tool got wrong: ">=18" on Node 20 is fine.
        self.assertIsNone(self._run("pnpm dev", None, ">=18.0.0", "v20.0.0"))

    def test_blocks_below_open_floor(self) -> None:
        self.assertEqual(self._run("pnpm test", None, ">=18.0.0", "v16.0.0"), 18)

    def test_allows_within_bounded_range(self) -> None:
        self.assertIsNone(self._run("pnpm dev", None, ">=18 <23", "v22.0.0"))

    def test_blocks_above_bounded_range(self) -> None:
        self.assertEqual(self._run("pnpm dev", None, ">=18 <23.0.0", "v23.1.0"), 22)

    def test_nvmrc_wins_over_engines(self) -> None:
        self.assertEqual(self._run("pnpm dev", "22", ">=18", "v24.0.0"), 22)

    def test_no_constraint_is_noop(self) -> None:
        self.assertIsNone(self._run("pnpm dev", None, None, "v24.0.0"))

    def test_non_run_command_is_noop(self) -> None:
        self.assertIsNone(self._run("pnpm install", "22", None, "v24.0.0"))

    def test_unknown_current_version_is_noop(self) -> None:
        self.assertIsNone(self._run("pnpm dev", "22", None, None))

    def test_ambiguous_engines_is_noop(self) -> None:
        self.assertIsNone(self._run("pnpm dev", None, ">=16 || >=18", "v24.0.0"))


class EndToEndSmokeTest(unittest.TestCase):
    def test_non_bash_tool_is_allowed(self) -> None:
        result = _run_payload({"tool_name": "Write", "tool_input": {"command": "pnpm dev"}})
        self.assertEqual(result.returncode, ALLOW)

    def test_bad_stdin_fails_open(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, ALLOW)

    def test_non_package_manager_command_is_allowed(self) -> None:
        # No constraint files in the test cwd + not a run verb → always allow.
        result = _run_payload({"tool_name": "Bash", "tool_input": {"command": "git status"}})
        self.assertEqual(result.returncode, ALLOW)


if __name__ == "__main__":
    unittest.main()
