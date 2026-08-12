# Verification loop

Use the cheapest evidence that can falsify the change, then broaden in
proportion to risk.

1. Read the repository's mapped `test-execution` guidance.
2. Run focused checks for the changed behavior while iterating.
3. Exercise affected integration or user-visible boundaries when unit tests
   cannot prove them.
4. Before delivery, run the repository-required gate for the current head.
5. Read the diff for unintended edits, missed failure paths, secrets, and debug
   residue.

Do not run generic build, lint, security, coverage, or browser rituals when the
repository does not require them or the change cannot affect that surface. Do
not skip a required repository gate because a narrower check passed.

Report exact commands, exit status, failures, skipped checks that matter, and
remaining uncertainty. Return `ready` only when required checks pass and the
evidence supports the requested behavior.
