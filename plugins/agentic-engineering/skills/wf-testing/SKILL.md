---
name: wf-testing
description: Workflow policy for test strategy, test-first development, regression coverage, browser or device testing, and verify-before-done evidence. Use when deciding what to test, executing validation, or proving a change works. Repository commands and environments must come from repository capability targets.
---

# Testing workflow

Layer: Workflow policy

Owns: the ready/not-ready verdict.

Requires repository capabilities: `development-environment`, `test-execution`.

Does not contain: repository test commands, fixture credentials, device setup, application URLs, or CI configuration.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require development-environment \
  --require test-execution
```

Stop on contract failure; read primary targets first, supporting targets only as needed.

## Route the request

- Write behavior before implementation: read [test-driven development](references/test-driven-development.md).
- Evaluate coverage and integration boundaries: read [test strategy reviewer](references/test-strategy-reviewer.md).
- Run the final evidence loop: read [verification loop](references/verification-loop.md).
- Test changed browser behavior: read [test browser](references/test-browser.md).

Load only the references needed for the affected interfaces.
Platform-specific device and build mechanics come from repository capability targets.

## Evidence ladder

Prefer the cheapest test that can falsify the claim, then add broader evidence in proportion to risk:

1. Focused unit or contract checks.
2. Cross-layer integration checks.
3. User-visible browser, device, or API behavior.
4. Full repository-required verification before delivery.

Report commands, outcomes, skipped checks, and remaining uncertainty. Compilation alone is not behavioral proof.

For a bug fix, add regression protection when it materially prevents recurrence
and rerun the original reproduction when available.

Testing ends with a ready/not-ready verdict and concise evidence. It may run
inside development; a separate testing handoff is not required.

## Wrong-layer recovery

Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
