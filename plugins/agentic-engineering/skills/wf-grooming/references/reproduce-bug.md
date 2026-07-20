# Reproduce a reported bug

Reproduction is a grooming gate. This reference defines the evidence needed;
the mapped repository capabilities define how to obtain it.

## Required context

Require and read `development-environment` and `bug-reproduction`. Also require
`observability` when reproduction depends on production, integration, or remote
system evidence. Follow `security-and-access` for any credentials or protected
systems.

## Procedure

1. Extract the reported starting state, actions, inputs, expected behavior, and
   actual behavior.
2. Establish a controlled baseline using the repository's reproduction
   guidance. Record version, environment, fixtures or data state, and relevant
   configuration without exposing secrets.
3. Execute the smallest faithful sequence that could exhibit the behavior.
4. Capture observable evidence appropriate to the interface: output, logs,
   response data, state transitions, screenshots, or test failures.
5. Repeat enough to distinguish a deterministic failure from an intermittent
   one. For intermittent failures, record frequency and timing conditions.
6. Reduce the sequence while preserving the failure.

Do not invent a server URL, command, account, fixture, log provider, browser
driver, or credential procedure. Those are repository operations.

## Outcomes

- **Reproduced:** record the minimal sequence, environment, evidence, and
  expected-versus-actual result. Grooming may continue.
- **Not reproduced:** record every attempted path and the evidence observed.
  The bug remains un-groomed unless the user explicitly reclassifies the work.
- **Blocked:** identify the missing access, environment, data, or repository
  guidance and route the gap to `wf-setup`.

A suspected root cause or proposed fix is not reproduction evidence.
