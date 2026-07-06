"""Tier-1 hermetic tests for bootstrap_lifecycle_board.py.

Covers the destructive-foot-gun surface with an argv-recording fake gh
(mirrors lifecycle_board_test.py's FakeRunner): golden-fixture assertions on
the exact updateProjectV2Field mutation document + variables for a fresh
default project (3 ids preserved + 6 new) and a canonical re-run (9 ids
preserved — idempotency); the fresh-project guard (unrecognized options ->
BoardError with a diff, NO mutation recorded); env-override refusal;
owner-from-origin (never @me in argv); and config-write content preservation
in a tempdir. No network, no gh.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

# Load lifecycle_board first (bootstrap imports it by module name), then the
# bootstrap module itself — the same importlib + sys.modules registration the
# sibling test uses.
_lb_spec = importlib.util.spec_from_file_location("lifecycle_board", SCRIPTS / "lifecycle_board.py")
assert _lb_spec is not None and _lb_spec.loader is not None
lb = importlib.util.module_from_spec(_lb_spec)
sys.modules["lifecycle_board"] = lb
_lb_spec.loader.exec_module(lb)

_bs_spec = importlib.util.spec_from_file_location(
    "bootstrap_lifecycle_board", SCRIPTS / "bootstrap_lifecycle_board.py")
assert _bs_spec is not None and _bs_spec.loader is not None
bs = importlib.util.module_from_spec(_bs_spec)
sys.modules["bootstrap_lifecycle_board"] = bs
_bs_spec.loader.exec_module(bs)


def _ctx(owner="acme", repo="widget"):
    return lb.RepoContext(root=".", main_root=".", origin_owner=owner,
                          origin_repo=repo, default_branch="main")


def _ok(stdout: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str = "boom") -> "subprocess.CompletedProcess[str]":
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


class FakeRunner:
    """Argv-recording fake gh. Each response is (expected_prefix, proc); an
    unexpected or drifted argv fails the test — mocks cannot drift from the
    contract without a test naming the divergence."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, args, timeout=None):
        self.calls.append(args)
        if not self.responses:
            raise AssertionError(f"unexpected gh call: gh {' '.join(args[:8])}")
        expect_prefix, proc = self.responses.pop(0)
        if args[:len(expect_prefix)] != expect_prefix:
            raise AssertionError(f"argv drift: expected {expect_prefix}, got {args[:len(expect_prefix)]}")
        return proc

    def graphql_calls(self):
        """Every recorded `gh api graphql ...` call as a dict of its -f/-F
        flag values (query, fieldId, options, ...)."""
        out = []
        for args in self.calls:
            if args[:2] != ["api", "graphql"]:
                continue
            flags = {}
            i = 2
            while i < len(args) - 1:
                if args[i] in ("-f", "-F"):
                    key, _, val = args[i + 1].partition("=")
                    flags[key] = val
                    i += 2
                else:
                    i += 1
            out.append(flags)
        return out


# The GitHub-default fresh-project Status field, with stable fake ids.
_DEFAULT_FIELD = bs.StatusField(field_id="FIELD_STATUS", options=[
    {"id": "opt_todo", "name": "Todo"},
    {"id": "opt_inprogress", "name": "In Progress"},
    {"id": "opt_done", "name": "Done"},
])

# A board already carrying the canonical 9 (a prior bootstrap's output).
_CANONICAL_FIELD = bs.StatusField(
    field_id="FIELD_STATUS",
    options=[{"id": f"opt_{s}", "name": s} for s in bs.STAGES])


class OptionMappingTest(unittest.TestCase):
    """Golden assertions on build_option_mapping — the id-preserving core."""

    def test_fresh_default_preserves_three_ids_adds_six(self) -> None:
        options = bs.build_option_mapping(_DEFAULT_FIELD, "default")
        # 9 options, in STAGES order, every one named + colored + described.
        self.assertEqual([o["name"] for o in options], list(bs.STAGES))
        for o in options:
            self.assertIn("color", o)
            self.assertIn("description", o)
        with_id = {o["name"]: o["id"] for o in options if "id" in o}
        self.assertEqual(with_id, {
            "stub": "opt_todo",
            "in_progress": "opt_inprogress",
            "shipped": "opt_done",
        })
        # The other six carry NO id (they are genuinely new options).
        id_less = [o["name"] for o in options if "id" not in o]
        self.assertEqual(sorted(id_less),
                         sorted(set(bs.STAGES) - {"stub", "in_progress", "shipped"}))

    def test_canonical_rerun_preserves_all_nine_ids(self) -> None:
        options = bs.build_option_mapping(_CANONICAL_FIELD, "canonical")
        self.assertEqual([o["name"] for o in options], list(bs.STAGES))
        # Idempotency: EVERY option keeps its id — never a partial/id-less list.
        self.assertTrue(all("id" in o for o in options))
        self.assertEqual({o["name"]: o["id"] for o in options},
                         {s: f"opt_{s}" for s in bs.STAGES})

    def test_colors_are_valid_enum_values(self) -> None:
        valid = {"GRAY", "BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE"}
        for o in bs.build_option_mapping(_CANONICAL_FIELD, "canonical"):
            self.assertIn(o["color"], valid)


class MutationDocumentTest(unittest.TestCase):
    """The exact GraphQL document + variables produced by apply_status_options."""

    def test_fresh_default_mutation_document_and_variables(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok(json.dumps(
                {"data": {"updateProjectV2Field": {"projectV2Field": {
                    "id": "FIELD_STATUS",
                    "options": [{"id": f"o{i}", "name": s} for i, s in enumerate(bs.STAGES)]}}}}))),
        ])
        options = bs.build_option_mapping(_DEFAULT_FIELD, "default")
        bs.apply_status_options(_DEFAULT_FIELD, options, runner)

        graphql = runner.graphql_calls()
        self.assertEqual(len(graphql), 1)
        flags = graphql[0]
        # Exact mutation document — pins the mutation name + input shape.
        self.assertEqual(flags["query"], bs.UPDATE_FIELD_MUTATION)
        self.assertIn("updateProjectV2Field(input: {fieldId: $fieldId, "
                      "singleSelectOptions: $options})", flags["query"])
        self.assertEqual(flags["fieldId"], "FIELD_STATUS")
        sent = json.loads(flags["options"])
        self.assertEqual([o["name"] for o in sent], list(bs.STAGES))
        self.assertEqual({o["name"]: o["id"] for o in sent if "id" in o},
                         {"stub": "opt_todo", "in_progress": "opt_inprogress", "shipped": "opt_done"})
        self.assertEqual(sum("id" in o for o in sent), 3)  # 3 preserved, 6 new

    def test_canonical_rerun_sends_nine_ids(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok(json.dumps(
                {"data": {"updateProjectV2Field": {"projectV2Field": {
                    "id": "FIELD_STATUS", "options": []}}}}))),
        ])
        options = bs.build_option_mapping(_CANONICAL_FIELD, "canonical")
        bs.apply_status_options(_CANONICAL_FIELD, options, runner)

        sent = json.loads(runner.graphql_calls()[0]["options"])
        self.assertEqual(len(sent), 9)
        # Idempotency guard: NOT a partial or id-less list — all nine ids sent.
        self.assertTrue(all("id" in o for o in sent))
        self.assertEqual({o["name"]: o["id"] for o in sent},
                         {s: f"opt_{s}" for s in bs.STAGES})

    def test_options_serialized_as_single_json_variable(self) -> None:
        # gh -F cannot express a nested list-of-objects; the options MUST ride
        # as one JSON-encoded -f variable, not many scalar flags.
        runner = FakeRunner([
            (["api", "graphql"], _ok(json.dumps(
                {"data": {"updateProjectV2Field": {"projectV2Field": {"options": []}}}}))),
        ])
        options = bs.build_option_mapping(_DEFAULT_FIELD, "default")
        bs.apply_status_options(_DEFAULT_FIELD, options, runner)
        call = runner.calls[0]
        # exactly one flag literally named options=... and it parses as JSON.
        option_flags = [a for a in call if a.startswith("options=")]
        self.assertEqual(len(option_flags), 1)
        json.loads(option_flags[0].split("=", 1)[1])  # must not raise


class FreshProjectGuardTest(unittest.TestCase):
    def test_default_option_set_is_accepted(self) -> None:
        self.assertEqual(bs.assert_fresh_or_canonical(_DEFAULT_FIELD), "default")

    def test_canonical_option_set_is_accepted(self) -> None:
        self.assertEqual(bs.assert_fresh_or_canonical(_CANONICAL_FIELD), "canonical")

    def test_unrecognized_option_set_hard_stops_with_diff_and_no_mutation(self) -> None:
        customized = bs.StatusField(field_id="F", options=[
            {"id": "a", "name": "Backlog"},
            {"id": "b", "name": "Doing"},
            {"id": "c", "name": "Shipped"},
        ])
        with self.assertRaises(bs.BoardError) as caught:
            bs.assert_fresh_or_canonical(customized)
        self.assertEqual(caught.exception.code, "unrecognized_project")
        # A printed diff names the current + expected option sets.
        message = str(caught.exception)
        self.assertIn("Backlog", message)
        self.assertIn("current options", message)
        self.assertIn("expected", message)

    def test_partial_canonical_is_rejected(self) -> None:
        # A board mid-migration (some canonical, some default) is NOT safe to
        # replace-all — only exact default or exact canonical pass.
        mixed = bs.StatusField(field_id="F", options=[
            {"id": "a", "name": "stub"},
            {"id": "b", "name": "In Progress"},
            {"id": "c", "name": "Done"},
        ])
        with self.assertRaises(bs.BoardError) as caught:
            bs.assert_fresh_or_canonical(mixed)
        self.assertEqual(caught.exception.code, "unrecognized_project")

    def test_guard_runs_before_any_mutation_in_full_flow(self) -> None:
        # End-to-end: a customized board must produce NO gh api graphql call.
        customized_json = json.dumps({"fields": [
            {"name": "Status", "id": "F", "options": [
                {"id": "a", "name": "Backlog"}, {"id": "b", "name": "Doing"}]},
        ]})
        runner = FakeRunner([
            (["--version"], _ok("gh version 2.96.0 (2026-07-02)")),
            (["auth", "status"], _ok("Logged in to github.com")),
            # No committed config on disk in main_root="." → create path.
            (["project", "create", "--owner", "acme"],
             _ok(json.dumps({"number": 7, "id": "PROJ"}))),
            (["project", "field-list", "7", "--owner", "acme"], _ok(customized_json)),
        ])
        with self.assertRaises(bs.BoardError) as caught:
            bs.bootstrap(_ctx(), runner, probe=False, environ={})
        self.assertEqual(caught.exception.code, "unrecognized_project")
        self.assertEqual(runner.graphql_calls(), [])  # nothing mutated


class PreconditionTest(unittest.TestCase):
    def test_gh_repo_override_refused(self) -> None:
        with self.assertRaises(bs.BoardError) as caught:
            bs.check_env_overrides({"GH_REPO": "attacker/evil"})
        self.assertEqual(caught.exception.code, "env_override_present")
        self.assertIn("GH_REPO", str(caught.exception))

    def test_gh_host_override_refused(self) -> None:
        with self.assertRaises(bs.BoardError) as caught:
            bs.check_env_overrides({"GH_HOST": "ghe.internal"})
        self.assertEqual(caught.exception.code, "env_override_present")

    def test_clean_env_passes(self) -> None:
        bs.check_env_overrides({"PATH": "/usr/bin"})  # must not raise

    def test_gh_too_old_refused(self) -> None:
        runner = FakeRunner([(["--version"], _ok("gh version 2.79.0 (2025-01-01)"))])
        with self.assertRaises(bs.BoardError) as caught:
            bs.check_gh_version(runner)
        self.assertEqual(caught.exception.code, "gh_too_old")

    def test_gh_version_ok(self) -> None:
        runner = FakeRunner([(["--version"], _ok("gh version 2.94.0 (2025-06-01)"))])
        self.assertEqual(bs.check_gh_version(runner), (2, 94, 0))

    def test_unauthenticated_refused_with_project_scope_hint(self) -> None:
        runner = FakeRunner([(["auth", "status"], _fail("not logged in"))])
        with self.assertRaises(bs.BoardError) as caught:
            bs.check_gh_authenticated(runner)
        self.assertEqual(caught.exception.code, "gh_unauthenticated")
        self.assertIn("project", caught.exception.fix)


class OwnerFromOriginTest(unittest.TestCase):
    def test_project_create_uses_origin_owner_never_at_me(self) -> None:
        runner = FakeRunner([
            (["project", "create", "--owner", "acme", "--title", "widget lifecycle"],
             _ok(json.dumps({"number": 12, "id": "PROJ12"}))),
        ])
        project = bs.resolve_or_create_project(_ctx(owner="acme", repo="widget"), runner)
        self.assertEqual((project.number, project.created), (12, True))
        # The literal "@me" must never appear anywhere in the argv.
        for call in runner.calls:
            self.assertNotIn("@me", call)
        # And the owner IS the origin owner.
        self.assertIn("acme", runner.calls[0])

    def test_existing_config_is_reused_not_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / bs.COMMITTED_CONFIG).write_text(
                "---\ngithub_project_owner: acme\ngithub_project_number: 5\n---\n",
                encoding="utf-8")
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="acme",
                                 origin_repo="widget", default_branch="main")
            runner = FakeRunner([
                (["project", "view", "5", "--owner", "acme"],
                 _ok(json.dumps({"number": 5, "id": "PROJ5"}))),
            ])
            project = bs.resolve_or_create_project(ctx, runner)
            self.assertEqual((project.number, project.created), (5, False))
            # No `project create` was attempted.
            self.assertFalse(any(c[:2] == ["project", "create"] for c in runner.calls))


class WorkflowConfigTest(unittest.TestCase):
    def _workflows_payload(self, *, reopened_enabled, closed_enabled, holder="user"):
        nodes = [
            {"id": "wf_reopened", "name": "Item reopened", "enabled": reopened_enabled},
            {"id": "wf_closed", "name": "Item closed", "enabled": closed_enabled},
            {"id": "wf_added", "name": "Item added", "enabled": True},
        ]
        return json.dumps({"data": {holder: {"projectV2": {"workflows": {"nodes": nodes}}}}})

    def test_disables_reopened_and_confirms_closed(self) -> None:
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _ok(self._workflows_payload(
                reopened_enabled=True, closed_enabled=True))),
            (["api", "graphql"], _ok(json.dumps(
                {"data": {"deleteProjectV2Workflow": {"clientMutationId": None}}}))),
        ])
        result = bs.configure_workflows(project, _ctx(), runner)
        self.assertTrue(result["reopened_disabled"])
        self.assertTrue(result["closed_enabled"])
        self.assertEqual(result["warnings"], [])
        # The delete mutation targeted the reopened workflow's id.
        delete_call = runner.graphql_calls()[1]
        self.assertEqual(delete_call["query"], bs.DELETE_WORKFLOW_MUTATION)
        self.assertEqual(delete_call["workflowId"], "wf_reopened")

    def test_warns_when_closed_workflow_disabled(self) -> None:
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _ok(self._workflows_payload(
                reopened_enabled=False, closed_enabled=False))),
        ])
        result = bs.configure_workflows(project, _ctx(), runner)
        self.assertFalse(result["reopened_disabled"])  # already off → no delete call
        self.assertFalse(result["closed_enabled"])
        self.assertTrue(any("Item closed" in w for w in result["warnings"]))
        self.assertEqual(len(runner.graphql_calls()), 1)  # only the query, no mutation

    def test_org_owned_project_workflows_resolve(self) -> None:
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _ok(self._workflows_payload(
                reopened_enabled=False, closed_enabled=True, holder="organization"))),
        ])
        result = bs.configure_workflows(project, _ctx(), runner)
        self.assertTrue(result["closed_enabled"])


class ConfigWriteTest(unittest.TestCase):
    def test_creates_file_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = bs.write_committed_config(tmp, "acme", 9)
            text = Path(path).read_text(encoding="utf-8")
            meta = lb.parse_frontmatter(text)
            self.assertEqual(meta["github_project_owner"], "acme")
            self.assertEqual(meta["github_project_number"], "9")

    def test_updates_only_two_keys_preserving_other_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = (
                "---\n"
                "title: My Project Config\n"
                "github_project_owner: old-owner\n"
                "github_project_number: 1\n"
                "some_other_key: keep-me\n"
                "---\n"
                "\n"
                "# Human notes\n"
                "\n"
                "This body must survive byte-for-byte.\n"
            )
            path = Path(tmp) / bs.COMMITTED_CONFIG
            path.write_text(original, encoding="utf-8")

            bs.write_committed_config(tmp, "acme", 42)
            updated = path.read_text(encoding="utf-8")

            meta = lb.parse_frontmatter(updated)
            self.assertEqual(meta["github_project_owner"], "acme")
            self.assertEqual(meta["github_project_number"], "42")
            # Unrelated frontmatter keys + the entire body are preserved.
            self.assertEqual(meta["title"], "My Project Config")
            self.assertEqual(meta["some_other_key"], "keep-me")
            self.assertIn("# Human notes", updated)
            self.assertIn("This body must survive byte-for-byte.", updated)

    def test_appends_missing_keys_without_touching_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = (
                "---\n"
                "title: Config\n"
                "---\n"
                "body text\n"
            )
            path = Path(tmp) / bs.COMMITTED_CONFIG
            path.write_text(original, encoding="utf-8")
            bs.write_committed_config(tmp, "acme", 7)
            updated = path.read_text(encoding="utf-8")
            meta = lb.parse_frontmatter(updated)
            self.assertEqual(meta["github_project_owner"], "acme")
            self.assertEqual(meta["github_project_number"], "7")
            self.assertEqual(meta["title"], "Config")
            self.assertIn("body text", updated)

    def test_updated_config_survives_read_board_config(self) -> None:
        # The write must round-trip through the real reader (owner==origin).
        with tempfile.TemporaryDirectory() as tmp:
            bs.write_committed_config(tmp, "acme", 15)
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="acme",
                                 origin_repo="widget", default_branch="main")
            board = lb.read_board_config(ctx)
            self.assertEqual((board.owner, board.number), ("acme", 15))


class ProbeTest(unittest.TestCase):
    """run_probe calls lifecycle_board.verb_set_status, which reads the
    committed config from disk — so these tests place one in a tempdir
    main_root (the same on-disk state bootstrap() has already written by the
    time the probe runs)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        (Path(root) / bs.COMMITTED_CONFIG).write_text(
            "---\ngithub_project_owner: acme\ngithub_project_number: 3\n---\n",
            encoding="utf-8")
        self.ctx = lb.RepoContext(root=root, main_root=root, origin_owner="acme",
                                  origin_repo="widget", default_branch="main")
        # Isolate the session cache: lifecycle_board's schema cache lives in the
        # git-common-dir, which the FakeRunner cannot see — stub it to empty so
        # each verb_set_status resolves the schema via a recorded field-list.
        _orig_load, _orig_save = lb.load_cache, lb.save_cache
        lb.load_cache = lambda _ctx: {}
        lb.save_cache = lambda _ctx, _cache: None
        self.addCleanup(lambda: (setattr(lb, "load_cache", _orig_load),
                                 setattr(lb, "save_cache", _orig_save)))

    def test_probe_passes_and_deletes_scratch_issue(self) -> None:
        ctx = self.ctx
        board_stub = {"fields": [{"name": "Status", "id": "F", "projectId": "P",
                                  "options": [{"id": f"o_{s}", "name": s} for s in bs.STAGES]}]}
        issue_shipped = {"data": {"repository": {"issue": {
            "number": 99, "state": "CLOSED", "stateReason": "COMPLETED", "url": "u",
            "authorAssociation": "OWNER", "assignees": {"nodes": []},
            "closedByPullRequestsReferences": {"nodes": []},
            "subIssues": {"nodes": []},
            "projectItems": {"nodes": [{"id": "item99",
                "project": {"id": "P", "number": 3, "owner": {"login": "acme"}},
                "fieldValueByName": {"name": "shipped"}}]}}}}}
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["issue", "create", "--repo", "acme/widget"],
             _ok("https://github.com/acme/widget/issues/99\n")),
            # verb_set_status: resolve_schema (field-list) then fetch_issue_state
            # (graphql + issue view blockedBy) then item-edit.
            (["project", "field-list", "3", "--owner", "acme"], _ok(json.dumps(board_stub))),
            (["api", "graphql"], _ok(json.dumps({"data": {"repository": {"issue": {
                "number": 99, "state": "OPEN", "stateReason": None, "url": "u",
                "authorAssociation": "OWNER", "assignees": {"nodes": []},
                "closedByPullRequestsReferences": {"nodes": []}, "subIssues": {"nodes": []},
                "projectItems": {"nodes": [{"id": "item99",
                    "project": {"id": "P", "number": 3, "owner": {"login": "acme"}},
                    "fieldValueByName": None}]}}}}}))),
            (["issue", "view", "99", "--repo", "acme/widget"], _ok(json.dumps({"blockedBy": []}))),
            (["project", "item-edit", "--id", "item99"], _ok("{}")),
            (["issue", "close", "99", "--repo", "acme/widget"], _ok("")),
            # poll #1 → already shipped.
            (["api", "graphql"], _ok(json.dumps(issue_shipped))),
            (["issue", "view", "99", "--repo", "acme/widget"], _ok(json.dumps({"blockedBy": []}))),
            (["issue", "delete", "99", "--repo", "acme/widget", "--yes"], _ok("")),
        ])
        result = bs.run_probe(project, ctx, runner, sleep=lambda _s: None)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["issue"], 99)
        # Scratch issue was deleted (cleanup in the finally block).
        self.assertTrue(any(c[:2] == ["issue", "delete"] for c in runner.calls))

    def test_probe_fails_and_still_deletes_when_issue_create_ok_but_never_ships(self) -> None:
        ctx = self.ctx
        board_stub = {"fields": [{"name": "Status", "id": "F", "projectId": "P",
                                  "options": [{"id": f"o_{s}", "name": s} for s in bs.STAGES]}]}
        open_stub = {"data": {"repository": {"issue": {
            "number": 99, "state": "OPEN", "stateReason": None, "url": "u",
            "authorAssociation": "OWNER", "assignees": {"nodes": []},
            "closedByPullRequestsReferences": {"nodes": []}, "subIssues": {"nodes": []},
            "projectItems": {"nodes": [{"id": "item99",
                "project": {"id": "P", "number": 3, "owner": {"login": "acme"}},
                "fieldValueByName": {"name": "stub"}}]}}}}}
        project = bs.Project(number=3, id="P", created=True)
        # One poll cycle: monotonic advances past the deadline after the first check.
        clock = iter([0.0, 0.0, 1000.0])
        runner = FakeRunner([
            (["issue", "create", "--repo", "acme/widget"],
             _ok("https://github.com/acme/widget/issues/99\n")),
            (["project", "field-list", "3", "--owner", "acme"], _ok(json.dumps(board_stub))),
            (["api", "graphql"], _ok(json.dumps(open_stub))),
            (["issue", "view", "99", "--repo", "acme/widget"], _ok(json.dumps({"blockedBy": []}))),
            (["project", "item-edit", "--id", "item99"], _ok("{}")),
            (["issue", "close", "99", "--repo", "acme/widget"], _ok("")),
            (["api", "graphql"], _ok(json.dumps(open_stub))),
            (["issue", "view", "99", "--repo", "acme/widget"], _ok(json.dumps({"blockedBy": []}))),
            (["issue", "delete", "99", "--repo", "acme/widget", "--yes"], _ok("")),
        ])
        result = bs.run_probe(project, ctx, runner, sleep=lambda _s: None, now=lambda: next(clock))
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["observed_stage"], "stub")
        self.assertTrue(any(c[:2] == ["issue", "delete"] for c in runner.calls))


if __name__ == "__main__":
    unittest.main()
