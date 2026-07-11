#!/usr/bin/env python3
"""
PreToolUse (WebFetch) — OPT-IN, revalidating doc cache. Serves a previously
fetched page back to the agent ONLY when the origin confirms it is unchanged
(HTTP 304), so the "verify against current docs" guarantee is never weakened.

Adapted from addyosmani/agent-skills `hooks/sdd-cache-pre.sh` (bash+jq+curl),
ported to python3 stdlib (urllib/hashlib/json) to match this plugin's hooks.

Opt-in posture (inert by default): does nothing unless the environment sets
``AGENTIC_SDD_CACHE=1``. This mirrors the v3.7.0 opt-in precedent
(nudge-todowrite-to-tracker.py) — off by default, explicit signal to enable —
but uses an env var rather than a committed frontmatter flag: caching is a
per-machine choice, an env var can never ride a PR to flip behaviour for every
clone, and it stays out of the ``agentic-engineering.local.md`` config surface.

Mechanism (preserved exactly from upstream):
  - Cache key is sha256(url) truncated to 32 hex chars, under
    ``$CLAUDE_PROJECT_DIR/.claude/sdd-cache/<key>.json``.
  - If a cached entry carries an ETag or Last-Modified validator, send a
    conditional HEAD (If-None-Match / If-Modified-Since, 5s timeout, follows
    redirects) to THAT SAME URL. On HTTP 304 the origin confirms the content is
    unchanged: emit the cached body on stderr and block the fetch (exit 2 —
    Claude Code deny semantics, same as block-no-verify.py). On anything else
    (200, error, timeout, no validator, no entry) let the fetch proceed.
  - No TTL: content is served only on a real 304 revalidation, never from a
    time window. If validators can't catch a change, nothing here will.

Fail-open contract: ANY error (bad stdin, unreadable cache, network failure)
results in exit 0 so a broken cache can never block a legitimate WebFetch.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV_FLAG = "AGENTIC_SDD_CACHE"
ALLOW = 0
BLOCK = 2  # Claude Code PreToolUse deny: stderr is delivered to the agent.
HEAD_TIMEOUT = 5


def _opted_in() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def _cache_dir() -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return os.path.join(root, ".claude", "sdd-cache")


def _cache_key(url: str) -> str:
    # MUST match sdd-cache-post.py: sha256(url), first 32 hex chars.
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _revalidation_status(url: str, etag: str, last_mod: str) -> "int | None":
    """Conditional HEAD to the same URL. Returns the HTTP status (304 on a
    confirmed hit) or None if the request could not be completed."""
    req = urllib.request.Request(url, method="HEAD")
    if etag:
        req.add_header("If-None-Match", etag)
    if last_mod:
        req.add_header("If-Modified-Since", last_mod)
    try:
        with urllib.request.urlopen(req, timeout=HEAD_TIMEOUT) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        # urllib raises HTTPError for 304 (it is not a redirect it follows).
        return exc.code
    except Exception:
        return None


def _iso(epoch: object) -> str:
    try:
        return datetime.datetime.fromtimestamp(
            float(epoch), tz=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError, OverflowError):
        return "unknown"


def _hit_message(url: str, prompt: str, verified_at: str, content: str) -> str:
    lines = [
        f"[sdd-cache] Cache hit for {url}",
        "",
        f"Revalidated via HTTP 304; unchanged since {verified_at}. Use the",
        "cached content below as if WebFetch had just returned it.",
        "",
    ]
    if prompt:
        lines += [
            f'Original WebFetch prompt: "{prompt}". If your angle differs,',
            "judge whether this reading still covers it.",
            "",
        ]
    lines += [
        "----- BEGIN CACHED CONTENT -----",
        content,
        "----- END CACHED CONTENT -----",
    ]
    return "\n".join(lines)


def _main() -> int:
    if not _opted_in():
        return ALLOW

    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return ALLOW
    if not isinstance(payload, dict):
        return ALLOW
    if payload.get("tool_name") != "WebFetch":
        return ALLOW

    tool_input = payload.get("tool_input") or {}
    url = tool_input.get("url") if isinstance(tool_input, dict) else None
    if not url or not isinstance(url, str):
        return ALLOW

    # Only http(s) — never hand a file://, ftp://, etc. URL to urllib.
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return ALLOW

    cache_file = os.path.join(_cache_dir(), _cache_key(url) + ".json")
    if not os.path.isfile(cache_file):
        return ALLOW

    try:
        with open(cache_file, encoding="utf-8") as fh:
            entry = json.load(fh)
    except (ValueError, OSError):
        return ALLOW
    if not isinstance(entry, dict):
        return ALLOW

    etag = (entry.get("etag") or "").strip()
    last_mod = (entry.get("last_modified") or "").strip()
    # No validator means freshness can't be verified — never serve from cache.
    if not etag and not last_mod:
        return ALLOW

    if _revalidation_status(url, etag, last_mod) != 304:
        return ALLOW

    content = entry.get("content") or ""
    if not content:
        return ALLOW

    message = _hit_message(
        url=url,
        prompt=(entry.get("prompt") or "").strip(),
        verified_at=_iso(entry.get("fetched_at", 0)),
        content=content,
    )
    sys.stderr.write(message + "\n")
    return BLOCK


def main() -> int:
    # Fail-open: a cache hit legitimately returns BLOCK (2); only an unexpected
    # error falls through to ALLOW (0) so the cache can never block a fetch.
    try:
        return _main()
    except Exception:
        return ALLOW


if __name__ == "__main__":
    sys.exit(main())
