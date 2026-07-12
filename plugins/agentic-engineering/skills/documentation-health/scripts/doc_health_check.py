#!/usr/bin/env python3
"""
doc_health_check.py — deterministic documentation-health scanner.

Runs on ANY repository (not just this one). Zero third-party dependencies;
Python 3.8+. Emits a severity-grouped report of the checkable signals behind
the `documentation-health` skill, and optional JSON for tooling.

It intentionally only performs the DETERMINISTIC checks. Judgment calls
(duplication, Diataxis mode-mixing, "is this generic filler", stale commands)
are left to the skill's read-and-reason pass — this script tells that pass
exactly which files to open.

Usage:
    python3 doc_health_check.py [REPO_DIR] [--json] [--claude-max N] [--readme-max N]

Exit code is 0 unless --strict is passed, in which case any ERROR finding
exits 1 (useful as a CI gate).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# --------------------------------------------------------------------------
# Config / thresholds (override via CLI). Numbers are sourced from the skill's
# reference.md — CLAUDE.md ~200-line soft ceiling, README ~400-line smell.
# --------------------------------------------------------------------------
CLAUDE_WARN_LINES = 200          # official soft ceiling
CLAUDE_ERROR_LINES = 300         # "definitely prune" territory
README_WARN_LINES = 400          # index+quickstart, not a manual
SHORT_DESC_MAX_CHARS = 120       # Standard-Readme rule

# Directories we never descend into.
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", "target",
    "vendor", ".next", ".turbo", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".claude/worktrees",  # git worktrees, if present
}

# Package-manifest files whose presence marks a "package" that should own a README.
PACKAGE_MANIFESTS = {
    "package.json", "pyproject.toml", "setup.py", "go.mod",
    "Cargo.toml", "Gemfile", "pom.xml", "build.gradle", "composer.json",
}

# Community-health files GitHub recognizes, checked across root / .github / docs.
COMMUNITY_HEALTH = [
    "README.md", "LICENSE", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
    "SECURITY.md", "SUPPORT.md",
]

# Placeholder / template rot left behind by scaffolding.
PLACEHOLDER_PATTERNS = [
    r"\bTODO\b", r"\bTBD\b", r"\bFIXME\b", r"lorem ipsum",
    r"<your[-_ ]", r"\bINSERT\b", r"\bYOUR_[A-Z_]+\b",
    r"username/repo\b", r"\bexample\.com\b",
    r"A short description of the project",
    r"\[description\]", r"\[link\]", r"\[TODO\]",
]

# Self-evident filler that dilutes a CLAUDE.md's signal.
FILLER_PATTERNS = [
    r"write clean code", r"use meaningful (variable |)names",
    r"follow best practices", r"add appropriate error handling",
    r"write (good|proper) (tests|documentation)", r"keep it simple",
    r"be consistent", r"use descriptive names",
]

# Rough secret shapes. Deliberately conservative to limit false positives.
SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"gh[pousr]_[A-Za-z0-9]{30,}", "GitHub token"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI-style secret key"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----", "private key"),
    (r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]", "hardcoded credential"),
]

# Facts that drift: standalone counts and versions living in prose.
HARDCODED_COUNT_RE = re.compile(
    r"\b\d+\s+(agents?|commands?|skills?|tests?|packages?|endpoints?|"
    r"components?|plugins?|files?|modules?|services?|tables?)\b", re.I)
VERSION_RE = re.compile(r"\bv?\d+\.\d+\.\d+\b")

# Internal-only markers that must not appear in a published docs tree.
LEAK_MARKERS = [
    r"\bINTERNAL\b", r"DO NOT SHIP", r"DO NOT PUBLISH",
    r"audience:\s*internal", r"published:\s*false", r"\bCONFIDENTIAL\b",
]

# Other tools' agent-context files. AGENTS.md (agents.md spec) is the
# cross-tool standard; Claude Code does NOT read it natively — when both files
# exist they must be bridged (CLAUDE.md = `@AGENTS.md` import, or a symlink)
# or they drift. Legacy per-tool configs are consolidation candidates
# (`/init` reads and merges them).
LEGACY_AGENT_CONFIGS = [
    ".cursorrules", ".windsurfrules", ".clinerules", "GEMINI.md",
    os.path.join(".github", "copilot-instructions.md"),
]
LEGACY_AGENT_CONFIG_DIRS = [
    os.path.join(".cursor", "rules"), os.path.join(".devin", "rules"),
]

# Raw `/init` scaffolding marker. Machine-generated context files that merely
# restate the repo measurably hurt agent success while adding cost
# (arXiv:2602.11988) — fine as a draft, a smell if shipped uncurated.
INIT_BOILERPLATE_RE = re.compile(r"This file provides guidance to Claude Code")

# Shouted emphasis: high density means rules are competing, not landing.
EMPHASIS_RE = re.compile(r"\b(IMPORTANT|CRITICAL|NEVER|ALWAYS|YOU MUST)\b")
EMPHASIS_MAX = 8

# Formatter/linter configs own style; style rules in CLAUDE.md prose then
# duplicate them (SSOT violation — the config is the authority).
LINTER_CONFIG_GLOBS = [
    ".prettierrc*", "prettier.config.*", ".eslintrc*", "eslint.config.*",
    "biome.json*", ".rubocop.yml", "ruff.toml", ".ruff.toml", ".flake8",
    "rustfmt.toml", ".clang-format",
]
STYLE_RULE_RE = re.compile(
    r"(?i)\b(indent(ation)?|semicolons?|single quotes|double quotes|"
    r"trailing commas?|import (order|sorting)|line (length|width)|"
    r"tabs? (vs\.?|or) spaces)\b")

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}


@dataclass
class Finding:
    severity: str          # ERROR | WARN | INFO
    layer: str             # e.g. "root-claude", "root-readme", "community-health"
    file: str              # repo-relative path (or "-" for repo-wide)
    message: str
    hint: str = ""


@dataclass
class Report:
    repo: str
    findings: list = field(default_factory=list)
    skipped_tools: list = field(default_factory=list)

    def add(self, *a, **kw):
        self.findings.append(Finding(*a, **kw))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def iter_files(root: Path, name: str):
    """Yield all files named `name` under root, skipping noise dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        # prune skip dirs in place
        rp = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and rel(root, rp / d) not in SKIP_DIRS
        ]
        if name in filenames:
            yield rp / name


def strip_code_and_comments(md: str) -> str:
    """Remove fenced code blocks, inline code spans, and HTML comments so that
    @import / regex scans don't trip on examples or maintainer notes."""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)         # HTML comments
    md = re.sub(r"```.*?```", "", md, flags=re.S)          # fenced blocks
    md = re.sub(r"~~~.*?~~~", "", md, flags=re.S)
    md = re.sub(r"`[^`]*`", "", md)                        # inline spans
    return md


def headings(md: str):
    """Return list of (level, text) ATX headings outside code fences."""
    body = re.sub(r"```.*?```", "", md, flags=re.S)
    out = []
    for line in body.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            out.append((len(m.group(1)), m.group(2).strip()))
    return out


def has_section(md: str, *keywords: str) -> bool:
    kw = [k.lower() for k in keywords]
    for _lvl, text in headings(md):
        t = text.lower()
        if any(k in t for k in kw):
            return True
    return False


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


# --------------------------------------------------------------------------
# Layer checks
# --------------------------------------------------------------------------
def content_checks(root: Path, path: Path, md: str, layer: str, rep: Report,
                   check_imports: bool = True, linter_configs=()):
    """Hygiene checks shared by every launch-loaded agent-context file:
    CLAUDE.md, a bridged AGENTS.md, and .claude/rules/*.md."""
    rp = rel(root, path)
    scan = strip_code_and_comments(md)

    counts = {mo.group(0).strip() for mo in HARDCODED_COUNT_RE.finditer(scan)}
    if counts:
        rep.add("WARN", layer, rp,
                "Hardcoded count(s) that will drift: " + ", ".join(sorted(counts)[:6]),
                "State WHERE the authoritative number lives (a generator/test/"
                "manifest) instead of the number itself.")
    versions = {mo.group(0) for mo in VERSION_RE.finditer(scan)}
    if versions:
        rep.add("INFO", layer, rp,
                "Hardcoded version(s): " + ", ".join(sorted(versions)[:6]),
                "Versions change frequently — reference package.json / the tag "
                "rather than pinning a literal here.")

    filler = [p for p in FILLER_PATTERNS if re.search(p, scan, re.I)]
    if filler:
        rep.add("WARN", layer, rp,
                f"Generic filler detected ({len(filler)} pattern(s)) — advice "
                "Claude already knows dilutes real rules.",
                "Delete self-evident guidance; keep only project-specific deltas.")

    # broken @imports (skipped for files no tool actually expands)
    if check_imports:
        for mo in re.finditer(r"(?m)(?:^|\s)@([^\s`]+)", scan):
            target = mo.group(1)
            if target.startswith("~"):
                resolved = Path(os.path.expanduser(target))
            elif target.startswith("/"):
                resolved = Path(target)
            else:
                resolved = (path.parent / target)
            if not resolved.exists():
                rep.add("ERROR", layer, rp,
                        f"Broken @import: `@{target}` does not resolve.",
                        "Fix the path or remove the import.")

    for pat, label in SECRET_PATTERNS:
        if re.search(pat, md):
            rep.add("ERROR", layer, rp,
                    f"Possible secret in {path.name} ({label}).",
                    "Remove it immediately and rotate the credential.")
            break

    placeholders = [p for p in PLACEHOLDER_PATTERNS if re.search(p, scan, re.I)]
    if placeholders:
        rep.add("INFO", layer, rp,
                f"Placeholder/TODO rot ({len(placeholders)} pattern(s)).",
                "Resolve or delete leftover scaffolding text.")

    if INIT_BOILERPLATE_RE.search(md):
        rep.add("INFO", layer, rp,
                "Looks like raw `/init` scaffolding (\"This file provides "
                "guidance to Claude Code…\").",
                "Curate it — generated context files that restate the repo "
                "measurably hurt agent success and add cost (arXiv:2602.11988); "
                "keep only rules the agent can't infer from the code.")

    n_emph = len(EMPHASIS_RE.findall(scan))
    if n_emph > EMPHASIS_MAX:
        rep.add("INFO", layer, rp,
                f"{n_emph} shouted-emphasis markers (IMPORTANT/NEVER/ALWAYS/"
                "YOU MUST) — at this density rules compete instead of landing.",
                "Prune or demote; phrase as \"prefer X; exception: Y\", and use "
                "a hook (enforced) for zero-exception rules.")

    if linter_configs:
        style = sorted({mo.group(0).lower() for mo in STYLE_RULE_RE.finditer(scan)})
        if style:
            rep.add("INFO", layer, rp,
                    "Style rules in prose (" + ", ".join(style[:4]) + ") while a "
                    f"formatter/linter config exists ({linter_configs[0]}).",
                    "The linter config is the SSOT for style — keep only "
                    "conventions tooling can't enforce.")


def check_claude_md(root: Path, path: Path, is_root: bool, rep: Report,
                    linter_configs=()):
    layer = "root-claude" if is_root else "nested-claude"
    md = read(path)
    lines = md.count("\n") + 1
    rp = rel(root, path)

    if lines > CLAUDE_ERROR_LINES:
        rep.add("ERROR", layer, rp,
                f"{lines} lines — well over the ~{CLAUDE_WARN_LINES}-line ceiling; "
                "bloat reduces instruction adherence.",
                "Prune, or move path-specific rules into .claude/rules/*.md "
                "(paths: globs) or a skill so they load on demand.")
    elif lines > CLAUDE_WARN_LINES:
        rep.add("WARN", layer, rp,
                f"{lines} lines — over the ~{CLAUDE_WARN_LINES}-line soft ceiling.",
                "Consider trimming or scoping detail into nested files / rules.")

    # file-by-file map heuristic: many "path — description" bullet lines
    map_lines = len(re.findall(r"^\s*[-*]\s+`?[\w./-]+`?\s+[—:-]\s+\S", md, re.M))
    if map_lines >= 12:
        rep.add("WARN", layer, rp,
                f"~{map_lines} file/dir description lines look like a file-by-file "
                "map (an explicit anti-pattern).",
                "Give orientation, not a manifest — Claude can read the tree.")

    content_checks(root, path, md, layer, rep, linter_configs=linter_configs)


def check_cross_tool_configs(root: Path, rep: Report, linter_configs=()) -> int:
    """AGENTS.md and legacy per-tool configs. Claude Code does not read
    AGENTS.md natively — when both files exist, CLAUDE.md must be a bridge
    (`@AGENTS.md` import or symlink) or the two copies drift.

    Returns AGENTS.md's line count when it is import-bridged (those lines
    expand into launch context), else 0.
    """
    agents = root / "AGENTS.md"
    claude = root / "CLAUDE.md"

    legacy = [f for f in LEGACY_AGENT_CONFIGS if (root / f).exists()]
    legacy += [d + "/" for d in LEGACY_AGENT_CONFIG_DIRS if (root / d).is_dir()]
    if legacy:
        rep.add("INFO", "cross-tool", "-",
                "Per-tool agent config(s) present: " + ", ".join(legacy) + ".",
                "Consolidate into CLAUDE.md/AGENTS.md (`/init` reads and merges "
                "legacy configs) — parallel copies of the same rules drift.")

    if not agents.exists():
        return 0

    symlinked = False
    if claude.is_symlink():
        try:
            symlinked = claude.resolve() == agents.resolve()
        except OSError:
            symlinked = False

    imported = False
    if claude.exists() and not symlinked:
        body = strip_code_and_comments(read(claude))
        imported = re.search(r"(?m)(?:^|\s)@\.?/?AGENTS\.md\b", body) is not None

    if not claude.exists():
        rep.add("INFO", "cross-tool", "AGENTS.md",
                "AGENTS.md present but no CLAUDE.md — Claude Code does not read "
                "AGENTS.md natively.",
                "Bridge it: a CLAUDE.md containing `@AGENTS.md` (plus any "
                "Claude-specific rules), or a symlink (symlinks need admin/"
                "Developer Mode on Windows — prefer the import there).")
    elif not (symlinked or imported):
        rep.add("WARN", "cross-tool", "CLAUDE.md",
                "CLAUDE.md and AGENTS.md are independent files — cross-tool "
                "context drift risk.",
                "Keep shared instructions in AGENTS.md and reduce CLAUDE.md to "
                "`@AGENTS.md` plus Claude-specific rules (or symlink them).")

    # A bridged AGENTS.md IS launch-loaded context; an unbridged one still
    # steers other tools — either way it gets the same hygiene bar. Skip the
    # symlink case (already scanned as CLAUDE.md). Only validate @imports when
    # Claude actually expands the file (other tools give @ no meaning).
    if symlinked:
        return 0
    md = read(agents)
    lines = md.count("\n") + 1
    if lines > CLAUDE_ERROR_LINES:
        rep.add("ERROR", "cross-tool", "AGENTS.md",
                f"{lines} lines — well over the ~{CLAUDE_WARN_LINES}-line "
                "ceiling that applies to launch-loaded agent context.",
                "Trim it like a CLAUDE.md: move detail into on-demand "
                "mechanisms instead of one giant file.")
    elif lines > CLAUDE_WARN_LINES:
        rep.add("WARN", "cross-tool", "AGENTS.md",
                f"{lines} lines — over the ~{CLAUDE_WARN_LINES}-line soft "
                "ceiling for launch-loaded agent context.",
                "Trim or move detail into on-demand mechanisms.")
    content_checks(root, agents, md, "cross-tool", rep,
                   check_imports=imported, linter_configs=linter_configs)
    return lines if imported else 0


def check_claude_local(root: Path, rep: Report):
    """CLAUDE.local.md holds personal, per-machine overrides (sandbox URLs,
    test data). Official guidance: add it to .gitignore."""
    local_files = sorted(iter_files(root, "CLAUDE.local.md"))
    if not local_files or not (root / ".git").exists():
        return
    for p in local_files:
        rp = rel(root, p)
        try:
            tracked = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--error-unmatch", rp],
                capture_output=True, timeout=10).returncode == 0
            ignored = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "-q", rp],
                capture_output=True, timeout=10).returncode == 0
        except Exception:
            return
        if tracked:
            rep.add("WARN", "local-claude", rp,
                    "CLAUDE.local.md is tracked by git — it exists to hold "
                    "personal, per-machine overrides.",
                    "`git rm --cached` it and add `CLAUDE.local.md` to "
                    ".gitignore; fold anything team-relevant into CLAUDE.md.")
        elif not ignored:
            rep.add("INFO", "local-claude", rp,
                    "CLAUDE.local.md is not gitignored — a future `git add -A` "
                    "would commit it.",
                    "Add `CLAUDE.local.md` to .gitignore.")


def check_rules(root: Path, rep: Report, linter_configs=()):
    """.claude/rules/*.md get the same hygiene bar as CLAUDE.md. Rules WITHOUT
    `paths:` frontmatter load at launch (same cost as CLAUDE.md itself).

    Returns [(label, lines)] for unscoped rules, for the launch budget."""
    rules_dir = root / ".claude" / "rules"
    if not rules_dir.is_dir():
        return []
    unscoped = []
    for p in sorted(rules_dir.rglob("*.md")):
        md = read(p)
        content_checks(root, p, md, "rules", rep, linter_configs=linter_configs)
        fm = re.match(r"^---\s*\n(.*?)\n---(\s*\n|\s*$)", md, re.S)
        if not (fm and re.search(r"(?m)^paths\s*:", fm.group(1))):
            unscoped.append((rel(root, p), md.count("\n") + 1))
    if unscoped:
        names = ", ".join(n for n, _ in unscoped[:6])
        rep.add("INFO", "rules", rel(root, rules_dir),
                f"{len(unscoped)} rule file(s) load at launch (no `paths:` "
                f"frontmatter): {names}.",
                "Rules scoped with `paths:` globs load only when matching "
                "files are touched — scope them where possible.")
    return unscoped


def check_launch_budget(root: Path, rep: Report, extra_parts):
    """The ~200-line ceiling applies to the WHOLE always-loaded set — root
    CLAUDE.md (either location) + CLAUDE.local.md + unscoped rules + a bridged
    AGENTS.md — not just the root file. Fires only when no single file tripped
    the per-file warning but the sum does."""
    parts = []
    for p in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md",
              root / "CLAUDE.local.md"):
        if p.exists():
            parts.append((rel(root, p), read(p).count("\n") + 1))
    parts += [pt for pt in extra_parts if pt[1]]
    total = sum(n for _, n in parts)
    biggest = max((n for _, n in parts), default=0)
    if len(parts) > 1 and biggest <= CLAUDE_WARN_LINES < total:
        rep.add("WARN", "root-claude", "-",
                f"Launch-loaded agent context totals ~{total} lines across "
                f"{len(parts)} files ({', '.join(n for n, _ in parts)}).",
                f"The ~{CLAUDE_WARN_LINES}-line ceiling applies to the whole "
                "always-loaded set — scope rules with `paths:` globs and move "
                "detail to skills/nested files (imports don't save context).")


def check_readme(root: Path, path: Path, is_root: bool, rep: Report,
                 license_exists: bool):
    layer = "root-readme" if is_root else "nested-readme"
    md = read(path)
    rp = rel(root, path)
    lines = md.count("\n") + 1
    hs = headings(md)

    # H1 / title
    if not any(lvl == 1 for lvl, _ in hs):
        rep.add("WARN", layer, rp, "No H1 title.",
                "Start with a single `# Title` matching the repo/package name.")

    # description: first non-heading, non-badge, non-blank line
    desc = None
    for line in md.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("[![") or s.startswith("!["):
            continue
        desc = s
        break
    if not desc:
        rep.add("WARN", layer, rp, "No one-line description under the title.",
                "Add a <120-char sentence stating what the project does.")
    elif is_root and len(desc) > SHORT_DESC_MAX_CHARS * 2:
        rep.add("INFO", layer, rp,
                "Opening description is long; keep the first line tight.",
                "Lead with a single crisp sentence; details below.")

    if is_root:
        if not has_section(md, "install", "getting started", "setup", "quick start", "quickstart"):
            rep.add("WARN", layer, rp,
                    "No Install / Getting-Started section.",
                    "Add copyable setup steps (omit only for pure-doc repos).")
        if not has_section(md, "usage", "example", "quick start", "quickstart"):
            rep.add("WARN", layer, rp, "No Usage/Quickstart section.",
                    "Show the fastest path to value with a runnable example.")
        if not has_section(md, "license"):
            if license_exists:
                rep.add("INFO", layer, rp,
                        "LICENSE file exists but README has no License section.",
                        "Add a short License section naming the SPDX id.")
            else:
                rep.add("WARN", layer, rp, "No License section and no LICENSE file.",
                        "Add a LICENSE file and reference it here.")

    if lines > README_WARN_LINES:
        rep.add("WARN", layer, rp,
                f"{lines} lines — a README is an index+quickstart, not a manual.",
                "Move reference/how-to/deep-dive content into /docs and link to it.")

    # TOC for long READMEs (GitHub auto-TOCs, but npm/others don't)
    if lines > 100 and not re.search(r"(?i)^#{1,3}\s*(table of contents|contents)\b", md, re.M) \
            and "<!-- toc -->" not in md.lower():
        rep.add("INFO", layer, rp,
                "Long README without a Table of Contents.",
                "Add one (e.g. `doctoc`) for non-GitHub renderers like npm.")

    placeholders = [p for p in PLACEHOLDER_PATTERNS if re.search(p, strip_code_and_comments(md), re.I)]
    if placeholders:
        rep.add("ERROR" if is_root else "WARN", layer, rp,
                f"Placeholder/template text left in README ({len(placeholders)} pattern(s)).",
                "Replace scaffolding text with real content.")

    if is_root and HARDCODED_COUNT_RE.search(strip_code_and_comments(md)):
        counts = {mo.group(0).strip() for mo in HARDCODED_COUNT_RE.finditer(strip_code_and_comments(md))}
        rep.add("INFO", layer, rp,
                "Hardcoded count(s) in README: " + ", ".join(sorted(counts)[:6]),
                "If a generator/test owns these numbers, generate them into the "
                "README (between markers) rather than hand-editing.")


def check_nested_readme_coverage(root: Path, rep: Report):
    for dirpath, dirnames, filenames in os.walk(root):
        rp = Path(dirpath)
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and rel(root, rp / d) not in SKIP_DIRS]
        if rp == root:
            continue
        if any(m in filenames for m in PACKAGE_MANIFESTS):
            if not any(f.lower() == "readme.md" for f in filenames):
                rep.add("WARN", "nested-readme", rel(root, rp),
                        "Package directory has no README.md.",
                        "Add a README: purpose, owner/contact, status, local usage; "
                        "link up to the root for workspace setup.")


def check_community_health(root: Path, rep: Report):
    locations = [root, root / ".github", root / "docs"]
    present = {}
    for fname in COMMUNITY_HEALTH:
        found = None
        for loc in locations:
            # LICENSE may lack extension
            candidates = [loc / fname]
            if fname == "LICENSE":
                candidates += [loc / "LICENSE.md", loc / "LICENSE.txt"]
            for c in candidates:
                if c.exists():
                    found = rel(root, c)
                    break
            if found:
                break
        present[fname] = found

    for fname, found in present.items():
        if not found:
            sev = "ERROR" if fname in ("README.md", "LICENSE") else "WARN"
            rep.add(sev, "community-health", "-",
                    f"Missing {fname} (checked root, .github/, docs/).",
                    "Note: an org-level .github repo may supply a default; "
                    "confirm before adding a local copy.")

    # issue/PR templates must live under .github/
    it = root / ".github" / "ISSUE_TEMPLATE"
    pr = list((root / ".github").glob("PULL_REQUEST_TEMPLATE*")) if (root / ".github").exists() else []
    if not it.exists():
        rep.add("INFO", "community-health", "-",
                "No .github/ISSUE_TEMPLATE/ directory.",
                "Add issue templates to guide bug reports/feature requests.")
    if not pr:
        rep.add("INFO", "community-health", "-",
                "No PULL_REQUEST_TEMPLATE in .github/.",
                "Add a PR template to standardize contributions.")


def check_adrs(root: Path, rep: Report):
    adr_dirs = [root / "docs" / "adr", root / "docs" / "decisions",
                root / "doc" / "adr", root / "adr",
                root / "docs" / "architecture" / "decisions"]
    found = [d for d in adr_dirs if d.exists()]
    if not found:
        rep.add("INFO", "internal-docs", "-",
                "No ADR (Architecture Decision Record) directory found.",
                "For non-trivial repos, start docs/adr/ (Nygard/MADR format) so "
                "the 'why' behind decisions is captured and append-only.")
        return
    for d in found:
        adrs = sorted([p for p in d.glob("*.md") if not p.name.lower().startswith("readme")])
        if not adrs:
            rep.add("INFO", "internal-docs", rel(root, d),
                    "ADR directory exists but contains no records.", "")
            continue
        # stuck 'proposed' decisions
        for a in adrs:
            txt = read(a).lower()
            if re.search(r"status:\s*proposed", txt) or re.search(r"^\s*##?\s*status\s*\n+\s*proposed", txt, re.M):
                rep.add("INFO", "internal-docs", rel(root, a),
                        "ADR still marked 'proposed'.",
                        "Move stuck decisions to accepted/rejected.")


def check_codeowners(root: Path, rep: Report):
    for loc in [root / "CODEOWNERS", root / ".github" / "CODEOWNERS", root / "docs" / "CODEOWNERS"]:
        if loc.exists():
            return
    rep.add("INFO", "internal-docs", "-",
            "No CODEOWNERS file.",
            "Map doc/code paths to owners so review is auto-requested and "
            "ownership is documented.")


def check_docs_leaks(root: Path, rep: Report):
    docs = root / "docs"
    if not docs.exists():
        return
    internal_dir = docs / "internal"
    for dirpath, dirnames, filenames in os.walk(docs):
        rp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        # Skip an explicitly-internal subtree from leak scanning of *markers*,
        # but still flag if it looks publishable (no ignore rule check here —
        # the skill's reason pass inspects the site config).
        for f in filenames:
            if not f.lower().endswith((".md", ".mdx", ".rst")):
                continue
            p = rp / f
            txt = read(p)
            hits = [m for m in LEAK_MARKERS if re.search(m, txt)]
            if hits:
                under_internal = internal_dir in p.parents
                sev = "INFO" if under_internal else "WARN"
                where = "in docs/internal/ (verify it is excluded from publishing)" \
                    if under_internal else "in a publishable docs path"
                rep.add(sev, "external-docs", rel(root, p),
                        f"Internal marker(s) {sorted(set(hits))} {where}.",
                        "Ensure internal-tagged pages cannot reach the published "
                        "bundle (default-deny publishing + rendered-output CI diff).")
            for pat, label in SECRET_PATTERNS:
                if re.search(pat, txt):
                    rep.add("ERROR", "external-docs", rel(root, p),
                            f"Possible secret in docs ({label}).",
                            "Remove and rotate; docs examples are a common leak vector.")
                    break


def run_optional_tools(root: Path, readmes, rep: Report):
    # link checking
    if tool_available("lychee"):
        try:
            targets = [str(p) for p in readmes] + \
                      ([str(root / "docs")] if (root / "docs").exists() else [])
            res = subprocess.run(["lychee", "--no-progress", *targets],
                                 cwd=root, capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                rep.add("WARN", "links", "-",
                        "lychee reported broken link(s).",
                        "Run `lychee " + " ".join(targets) + "` to see them.")
        except Exception:
            rep.skipped_tools.append("lychee (errored)")
    else:
        rep.skipped_tools.append("lychee (link check) — not installed")

    # TOC drift
    if tool_available("doctoc"):
        for p in readmes:
            if "<!-- START doctoc" in read(p) or "<!-- toc -->" in read(p).lower():
                try:
                    res = subprocess.run(["doctoc", "--dryrun", str(p)],
                                         cwd=root, capture_output=True, text=True, timeout=30)
                    if "will be updated" in (res.stdout + res.stderr).lower():
                        rep.add("WARN", "root-readme" if p.parent == root else "nested-readme",
                                rel(root, p), "Table of Contents is out of sync.",
                                "Run `doctoc " + rel(root, p) + "`.")
                except Exception:
                    pass
    else:
        rep.skipped_tools.append("doctoc (TOC drift) — not installed")

    if not tool_available("markdownlint") and not tool_available("markdownlint-cli2"):
        rep.skipped_tools.append("markdownlint (format) — not installed")


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def scan(root: Path, args) -> Report:
    rep = Report(repo=str(root))

    license_exists = any((root / n).exists() for n in ("LICENSE", "LICENSE.md", "LICENSE.txt")) \
        or any((root / ".github" / n).exists() for n in ("LICENSE", "LICENSE.md"))

    linter_configs = sorted({p.name for g in LINTER_CONFIG_GLOBS
                             for p in root.glob(g)})

    claude_files = sorted(iter_files(root, "CLAUDE.md"))
    readme_files = sorted(iter_files(root, "README.md"))

    if not claude_files:
        rep.add("INFO", "root-claude", "-",
                "No CLAUDE.md found.",
                "If an AI agent works in this repo, add a lean CLAUDE.md of "
                "non-obvious commands/conventions/guardrails.")
    for p in claude_files:
        # ./.claude/CLAUDE.md is an official alternate project-root location
        check_claude_md(root, p,
                        is_root=(p.parent == root or p.parent == root / ".claude"),
                        rep=rep, linter_configs=linter_configs)

    launch_extras = []
    bridged_agents_lines = check_cross_tool_configs(root, rep, linter_configs)
    if bridged_agents_lines:
        launch_extras.append(("AGENTS.md (imported)", bridged_agents_lines))
    check_claude_local(root, rep)
    launch_extras += check_rules(root, rep, linter_configs)
    check_launch_budget(root, rep, launch_extras)

    if not any(p.parent == root for p in readme_files):
        rep.add("ERROR", "root-readme", "-", "No root README.md.",
                "Add one: title, description, install, usage, license.")
    for p in readme_files:
        check_readme(root, p, is_root=(p.parent == root), rep=rep,
                     license_exists=license_exists)

    check_nested_readme_coverage(root, rep)
    check_community_health(root, rep)
    check_adrs(root, rep)
    check_codeowners(root, rep)
    check_docs_leaks(root, rep)
    if not args.no_tools:
        run_optional_tools(root, readme_files, rep)

    return rep


def render(rep: Report) -> str:
    rep.findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.layer, f.file))
    n_err = sum(1 for f in rep.findings if f.severity == "ERROR")
    n_warn = sum(1 for f in rep.findings if f.severity == "WARN")
    n_info = sum(1 for f in rep.findings if f.severity == "INFO")

    out = []
    out.append(f"Documentation health — {rep.repo}")
    out.append("=" * 60)
    out.append(f"  {n_err} error(s)   {n_warn} warning(s)   {n_info} info")
    out.append("")

    if not rep.findings:
        out.append("  No deterministic findings. Run the skill's reason pass for "
                   "judgment checks (duplication, mode-mixing, stale commands).")
    icon = {"ERROR": "✗", "WARN": "!", "INFO": "·"}
    last_layer = None
    for f in rep.findings:
        if f.layer != last_layer:
            out.append(f"\n[{f.layer}]")
            last_layer = f.layer
        loc = f"" if f.file == "-" else f" ({f.file})"
        out.append(f"  {icon.get(f.severity,'?')} {f.severity}{loc}: {f.message}")
        if f.hint:
            out.append(f"      → {f.hint}")

    if rep.skipped_tools:
        out.append("\nSkipped external tools (install for deeper checks):")
        for t in rep.skipped_tools:
            out.append(f"  - {t}")
    out.append("")
    out.append("Deterministic scan only. Next: open the flagged files and run the "
               "judgment checks in reference.md (duplication, Diataxis mode-mixing,")
    out.append("stale commands/counts, README↔CLAUDE.md drift, cross-tool "
               "contradictions).")
    return "\n".join(out)


def main(argv=None):
    global CLAUDE_WARN_LINES, README_WARN_LINES
    ap = argparse.ArgumentParser(description="Documentation-health scanner")
    ap.add_argument("repo", nargs="?", default=".", help="Repo dir (default: cwd)")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any ERROR found")
    ap.add_argument("--no-tools", action="store_true",
                    help="Skip external tools (lychee/doctoc/markdownlint)")
    ap.add_argument("--claude-max", type=int, default=None,
                    help=f"CLAUDE.md warn line ceiling (default {CLAUDE_WARN_LINES})")
    ap.add_argument("--readme-max", type=int, default=None,
                    help=f"README warn line ceiling (default {README_WARN_LINES})")
    args = ap.parse_args(argv)

    if args.claude_max:
        CLAUDE_WARN_LINES = args.claude_max
    if args.readme_max:
        README_WARN_LINES = args.readme_max

    root = Path(args.repo).resolve()
    if not root.exists():
        print(f"error: {root} does not exist", file=sys.stderr)
        return 2

    rep = scan(root, args)

    if args.json:
        print(json.dumps({
            "repo": rep.repo,
            "findings": [asdict(f) for f in rep.findings],
            "skipped_tools": rep.skipped_tools,
        }, indent=2))
    else:
        print(render(rep))

    if args.strict and any(f.severity == "ERROR" for f in rep.findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
