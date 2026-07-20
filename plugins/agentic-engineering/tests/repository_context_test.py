"""Unit tests for the strict repository context contract."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "repository-context.py"
spec = importlib.util.spec_from_file_location("repository_context", SCRIPT)
assert spec is not None and spec.loader is not None
repository_context = importlib.util.module_from_spec(spec)
sys.modules["repository_context"] = repository_context
spec.loader.exec_module(repository_context)


class RepositoryContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

    def _write_guidance(self, capability: str, *, skill_name: str | None = None) -> str:
        if skill_name:
            target = self.repo / ".agents" / "skills" / skill_name / "SKILL.md"
            frontmatter = f"---\nname: {skill_name}\ndescription: Repository operations.\n---\n\n"
        else:
            target = self.repo / "docs" / f"{capability}.md"
            frontmatter = ""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"{frontmatter}# {capability}\n\n"
            "Layer: Repository operations\n"
            f"Capability: {capability}\n",
            encoding="utf-8",
        )
        return target.relative_to(self.repo).as_posix()

    def _write_contract(self, values: dict[str, str] | None = None) -> None:
        values = values or {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        lines = [
            "# Agent instructions",
            "",
            repository_context.CONTRACT_HEADING,
            "",
            f"contract-version: {repository_context.CONTRACT_VERSION}",
            "",
            *[f"- {key}: {value}" for key, value in values.items()],
            "",
        ]
        (self.repo / "AGENTS.md").write_text("\n".join(lines), encoding="utf-8")

    def test_complete_contract_resolves_every_capability(self) -> None:
        self._write_contract()
        result = repository_context.validate_contract(self.repo)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(set(result["capabilities"]), set(repository_context.CAPABILITIES))
        self.assertEqual(
            result["capabilities"]["repository-overview"]["targets"][0]["label"],
            "repository-overview",
        )

    def test_missing_agents_file_fails_closed(self) -> None:
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "agents_missing")

    def test_every_capability_key_is_mandatory(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES[:-1]
        }
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn(
            "documentation",
            [error.get("capability") for error in result["errors"]],
        )

    def test_contract_section_must_appear_exactly_once(self) -> None:
        self._write_contract()
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            agents.read_text(encoding="utf-8")
            + f"\n{repository_context.CONTRACT_HEADING}\n",
            encoding="utf-8",
        )
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "contract_section_count")

    def test_v1_contract_requires_migration(self) -> None:
        self._write_contract()
        agents = self.repo / "AGENTS.md"
        agents.write_text(
            agents.read_text(encoding="utf-8").replace(
                f"contract-version: {repository_context.CONTRACT_VERSION}",
                "contract-version: 1",
            ),
            encoding="utf-8",
        )
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn(
            "unsupported_contract_version",
            [error["code"] for error in result["errors"]],
        )

    def test_repository_root_is_discovered_from_a_subdirectory(self) -> None:
        self._write_contract()
        (self.repo / ".git").mkdir()
        nested = self.repo / "packages" / "example"
        nested.mkdir(parents=True)
        self.assertEqual(
            repository_context._discover_repo_root(nested),
            self.repo.resolve(),
        )

    def test_not_applicable_is_valid_until_workflow_requires_it(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["data-operations"] = (
            "not-applicable — This repository has no persistent application data."
        )
        self._write_contract(values)
        self.assertTrue(repository_context.validate_contract(self.repo)["ok"])

        result = repository_context.validate_contract(
            self.repo, required=("data-operations",)
        )
        self.assertFalse(result["ok"])
        self.assertIn(
            "required_capability_not_applicable",
            [error["code"] for error in result["errors"]],
        )

    def test_existing_document_needs_no_contract_annotations(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        target = self.repo / "docs" / "bug-reproduction.md"
        target.write_text(
            "# Debugging playbook\n\nRun the application and capture the error.\n",
            encoding="utf-8",
        )
        values["bug-reproduction"] = "[debugging playbook](docs/bug-reproduction.md)"
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertTrue(result["ok"], result["errors"])

    def test_capability_accepts_multiple_ordered_targets(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        primary = self._write_guidance("bug-reproduction")
        supporting = self._write_guidance("development-environment")
        values["bug-reproduction"] = (
            f"[debugging playbook]({primary}), "
            f"[local environment]({supporting})"
        )
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(
            [
                target["label"]
                for target in result["capabilities"]["bug-reproduction"]["targets"]
            ],
            ["debugging playbook", "local environment"],
        )

    def test_one_target_can_serve_multiple_capabilities(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        shared = self.repo / "docs" / "engineering.md"
        shared.write_text("# Engineering guide\n", encoding="utf-8")
        values["development-environment"] = "[engineering guide](docs/engineering.md)"
        values["test-execution"] = "[engineering guide](docs/engineering.md)"
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertTrue(result["ok"], result["errors"])

    def test_fragment_targets_validate_the_underlying_file(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["bug-reproduction"] = (
            "[reproduction procedure](docs/bug-reproduction.md#known-failures)"
        )
        target = self.repo / "docs" / "bug-reproduction.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n## Known failures\n",
            encoding="utf-8",
        )
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(
            result["capabilities"]["bug-reproduction"]["targets"][0]["fragment"],
            "known-failures",
        )

    def test_missing_fragment_invalidates_capability(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["bug-reproduction"] = (
            "[reproduction procedure](docs/bug-reproduction.md#missing-section)"
        )
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn(
            "target_fragment_missing",
            [error["code"] for error in result["errors"]],
        )

    def test_malformed_target_list_is_rejected(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["bug-reproduction"] = (
            "[bug reproduction](docs/bug-reproduction.md) "
            "[test execution](docs/test-execution.md)"
        )
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn(
            "invalid_capability_value",
            [error["code"] for error in result["errors"]],
        )

    def test_duplicate_target_within_capability_is_rejected(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["bug-reproduction"] = (
            "[primary](docs/bug-reproduction.md), "
            "[duplicate](docs/bug-reproduction.md)"
        )
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn(
            "duplicate_capability_target",
            [error["code"] for error in result["errors"]],
        )

    def test_missing_supporting_target_invalidates_capability(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["bug-reproduction"] = (
            "[primary](docs/bug-reproduction.md), [missing](docs/missing.md)"
        )
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["capabilities"]["bug-reproduction"]["status"], "invalid"
        )
        self.assertIn("target_missing", [error["code"] for error in result["errors"]])

    def test_repository_skills_do_not_require_repo_prefix(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        existing_path = self._write_guidance(
            "bug-reproduction", skill_name="debugging-playbook"
        )
        values["bug-reproduction"] = f"[bug-reproduction]({existing_path})"
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertTrue(result["ok"], result["errors"])

    def test_target_cannot_escape_repository(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["observability"] = "[observability](../outside.md)"
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn(
            "target_outside_repository",
            [error["code"] for error in result["errors"]],
        )

    def test_target_cannot_use_an_external_scheme(self) -> None:
        values = {
            capability: f"[{capability}]({self._write_guidance(capability)})"
            for capability in repository_context.CAPABILITIES
        }
        values["observability"] = "[external runbook](https://example.com/runbook)"
        self._write_contract(values)
        result = repository_context.validate_contract(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn(
            "non_local_target",
            [error["code"] for error in result["errors"]],
        )


if __name__ == "__main__":
    unittest.main()
