#!/usr/bin/env python3
"""
Claude Code hook to block `prisma db push`, which bypasses migration history.

`prisma db push` mutates the database schema directly to match `schema.prisma`
without generating a migration file. That causes schema drift between the live
database and the migration history, which:
- breaks integration tests that apply migrations from scratch (e.g. Testcontainers),
- breaks CI/CD and production deploys, which run migrations rather than `push`,
- destroys the single source of truth for the schema.

Correct alternative: `prisma migrate dev --name <migration-name>`, which records
a migration that keeps the database and history in sync.

Design notes (matching the plugin's other guards' precision ethos):
- Only fires when `prisma db push` is the actual command verb, in any of its
  common runner forms (`prisma`, `npx prisma`, `pnpm prisma`, `pnpm exec prisma`,
  `bunx prisma`, `yarn prisma`, `pnpm dlx prisma`, `dotenv -e .env -- prisma`, …).
- Segment/quote/comment-aware: a command that merely *mentions* the phrase in a
  quoted string or a `#` comment is NOT blocked, so prose about the anti-pattern
  passes through — mirroring `block-no-verify.py` / `block-slack-webhook.py`.
"""
import json
import re
import sys

# `db` and `push` may be separated by flags/env prefixes but must both belong to
# a `prisma` invocation. Require `prisma` before `db push` within the same
# segment; `[^&|;]*?` keeps it inside one simple command (not after a later
# `&&`/`;`/`|`).
DB_PUSH = re.compile(r"\bprisma\b[^&|;]*?\bdb\s+push\b")

ERROR_MSG = """
❌ BLOCKED: `prisma db push` bypasses migration history and causes schema drift.

Pushing the schema directly desyncs the database from the migration history,
which breaks integration tests (they apply migrations from scratch) and CI/CD
and production deploys (they run migrations, not `push`).

Use a migration instead:
    prisma migrate dev --name <migration-name>

This records a migration file so the database and its history stay in sync.
Consult your repo's migration workflow (e.g. a `prisma-migrate` skill or the
`/dev:migrate-database` command) if one is available.
""".strip()


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    if is_db_push(command):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


def is_db_push(command: str) -> bool:
    return bool(DB_PUSH.search(sanitize(command)))


def sanitize(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    command = re.sub(r"#.*", "", command)
    return command


if __name__ == "__main__":
    main()
