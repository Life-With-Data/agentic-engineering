# Verify changed browser behavior

Use browser verification when the changed contract is user-visible or depends
on real browser behavior. The repository's `development-environment` and
`test-execution` targets must supply the server, URL, accounts, fixtures,
browser tool, and commands.

## Select scenarios

1. Identify the affected user journeys and their observable outcomes.
2. Cover the changed path, its highest-risk alternate path, and relevant error
   handling.
3. Include a regression scenario for a bug fix using the original reproduction.
4. Prefer stable semantic interactions and repository-owned fixtures.

## Execute

For each scenario:

1. Establish the documented starting state.
2. Perform the user actions through the repository-approved browser mechanism.
3. Assert visible results and durable side effects.
4. Inspect console, network, and application evidence when the repository's
   tooling exposes it.
5. Capture screenshots or traces when they materially support the verdict.

Do not install a browser tool, assume localhost or a port, start infrastructure,
or guess credentials unless the mapped repository guidance explicitly directs
that action.

## Report

List the scenarios, environment, mechanism, observed results, artifacts, and any
skipped coverage. Browser verification complements focused automated tests; it
does not replace the repository's required test suite.
