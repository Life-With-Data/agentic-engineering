"""Unit tests for config_registry.py.

Covers: inventory shape, per-kind validation, invalid-value flagging,
tracked-guard refusal, identity-write refusal, byte-preservation, and
absent-file degradation. `verb_*` functions take an explicit RepoContext
rather than going through repo_context() (which shells out assuming
cwd == repo root, per the convention every sibling hook script relies on),
so these tests construct one directly and never need to chdir.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "config_registry.py"

spec = importlib.util.spec_from_file_location("config_registry", SCRIPT)
assert spec is not None and spec.loader is not None
config_registry = importlib.util.module_from_spec(spec)
sys.modules["config_registry"] = config_registry
spec.loader.exec_module(config_registry)

lifecycle_board = config_registry.lifecycle_board


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _init_repo(repo: str) -> "lifecycle_board.RepoContext":
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return lifecycle_board.RepoContext(
        root=repo, main_root=repo, origin_owner="aagnone3",
        origin_repo="agentic-engineering", default_branch="main")


class InventoryShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ctx = _init_repo(self._tmp.name)

    def test_absent_file_degrades_to_all_unset_defaults(self) -> None:
        inv = config_registry.verb_inventory(self.ctx)
        self.assertEqual(len(inv["flags"]), len(config_registry.CONFIG_FLAGS))
        for row in inv["flags"]:
            self.assertFalse(row["set"])
            self.assertTrue(row["valid"])
            self.assertEqual(row["effective"], row["default"])
            self.assertEqual(row["source"], "default")

    def test_every_flag_has_required_fields(self) -> None:
        inv = config_registry.verb_inventory(self.ctx)
        required = {"key", "kind", "default", "effective", "set", "valid",
                    "source", "toggleable", "file", "owner", "description", "plugin"}
        for row in inv["flags"]:
            self.assertEqual(required, set(row.keys()))

    def test_identity_flags_are_not_toggleable(self) -> None:
        inv = config_registry.verb_inventory(self.ctx)
        identity_rows = [r for r in inv["flags"] if r["kind"] == "identity"]
        self.assertEqual({"github_project_owner", "github_project_number"},
                          {r["key"] for r in identity_rows})
        for row in identity_rows:
            self.assertFalse(row["toggleable"])
            self.assertEqual(row["file"], "committed")

    def test_get_unknown_flag_errors(self) -> None:
        with self.assertRaises(lifecycle_board.BoardError) as cm:
            config_registry.verb_get(self.ctx, "nonexistent_flag")
        self.assertEqual(cm.exception.code, "unknown_flag")


class ValidationTest(unittest.TestCase):
    def test_boolean_accepts_true_false_case_insensitive(self) -> None:
        flag = config_registry._BY_KEY["nudge_todowrite"]
        for value in ("true", "false", "True", "FALSE"):
            self.assertTrue(config_registry._validate(flag, value))
        for value in ("yes", "1", "maybe", ""):
            self.assertFalse(config_registry._validate(flag, value))

    def test_enum_accepts_only_declared_choices(self) -> None:
        # github-project is currently the only supported tracker; retired
        # modes (none, github) and never-supported trackers are invalid.
        flag = config_registry._BY_KEY["issue_tracker"]
        for value in ("github-project", "GITHUB-PROJECT"):
            self.assertTrue(config_registry._validate(flag, value))
        for value in ("linear", "beads", "github", "none", ""):
            self.assertFalse(config_registry._validate(flag, value))

class InvalidStaleValueTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ctx = _init_repo(self._tmp.name)

    def test_stale_invalid_value_is_flagged_not_crashed(self) -> None:
        # A stale pre-3.0.0-style override (see workflow_repo_preflight_test.py)
        # must surface as invalid, not raise and not silently pass through.
        Path(self.ctx.root, "agentic-engineering.local.md").write_text(
            "---\nissue_tracker: linear\n---\n", encoding="utf-8")
        row = config_registry.verb_get(self.ctx, "issue_tracker")
        self.assertTrue(row["set"])
        self.assertFalse(row["valid"])
        self.assertEqual(row["effective"], "auto-detect")  # falls back to default


class SetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ctx = _init_repo(self._tmp.name)

    def test_set_boolean_creates_file_and_gitignore(self) -> None:
        result = config_registry.verb_set(self.ctx, "nudge_todowrite", "true")
        self.assertEqual(result["value"], "true")
        self.assertIsNone(result["previous"])
        local_config = Path(self.ctx.root, "agentic-engineering.local.md")
        self.assertIn("nudge_todowrite: true", local_config.read_text(encoding="utf-8"))
        gitignore = Path(self.ctx.root, ".gitignore")
        self.assertIn("agentic-engineering.local.md", gitignore.read_text(encoding="utf-8"))

    def test_set_reports_previous_value(self) -> None:
        config_registry.verb_set(self.ctx, "nudge_todowrite", "true")
        result = config_registry.verb_set(self.ctx, "nudge_todowrite", "false")
        self.assertEqual(result["previous"], "true")
        self.assertEqual(result["value"], "false")

    def test_set_invalid_value_refused(self) -> None:
        with self.assertRaises(lifecycle_board.BoardError) as cm:
            config_registry.verb_set(self.ctx, "issue_tracker", "bogus")
        self.assertEqual(cm.exception.code, "invalid_value")
        self.assertFalse(Path(self.ctx.root, "agentic-engineering.local.md").exists())

    def test_set_identity_flag_refused(self) -> None:
        with self.assertRaises(lifecycle_board.BoardError) as cm:
            config_registry.verb_set(self.ctx, "github_project_owner", "someone")
        self.assertEqual(cm.exception.code, "not_toggleable")

    def test_set_unknown_flag_errors(self) -> None:
        with self.assertRaises(lifecycle_board.BoardError) as cm:
            config_registry.verb_set(self.ctx, "nonexistent_flag", "x")
        self.assertEqual(cm.exception.code, "unknown_flag")

    def test_set_refuses_tracked_local_config_and_leaves_file_unchanged(self) -> None:
        local_config = Path(self.ctx.root, "agentic-engineering.local.md")
        local_config.write_text("---\nnudge_todowrite: false\n---\n", encoding="utf-8")
        _git(self.ctx.root, "add", "-f", local_config.name)
        _git(self.ctx.root, "commit", "-q", "-m", "accidentally tracked")
        before = local_config.read_text(encoding="utf-8")

        with self.assertRaises(lifecycle_board.BoardError) as cm:
            config_registry.verb_set(self.ctx, "nudge_todowrite", "true")
        self.assertEqual(cm.exception.code, "local_config_tracked")
        self.assertEqual(local_config.read_text(encoding="utf-8"), before)

    def test_set_preserves_other_frontmatter_keys_and_body_byte_for_byte(self) -> None:
        local_config = Path(self.ctx.root, "agentic-engineering.local.md")
        original = (
            "---\n"
            "issue_tracker: github-project\n"
            "review_agents: [kieran-rails-reviewer, code-simplicity-reviewer]\n"
            "---\n\n"
            "# Review Context\n\n"
            "Add project-specific review instructions here.\n"
        )
        local_config.write_text(original, encoding="utf-8")

        config_registry.verb_set(self.ctx, "nudge_todowrite", "true")

        after = local_config.read_text(encoding="utf-8")
        self.assertIn("nudge_todowrite: true", after)
        self.assertIn("issue_tracker: github-project", after)
        self.assertIn("review_agents: [kieran-rails-reviewer, code-simplicity-reviewer]", after)
        self.assertIn("# Review Context\n\nAdd project-specific review instructions here.\n", after)


class EnsureGitignoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ctx = _init_repo(self._tmp.name)

    def test_creates_gitignore_when_absent(self) -> None:
        config_registry._ensure_gitignore(self.ctx.root)
        gitignore = Path(self.ctx.root, ".gitignore")
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "agentic-engineering.local.md\n")

    def test_appends_without_duplicating(self) -> None:
        gitignore = Path(self.ctx.root, ".gitignore")
        gitignore.write_text("node_modules/\n", encoding="utf-8")
        config_registry._ensure_gitignore(self.ctx.root)
        config_registry._ensure_gitignore(self.ctx.root)  # idempotent
        text = gitignore.read_text(encoding="utf-8")
        self.assertEqual(text.count("agentic-engineering.local.md"), 1)
        self.assertIn("node_modules/", text)


if __name__ == "__main__":
    unittest.main()
