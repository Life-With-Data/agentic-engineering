"""Tier-1 hermetic tests for lifecycle_board.py's pure decision core.

Covers: gate verdict tables, claim decisions (sole-assignee / blocked),
the CLOSED five-repair reconciler set with never-repair negatives, repo-scoped
ready-work merge + Priority sort + truncation flag, join-key normalization,
and call-count budgets via an argv-recording fake runner. No network, no gh.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lifecycle_board.py"

spec = importlib.util.spec_from_file_location("lifecycle_board", SCRIPT)
assert spec is not None and spec.loader is not None
lb = importlib.util.module_from_spec(spec)
sys.modules["lifecycle_board"] = lb
spec.loader.exec_module(lb)


def _issue(number=1, state="OPEN", state_reason=None, assignees=(), stage=None,
           closing_prs=(), open_subs=(), blocked=0):
    return lb.IssueState(
        number=number, state=state, state_reason=state_reason,
        assignees=list(assignees), author_association="OWNER", stage=stage,
        item_id="item", closing_prs=list(closing_prs),
        open_sub_issues=list(open_subs), blocked_by_count=blocked,
    )


def _pr(number=10, state="MERGED", merged=True, base="main", author="me"):
    return {"number": number, "state": state, "merged": merged,
            "baseRefName": base, "author": author}


class StageOrderTest(unittest.TestCase):
    def test_deployed_and_compounded_are_order_independent_refinements(self) -> None:
        self.assertEqual(lb._ORDER["deployed"], lb._ORDER["shipped"])
        self.assertEqual(lb._ORDER["compounded"], lb._ORDER["shipped"])

    def test_stage_at_least(self) -> None:
        self.assertTrue(lb.stage_at_least("in_review", "planned"))
        self.assertFalse(lb.stage_at_least("stub", "planned"))
        self.assertFalse(lb.stage_at_least(None, "stub"))
        self.assertFalse(lb.stage_at_least("abandoned", "stub"))


class GateTest(unittest.TestCase):
    """The idempotent entry-gate table: stage + artifact, never stage alone."""

    def test_brainstorm_proceeds_on_stub(self) -> None:
        g = lb.evaluate_gate("brainstorm", "stub", True, None, None)
        self.assertEqual(g.verdict, "proceed")

    def test_brainstorm_routes_to_plan_when_brainstormed_with_doc(self) -> None:
        g = lb.evaluate_gate("brainstorm", "brainstormed", True, None, "docs/brainstorms/x.md")
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_plan"))

    def test_brainstorm_repairs_when_stage_lies_about_doc(self) -> None:
        g = lb.evaluate_gate("brainstorm", "brainstormed", True, None, None)
        self.assertEqual(g.verdict, "repair_needed")

    def test_brainstorm_on_stage_beyond_brainstormed_never_repairs(self) -> None:
        # An item that legally skipped stub→planned has no brainstorm doc by
        # construction — the gate must not walk the board backwards.
        g = lb.evaluate_gate("brainstorm", "planned", True, None, None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_plan"))
        for stage in ("in_progress", "in_review", "shipped", "deployed",
                      "compounded", "abandoned"):
            with self.subTest(stage=stage):
                g = lb.evaluate_gate("brainstorm", stage, True, None, None)
                self.assertEqual(g.verdict, "already_done")
                self.assertNotEqual(g.verdict, "repair_needed")

    def test_plan_already_done_offers_work(self) -> None:
        g = lb.evaluate_gate("plan", "planned", True, "docs/plans/x.md", None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_work"))

    def test_plan_treats_planned_without_doc_as_ungroomed(self) -> None:
        # A human dragged the card to planned; no join-keyed plan doc exists.
        g = lb.evaluate_gate("plan", "planned", True, None, None)
        self.assertEqual(g.verdict, "repair_needed")

    def test_work_requires_at_least_planned(self) -> None:
        g = lb.evaluate_gate("work", "brainstormed", True, None, None)
        self.assertEqual((g.verdict, g.route), ("route_to_plan", "plan"))

    def test_work_gate_is_stage_plus_artifact(self) -> None:
        # Scenario 5: stage says planned but no plan doc -> route back to plan.
        g = lb.evaluate_gate("work", "planned", True, None, None)
        self.assertEqual(g.verdict, "route_to_plan")
        g = lb.evaluate_gate("work", "planned", True, "docs/plans/x.md", None)
        self.assertEqual(g.verdict, "proceed")

    def test_work_gate_no_doc_reason_names_the_actual_stage(self) -> None:
        # Issue #46: the reason is echoed verbatim by commands on STOP — a
        # hard-coded "planned" misdirects the human when the stage is later.
        g = lb.evaluate_gate("work", "in_progress", True, None, None)
        self.assertEqual(g.verdict, "route_to_plan")
        self.assertIn("in_progress", g.reason)
        self.assertNotIn("planned", g.reason)

    def test_work_terminal_stages_are_already_done(self) -> None:
        for stage in ("shipped", "deployed", "compounded", "abandoned"):
            with self.subTest(stage=stage):
                g = lb.evaluate_gate("work", stage, True, "docs/plans/x.md", None)
                self.assertEqual(g.verdict, "already_done")

    def test_compound_hotfix_path_without_issue(self) -> None:
        g = lb.evaluate_gate("compound", None, False, None, None)
        self.assertEqual(g.verdict, "proceed")
        self.assertIn("skip the Status write", g.reason)

    def test_compound_stamps_only_from_shipped_or_deployed(self) -> None:
        self.assertEqual(lb.evaluate_gate("compound", "shipped", True, None, None).verdict, "proceed")
        self.assertEqual(lb.evaluate_gate("compound", "compounded", True, None, None).verdict, "already_done")
        self.assertEqual(lb.evaluate_gate("compound", "in_review", True, None, None).verdict, "repair_needed")

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
    """The repair set is CLOSED at five; everything else is a never-repair."""

    def test_rule1_merged_close_missed_becomes_shipped(self) -> None:
        s = _issue(state="CLOSED", state_reason="COMPLETED", stage="in_review",
                   closing_prs=[_pr()])
        repairs, flags = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs],
                         [("merged_close_missed", "shipped")])
        self.assertEqual(flags, [])

    def test_rule2_not_planned_close_becomes_abandoned_with_cascade(self) -> None:
        s = _issue(state="CLOSED", state_reason="NOT_PLANNED", stage="shipped",
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
        for stage in ("stub", "planned", "in_progress", "in_review", "shipped", "compounded"):
            with self.subTest(stage=stage):
                repairs, flags = lb.plan_repairs([_issue(stage=stage)], "main")
                self.assertEqual((repairs, flags), ([], []))

    def test_abandoned_never_promoted_to_shipped(self) -> None:
        s = _issue(state="CLOSED", state_reason="COMPLETED", stage="abandoned",
                   closing_prs=[_pr()])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual(repairs, [])


class ReadyWorkTest(unittest.TestCase):
    def _item(self, number, repo="o/r", priority=None, title="t", type_="Issue"):
        return {"content": {"type": type_, "number": number, "repository": repo, "title": title},
                "priority": priority}

    def test_foreign_repo_items_are_dropped_never_written(self) -> None:
        items = [self._item(1, repo="o/r"), self._item(2, repo="other/repo")]
        ready, _ = lb.merge_ready_legs(items, {}, "o/r")
        self.assertEqual([r.number for r in ready], [1])

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


class JoinKeyTest(unittest.TestCase):
    def test_bare_number_is_repo_local(self) -> None:
        self.assertEqual(lb.normalize_join_key("42", "o/r"), "o/r#42")

    def test_qualified_form(self) -> None:
        self.assertEqual(lb.normalize_join_key("a/b#7", "o/r"), "a/b#7")

    def test_placeholder_rejected(self) -> None:
        self.assertIsNone(lb.normalize_join_key("NNN", "o/r"))


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
                          item_id="item5", url="u"):
    """Build an ISSUE_QUERY graphql response with the dict-shaped blockedBy the
    new parser reads (blockedBy(first:1){totalCount})."""
    return {"data": {"repository": {"issue": {
        "number": number, "state": "OPEN", "stateReason": None, "url": url,
        "authorAssociation": "OWNER",
        "blockedBy": {"totalCount": blocked},
        "assignees": {"nodes": [{"login": a} for a in assignees]},
        "closedByPullRequestsReferences": {"nodes": []},
        "subIssues": {"nodes": []},
        "projectItems": {"nodes": [{"id": item_id,
            "project": {"id": "P", "number": 1, "owner": {"login": "acme"}},
            "fieldValueByName": {"name": stage}}]}}}}}


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


class FixtureReplayTest(unittest.TestCase):
    """Recorded gh fixtures are load-bearing: each is replayed through its real
    engine consumer so a shape drift in a re-record breaks a test, not prod."""

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gh"

    def _load(self, name: str):
        return json.loads((self.FIXTURES / name).read_text(encoding="utf-8"))

    def test_project_field_list_resolves_all_nine_stages(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
