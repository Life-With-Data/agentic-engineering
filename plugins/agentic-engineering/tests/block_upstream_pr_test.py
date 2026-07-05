"""Allow/deny matrix for ``.claude/hooks/block-upstream-pr.sh``.

The hook is the PreToolUse(Bash) backstop for the "fork trap": it denies any
``gh`` write that could land on upstream (EveryInc/compound-engineering-plugin)
instead of origin (aagnone3/agentic-engineering). These tests drive it as a
subprocess with a PreToolUse JSON payload on stdin — ``{"tool_input":
{"command": "<the bash command>"}}`` — exactly the shape Claude Code sends, and
assert the ``permissionDecision`` in the JSON response (deny) or its absence
(allow, empty stdout).

The flagless-unpinned legs depend on gh's default repo NOT being pinned to
origin. The hook reads that from the *cwd's* git config
(``remote.origin.gh-resolved``) and derives the origin slug from
``git remote get-url origin``. So each flagless case runs inside a throwaway git
repo whose origin points at the fork and whose ``gh-resolved`` we set (or leave
unset) to simulate the pinned / unpinned states.

Run with:
``python3 -m unittest discover -s plugins/agentic-engineering/tests -p 'block_upstream_pr_test.py' -v``
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = (
    Path(__file__).resolve().parent.parent.parent.parent
    / ".claude"
    / "hooks"
    / "block-upstream-pr.sh"
)

ORIGIN_URL = "git@github.com:aagnone3/agentic-engineering.git"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _run(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


def _is_deny(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode != 0:
        raise AssertionError(
            f"hook exited nonzero ({result.returncode}): {result.stderr}"
        )
    if not result.stdout.strip():
        return False
    body = json.loads(result.stdout)
    return (
        body.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    )


class _RepoCase(unittest.TestCase):
    """Base: a temp git repo with an origin remote pointing at the fork.

    ``gh_resolved`` controls the pinned/unpinned simulation:
      - "base"  → gh default pinned to origin (flagless commands are safe)
      - None    → unpinned (flagless commands would resolve to the parent)
    """

    gh_resolved: str | None = "base"

    def setUp(self) -> None:
        self.assertTrue(HOOK.exists(), f"hook not found at {HOOK}")
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)
        _git(self.cwd, "init", "-q")
        _git(self.cwd, "remote", "add", "origin", ORIGIN_URL)
        if self.gh_resolved is not None:
            _git(
                self.cwd,
                "config",
                "remote.origin.gh-resolved",
                self.gh_resolved,
            )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assertAllow(self, command: str) -> None:
        self.assertFalse(
            _is_deny(_run(command, self.cwd)), msg=f"expected ALLOW: {command}"
        )

    def assertDeny(self, command: str) -> None:
        self.assertTrue(
            _is_deny(_run(command, self.cwd)), msg=f"expected DENY: {command}"
        )


class PinnedRepoTest(_RepoCase):
    """gh default pinned to origin — flagless commands are allowed; explicit
    upstream references are still denied."""

    gh_resolved = "base"

    # ---- pr / issue (original checks a + b) -------------------------------

    def test_explicit_repo_origin_allowed(self) -> None:
        self.assertAllow(
            "gh pr create --repo aagnone3/agentic-engineering --title x"
        )

    def test_explicit_upstream_pr_denied(self) -> None:
        self.assertDeny(
            "gh pr create --repo EveryInc/compound-engineering-plugin --title x"
        )

    def test_explicit_upstream_issue_denied(self) -> None:
        self.assertDeny(
            "gh issue create "
            "--repo EveryInc/compound-engineering-plugin --title x"
        )

    def test_flagless_pr_allowed_when_pinned(self) -> None:
        # Pinned → flagless resolves to origin, so it is safe.
        self.assertAllow("gh pr create --title x --body y")

    # ---- gh project -------------------------------------------------------

    def test_project_item_edit_origin_owner_allowed(self) -> None:
        self.assertAllow(
            "gh project item-edit --owner aagnone3 --id ITEM --field-id F"
        )

    def test_project_item_edit_upstream_owner_denied(self) -> None:
        self.assertDeny(
            "gh project item-edit --owner EveryInc --id ITEM --field-id F"
        )

    def test_flagless_project_write_allowed_when_pinned(self) -> None:
        self.assertAllow("gh project item-create --title 'draft'")

    def test_project_item_list_read_always_allowed(self) -> None:
        # item-list is a read subcommand — never matched, even with upstream owner.
        self.assertAllow("gh project item-list 1 --owner EveryInc")

    def test_project_field_create_upstream_owner_denied(self) -> None:
        self.assertDeny(
            "gh project field-create --owner EveryInc --name Priority "
            "--data-type SINGLE_SELECT"
        )

    # ---- gh api graphql (ProjectV2 mutations) -----------------------------

    def test_graphql_mutation_mentioning_upstream_denied(self) -> None:
        self.assertDeny(
            "gh api graphql -f query='mutation { "
            "updateProjectV2ItemFieldValue(input:{}) }' # board owner EveryInc"
        )

    def test_graphql_mutation_node_ids_only_allowed(self) -> None:
        # Node IDs are opaque; no upstream owner text → allowed (in-script
        # discipline is the real guard).
        self.assertAllow(
            "gh api graphql -f query='mutation { "
            'updateProjectV2Field(input:{projectId:"PVT_x",fieldId:"PVTF_y"}) }\''
        )

    def test_graphql_add_item_upstream_denied(self) -> None:
        self.assertDeny(
            "gh api graphql "
            '-f owner=EveryInc '
            "-f query='mutation { addProjectV2ItemById(input:{}) }'"
        )

    def test_graphql_non_projectv2_mutation_allowed(self) -> None:
        # resolveReviewThread etc. operate on opaque node IDs and are not
        # ProjectV2 mutations — never matched.
        self.assertAllow(
            "gh api graphql -f threadId=PRRT_x "
            "-f query='mutation { resolveReviewThread(input:{}) }'"
        )

    # ---- gh api REST + GH_REPO env prefix ---------------------------------

    def test_rest_post_to_upstream_denied(self) -> None:
        self.assertDeny(
            "gh api -X POST "
            "repos/EveryInc/compound-engineering-plugin/issues -f title=x"
        )

    def test_rest_method_flag_patch_upstream_denied(self) -> None:
        self.assertDeny(
            "gh api --method PATCH "
            "repos/EveryInc/compound-engineering-plugin/issues/1 -f state=closed"
        )

    def test_rest_get_upstream_read_allowed(self) -> None:
        # No write method → a read; upstream reads are fine (upstream-scan reads).
        self.assertAllow(
            "gh api repos/EveryInc/compound-engineering-plugin/issues"
        )

    def test_rest_post_to_origin_allowed(self) -> None:
        self.assertAllow(
            "gh api -X POST repos/aagnone3/agentic-engineering/issues -f title=x"
        )

    def test_gh_repo_upstream_prefix_denied(self) -> None:
        self.assertDeny(
            "GH_REPO=EveryInc/compound-engineering-plugin "
            "gh issue create --title x"
        )

    def test_gh_repo_origin_prefix_allowed(self) -> None:
        self.assertAllow(
            "GH_REPO=aagnone3/agentic-engineering gh issue create --title x"
        )

    # ---- untouched surfaces ----------------------------------------------

    def test_pr_view_read_always_allowed(self) -> None:
        self.assertAllow("gh pr view 5 --json title,body")

    def test_non_gh_command_untouched(self) -> None:
        self.assertAllow("echo hello && ls -la")

    def test_empty_command_allowed(self) -> None:
        result = _run("", self.cwd)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


class UnpinnedRepoTest(_RepoCase):
    """gh default NOT pinned to origin — flagless writes would resolve to the
    parent, so they are denied; explicit --repo/--owner origin still allowed."""

    gh_resolved = None

    def test_flagless_pr_denied_when_unpinned(self) -> None:
        self.assertDeny("gh pr create --title x --body y")

    def test_flagless_issue_denied_when_unpinned(self) -> None:
        self.assertDeny("gh issue create --title x --body y")

    def test_flagless_project_write_denied_when_unpinned(self) -> None:
        self.assertDeny("gh project item-create --title 'draft'")

    def test_flagless_project_edit_denied_when_unpinned(self) -> None:
        self.assertDeny("gh project item-edit --id ITEM --field-id F")

    def test_explicit_repo_origin_allowed_when_unpinned(self) -> None:
        # An explicit origin --repo is safe regardless of pin state.
        self.assertAllow(
            "gh issue create --repo aagnone3/agentic-engineering --title x"
        )

    def test_explicit_owner_origin_allowed_when_unpinned(self) -> None:
        self.assertAllow(
            "gh project item-create --owner aagnone3 --title 'draft'"
        )

    def test_project_read_allowed_when_unpinned(self) -> None:
        # Reads are never denied, even flagless while unpinned.
        self.assertAllow("gh project item-list 1")

    def test_pr_view_read_allowed_when_unpinned(self) -> None:
        self.assertAllow("gh pr view 5")


if __name__ == "__main__":
    unittest.main()
