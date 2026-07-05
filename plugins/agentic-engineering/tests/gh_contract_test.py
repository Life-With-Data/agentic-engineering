"""Tier-2 gh contract tests for the unified lifecycle design.

The lifecycle_board module drives GitHub Projects v2 and native issue
dependencies exclusively through the ``gh`` CLI. That coupling is only safe if
the exact flags and JSON field names the design depends on actually exist in the
installed ``gh`` binary. Hand-written mocks cannot catch a flag rename or a JSON
shape change in a future gh release — only the real binary can.

Two legs, per the plan's Test Strategy (tier 2):

  (a) Flag-surface pinning — NO auth, NO network. Table-driven ``gh <cmd>
      --help`` assertions plus a version-gate (``gh --version`` >= 2.94.0) and an
      invalid-JSON-field probe that pins the dependency field names (blockedBy /
      blocking / parent) via gh's own "Available fields" error enumeration.
      This leg SKIPs loudly when gh is absent, but a version-gate failure is a
      real failure (never a skip) — gh < 2.94.0 lacks --parent/--blocked-by.

  (b) Read-only JSON-shape probes — network + auth. Runs against THIS repo's own
      history (aagnone3/agentic-engineering) and asserts the JSON shapes the
      reconciler reads: issue state/stateReason, PR mergedAt, and
      closedByPullRequestsReferences. Auto-SKIPs when ``gh auth status`` fails
      (e.g. CI without a configured token). Capped at <= 4 gh calls.

All gh invocations carry an explicit ``--repo aagnone3/agentic-engineering``
(fork-trap discipline — the plan's security invariant 7).

Run with:
    python3 -m unittest discover \
        -s plugins/agentic-engineering/tests -p 'gh_contract_test.py' -v
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest

REPO = "aagnone3/agentic-engineering"
MIN_GH = (2, 94, 0)

# Flags the lifecycle design depends on, keyed by gh subcommand. Each flag must
# appear verbatim in ``gh <subcommand> --help`` output. If gh renames or drops
# any of these, the corresponding writer contract in lifecycle_board silently
# breaks — this table is the tripwire.
HELP_FLAG_MATRIX = {
    "issue create": ["--parent", "--blocked-by"],
    "issue edit": ["--add-blocked-by", "--add-blocking", "--parent"],
    "issue list": ["--json"],
    "issue view": ["--json"],
    "project item-list": ["--query", "--owner", "--format", "--limit"],
    "project item-edit": [
        "--project-id",
        "--id",
        "--field-id",
        "--single-select-option-id",
    ],
    "project field-list": ["--owner", "--format"],
    "project create": ["--owner"],
}


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _run_gh(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _gh_authed() -> bool:
    """True only when gh can actually talk to github.com as an authed user."""
    if not _gh_available():
        return False
    try:
        proc = _run_gh(["auth", "status"], timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _parse_gh_version(version_output: str) -> tuple[int, int, int]:
    """Extract (major, minor, patch) from ``gh --version`` output.

    Example first line: ``gh version 2.96.0 (2026-07-02)``.
    """
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", version_output)
    if not match:
        raise AssertionError(
            f"could not parse gh version from output: {version_output!r}"
        )
    return tuple(int(g) for g in match.groups())  # type: ignore[return-value]


class GhFlagSurfaceTest(unittest.TestCase):
    """Leg (a): flag-surface pinning. No auth, no network required.

    The whole leg SKIPs loudly when gh is absent. Version-gate failures are
    real failures — a stale gh is exactly what this test exists to catch.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not _gh_available():
            raise unittest.SkipTest(
                "\n\n  !!! gh CLI not found on PATH — skipping the entire "
                "flag-surface leg. !!!\n"
                "  The lifecycle design REQUIRES gh >= 2.94.0. Install it "
                "(https://cli.github.com) and pin it in CI so this leg runs.\n"
            )

    def test_version_meets_floor(self) -> None:
        """gh --version must parse to >= 2.94.0 (a real failure, not a skip)."""
        proc = _run_gh(["--version"])
        self.assertEqual(
            proc.returncode, 0, f"`gh --version` failed: {proc.stderr}"
        )
        version = _parse_gh_version(proc.stdout)
        self.assertGreaterEqual(
            version,
            MIN_GH,
            f"gh {'.'.join(map(str, version))} is below the required "
            f"{'.'.join(map(str, MIN_GH))} — it lacks --parent/--blocked-by "
            "and the dependency JSON fields the lifecycle design needs.",
        )

    def test_help_flags_present(self) -> None:
        """Every (subcommand, flag) pair the design uses appears in --help."""
        for subcommand, flags in HELP_FLAG_MATRIX.items():
            with self.subTest(subcommand=subcommand):
                args = subcommand.split() + ["--help"]
                proc = _run_gh(args)
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"`gh {subcommand} --help` failed: {proc.stderr}",
                )
                # gh prints help to stdout; some builds mix in stderr.
                help_text = proc.stdout + proc.stderr
                for flag in flags:
                    self.assertIn(
                        flag,
                        help_text,
                        f"`gh {subcommand}` is missing the required flag "
                        f"{flag!r}. The lifecycle design depends on it.",
                    )

    def test_dependency_json_fields_enumerated(self) -> None:
        """An invalid --json field error enumerates the dependency fields.

        ``gh issue list --json bogusfield`` exits nonzero and prints an
        "Available fields" list. This pins blockedBy / blocking / parent as
        valid JSON fields WITHOUT any network call — if gh drops native
        dependency support, this error stops naming them.
        """
        proc = _run_gh(
            ["issue", "list", "--repo", REPO, "--json", "bogusfield"]
        )
        self.assertNotEqual(
            proc.returncode,
            0,
            "`gh issue list --json bogusfield` unexpectedly succeeded; the "
            "invalid-field enumeration probe is no longer valid.",
        )
        error_text = proc.stdout + proc.stderr
        for field in ("blockedBy", "blocking", "parent"):
            self.assertIn(
                field,
                error_text,
                f"gh no longer enumerates {field!r} as a valid issue JSON "
                "field — native dependency support may have changed.",
            )


class GhJsonShapeProbeTest(unittest.TestCase):
    """Leg (b): read-only JSON-shape probes. Network + auth required.

    Auto-SKIPs when ``gh auth status`` fails (CI without a configured token
    can't reach the API — that is expected and fine). Probes are capped at
    <= 4 gh calls total, all against this repo's own committed history.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not _gh_authed():
            raise unittest.SkipTest(
                "gh is unavailable or not authenticated (`gh auth status` "
                "failed) — skipping the read-only JSON-shape probe leg. This "
                "is expected in CI without a configured token."
            )

    def test_issue_view_state_shape(self) -> None:
        """issue view exposes state + stateReason with the expected casing.

        Probes issue #28 (this plan's own join key). state is UPPERCASE
        (OPEN or CLOSED) as gh emits it; stateReason is present (possibly the
        empty string for an open issue).
        """
        proc = _run_gh(
            [
                "issue",
                "view",
                "28",
                "--repo",
                REPO,
                "--json",
                "state,stateReason",
            ]
        )
        self.assertEqual(
            proc.returncode, 0, f"issue view failed: {proc.stderr}"
        )
        import json

        data = json.loads(proc.stdout)
        self.assertIn("state", data)
        self.assertIn("stateReason", data)
        # gh emits state in UPPERCASE — the reconciler compares against these.
        self.assertIn(
            data["state"],
            ("OPEN", "CLOSED"),
            f"unexpected state casing: {data['state']!r} (expected OPEN or "
            "CLOSED uppercase)",
        )

    def test_closed_issue_state_reason_casing(self) -> None:
        """A closed issue emits an UPPERCASE stateReason (e.g. COMPLETED).

        Issue #31 is closed-as-completed in this repo's history. Recording the
        actual casing here pins the strings the reconciler switches on
        (COMPLETED vs NOT_PLANNED). Reconciler repair #2 keys on NOT_PLANNED.
        """
        proc = _run_gh(
            [
                "issue",
                "view",
                "31",
                "--repo",
                REPO,
                "--json",
                "state,stateReason,closedByPullRequestsReferences",
            ]
        )
        self.assertEqual(
            proc.returncode, 0, f"issue view failed: {proc.stderr}"
        )
        import json

        data = json.loads(proc.stdout)
        self.assertEqual(data["state"], "CLOSED")
        # As emitted by gh 2.96.0 for a completed close: UPPERCASE "COMPLETED".
        self.assertEqual(
            data["stateReason"],
            "COMPLETED",
            f"expected stateReason 'COMPLETED' (uppercase) for a completed "
            f"close; got {data['stateReason']!r}",
        )
        # closedByPullRequestsReferences is a list; issue #31 was closed by a PR.
        self.assertIn("closedByPullRequestsReferences", data)
        self.assertIsInstance(data["closedByPullRequestsReferences"], list)
        self.assertGreaterEqual(
            len(data["closedByPullRequestsReferences"]),
            1,
            "issue #31 should carry at least one closing-PR reference",
        )
        ref = data["closedByPullRequestsReferences"][0]
        self.assertIn("number", ref)
        self.assertIn("url", ref)

    def test_merged_pr_shape(self) -> None:
        """A merged PR exposes a non-null mergedAt timestamp.

        The reconciler distinguishes merged from closed-unmerged PRs via
        mergedAt. Uses one call to find a merged PR (single source of truth).
        """
        proc = _run_gh(
            [
                "pr",
                "list",
                "--repo",
                REPO,
                "--state",
                "merged",
                "--limit",
                "1",
                "--json",
                "number,mergedAt",
            ]
        )
        self.assertEqual(
            proc.returncode, 0, f"pr list failed: {proc.stderr}"
        )
        import json

        prs = json.loads(proc.stdout)
        self.assertIsInstance(prs, list)
        self.assertGreaterEqual(
            len(prs), 1, "expected at least one merged PR in repo history"
        )
        pr = prs[0]
        self.assertIn("mergedAt", pr)
        self.assertIsNotNone(
            pr["mergedAt"],
            "a merged PR must have a non-null mergedAt timestamp",
        )
        # Shape check: ISO-8601 Z-suffixed timestamp.
        self.assertRegex(
            pr["mergedAt"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            f"unexpected mergedAt shape: {pr['mergedAt']!r}",
        )


if __name__ == "__main__":
    unittest.main()
