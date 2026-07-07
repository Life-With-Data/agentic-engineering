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

import atexit
import importlib.util
import json
import shutil
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


_HERMETIC_DIR = tempfile.mkdtemp(prefix="bootstrap-test-ctx-")
atexit.register(lambda: shutil.rmtree(_HERMETIC_DIR, ignore_errors=True))


def _ctx(owner="acme", repo="widget"):
    # main_root MUST be an empty tempdir, never "." — the real repo may carry a
    # committed agentic-engineering.md (it does, post-bootstrap), and a "."
    # context would leak it into every test via read_board_config.
    return lb.RepoContext(root=_HERMETIC_DIR, main_root=_HERMETIC_DIR,
                          origin_owner=owner, origin_repo=repo, default_branch="main")


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
        # The options are INLINED into the document as a GraphQL literal — gh
        # api graphql has no list-of-objects variable transport (verified
        # live: an options=<json> -f flag arrives as a string and is rejected).
        query = flags["query"]
        self.assertIn("updateProjectV2Field(input: {fieldId: $fieldId, "
                      "singleSelectOptions: [", query)
        self.assertNotIn("__OPTIONS__", query)  # template placeholder replaced
        self.assertEqual(flags["fieldId"], "FIELD_STATUS")
        # 3 preserved ids (Todo→stub, In Progress→in_progress, Done→shipped), 6 id-less.
        self.assertEqual(query.count("id: "), 3)
        for old_id, new_name in (("opt_todo", "stub"), ("opt_inprogress", "in_progress"),
                                 ("opt_done", "shipped")):
            self.assertIn(f'id: "{old_id}", name: "{new_name}"', query)
        for stage in bs.STAGES:
            self.assertIn(f'name: "{stage}"', query)
        # Colors are enum literals — unquoted.
        self.assertIn("color: GRAY", query)
        self.assertNotIn('color: "', query)

    def test_canonical_rerun_sends_nine_ids(self) -> None:
        runner = FakeRunner([
            (["api", "graphql"], _ok(json.dumps(
                {"data": {"updateProjectV2Field": {"projectV2Field": {
                    "id": "FIELD_STATUS", "options": []}}}}))),
        ])
        options = bs.build_option_mapping(_CANONICAL_FIELD, "canonical")
        bs.apply_status_options(_CANONICAL_FIELD, options, runner)

        query = runner.graphql_calls()[0]["query"]
        # Idempotency guard: NOT a partial or id-less list — all nine ids sent.
        self.assertEqual(query.count("id: "), 9)
        for s in bs.STAGES:
            self.assertIn(f'id: "opt_{s}", name: "{s}"', query)

    def test_options_never_ride_as_a_variable_flag(self) -> None:
        # gh api graphql has NO transport for list-of-objects variables — an
        # `options=<json>` -f flag arrives as a string and the API rejects it
        # (verified live). The options must be inlined into the document; the
        # only variable flag besides the query is fieldId.
        runner = FakeRunner([
            (["api", "graphql"], _ok(json.dumps(
                {"data": {"updateProjectV2Field": {"projectV2Field": {"options": []}}}}))),
        ])
        options = bs.build_option_mapping(_DEFAULT_FIELD, "default")
        bs.apply_status_options(_DEFAULT_FIELD, options, runner)
        call = runner.calls[0]
        self.assertEqual([a for a in call if a.startswith("options=")], [])
        self.assertEqual(len([a for a in call if a.startswith("fieldId=")]), 1)

    def test_graphql_literal_escapes_strings_and_keeps_enums_bare(self) -> None:
        literal = bs._options_graphql_literal([
            {"id": "x1", "name": 'quo"te', "color": "RED", "description": "d\\esc"},
            {"name": "plain", "color": "BLUE", "description": ""},
        ])
        self.assertEqual(
            literal,
            '[{id: "x1", name: "quo\\"te", color: RED, description: "d\\\\esc"}, '
            '{name: "plain", color: BLUE, description: ""}]',
        )


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
    def _workflows_payload(self, *, reopened_enabled, closed_enabled):
        # The query resolves the owner via repositoryOwner (works for BOTH
        # User and Organization — querying organization(login:) for a user is
        # a hard GraphQL error, verified live), so there is one holder shape.
        nodes = [
            {"id": "wf_reopened", "name": "Item reopened", "enabled": reopened_enabled},
            {"id": "wf_closed", "name": "Item closed", "enabled": closed_enabled},
            {"id": "wf_added", "name": "Item added", "enabled": True},
        ]
        return json.dumps({"data": {"repositoryOwner": {"projectV2": {"workflows": {"nodes": nodes}}}}})

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

    def test_workflows_query_uses_repository_owner(self) -> None:
        # Pin the owner-type-agnostic query shape: one repositoryOwner lookup
        # with inline fragments, never separate user/organization queries.
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _ok(self._workflows_payload(
                reopened_enabled=False, closed_enabled=True))),
        ])
        result = bs.configure_workflows(project, _ctx(), runner)
        self.assertTrue(result["closed_enabled"])
        query = runner.graphql_calls()[0]["query"]
        self.assertIn("repositoryOwner(login: $owner)", query)
        self.assertIn("... on User", query)
        self.assertIn("... on Organization", query)
        self.assertNotIn("organization(login:", query)


class LinkRepoTest(unittest.TestCase):
    """link_repo is idempotent (skips the mutation when already linked) and
    non-fatal (a link failure degrades to a warning, never a raise)."""

    @staticmethod
    def _repos_payload(slugs):
        nodes = [{"nameWithOwner": s} for s in slugs]
        return json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "repositories": {"nodes": nodes}}}}})

    def test_links_when_not_linked(self) -> None:
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _ok(self._repos_payload([]))),
            (["project", "link", "3", "--owner", "acme", "--repo", "acme/widget"], _ok("")),
        ])
        result = bs.link_repo(project, _ctx(), runner)
        self.assertTrue(result["linked"])
        self.assertFalse(result["already_linked"])
        self.assertIsNone(result["warning"])

    def test_skips_mutation_when_already_linked(self) -> None:
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _ok(self._repos_payload(["acme/widget"]))),
        ])
        result = bs.link_repo(project, _ctx(), runner)
        self.assertFalse(result["linked"])
        self.assertTrue(result["already_linked"])
        self.assertIsNone(result["warning"])
        self.assertFalse(any(c[:2] == ["project", "link"] for c in runner.calls))

    def test_attempts_link_when_link_state_unknown(self) -> None:
        # A failed/unparseable links query returns None → still attempt the link
        # (idempotent server-side) rather than silently skip.
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _fail("boom")),
            (["project", "link", "3", "--owner", "acme", "--repo", "acme/widget"], _ok("")),
        ])
        result = bs.link_repo(project, _ctx(), runner)
        self.assertTrue(result["linked"])

    def test_nonfatal_warning_on_link_failure(self) -> None:
        project = bs.Project(number=3, id="P", created=True)
        runner = FakeRunner([
            (["api", "graphql"], _ok(self._repos_payload([]))),
            (["project", "link", "3", "--owner", "acme", "--repo", "acme/widget"],
             _fail("insufficient permission")),
        ])
        result = bs.link_repo(project, _ctx(), runner)
        self.assertFalse(result["linked"])
        self.assertIsNotNone(result["warning"])
        self.assertIn("acme/widget", result["warning"])


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

    def test_empty_frontmatter_gets_keys_without_second_block(self) -> None:
        # `---\n---\n` (empty frontmatter) must have the keys inserted between
        # the fences, not a second --- block prepended.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / bs.COMMITTED_CONFIG
            path.write_text("---\n---\nbody\n", encoding="utf-8")
            bs.write_committed_config(tmp, "acme", 8)
            updated = path.read_text(encoding="utf-8")
            # Exactly two fence lines (one open, one close) — no doubled block.
            self.assertEqual(updated.count("---\n"), 2, updated)
            meta = lb.parse_frontmatter(updated)
            self.assertEqual(meta["github_project_owner"], "acme")
            self.assertEqual(meta["github_project_number"], "8")
            self.assertIn("body", updated)

    def test_updated_config_survives_read_board_config(self) -> None:
        # The write must round-trip through the real reader (owner==origin).
        with tempfile.TemporaryDirectory() as tmp:
            bs.write_committed_config(tmp, "acme", 15)
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="acme",
                                 origin_repo="widget", default_branch="main")
            board = lb.read_board_config(ctx)
            self.assertEqual((board.owner, board.number), ("acme", 15))

    def test_records_forward_binding_in_same_write_as_identity(self) -> None:
        # Issue #64: identity + forward binding land in ONE write (atomicity).
        with tempfile.TemporaryDirectory() as tmp:
            bs.write_committed_config(tmp, "acme", 5, "auto-add")
            ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="acme",
                                 origin_repo="widget", default_branch="main")
            board = lb.read_board_config(ctx)
            binding = lb.read_binding_config(ctx)
            self.assertEqual((board.owner, board.number), ("acme", 5))
            self.assertEqual(binding.forward_binding, "auto-add")

    def test_omits_forward_binding_key_when_not_supplied(self) -> None:
        # The 3-arg form (identity only) must not write a binding key.
        with tempfile.TemporaryDirectory() as tmp:
            path = bs.write_committed_config(tmp, "acme", 5)
            meta = lb.parse_frontmatter(Path(path).read_text(encoding="utf-8"))
            self.assertNotIn(lb.CONFIG_KEY_FORWARD_BINDING, meta)


class ForwardBindingBootstrapTest(unittest.TestCase):
    """Issue #64: bootstrap records the forward binding, preserves a prior
    choice on re-run when --forward-binding is omitted, and defaults to
    workflow-only on a first run. Full happy-path flow over a canonical board."""

    def _canonical_fields(self):
        return json.dumps({"fields": [
            {"name": "Status", "id": "F", "projectId": "P",
             "options": [{"id": f"o_{s}", "name": s} for s in bs.STAGES]},
            {"name": "Priority", "id": "PRI",
             "options": [{"id": f"p_{p}", "name": p} for p in ("p1", "p2", "p3")]},
        ]})

    def _workflows(self):
        nodes = [{"id": "wf_r", "name": "Item reopened", "enabled": False},
                 {"id": "wf_c", "name": "Item closed", "enabled": True}]
        return json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "workflows": {"nodes": nodes}}}}})

    def _linked(self, slugs):
        nodes = [{"nameWithOwner": s} for s in slugs]
        return json.dumps({"data": {"repositoryOwner": {"projectV2": {
            "repositories": {"nodes": nodes}}}}})

    def _run(self, tmp, existing_config, forward_binding):
        (Path(tmp) / bs.COMMITTED_CONFIG).write_text(existing_config, encoding="utf-8")
        ctx = lb.RepoContext(root=tmp, main_root=tmp, origin_owner="acme",
                             origin_repo="widget", default_branch="main")
        runner = FakeRunner([
            (["--version"], _ok("gh version 2.96.0 (2026-07-02)")),
            (["auth", "status"], _ok("Logged in to github.com")),
            (["project", "view", "5", "--owner", "acme"], _ok(json.dumps({"number": 5, "id": "P"}))),
            (["project", "field-list", "5", "--owner", "acme"], _ok(self._canonical_fields())),
            (["api", "graphql"], _ok(json.dumps({"data": {"updateProjectV2Field": {
                "projectV2Field": {"id": "F", "options": []}}}}))),
            (["project", "field-list", "5", "--owner", "acme"], _ok(self._canonical_fields())),
            (["api", "graphql"], _ok(self._workflows())),
            (["api", "graphql"], _ok(self._linked(["acme/widget"]))),
            # Consumed only when the resolved binding is auto-add (scaffold step);
            # harmless leftovers otherwise.
            (["api", "users/acme", "--jq", ".type"], _ok("User")),
            (["api", "repos/actions/add-to-project/commits/v2", "--jq", ".sha"],
             _ok("5afcf98fcd03f1c2f92c3c83f58ae24323cc57fd")),
        ])
        summary = bs.bootstrap(ctx, runner, probe=False, forward_binding=forward_binding, environ={})
        return ctx, summary

    _CFG_AUTO = ("---\ngithub_project_owner: acme\ngithub_project_number: 5\n"
                 "github_project_forward_binding: auto-add\n---\n")
    _CFG_BARE = "---\ngithub_project_owner: acme\ngithub_project_number: 5\n---\n"

    def test_preserves_recorded_auto_add_on_rerun_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx, summary = self._run(tmp, self._CFG_AUTO, forward_binding=None)
            self.assertEqual(summary["forward_binding"], "auto-add")
            self.assertEqual(lb.read_binding_config(ctx).forward_binding, "auto-add")

    def test_explicit_flag_overrides_recorded_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _summary = self._run(tmp, self._CFG_AUTO, forward_binding="none")
            self.assertEqual(lb.read_binding_config(ctx).forward_binding, "none")

    def test_first_run_defaults_to_workflow_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _summary = self._run(tmp, self._CFG_BARE, forward_binding=None)
            self.assertEqual(lb.read_binding_config(ctx).forward_binding, "workflow-only")

    def test_scaffolds_workflow_only_on_auto_add(self) -> None:
        # auto-add → workflow file written + summary carries the scaffold record.
        with tempfile.TemporaryDirectory() as tmp:
            ctx, summary = self._run(tmp, self._CFG_BARE, forward_binding="auto-add")
            self.assertTrue(summary["auto_add_scaffold"]["scaffolded"])
            self.assertEqual(lb.find_auto_add_workflow(ctx), bs.WORKFLOW_FILENAME)
        # workflow-only → nothing scaffolded.
        with tempfile.TemporaryDirectory() as tmp:
            ctx, summary = self._run(tmp, self._CFG_BARE, forward_binding="workflow-only")
            self.assertIsNone(summary["auto_add_scaffold"])
            self.assertIsNone(lb.find_auto_add_workflow(ctx))

    def test_rerun_preserves_a_malformed_recorded_binding_not_clobber(self) -> None:
        # A typo'd (invalid enum) recorded binding must be PRESERVED on re-run,
        # not silently reset to the default — the raw value rides through so the
        # doctor can WARN on it rather than the operator's decision vanishing.
        cfg = ("---\ngithub_project_owner: acme\ngithub_project_number: 5\n"
               "github_project_forward_binding: auto_add\n---\n")  # underscore typo
        with tempfile.TemporaryDirectory() as tmp:
            ctx, summary = self._run(tmp, cfg, forward_binding=None)
            self.assertEqual(summary["forward_binding"], "auto_add")  # preserved verbatim
            self.assertEqual(lb.read_binding_config(ctx).forward_raw, "auto_add")


class ScaffoldAutoAddTest(unittest.TestCase):
    """Issue #63: scaffold .github/workflows/add-to-project.yml (+ dependabot)
    when forward_binding == auto-add. Idempotent + non-fatal, mirroring link_repo."""

    def _ctx(self, owner="acme"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return lb.RepoContext(root=tmp.name, main_root=tmp.name, origin_owner=owner,
                              origin_repo="widget", default_branch="main"), Path(tmp.name)

    _SHA = "5afcf98fcd03f1c2f92c3c83f58ae24323cc57fd"

    def _scaffold_runner(self, owner_type="User"):
        return FakeRunner([
            (["api", "users/acme", "--jq", ".type"], _ok(owner_type)),
            (["api", "repos/actions/add-to-project/commits/v2", "--jq", ".sha"], _ok(self._SHA)),
        ])

    def test_render_is_hardened(self) -> None:
        y = bs.render_add_to_project_workflow(
            "https://github.com/users/acme/projects/5", self._SHA, "v2.0.0")
        self.assertEqual(y.count("permissions: {}"), 2)          # top + job level
        self.assertIn(f"actions/add-to-project@{self._SHA}", y)  # SHA-pinned
        self.assertIn("${{ secrets.ADD_TO_PROJECT_PAT }}", y)
        self.assertIn("project-url: https://github.com/users/acme/projects/5", y)
        # No run: step (the only "run:" is inside the security comment).
        self.assertNotIn("\n      - run:", y)
        self.assertNotIn("\n        run:", y)

    def test_scaffolds_user_url_when_absent(self) -> None:
        ctx, root = self._ctx()
        project = bs.Project(number=5, id="P", created=True)
        result = bs.scaffold_add_to_project_workflow(project, ctx, self._scaffold_runner("User"))
        self.assertTrue(result["scaffolded"])
        text = (root / bs.WORKFLOW_FILENAME).read_text(encoding="utf-8")
        self.assertIn("https://github.com/users/acme/projects/5", text)
        # Cross-consistency: the doctor's detector must find what bootstrap wrote.
        self.assertEqual(lb.find_auto_add_workflow(ctx), bs.WORKFLOW_FILENAME)

    def test_scaffolds_org_url(self) -> None:
        ctx, root = self._ctx()
        project = bs.Project(number=5, id="P", created=True)
        bs.scaffold_add_to_project_workflow(project, ctx, self._scaffold_runner("Organization"))
        text = (root / bs.WORKFLOW_FILENAME).read_text(encoding="utf-8")
        self.assertIn("https://github.com/orgs/acme/projects/5", text)

    def test_idempotent_skips_existing_file(self) -> None:
        ctx, root = self._ctx()
        wf = root / bs.WORKFLOW_FILENAME
        wf.parent.mkdir(parents=True)
        wf.write_text("# user's own workflow\n", encoding="utf-8")
        project = bs.Project(number=5, id="P", created=True)
        # No gh calls expected — an empty runner raises if any are made.
        result = bs.scaffold_add_to_project_workflow(project, ctx, FakeRunner([]))
        self.assertTrue(result["already_exists"])
        self.assertFalse(result["scaffolded"])
        self.assertEqual(wf.read_text(encoding="utf-8"), "# user's own workflow\n")  # untouched

    def test_action_ref_falls_back_when_resolve_fails(self) -> None:
        runner = FakeRunner([
            (["api", "repos/actions/add-to-project/commits/v2", "--jq", ".sha"], _fail("offline")),
        ])
        sha, ref = bs._resolve_action_ref(runner)
        self.assertEqual(sha, bs.ADD_TO_PROJECT_PINNED_SHA)
        self.assertEqual(ref, bs.ADD_TO_PROJECT_PINNED_REF)

    def test_action_ref_rejects_non_sha_output(self) -> None:
        # A garbled response must not become the pin — fall back to the constant.
        runner = FakeRunner([
            (["api", "repos/actions/add-to-project/commits/v2", "--jq", ".sha"], _ok("not-a-sha")),
        ])
        sha, _ref = bs._resolve_action_ref(runner)
        self.assertEqual(sha, bs.ADD_TO_PROJECT_PINNED_SHA)

    def test_dependabot_created_when_absent(self) -> None:
        ctx, root = self._ctx()
        result = bs._ensure_dependabot(ctx)
        self.assertTrue(result["created"])
        self.assertIn("github-actions", (root / bs.DEPENDABOT_FILENAME).read_text(encoding="utf-8"))

    def test_dependabot_warns_when_present_without_actions(self) -> None:
        ctx, root = self._ctx()
        dep = root / bs.DEPENDABOT_FILENAME
        dep.parent.mkdir(parents=True)
        dep.write_text("version: 2\nupdates:\n  - package-ecosystem: npm\n", encoding="utf-8")
        result = bs._ensure_dependabot(ctx)
        self.assertFalse(result["created"])
        self.assertIsNotNone(result["warning"])
        self.assertNotIn("github-actions", dep.read_text(encoding="utf-8"))  # untouched

    def test_dependabot_noop_when_already_covers_actions(self) -> None:
        ctx, root = self._ctx()
        dep = root / bs.DEPENDABOT_FILENAME
        dep.parent.mkdir(parents=True)
        dep.write_text("version: 2\nupdates:\n  - package-ecosystem: github-actions\n",
                       encoding="utf-8")
        result = bs._ensure_dependabot(ctx)
        self.assertFalse(result["created"])
        self.assertTrue(result["already_covers_actions"])
        self.assertIsNone(result["warning"])

    def test_dependabot_comment_mention_is_not_treated_as_covered(self) -> None:
        # A bare "github-actions" in a comment (real ecosystem = npm) must NOT
        # read as covered — that would silently skip the wiring.
        ctx, root = self._ctx()
        dep = root / bs.DEPENDABOT_FILENAME
        dep.parent.mkdir(parents=True)
        dep.write_text("version: 2\nupdates:\n  # TODO maybe github-actions later\n"
                       "  - package-ecosystem: npm\n    directory: /\n", encoding="utf-8")
        result = bs._ensure_dependabot(ctx)
        self.assertFalse(result["already_covers_actions"])
        self.assertIsNotNone(result["warning"])

    def test_owner_type_unresolved_surfaces_a_warning(self) -> None:
        ctx, _root = self._ctx()
        seg, warning = bs._resolve_owner_url_segment(ctx, FakeRunner([
            (["api", "users/acme", "--jq", ".type"], _fail("HTTP 503")),
        ]))
        self.assertEqual(seg, "users")           # safe default
        self.assertIsNotNone(warning)            # but the ambiguity is visible
        self.assertIn("organization", warning.lower())

    def test_scaffold_folds_owner_type_warning_into_result(self) -> None:
        ctx, _root = self._ctx()
        project = bs.Project(number=5, id="P", created=True)
        runner = FakeRunner([
            (["api", "users/acme", "--jq", ".type"], _fail("HTTP 503")),
            (["api", "repos/actions/add-to-project/commits/v2", "--jq", ".sha"], _ok(self._SHA)),
        ])
        result = bs.scaffold_add_to_project_workflow(project, ctx, runner)
        self.assertTrue(result["scaffolded"])
        self.assertIsNotNone(result["warning"])  # segment-unresolved warning propagated

    def test_render_rejects_non_sha_and_unsafe_ref(self) -> None:
        with self.assertRaises(ValueError):
            bs.render_add_to_project_workflow("https://github.com/users/a/projects/1", "v2", "v2")
        with self.assertRaises(ValueError):
            bs.render_add_to_project_workflow(
                "https://github.com/users/a/projects/1", self._SHA, "v2\ninjected: true")


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
            # (one graphql read — blockedBy now rides ISSUE_QUERY) then item-edit.
            (["project", "field-list", "3", "--owner", "acme"], _ok(json.dumps(board_stub))),
            (["api", "graphql"], _ok(json.dumps({"data": {"repository": {"issue": {
                "number": 99, "state": "OPEN", "stateReason": None, "url": "u",
                "authorAssociation": "OWNER", "blockedBy": {"totalCount": 0},
                "assignees": {"nodes": []},
                "closedByPullRequestsReferences": {"nodes": []}, "subIssues": {"nodes": []},
                "projectItems": {"nodes": [{"id": "item99",
                    "project": {"id": "P", "number": 3, "owner": {"login": "acme"}},
                    "fieldValueByName": None}]}}}}}))),
            (["project", "item-edit", "--id", "item99"], _ok("{}")),
            (["issue", "close", "99", "--repo", "acme/widget"], _ok("")),
            # poll #1 → already shipped.
            (["api", "graphql"], _ok(json.dumps(issue_shipped))),
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
            "authorAssociation": "OWNER", "blockedBy": {"totalCount": 0},
            "assignees": {"nodes": []},
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
            (["project", "item-edit", "--id", "item99"], _ok("{}")),
            (["issue", "close", "99", "--repo", "acme/widget"], _ok("")),
            (["api", "graphql"], _ok(json.dumps(open_stub))),
            (["issue", "delete", "99", "--repo", "acme/widget", "--yes"], _ok("")),
        ])
        result = bs.run_probe(project, ctx, runner, sleep=lambda _s: None, now=lambda: next(clock))
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["observed_stage"], "stub")
        self.assertTrue(any(c[:2] == ["issue", "delete"] for c in runner.calls))


if __name__ == "__main__":
    unittest.main()
