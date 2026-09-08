# Review execution contract

Every review agent runs under this contract. It overrides anything in the
agent's own instructions that conflicts with it.

## Read-only on the checkout

Do not edit, write, or delete any file except a report file the dispatcher
names. Do not commit, branch, stash, or otherwise change git state. Reading
files, running `git diff`, and running a focused test are allowed.

## No dispatching

Do not spawn sub-agents and do not load a `wf-*` workflow router. This review
seat does its own reading. A reviewer that spawns another reviewer duplicates
a seat at full cost and its verdict counts for nothing.

## The implementer's report is a claim, not evidence

Treat the implementer's report, including any "tests pass" statement, as an
unverified claim to check against the diff. Verify it yourself.

## Do not re-run the whole suite

The orchestrator reruns gates independently after review. Do not re-run the
full test suite to confirm the implementer's report. Re-run only a single
focused test, and only when reading the code raises a specific, namable
doubt that no existing evidence answers. Name that doubt in the finding that
prompted the test.

## Stay inside the diff unless a named risk sends you out

Inspect files outside the diff only to check a risk you can name: a caller
the change breaks, an invariant the change relies on. Say which risk sent
you there. Every finding carries file:line evidence; verdict vocabulary
stays whatever the agent already uses.
