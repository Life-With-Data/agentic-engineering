---
name: wf-testing
description: Workflow policy for test strategy, test-first development, regression coverage, browser or device testing, and verify-before-done evidence. Use when deciding what to test, executing validation, or proving a change works. Repository commands and environments must come from repository capability targets.
---

# Testing workflow

Layer: Workflow policy

Owns: test selection, evidence standards, regression expectations, layered verification, and ready/not-ready verdicts.

Requires repository capabilities: `development-environment`, `test-execution`.

Does not contain: repository test commands, fixture credentials, device setup, application URLs, or CI configuration.

## Start here

Resolve `<skill-directory>` to the directory containing this `SKILL.md`. All
scripts used by this workflow are bundled there; do not resolve them through a
plugin root.

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require development-environment \
  --require test-execution
```

Stop on contract failure. Read the primary target for both required capabilities, then supporting targets only when needed, before selecting tests.

## Route the request

- Write behavior before implementation: read [test-driven development](references/test-driven-development.md).
- Evaluate coverage and integration boundaries: read [test strategy reviewer](references/test-strategy-reviewer.md).
- Run the final evidence loop: read [verification loop](references/verification-loop.md).
- Test changed browser behavior: read [test browser](references/test-browser.md).

Load only the references needed for the affected interfaces.
Platform-specific device and build mechanics come from repository capability targets.

## Sub-agent delegation

The session's default agent orchestrates and validates testing; it delegates
the authoring. Dispatch focused sub-agents to write tests per surface and to
analyze failures. The orchestrator retains test strategy, evidence
sufficiency, and the ready/not-ready verdict, and independently reruns the
decisive checks rather than trusting a sub-agent's report. Choose each
sub-agent's model by task complexity: an economy tier for running prescribed
checks and reporting output, a standard tier for test authoring against clear
criteria, the strongest available tier for flaky-failure or cross-layer
analysis. Hosts without a sub-agent mechanism run the same steps inline.

## Evidence ladder

Prefer the cheapest test that can falsify the claim, then add broader evidence in proportion to risk:

1. Focused unit or contract checks.
2. Cross-layer integration checks.
3. User-visible browser, device, or API behavior.
4. Full repository-required verification.

Report commands, outcomes, skipped checks, and remaining uncertainty. Compilation alone is not behavioral proof.

For every bug fix, add regression protection and rerun the original `wf-grooming` reproduction after the change. A passing replacement test without the original reproduction is insufficient evidence.

## Wrong-layer recovery

If a testing reference proposes a framework or command that differs from the mapped repository assets, the repository capability wins. Return here afterward to judge whether the collected evidence satisfies the workflow.
