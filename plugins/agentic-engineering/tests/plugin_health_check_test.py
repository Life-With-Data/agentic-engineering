"""Pure decision and cache tests for plugin-health-check.py; no sockets are opened."""
from __future__ import annotations

import importlib.util
import multiprocessing
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "plugin-health-check.py"
spec = importlib.util.spec_from_file_location("plugin_health_check", SCRIPT)
assert spec and spec.loader
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


def statuses(rows):
    return {row["check"]: row["status"] for row in rows}


def _concurrent_probe(cache_name, marker_name, start):
    start.wait()
    def io():
        with open(marker_name, "a", encoding="utf-8") as marker:
            marker.write("probe\n")
        time.sleep(0.15)
        return {"present": False}
    health._cached_rows(Path(cache_name), 60, io, time.time)


class EvaluateTest(unittest.TestCase):
    def test_absent_is_skip_and_silent(self):
        rows = health.evaluate({"present": False})
        self.assertEqual(rows[0]["status"], "SKIP")
        self.assertEqual(health.render(rows), "")

    def test_worker_unreachable_is_fail(self):
        rows = health.evaluate({"present": True, "worker": "unreachable"})
        self.assertEqual(statuses(rows)["claude-mem worker"], "FAIL")

    def test_worker_timeout_is_skip_and_other_results_continue(self):
        rows = health.evaluate({"present": True, "worker": "timeout", "auth": "401"})
        self.assertEqual(statuses(rows)["claude-mem worker"], "SKIP")
        self.assertEqual(statuses(rows)["claude-mem distillation"], "FAIL")

    def test_auth_401_is_fail(self):
        rows = health.evaluate({"present": True, "worker": "ok", "auth": "401"})
        self.assertEqual(statuses(rows)["claude-mem distillation"], "FAIL")

    def test_version_behind_is_warn(self):
        rows = health.evaluate({"present": True, "worker": "ok", "installed_version": "9.0.17", "latest_version": "13.10.2"})
        self.assertEqual(statuses(rows)["claude-mem version"], "WARN")

    def test_offline_latest_lookup_is_skip(self):
        rows = health.evaluate({"present": True, "worker": "ok", "latest_error": "offline"})
        version = next(row for row in rows if row["check"] == "claude-mem version")
        self.assertEqual(version["status"], "SKIP")
        self.assertIn("offline", version["detail"])

    def test_queue_and_freshness_warmup_are_skip(self):
        rows = health.evaluate({"present": True, "worker": "ok", "queue": {"warmup": True}, "freshness": {"warmup": True}})
        result = statuses(rows)
        self.assertEqual(result["claude-mem queue"], "SKIP")
        self.assertEqual(result["claude-mem freshness"], "SKIP")

    def test_fresh_healthy_install_is_silent(self):
        rows = health.evaluate({"present": True, "worker": "ok", "auth": "ok", "installed_version": "13.0.0", "latest_version": "13.10.2", "queue": {"warmup": True}, "freshness": {"warmup": True}})
        self.assertEqual(health.render(rows), "")


class CacheTest(unittest.TestCase):
    def test_corrupt_and_clock_skewed_cache_reprobe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text("not json", encoding="utf-8")
            self.assertIsNone(health._read_cache(path, 100, 10))
            health._write_cache(path, [health.finding("x", "PASS", "ok")], 200)
            self.assertIsNone(health._read_cache(path, 100, 10))

    def test_parseable_malformed_cache_is_reprobed_and_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text('{"timestamp": 100, "rows": [{"check": "x", "status": "WARN", "detail": "bad", "fix": 3}]}', encoding="utf-8")
            calls = []
            rows = health._cached_rows(path, 60, lambda: calls.append(True) or {"present": False}, lambda: 100)
            self.assertEqual(calls, [True])
            self.assertEqual(rows[0]["status"], "SKIP")
            self.assertEqual(health._read_cache(path, 100, 60), rows)

    def test_cache_miss_is_probed_once_across_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = str(Path(tmp) / "cache.json")
            marker = str(Path(tmp) / "probes")
            context = multiprocessing.get_context("fork")
            start = context.Event()
            processes = [context.Process(target=_concurrent_probe, args=(cache, marker, start)) for _ in range(2)]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(5)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(Path(marker).read_text(encoding="utf-8").splitlines(), ["probe"])

    def test_cached_warning_is_rendered_every_session(self):
        rows = [health.finding("x", "WARN", "still bad", "fix it")]
        self.assertIn("still bad", health.render(rows))


class RuntimeSafetyTest(unittest.TestCase):
    def test_invalid_port_skips_without_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude" / "plugins" / "claude-mem").mkdir(parents=True)
            with patch.object(health.pathlib.Path, "home", return_value=root), patch.object(health, "_request") as request, patch.dict(os.environ, {"CLAUDE_MEM_PORT": "1/evil"}, clear=False):
                data = health.collect()
            request.assert_not_called()
            self.assertEqual(data["worker"], "unknown")

    def test_nested_cwd_reads_untracked_root_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            nested = root / "nested" / "path"
            nested.mkdir(parents=True)
            (root / "agentic-engineering.local.md").write_text("---\nplugin_health_enabled: false\n---\n", encoding="utf-8")
            enabled, _, _ = health._config(str(nested))
            self.assertFalse(enabled)


if __name__ == "__main__":
    unittest.main()
