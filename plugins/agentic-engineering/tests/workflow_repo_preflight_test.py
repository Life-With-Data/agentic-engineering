"""Unit tests for workflow-repo-preflight.py's resolution logic.

Issue-tracker resolution is two-state: committed board config ->
github-project, otherwise "unconfigured" (a state, not a mode — the repo has
not run the wf-setup lifecycle bootstrap). Delivery posture is not a preflight
concern: it resolves from the ticket's own labels via lifecycle_board.py
(#401 removed the repo-level delivery_mode tier). The script filename is
hyphenated, so the module loads via importlib from its path.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "workflow-repo-preflight.py"

spec = importlib.util.spec_from_file_location("workflow_repo_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
sys.modules["workflow_repo_preflight"] = preflight
spec.loader.exec_module(preflight)


class ResolveIssueTrackerTest(unittest.TestCase):
    def test_board_config_resolves_github_project(self) -> None:
        info = preflight.resolve_issue_tracker(board_configured=True)
        self.assertEqual(info["resolved"], "github-project")
        self.assertEqual(info["source"], "auto-detect")

    def test_no_board_resolves_unconfigured(self) -> None:
        # No board -> the unconfigured *state* (not a mode): gates direct to
        # the wf-setup lifecycle bootstrap.
        info = preflight.resolve_issue_tracker(board_configured=False)
        self.assertEqual(info["resolved"], "unconfigured")
        self.assertEqual(info["source"], "auto-detect")

    def test_board_config_is_the_only_tracker_signal(self) -> None:
        # gh authentication and local-config overrides are not tracker
        # signals: the resolver takes exactly one input.
        params = inspect.signature(preflight.resolve_issue_tracker).parameters
        self.assertEqual(list(params), ["board_configured"])


class NoDeliveryModeTierTest(unittest.TestCase):
    """#401: the repo-level delivery-posture tier is deleted. Freeze the
    deletion by category — preflight must expose no delivery-posture
    resolution surface at all, under any spelling."""

    def test_preflight_has_no_delivery_posture_surface(self) -> None:
        offenders = [name for name in dir(preflight)
                     if "delivery" in name.lower() or "posture" in name.lower()]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
