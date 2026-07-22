"""Guardrail: every owned lifecycle transition maps to an engine procedure + read-back.

Motivation (issue #262): a `wf-*` workflow skill claimed ownership of "the
transition to ready-for-development" in its prose while nothing in the skill
actually routed to the `lifecycle_board.py` procedure that effects the
transition, nor to the read-back that verifies it landed. The prose has since
been repaired; this test freezes the invariant so the class of bug cannot
silently reopen.

The invariant: for each `wf-*` skill that OWNS a board transition, the union of
its `SKILL.md` and every `references/*.md` must mention — somewhere, in any
wording — the `lifecycle_board.py` verb(s) that effect the transition and the
route stamp / status read-back that confirms it. The assertion is category-level
(does the token appear at all), never sentence-, heading-, filename-, or
line-position-level: repo guardrail policy is to freeze the surface by category
so wording and file layout can evolve freely (see
`docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md`).

Run with: ``python3 -m unittest tests.skill_transition_ownership_test``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

# Declaration of owned lifecycle transitions (issue #262). Each entry names a
# `wf-*` skill that owns a board transition and the tokens whose presence proves
# the skill routes to the engine procedure that effects the transition AND to
# the read-back / route stamp that verifies it. Tokens are matched as plain
# case-sensitive substrings anywhere in the skill's concatenated text.
#
# If ownership genuinely moves, update BOTH this map and the #262 reference above
# in the same change — do not weaken a token to make a red test pass.
OWNED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    # grooming -> ready-for-development: decompose writes Status=planned, and the
    # brainstorm route stamps `brainstormed`; --set-status / --groom-verify verify.
    "wf-grooming": ("--decompose", "--groom-verify", "--set-status", "brainstormed"),
    # development -> in_review: claim moves work in-progress, --set-status hands it
    # to `in_review` for the review gate.
    "wf-development": ("--claim", "--set-status", "in_review"),
    # delivery -> merged/closed: reconcile the board and delete the work packet.
    "wf-delivery": ("--reconcile", "--delete-packet"),
}

# Coarse inverse-guard keyword: a `wf-*` skill whose `Owns:` block claims a
# "transition" but is absent from OWNED_TRANSITIONS must be added to the map (and
# route to its engine procedure). Single keyword by design — a prompt to update
# the map, not NLP.
_TRANSITION_KEYWORD = "transition"


def missing_tokens(skill_text: str, required: tuple[str, ...]) -> list[str]:
    """Return the required tokens absent from ``skill_text`` (case-sensitive substring)."""
    return [token for token in required if token not in skill_text]


def _concatenated_skill_text(skill_name: str) -> str:
    """Concatenate a skill's SKILL.md and every references/*.md into one string."""
    skill_dir = SKILLS_DIR / skill_name
    parts: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        parts.append(skill_md.read_text(encoding="utf-8"))
    references = skill_dir / "references"
    if references.is_dir():
        for ref in sorted(references.glob("*.md")):
            parts.append(ref.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _owns_block(skill_md_text: str) -> str:
    """Extract the `Owns:` block: the `Owns:` line and continuation up to a blank line."""
    lines = skill_md_text.splitlines()
    collecting = False
    block: list[str] = []
    for line in lines:
        if not collecting and line.startswith("Owns:"):
            collecting = True
            block.append(line)
            continue
        if collecting:
            if line.strip() == "":
                break
            block.append(line)
    return "\n".join(block)


class MissingTokensUnitTest(unittest.TestCase):
    """Pure-function fail/pass coverage independent of repo files (mutation-proof)."""

    def test_all_tokens_present_returns_empty(self) -> None:
        text = "route via --decompose then --groom-verify and --set-status; stamp brainstormed"
        self.assertEqual(missing_tokens(text, ("--decompose", "brainstormed")), [])

    def test_missing_token_is_reported(self) -> None:
        # Same shape as removing `--groom-verify` from a real skill's text.
        text = "route via --decompose then --set-status; stamp brainstormed"
        self.assertEqual(
            missing_tokens(text, ("--decompose", "--groom-verify", "brainstormed")),
            ["--groom-verify"],
        )

    def test_multiple_missing_tokens_preserve_order(self) -> None:
        self.assertEqual(
            missing_tokens("", ("--claim", "--set-status", "in_review")),
            ["--claim", "--set-status", "in_review"],
        )


class OwnsBlockUnitTest(unittest.TestCase):
    """The Owns-block extractor is single-line and multi-line aware."""

    def test_single_line_block(self) -> None:
        md = "Layer: Workflow policy\n\nOwns: a, b, and c.\n\nRequires: x.\n"
        self.assertEqual(_owns_block(md), "Owns: a, b, and c.")

    def test_multi_line_block_stops_at_blank(self) -> None:
        md = "Owns: intent discovery,\nand the transition to\nready-for-development.\n\nNext: x.\n"
        block = _owns_block(md)
        self.assertIn("transition", block)
        self.assertNotIn("Next", block)

    def test_no_owns_line_returns_empty(self) -> None:
        self.assertEqual(_owns_block("# Heading\n\nBody text.\n"), "")


class OwnedTransitionIntegrationTest(unittest.TestCase):
    """Each mapped skill's real files must contain every required token."""

    def test_mapped_skills_reference_engine_procedure_and_read_back(self) -> None:
        for skill_name, required in OWNED_TRANSITIONS.items():
            with self.subTest(skill=skill_name):
                text = _concatenated_skill_text(skill_name)
                self.assertNotEqual(
                    text,
                    "",
                    f"{skill_name}: no SKILL.md/references text found under {SKILLS_DIR / skill_name}",
                )
                absent = missing_tokens(text, required)
                self.assertEqual(
                    absent,
                    [],
                    f"{skill_name} owns a lifecycle transition but its SKILL.md + "
                    f"references/*.md never mention {absent}. Add the "
                    f"lifecycle_board.py procedure/read-back for this transition to the "
                    f"skill's route references, or — if ownership genuinely changed — "
                    f"update OWNED_TRANSITIONS and the issue #262 reference in this test.",
                )


class InverseTransitionOwnershipGuardTest(unittest.TestCase):
    """A wf-* skill claiming a transition in `Owns:` must be in the map."""

    def test_unmapped_skills_do_not_claim_a_transition(self) -> None:
        for skill_dir in sorted(SKILLS_DIR.glob("wf-*")):
            if not skill_dir.is_dir():
                continue
            skill_name = skill_dir.name
            if skill_name in OWNED_TRANSITIONS:
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            with self.subTest(skill=skill_name):
                owns = _owns_block(skill_md.read_text(encoding="utf-8"))
                self.assertNotIn(
                    _TRANSITION_KEYWORD,
                    owns,
                    f"{skill_name} claims a '{_TRANSITION_KEYWORD}' in its Owns: block but "
                    f"is not in OWNED_TRANSITIONS. Add the transition's lifecycle_board.py "
                    f"engine procedure to the skill and an entry to the map (with a #262 "
                    f"rationale) so the transition-to-procedure invariant is enforced for it.",
                )


if __name__ == "__main__":
    unittest.main()
