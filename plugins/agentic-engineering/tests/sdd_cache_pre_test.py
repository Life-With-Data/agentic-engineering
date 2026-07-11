"""Regression tests for ``scripts/sdd-cache-pre.py``.

This PreToolUse/WebFetch hook is an opt-in doc cache. Its load-bearing property
is that a cached entry is served back to the agent (exit 2, Claude Code deny)
*only* when the origin confirms the page is unchanged with an HTTP ``304`` — any
other outcome (a changed page = ``200``, an error, a timeout, a missing
validator) must let the real WebFetch proceed (exit 0). It must also be inert
unless ``AGENTIC_SDD_CACHE=1`` and fail-open on any error.

Offline only: the single network call (the conditional-HEAD revalidation) is
either short-circuited by an early-return branch or mocked out. No test performs
real network I/O.

Contract: exit 2 serves the cache and blocks the fetch; exit 0 lets it proceed.

Run with: ``python3 -m unittest tests.sdd_cache_pre_test``.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sdd-cache-pre.py"

_spec = importlib.util.spec_from_file_location("sdd_cache_pre", SCRIPT)
assert _spec is not None and _spec.loader is not None
pre = importlib.util.module_from_spec(_spec)
sys.modules["sdd_cache_pre"] = pre
_spec.loader.exec_module(pre)

ALLOW = 0
BLOCK = 2
URL = "https://docs.example.com/guide"


def _run(payload: str, *, opted_in: bool, project_dir: str) -> subprocess.CompletedProcess[str]:
    """Drive the real script as a subprocess. Only used for branches that
    return before the network call, so it stays offline."""
    env = {k: v for k, v in os.environ.items() if k != "AGENTIC_SDD_CACHE"}
    env["CLAUDE_PROJECT_DIR"] = project_dir
    if opted_in:
        env["AGENTIC_SDD_CACHE"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


def _webfetch(url: str = URL) -> str:
    return json.dumps({"tool_name": "WebFetch", "tool_input": {"url": url}})


def _write_entry(project_dir: str, url: str, **fields: object) -> Path:
    cache_dir = Path(project_dir) / ".claude" / "sdd-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "url": url,
        "prompt": "",
        "etag": "",
        "last_modified": "",
        "content": "",
        "fetched_at": 0,
    }
    entry.update(fields)
    path = cache_dir / f"{pre._cache_key(url)}.json"
    path.write_text(json.dumps(entry), encoding="utf-8")
    return path


class OptInGateTest(unittest.TestCase):
    """Inert by default; a valid cached entry is ignored unless opted in."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # An entry that WOULD be a hit — proves the gate, not a miss, keeps it quiet.
        _write_entry(self._tmp.name, URL, etag='"v1"', content="cached body")

    def test_opt_out_is_inert_even_with_a_hittable_entry(self) -> None:
        result = _run(_webfetch(), opted_in=False, project_dir=self._tmp.name)
        self.assertEqual(result.returncode, ALLOW)
        self.assertEqual(result.stderr, "")

    def test_opt_out_never_touches_the_network(self) -> None:
        # Sanity: opted out returns before any revalidation could run.
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self._tmp.name}, clear=False), \
                mock.patch.object(pre, "_revalidation_status") as revalidate, \
                mock.patch.object(sys, "stdin", io.StringIO(_webfetch())):
            os.environ.pop("AGENTIC_SDD_CACHE", None)
            self.assertEqual(pre.main(), ALLOW)
        revalidate.assert_not_called()


class OfflineEarlyReturnTest(unittest.TestCase):
    """Every branch here returns ALLOW before the network call — safe as a
    subprocess with the real entry point."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_malformed_stdin_fails_open(self) -> None:
        self.assertEqual(_run("not json", opted_in=True, project_dir=self._tmp.name).returncode, ALLOW)

    def test_non_webfetch_tool_is_ignored(self) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(_run(payload, opted_in=True, project_dir=self._tmp.name).returncode, ALLOW)

    def test_missing_url_is_ignored(self) -> None:
        payload = json.dumps({"tool_name": "WebFetch", "tool_input": {}})
        self.assertEqual(_run(payload, opted_in=True, project_dir=self._tmp.name).returncode, ALLOW)

    def test_non_http_scheme_is_ignored(self) -> None:
        payload = _webfetch("file:///etc/passwd")
        self.assertEqual(_run(payload, opted_in=True, project_dir=self._tmp.name).returncode, ALLOW)

    def test_no_cache_file_proceeds(self) -> None:
        # Empty project dir → no entry → nothing to serve.
        self.assertEqual(_run(_webfetch(), opted_in=True, project_dir=self._tmp.name).returncode, ALLOW)

    def test_entry_without_validator_never_revalidates(self) -> None:
        _write_entry(self._tmp.name, URL, etag="", last_modified="", content="body")
        self.assertEqual(_run(_webfetch(), opted_in=True, project_dir=self._tmp.name).returncode, ALLOW)


class RevalidationTest(unittest.TestCase):
    """The 304-only property, with the network call mocked."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _call(self, status: object, entry_fields: dict) -> "tuple[int, str]":
        _write_entry(self._tmp.name, URL, **entry_fields)
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"AGENTIC_SDD_CACHE": "1", "CLAUDE_PROJECT_DIR": self._tmp.name}), \
                mock.patch.object(pre, "_revalidation_status", return_value=status), \
                mock.patch.object(sys, "stdin", io.StringIO(_webfetch())), \
                mock.patch.object(sys, "stderr", stderr):
            rc = pre.main()
        return rc, stderr.getvalue()

    def test_304_serves_cache_and_blocks(self) -> None:
        rc, err = self._call(304, {"etag": '"v1"', "content": "the cached reading", "prompt": "extract signature"})
        self.assertEqual(rc, BLOCK)
        self.assertIn("[sdd-cache] Cache hit", err)
        self.assertIn("the cached reading", err)
        self.assertIn("extract signature", err)  # original prompt surfaced

    def test_200_means_changed_and_proceeds(self) -> None:
        # The safety-critical path: origin says the page changed → never serve stale.
        rc, err = self._call(200, {"etag": '"v1"', "content": "STALE — must not be served"})
        self.assertEqual(rc, ALLOW)
        self.assertEqual(err, "")

    def test_network_failure_proceeds(self) -> None:
        # _revalidation_status returns None on any network error → fetch proceeds.
        rc, _ = self._call(None, {"last_modified": "Wed, 01 Jul 2026 00:00:00 GMT", "content": "body"})
        self.assertEqual(rc, ALLOW)

    def test_304_but_empty_content_proceeds(self) -> None:
        rc, _ = self._call(304, {"etag": '"v1"', "content": ""})
        self.assertEqual(rc, ALLOW)

    def test_no_validator_short_circuits_before_network(self) -> None:
        _write_entry(self._tmp.name, URL, etag="", last_modified="", content="body")
        with mock.patch.dict(os.environ, {"AGENTIC_SDD_CACHE": "1", "CLAUDE_PROJECT_DIR": self._tmp.name}), \
                mock.patch.object(pre, "_revalidation_status") as revalidate, \
                mock.patch.object(sys, "stdin", io.StringIO(_webfetch())):
            self.assertEqual(pre.main(), ALLOW)
        revalidate.assert_not_called()

    def test_revalidation_raising_fails_open(self) -> None:
        _write_entry(self._tmp.name, URL, etag='"v1"', content="body")
        with mock.patch.dict(os.environ, {"AGENTIC_SDD_CACHE": "1", "CLAUDE_PROJECT_DIR": self._tmp.name}), \
                mock.patch.object(pre, "_revalidation_status", side_effect=RuntimeError("boom")), \
                mock.patch.object(sys, "stdin", io.StringIO(_webfetch())):
            self.assertEqual(pre.main(), ALLOW)  # outer try/except → fail open


class HelperTest(unittest.TestCase):
    def test_cache_key_is_deterministic_32_hex(self) -> None:
        key = pre._cache_key(URL)
        self.assertEqual(len(key), 32)
        self.assertTrue(all(c in "0123456789abcdef" for c in key))
        self.assertEqual(key, pre._cache_key(URL))

    def test_iso_handles_bad_epoch(self) -> None:
        self.assertEqual(pre._iso("not-a-number"), "unknown")
        self.assertRegex(pre._iso(0), r"^1970-01-01T00:00:00Z$")


if __name__ == "__main__":
    unittest.main()
