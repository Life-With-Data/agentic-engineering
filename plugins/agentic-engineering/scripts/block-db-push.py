#!/usr/bin/env python3
"""
Claude Code hook to block `prisma db push`, which bypasses the migration
history and silently drifts the database schema.

`prisma db push` mutates the live database to match `schema.prisma` *without*
writing a migration. That feels convenient in the moment but breaks the
workflows that rely on migrations being the source of truth:
- Integration tests that apply migrations from scratch (e.g. Testcontainers)
  diverge from a dev DB that was `push`ed, so tests pass locally and fail in CI
  (or vice versa).
- CI/CD and production deploy by running migrations — a schema that only exists
  as a `push` never ships, so prod is missing columns dev has.
- The "what is the real schema?" question loses its single answer.

This hook blocks the command before it runs and points at the migration
workflow instead (`prisma migrate dev`). It is the DB-safety sibling of the
`prevent-main-commit` / `block-no-verify` git guards.

No-ops entirely for projects that never run `prisma db push`, and for any tool
call that isn't Bash — it only ever fires on the exact footgun command, so a
non-Prisma repo pays nothing.

Design notes:
- Segment-aware quote stripping mirrors the other PreToolUse hooks, so a
  command that merely *mentions* the phrase (a quoted commit message, a `grep`
  for it, an `echo`) is NOT blocked.
- Pure logic lives in `evaluate()` so it can be unit tested without driving the
  hook through stdin.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import emit_allow, normalize

# Direct invocation in any wrapper form: `prisma db push`, `npx prisma db
# push`, `pnpm prisma db push`, `pnpm dlx prisma db push`, `dotenv -- prisma db
# push`, etc. The `db` and `push` tokens may be separated by flags on either
# side, so match them as adjacent subcommand words.
DIRECT_DB_PUSH = re.compile(r"\bprisma\s+db\s+push\b")

# Package-script aliases that resolve to a push, e.g. a repo that exposes
# `pnpm --filter @repo/database push` or `... prisma push` as a script.
FILTER_PUSH = re.compile(r"\bpnpm\s+--filter\s+\S+\s+(?:prisma\s+)?push\b")

ERROR_MSG = """
❌ BLOCKED: `prisma db push` drifts the schema away from your migration history.

`db push` mutates the database without writing a migration, so:
  • tests that apply migrations from scratch diverge from your dev DB
  • CI/CD and production (which run migrations) never get the change
  • there's no longer a single source of truth for the schema

Use a migration instead — it keeps the DB and history in sync:
  prisma migrate dev --name <migration-name>
  # or your repo's wrapper, e.g. pnpm --filter <db-pkg> migrate dev --name <...>
""".strip()


def main():
    input_data = normalize(json.load(sys.stdin))

    if input_data.get("tool_name") != "Bash":
        emit_allow()

    command = input_data.get("tool_input", {}).get("command", "")

    if evaluate(command):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)

    emit_allow()


def evaluate(command: str) -> bool:
    """Return True if `command` should be blocked as a `prisma db push`."""
    cleaned = strip_quotes(command)
    return bool(DIRECT_DB_PUSH.search(cleaned) or FILTER_PUSH.search(cleaned))


def strip_quotes(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    return command


if __name__ == "__main__":
    main()
