"""Unit tests for the review agent execution contract (issue #458).

Covers: every markdown file under agents/review/ declares a tools:
allowlist, that allowlist excludes edit/write/dispatch tools, and the body
points at the shared review execution contract. Asserted by category
(walking the filesystem), never a frozen list of agent names.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REVIEW_AGENTS_DIR = (
    Path(__file__).resolve().parent.parent / "agents" / "review"
)

FORBIDDEN_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Task", "Agent"}

CONTRACT_TOKEN = "review-execution-contract.md"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _split_frontmatter(text: str) -> "tuple[dict[str, str], str]":
    """Flat key: value scalars from a leading --- fenced block, plus body."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data: "dict[str, str]" = {}
    for line in match.group(1).splitlines():
        key_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if key_match:
            data[key_match.group(1)] = key_match.group(2).strip()
    body = text[match.end():]
    return data, body


def _review_agent_files() -> "list[Path]":
    return sorted(REVIEW_AGENTS_DIR.glob("*.md"))


class ReviewAgentContractTest(unittest.TestCase):
    def test_finds_review_agents(self) -> None:
        # Guards against a silently-empty test.each: if the directory moves
        # or empties out, every other test here would vacuously pass.
        self.assertTrue(_review_agent_files())

    def test_every_review_agent_declares_a_tools_allowlist(self) -> None:
        for path in _review_agent_files():
            with self.subTest(agent=path.name):
                data, _ = _split_frontmatter(path.read_text())
                self.assertIn("tools", data, f"{path.name} has no tools: key")
                self.assertTrue(
                    data["tools"].strip(),
                    f"{path.name} has an empty tools: value",
                )

    def test_no_review_agent_can_edit_dispatch_or_write(self) -> None:
        for path in _review_agent_files():
            with self.subTest(agent=path.name):
                data, _ = _split_frontmatter(path.read_text())
                declared = {t.strip() for t in data.get("tools", "").split(",")}
                overlap = declared & FORBIDDEN_TOOLS
                self.assertFalse(
                    overlap,
                    f"{path.name} tools: includes forbidden {overlap}",
                )

    def test_every_review_agent_points_at_the_execution_contract(self) -> None:
        for path in _review_agent_files():
            with self.subTest(agent=path.name):
                _, body = _split_frontmatter(path.read_text())
                self.assertIn(
                    CONTRACT_TOKEN,
                    body,
                    f"{path.name} body does not reference {CONTRACT_TOKEN}",
                )


if __name__ == "__main__":
    unittest.main()
