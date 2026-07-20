#!/usr/bin/env python3
"""Validate the repository context contract consumed by wf-* skills.

The contract is deliberately strict at the mapping boundary: every capability
key must appear exactly once in the root AGENTS.md. Available capabilities
resolve to one or more ordered repository-local assets; unsupported
capabilities use an explicit ``not-applicable`` reason.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any
from urllib.parse import unquote


CONTRACT_HEADING = "## Agentic Engineering Repository Contract"
CONTRACT_VERSION = 2
CAPABILITIES = (
    "repository-overview",
    "development-environment",
    "test-execution",
    "bug-reproduction",
    "observability",
    "data-operations",
    "infrastructure-operations",
    "delivery",
    "security-and-access",
    "documentation",
)

_VERSION_RE = re.compile(r"^contract-version:\s*(\d+)\s*$")
_ENTRY_RE = re.compile(r"^-\s+([a-z][a-z0-9-]*):\s*(.+?)\s*$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_LINK_LIST_RE = re.compile(
    r"^\[[^\]]+\]\([^)]+\)(?:\s*,\s*\[[^\]]+\]\([^)]+\))*$"
)
_NA_RE = re.compile(r"^not-applicable\s+[—-]\s+(.+)$")
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_ATX_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_SETEXT_HEADING_RE = re.compile(r"^\s*(?:=+|-+)\s*$")
_EXPLICIT_ANCHOR_RE = re.compile(
    r"<(?:a\s+(?:name|id)|[^>]+\s+id)=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


def _section(text: str) -> list[str] | None:
    lines = text.splitlines()
    try:
        start = lines.index(CONTRACT_HEADING) + 1
    except ValueError:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return lines[start:end]


def _discover_repo_root(start: pathlib.Path) -> pathlib.Path:
    """Find the containing checkout without assuming invocation from its root."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file():
            return candidate
    return start


def _inside_repo(repo_root: pathlib.Path, candidate: pathlib.Path) -> bool:
    try:
        candidate.relative_to(repo_root)
    except ValueError:
        return False
    return True


def _heading_slug(heading: str) -> str:
    """Approximate GitHub's Markdown heading IDs without external packages."""
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"!?(?:\[([^]]+)\])\([^)]+\)", r"\1", heading)
    heading = re.sub(r"[`*_~]", "", heading).strip().lower()
    heading = re.sub(r"[^\w\s-]", "", heading, flags=re.UNICODE)
    return re.sub(r"\s", "-", heading)


def _document_anchors(target: pathlib.Path) -> set[str]:
    """Return explicit and Markdown-heading anchors addressable in a target."""
    text = target.read_text(encoding="utf-8")
    anchors = {unquote(match) for match in _EXPLICIT_ANCHOR_RE.findall(text)}
    slug_counts: dict[str, int] = {}
    lines = text.splitlines()

    for index, line in enumerate(lines):
        match = _ATX_HEADING_RE.match(line)
        heading = match.group(1) if match else None
        if heading is None and index + 1 < len(lines) and _SETEXT_HEADING_RE.match(lines[index + 1]):
            heading = line.strip()
        if not heading:
            continue

        base = _heading_slug(heading)
        if not base:
            continue
        duplicate = slug_counts.get(base, 0)
        anchors.add(base if duplicate == 0 else f"{base}-{duplicate}")
        slug_counts[base] = duplicate + 1

    return anchors


def _validate_target(
    repo_root: pathlib.Path,
    capability: str,
    label: str,
    raw_target: str,
    errors: list[dict[str, str]],
) -> dict[str, str]:
    raw_path, separator, fragment = raw_target.partition("#")
    decoded_path = unquote(raw_path)
    if (
        not decoded_path
        or decoded_path.startswith(("/", "~"))
        or _SCHEME_RE.match(decoded_path)
        or "?" in decoded_path
    ):
        errors.append({
            "code": "non_local_target",
            "capability": capability,
            "message": "Capability targets must be repository-relative paths.",
        })
        return {"status": "invalid", "label": label, "target": raw_target}

    target = (repo_root / decoded_path).resolve()
    if not _inside_repo(repo_root, target):
        errors.append({
            "code": "target_outside_repository",
            "capability": capability,
            "message": f"Target escapes the repository: {raw_target}",
        })
        return {"status": "invalid", "label": label, "target": raw_target}
    if not target.is_file():
        errors.append({
            "code": "target_missing",
            "capability": capability,
            "message": f"Target does not exist: {raw_target}",
        })
        return {"status": "invalid", "label": label, "target": raw_target}

    decoded_fragment = unquote(fragment)
    if separator and (
        not decoded_fragment or decoded_fragment not in _document_anchors(target)
    ):
        errors.append({
            "code": "target_fragment_missing",
            "capability": capability,
            "message": f"Target fragment does not exist: {raw_target}",
        })
        return {"status": "invalid", "label": label, "target": raw_target}

    result = {"status": "available", "label": label, "target": raw_target}
    if separator:
        result["fragment"] = decoded_fragment
    return result


def validate_contract(repo_root: pathlib.Path, required: tuple[str, ...] = ()) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    agents_path = repo_root / "AGENTS.md"
    errors: list[dict[str, str]] = []
    resolved: dict[str, dict[str, Any]] = {}

    unknown_required = sorted(set(required) - set(CAPABILITIES))
    for capability in unknown_required:
        errors.append({
            "code": "unknown_required_capability",
            "capability": capability,
            "message": f"Unknown required capability: {capability}",
        })

    if not agents_path.is_file():
        return {
            "ok": False,
            "contract_version": None,
            "agents_path": str(agents_path),
            "capabilities": resolved,
            "required": list(required),
            "errors": [{
                "code": "agents_missing",
                "message": "The repository root must contain AGENTS.md.",
            }, *errors],
        }

    agents_text = agents_path.read_text(encoding="utf-8")
    heading_count = agents_text.splitlines().count(CONTRACT_HEADING)
    if heading_count != 1:
        return {
            "ok": False,
            "contract_version": None,
            "agents_path": str(agents_path),
            "capabilities": resolved,
            "required": list(required),
            "errors": [{
                "code": "contract_section_count",
                "message": (
                    f"AGENTS.md must contain exactly one '{CONTRACT_HEADING}' section; "
                    f"found {heading_count}."
                ),
            }, *errors],
        }

    section = _section(agents_text)
    if section is None:
        return {
            "ok": False,
            "contract_version": None,
            "agents_path": str(agents_path),
            "capabilities": resolved,
            "required": list(required),
            "errors": [{
                "code": "contract_section_missing",
                "message": f"AGENTS.md must contain '{CONTRACT_HEADING}'.",
            }, *errors],
        }

    version_values = [
        int(match.group(1))
        for line in section
        if (match := _VERSION_RE.match(line.strip()))
    ]
    version = version_values[0] if len(version_values) == 1 else None
    if len(version_values) != 1:
        errors.append({
            "code": "contract_version_count",
            "message": "The contract section must contain exactly one contract-version line.",
        })
    elif version != CONTRACT_VERSION:
        errors.append({
            "code": "unsupported_contract_version",
            "message": f"Expected contract-version: {CONTRACT_VERSION}; found {version}.",
        })

    entries: dict[str, str] = {}
    for line in section:
        match = _ENTRY_RE.match(line.strip())
        if not match:
            continue
        capability, value = match.groups()
        if capability in entries:
            errors.append({
                "code": "duplicate_capability",
                "capability": capability,
                "message": f"Capability appears more than once: {capability}",
            })
            continue
        entries[capability] = value

    for capability in sorted(set(entries) - set(CAPABILITIES)):
        errors.append({
            "code": "unknown_capability",
            "capability": capability,
            "message": f"Unknown capability in contract: {capability}",
        })

    for capability in CAPABILITIES:
        value = entries.get(capability)
        if value is None:
            errors.append({
                "code": "capability_missing",
                "capability": capability,
                "message": f"Required capability key is missing: {capability}",
            })
            continue

        na_match = _NA_RE.match(value)
        if na_match:
            reason = na_match.group(1).strip()
            if len(reason) < 12:
                errors.append({
                    "code": "not_applicable_reason_too_short",
                    "capability": capability,
                    "message": "not-applicable entries require a concrete reason.",
                })
            resolved[capability] = {"status": "not-applicable", "reason": reason}
            if capability in required:
                errors.append({
                    "code": "required_capability_not_applicable",
                    "capability": capability,
                    "message": f"This workflow requires capability: {capability}",
                })
            continue

        if not _LINK_LIST_RE.fullmatch(value):
            errors.append({
                "code": "invalid_capability_value",
                "capability": capability,
                "message": (
                    "Use one or more comma-separated repository-relative Markdown "
                    "links or not-applicable — <reason>."
                ),
            })
            resolved[capability] = {"status": "invalid", "value": value}
            continue

        targets: list[dict[str, str]] = []
        seen_targets: set[str] = set()
        for link_match in _LINK_RE.finditer(value):
            label, raw_target = link_match.groups()
            if raw_target in seen_targets:
                errors.append({
                    "code": "duplicate_capability_target",
                    "capability": capability,
                    "message": f"Capability repeats the same target: {raw_target}",
                })
                targets.append({
                    "status": "invalid",
                    "label": label,
                    "target": raw_target,
                })
                continue
            seen_targets.add(raw_target)
            targets.append(
                _validate_target(repo_root, capability, label, raw_target, errors)
            )

        resolved[capability] = {
            "status": (
                "available"
                if all(target["status"] == "available" for target in targets)
                else "invalid"
            ),
            "targets": targets,
        }

    return {
        "ok": not errors,
        "contract_version": version,
        "agents_path": str(agents_path),
        "capabilities": resolved,
        "required": list(required),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root")
    parser.add_argument("--require", action="append", default=[])
    args = parser.parse_args()

    repo_root = (
        pathlib.Path(args.repo_root)
        if args.repo_root
        else _discover_repo_root(pathlib.Path.cwd())
    )
    result = validate_contract(repo_root, tuple(args.require))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
