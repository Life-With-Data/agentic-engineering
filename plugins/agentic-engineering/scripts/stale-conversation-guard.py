#!/usr/bin/env python3
"""UserPromptSubmit hook: pause a conversation that has gone cold.

Anthropic's prompt cache expires a few minutes after the last turn. Picking a
long-idle conversation back up re-sends the whole context uncached — the same
tokens you already paid to cache, billed again at full write price. That is
rarely what you want after walking away for an hour: usually a fresh session
(or `/clear`) is cheaper than reheating a large stale context.

So when the newest transcript entry is older than the staleness threshold, the
first prompt is blocked with an explanation. Submitting again within
`ACK_GRACE_MINUTES` is the approval — the guard records the wall-clock time of
the block and stands down for any prompt that arrives shortly after. Once that
grace window passes (or the conversation goes cold again after resuming), the
guard re-arms.

The ack is keyed to wall-clock, NOT to the transcript's newest timestamp: the
transcript is written asynchronously and may lag the live conversation, so a
timestamp-keyed ack could desync between the block and the re-submit and wedge
the session in a loop it has no way to approve.

Blocking uses the JSON `{"decision": "block"}` contract with exit 0, not exit 2.
On this event exit-2 stderr is fed back to *Claude*, so the user would watch
their prompt vanish with no explanation; `systemMessage` is the documented
user-visible channel.

It only ever blocks when a human is there to see the block. `UserPromptSubmit`
also fires under `claude -p`, scheduled agents, and SDK embeddings, where an
erased prompt is a silent no-op nobody can approve — so an unrecognized or
automated entrypoint (or `CI`) skips the guard entirely.

Config is by ENVIRONMENT VARIABLE, not `agentic-engineering.local.md`
frontmatter — matching the `sdd-cache` / `worktree-session` precedent, since
cost tolerance is a per-machine choice that should not ride a PR.

  AGENTIC_STALE_MINUTES   minutes of idle before the guard fires (default 60;
                          `0` disables the hook entirely)

Fail-open: any error (unreadable transcript, unparseable timestamp, missing
payload) allows the prompt. A broken guard must never wedge a session.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STALE_MINUTES = 60

# How long a block stays approved. Long enough to retype a prompt the block
# erased, short enough that the next idle stretch re-arms the guard.
ACK_GRACE_MINUTES = 10

# Entrypoints where a human is watching the session and can act on a block.
# Deliberately an ALLOWLIST: an unknown entrypoint (a new automation surface, an
# SDK embedding, `mcp`) skips the guard, so the failure mode of being wrong is a
# missed cost warning rather than an erased prompt nobody can re-send. A TTY
# check can't stand in for this — the desktop app has no controlling terminal
# and `claude -p` inherits one.
INTERACTIVE_ENTRYPOINTS = frozenset(
    {"cli", "claude-desktop", "vscode", "jetbrains"}
)

MESSAGE = """
⏸  PAUSED: this conversation has been idle for {age}.

The prompt cache for this context has almost certainly expired, so continuing
re-sends the entire conversation as uncached tokens — you pay full price for
context you already paid to cache.

  • Cheaper: start a fresh session (or /clear) and state the task directly.
  • Continue anyway: submit again — the next prompt goes through.

Blocking erases the prompt, so your text was NOT kept.

Set AGENTIC_STALE_MINUTES=0 to disable this guard, or to another number of
minutes to change the threshold.
""".strip()


def _last_timestamp(transcript: Path) -> "datetime | None":
    """Newest `timestamp` in a JSONL transcript, scanning from the end."""
    lines = transcript.read_text(errors="replace").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        raw = entry.get("timestamp") if isinstance(entry, dict) else None
        if not isinstance(raw, str):
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _format_age(minutes: float) -> str:
    if minutes < 120:
        return f"{int(minutes)} minutes"
    hours = minutes / 60
    if hours < 48:
        return f"{hours:.1f} hours"
    return f"{hours / 24:.1f} days"


def is_interactive(env) -> bool:
    """True when a human can see (and answer) a blocked prompt."""
    if env.get("CI"):
        return False
    return env.get("CLAUDE_CODE_ENTRYPOINT", "") in INTERACTIVE_ENTRYPOINTS


def evaluate(transcript_path: str, now: datetime, threshold_minutes: int):
    """Return (block, message). Pure enough to unit test without stdin."""
    if threshold_minutes <= 0 or not transcript_path:
        return False, ""

    transcript = Path(transcript_path)
    try:
        last = _last_timestamp(transcript)
    except OSError:
        return False, ""
    if last is None:
        return False, ""

    age_minutes = (now - last).total_seconds() / 60
    if age_minutes < threshold_minutes:
        return False, ""

    ack = transcript.with_name(transcript.name + ".stale-ack")
    try:
        acked = datetime.fromisoformat(ack.read_text().strip())
        if 0 <= (now - acked).total_seconds() / 60 < ACK_GRACE_MINUTES:
            return False, ""
    except (OSError, ValueError):
        pass
    try:
        ack.write_text(now.isoformat())
    except OSError:
        # Can't record the ack, so a re-send would block again — allow instead
        # of trapping the user in an unapprovable loop.
        return False, ""

    return True, MESSAGE.format(age=_format_age(age_minutes))


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)

    if not is_interactive(os.environ):
        sys.exit(0)

    try:
        threshold = int(os.environ.get("AGENTIC_STALE_MINUTES", DEFAULT_STALE_MINUTES))
    except ValueError:
        threshold = DEFAULT_STALE_MINUTES

    block, message = evaluate(
        data.get("transcript_path") or "", datetime.now(timezone.utc), threshold
    )
    if block:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": message,
                    "systemMessage": message,
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
