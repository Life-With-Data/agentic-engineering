#!/usr/bin/env python3
"""Advisory SessionStart health checks for separately-installed plugin assets.

All decisions live in :func:`evaluate`; runtime I/O is isolated in ``collect``
so tests can exercise every outcome without opening sockets.  Unknown external
claude-mem surfaces deliberately degrade to SKIP, never a false alarm.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any, Callable

STATUSES = {"PASS", "WARN", "FAIL", "SKIP"}
DEFAULT_TTL = 900


def finding(check: str, status: str, detail: str, fix: str = "") -> dict[str, str]:
    assert status in STATUSES
    if status in {"WARN", "FAIL"}:
        assert fix
    return {"check": check, "status": status, "detail": detail, "fix": fix}


def major(version: str | None) -> int | None:
    try:
        return int((version or "").lstrip("v").split(".", 1)[0])
    except ValueError:
        return None


def evaluate(data: dict[str, Any]) -> list[dict[str, str]]:
    """Pure claude-mem decision table. ``data`` is supplied by the I/O layer."""
    if not data.get("present"):
        return [finding("claude-mem presence", "SKIP", "claude-mem is not installed")]
    rows: list[dict[str, str]] = []
    worker = data.get("worker", "unknown")
    if worker == "unreachable":
        rows.append(finding("claude-mem worker", "FAIL", "worker port is unreachable", "restart the claude-mem worker; check for a stale PID holding its port"))
    elif worker == "ok":
        rows.append(finding("claude-mem worker", "PASS", "worker health endpoint returned 200"))
    else:
        rows.append(finding("claude-mem worker", "SKIP", "worker probe timed out" if worker == "timeout" else "worker state is unavailable"))
    if data.get("auth") == "401":
        rows.append(finding("claude-mem distillation", "FAIL", "recent model calls returned 401 authentication errors", "re-authenticate the model provider"))
    else:
        rows.append(finding("claude-mem distillation", "PASS" if data.get("auth") == "ok" else "SKIP", "no authentication errors detected" if data.get("auth") == "ok" else "auth error state is unavailable"))
    latest = data.get("latest_version")
    installed = data.get("installed_version")
    if data.get("latest_error") or not latest:
        rows.append(finding("claude-mem version", "SKIP", "latest-version lookup unavailable" + (": " + str(data.get("latest_error")) if data.get("latest_error") else "")))
    elif major(installed) is not None and major(latest) is not None and major(installed) < major(latest):
        rows.append(finding("claude-mem version", "WARN", f"installed {installed}; latest {latest}", "claude plugin update claude-mem"))
    else:
        rows.append(finding("claude-mem version", "PASS", "installed version is current"))
    queue = data.get("queue")
    if queue is None:
        rows.append(finding("claude-mem queue", "SKIP", "queue baseline is unavailable"))
    elif queue.get("warmup", False):
        rows.append(finding("claude-mem queue", "SKIP", "queue is in warmup"))
    elif queue.get("failed", 0) > 0 or queue.get("stuck_processing", 0) > 0:
        rows.append(finding("claude-mem queue", "WARN", "failed or stuck processing observations are backlogged", "drain or retry the claude-mem queue"))
    else:
        rows.append(finding("claude-mem queue", "PASS", "no backed-up observations"))
    fresh = data.get("freshness")
    if not fresh or fresh.get("warmup", False) or not fresh.get("activity"):
        rows.append(finding("claude-mem freshness", "SKIP", "no reliable activity and history baseline yet"))
    elif fresh.get("new_observations", 0) == 0:
        rows.append(finding("claude-mem freshness", "WARN", "no new observations despite recent session activity", "investigate distillation; check authentication, version, and queue findings"))
    else:
        rows.append(finding("claude-mem freshness", "PASS", "recent observations are being distilled"))
    return rows


def _request(url: str, timeout: float = 0.7) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310 -- local health URL only
            return response.status, response.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096).decode("utf-8", "replace")
    except TimeoutError:
        return None, "timeout"
    except Exception:
        return None, ""


def collect() -> dict[str, Any]:
    """Best-effort real probes; undocumented claude-mem APIs remain SKIP."""
    plugin_root = pathlib.Path.home() / ".claude" / "plugins"
    present = plugin_root.exists() and any("claude-mem" in str(p).lower() for p in plugin_root.glob("**/*claude-mem*"))
    if not present:
        return {"present": False}
    try:
        port_number = int(os.environ.get("CLAUDE_MEM_PORT", "37777"))
        if not 1 <= port_number <= 65535:
            raise ValueError
    except ValueError:
        return {"present": True, "worker": "unknown", "auth": "unknown", "latest_error": "no stable claude-mem latest-version endpoint", "queue": None, "freshness": None}
    port = str(port_number)
    status, body = _request(f"http://127.0.0.1:{port}/api/health")
    worker = "ok" if status == 200 else ("timeout" if body == "timeout" else "unreachable")
    # The plugin's authenticated failure is visible in the health response on supported versions.
    auth = "401" if "401" in body or "invalid authentication" in body.lower() else "unknown"
    return {"present": True, "worker": worker, "auth": auth, "latest_error": "no stable claude-mem latest-version endpoint", "queue": None, "freshness": None}


def _duration(value: str) -> int:
    value = value.strip().lower()
    if re.fullmatch(r"[1-9][0-9]*(?:[smhd])?", value) is None:
        raise ValueError("duration must be positive seconds or use an s/m/h/d suffix")
    factor = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(value[-1:], 1)
    return int(value[:-1] if value[-1:] in "smhd" else value) * factor


def _enabled(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError("plugin_health_enabled must be a boolean")
    return normalized == "true"


def _config(cwd: str) -> tuple[bool, int, bool]:
    """Read untracked local frontmatter only; malformed config falls back safely."""
    try:
        script_dir = pathlib.Path(__file__).resolve().parent
        sys.path.insert(0, str(script_dir))
        import lifecycle_board  # type: ignore
        resolved = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        root = pathlib.Path(resolved.stdout.strip()) if resolved.returncode == 0 else pathlib.Path(cwd)
        local = root / lifecycle_board.LOCAL_CONFIG
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", local.name], capture_output=True).returncode == 0
        if tracked or not local.is_file():
            return True, DEFAULT_TTL, True
        meta = lifecycle_board.parse_frontmatter(local.read_text(encoding="utf-8"))
        try:
            enabled = _enabled(meta.get("plugin_health_enabled", "true"))
        except ValueError:
            enabled = True
        assets = meta.get("plugin_health_assets", "claude-mem")
        ttl_raw = meta.get("plugin_health_ttl", "15m")
        try:
            ttl = _duration(ttl_raw)
        except ValueError:
            ttl = DEFAULT_TTL
        return enabled, ttl, "claude-mem" in assets.lower()
    except Exception:
        return True, DEFAULT_TTL, True


def _cache_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache")) / "agentic-engineering" / "plugin-health" / "claude-mem.json"


def _read_cache(path: pathlib.Path, now: float, ttl: int) -> list[dict[str, str]] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        timestamp = float(raw["timestamp"])
        rows = raw["rows"]
        if timestamp > now or now - timestamp > ttl or not isinstance(rows, list) or not all(_valid_finding(row) for row in rows):
            return None
        return rows
    except Exception:
        return None


def _valid_finding(row: Any) -> bool:
    if not isinstance(row, dict) or set(row) != {"check", "status", "detail", "fix"}:
        return False
    if not all(isinstance(row[key], str) for key in row):
        return False
    return row["status"] in STATUSES and (row["status"] not in {"WARN", "FAIL"} or bool(row["fix"]))


def _write_cache(path: pathlib.Path, rows: list[dict[str, str]], now: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"timestamp": now, "rows": rows}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _cache_lock(path: pathlib.Path, timeout: float = 1.0):
    """Best-effort interprocess lock. Failure to lock is advisory-only, never fatal."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")
    acquired = False
    try:
        try:
            import fcntl
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.02)
        except Exception:
            acquired = False
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        handle.close()


def _cached_rows(path: pathlib.Path, ttl: int, io: Callable[[], dict[str, Any]], clock: Callable[[], float]) -> list[dict[str, str]] | None:
    """Serialize cache miss handling so concurrent startups do one live probe."""
    now = clock()
    rows = _read_cache(path, now, ttl)
    if rows is not None:
        return rows
    with _cache_lock(path) as acquired:
        if not acquired:
            return _read_cache(path, clock(), ttl)
        now = clock()
        rows = _read_cache(path, now, ttl)
        if rows is None:
            rows = evaluate(io())
            _write_cache(path, rows, now)
        return rows


def render(rows: list[dict[str, str]]) -> str:
    bad = [row for row in rows if row["status"] in {"WARN", "FAIL"}]
    if not bad:
        return ""
    text = "Plugin health check:\n" + "\n".join(f"- {r['status']}: {r['detail']}. Fix: {r['fix']}" for r in bad)
    if len(bad) > 1 or any(not r["fix"] for r in bad):
        text += "\nFor a broader diagnosis, run `lifecycle-doctor`."
    return text


def _emit(note: str) -> None:
    if note:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}}))


def main(cwd: str | None = None, io: Callable[[], dict[str, Any]] = collect, clock: Callable[[], float] = time.time) -> int:
    try:
        if cwd is None:
            payload = json.loads(sys.stdin.read() or "{}")
            cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        enabled, ttl, selected = _config(cwd)
        if not enabled or not selected:
            return 0
        rows = _cached_rows(_cache_path(), ttl, io, clock)
        if rows is not None:
            _emit(render(rows))
    except Exception:
        # A SessionStart adviser must never block startup.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
