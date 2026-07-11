"""Regression tests for ``scripts/sdd-cache-post.py``.

This PostToolUse/WebFetch hook records a fetched page plus the origin's current
ETag / Last-Modified so ``sdd-cache-pre.py`` can revalidate it later. It must be
inert unless ``AGENTIC_SDD_CACHE=1``; it must only cache when a validator exists
(otherwise the entry could never be revalidated, so a stale copy is removed
instead); and it must never raise (it runs after the tool has already executed).

Offline only: the validator-capturing HEAD is mocked. No test performs real
network I/O. It also pins the cross-hook invariant that pre and post derive the
*same* cache key for a URL — a divergence would silently disable every hit.

Run with: ``python3 -m unittest tests.sdd_cache_post_test``.
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

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sdd-cache-post.py"

_spec = importlib.util.spec_from_file_location("sdd_cache_post", SCRIPT)
assert _spec is not None and _spec.loader is not None
post = importlib.util.module_from_spec(_spec)
sys.modules["sdd_cache_post"] = post
_spec.loader.exec_module(post)

# Import the pre hook too, to pin the shared cache-key invariant.
_PRE = SCRIPT.parent.parent / "scripts" / "sdd-cache-pre.py"
_pre_spec = importlib.util.spec_from_file_location("sdd_cache_pre_forkey", _PRE)
assert _pre_spec is not None and _pre_spec.loader is not None
pre = importlib.util.module_from_spec(_pre_spec)
_pre_spec.loader.exec_module(pre)

URL = "https://docs.example.com/guide"


def _payload(tool_response: object, url: str = URL, prompt: str = "extract the signature") -> str:
    return json.dumps(
        {"tool_name": "WebFetch", "tool_input": {"url": url, "prompt": prompt}, "tool_response": tool_response}
    )


def _entry_path(project_dir: str, url: str = URL) -> Path:
    return Path(project_dir) / ".claude" / "sdd-cache" / f"{post._cache_key(url)}.json"


def _run_main(project_dir: str, payload: str, validators: "tuple[str, str]") -> int:
    with mock.patch.dict(os.environ, {"AGENTIC_SDD_CACHE": "1", "CLAUDE_PROJECT_DIR": project_dir}), \
            mock.patch.object(post, "_final_validators", return_value=validators), \
            mock.patch.object(sys, "stdin", io.StringIO(payload)):
        return post.main()


class OptInGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_opt_out_writes_nothing(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "AGENTIC_SDD_CACHE"}
        env["CLAUDE_PROJECT_DIR"] = self._tmp.name
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=_payload({"result": "body"}),
            capture_output=True, text=True, timeout=10, env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(_entry_path(self._tmp.name).exists())

    def test_opt_out_never_touches_network(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self._tmp.name}, clear=False), \
                mock.patch.object(post, "_final_validators") as head, \
                mock.patch.object(sys, "stdin", io.StringIO(_payload({"result": "b"}))):
            os.environ.pop("AGENTIC_SDD_CACHE", None)
            self.assertEqual(post.main(), 0)
        head.assert_not_called()


class WriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_writes_entry_with_validator(self) -> None:
        rc = _run_main(self._tmp.name, _payload({"result": "the reading"}), ('"abc"', "Wed, 01 Jul 2026 00:00:00 GMT"))
        self.assertEqual(rc, 0)
        entry = json.loads(_entry_path(self._tmp.name).read_text())
        self.assertEqual(entry["url"], URL)
        self.assertEqual(entry["prompt"], "extract the signature")
        self.assertEqual(entry["etag"], '"abc"')
        self.assertEqual(entry["last_modified"], "Wed, 01 Jul 2026 00:00:00 GMT")
        self.assertEqual(entry["content"], "the reading")
        self.assertIsInstance(entry["fetched_at"], int)

    def test_last_modified_only_is_enough_to_cache(self) -> None:
        rc = _run_main(self._tmp.name, _payload({"result": "body"}), ("", "Wed, 01 Jul 2026 00:00:00 GMT"))
        self.assertEqual(rc, 0)
        self.assertTrue(_entry_path(self._tmp.name).exists())

    def test_no_validator_writes_nothing_and_removes_stale(self) -> None:
        # Pre-seed a stale entry; a validator-less refetch must delete it.
        path = _entry_path(self._tmp.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"url": URL, "etag": '"old"', "content": "stale"}), encoding="utf-8")
        rc = _run_main(self._tmp.name, _payload({"result": "body"}), ("", ""))
        self.assertEqual(rc, 0)
        self.assertFalse(path.exists())

    def test_atomic_write_leaves_no_tmp_files(self) -> None:
        _run_main(self._tmp.name, _payload({"result": "body"}), ('"e"', ""))
        cache_dir = _entry_path(self._tmp.name).parent
        tmp_leftovers = [p for p in cache_dir.iterdir() if ".tmp" in p.name]
        self.assertEqual(tmp_leftovers, [])


class ContentExtractionTest(unittest.TestCase):
    def test_prefers_result_key(self) -> None:
        self.assertEqual(post._extract_content({"result": "R", "output": "O"}), "R")

    def test_falls_back_through_known_keys(self) -> None:
        self.assertEqual(post._extract_content({"body": "B"}), "B")

    def test_bare_string_response(self) -> None:
        self.assertEqual(post._extract_content("just text"), "just text")

    def test_unknown_shape_yields_empty(self) -> None:
        self.assertEqual(post._extract_content(42), "")
        self.assertEqual(post._extract_content(None), "")
        self.assertEqual(post._extract_content({"nope": "x"}), "")

    def test_empty_content_skips_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = _run_main(tmp, _payload({"result": ""}), ('"e"', ""))
            self.assertEqual(rc, 0)
            self.assertFalse(_entry_path(tmp).exists())


class RobustnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_non_webfetch_ignored(self) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": "x"})
        self.assertEqual(_run_main(self._tmp.name, payload, ('"e"', "")), 0)
        self.assertFalse(_entry_path(self._tmp.name).exists())

    def test_non_http_scheme_ignored(self) -> None:
        self.assertEqual(_run_main(self._tmp.name, _payload({"result": "b"}, url="ftp://x/y"), ('"e"', "")), 0)

    def test_malformed_stdin_fails_open(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "AGENTIC_SDD_CACHE"}
        env["AGENTIC_SDD_CACHE"] = "1"
        env["CLAUDE_PROJECT_DIR"] = self._tmp.name
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], input="not json",
            capture_output=True, text=True, timeout=10, env=env,
        )
        self.assertEqual(result.returncode, 0)


class SharedKeyInvariantTest(unittest.TestCase):
    """pre and post MUST derive the same cache key or every hit silently misses."""

    def test_keys_match_across_hooks(self) -> None:
        for url in (URL, "https://a.b/c?d=e#f", "http://x/y"):
            self.assertEqual(post._cache_key(url), pre._cache_key(url))


if __name__ == "__main__":
    unittest.main()
