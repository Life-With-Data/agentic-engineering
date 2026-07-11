#!/usr/bin/env python3
"""
PostToolUse (WebFetch) — OPT-IN. Records a fetched page under
``$CLAUDE_PROJECT_DIR/.claude/sdd-cache/<key>.json`` together with the origin's
current ETag / Last-Modified validators, so sdd-cache-pre.py can revalidate it
on the next fetch and serve it only on a real HTTP 304.

Adapted from addyosmani/agent-skills `hooks/sdd-cache-post.sh` (bash+jq+curl),
ported to python3 stdlib (urllib/hashlib/json) to match this plugin's hooks.

Opt-in posture (inert by default): does nothing unless ``AGENTIC_SDD_CACHE=1``
is set — same gate as sdd-cache-pre.py (see that file for the rationale).

Mechanism (preserved exactly from upstream):
  - Extract the response body from ``tool_response`` (object → .result, with
    .output/.text/.content/.body as defensive fallbacks; or a bare string).
  - HEAD the URL (5s timeout, follows redirects) and read ETag / Last-Modified
    from the FINAL redirect hop — urllib exposes the resolved response's
    headers directly, so no redirect-chain header parsing is needed.
  - No validator → the entry can never be revalidated, so remove any stale copy
    and store nothing (caching without a validator would be trusting memory).
  - With a validator, write ``{url, prompt, etag, last_modified, content,
    fetched_at}`` atomically (temp file + os.replace).

Never blocks: PostToolUse runs after the tool; this hook always exits 0.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENV_FLAG = "AGENTIC_SDD_CACHE"
HEAD_TIMEOUT = 5


def _opted_in() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def _cache_dir() -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return os.path.join(root, ".claude", "sdd-cache")


def _cache_key(url: str) -> str:
    # MUST match sdd-cache-pre.py: sha256(url), first 32 hex chars.
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _extract_content(tool_response: object) -> str:
    """WebFetch tool_response is an object whose body lives at .result (Claude
    Code as of 2026-04); the other keys are defensive fallbacks. A bare string
    handles older/custom integrations."""
    if isinstance(tool_response, dict):
        for key in ("result", "output", "text", "content", "body"):
            value = tool_response.get(key)
            if isinstance(value, str) and value:
                return value
        return ""
    if isinstance(tool_response, str):
        return tool_response
    return ""


def _final_validators(url: str) -> "tuple[str, str]":
    """HEAD the URL and return (etag, last_modified) from the resolved (final
    redirect hop) response. Empty strings if unavailable."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=HEAD_TIMEOUT) as resp:
            headers = resp.headers
    except urllib.error.HTTPError as exc:
        # A non-2xx response still carries headers (e.g. a 405 to HEAD); read
        # whatever validators it exposes rather than discarding them.
        headers = exc.headers
    except Exception:
        return "", ""
    etag = (headers.get("ETag") or "").strip()
    last_mod = (headers.get("Last-Modified") or "").strip()
    return etag, last_mod


def _atomic_write(cache_file: str, obj: dict) -> None:
    tmp = f"{cache_file}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        os.replace(tmp, cache_file)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _main() -> int:
    if not _opted_in():
        return 0

    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "WebFetch":
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    url = tool_input.get("url")
    if not url or not isinstance(url, str):
        return 0
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return 0
    prompt = tool_input.get("prompt") or ""
    if not isinstance(prompt, str):
        prompt = ""

    content = _extract_content(payload.get("tool_response"))
    if not content:
        return 0

    cache_dir = _cache_dir()
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError:
        return 0
    cache_file = os.path.join(cache_dir, _cache_key(url) + ".json")

    etag, last_mod = _final_validators(url)
    if not etag and not last_mod:
        # Can't revalidate later — drop any stale entry and cache nothing.
        try:
            os.remove(cache_file)
        except OSError:
            pass
        return 0

    _atomic_write(
        cache_file,
        {
            "url": url,
            "prompt": prompt,
            "etag": etag,
            "last_modified": last_mod,
            "content": content,
            "fetched_at": int(time.time()),
        },
    )
    return 0


def main() -> int:
    # Never blocks and never raises: a broken cache write must not disrupt the
    # session after WebFetch has already run.
    try:
        return _main()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
