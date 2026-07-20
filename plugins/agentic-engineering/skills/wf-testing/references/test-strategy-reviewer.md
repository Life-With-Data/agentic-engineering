# Test Strategy Reviewer

Analyze test files to identify coverage gaps, mock depth issues, and untested integration boundaries. Produces actionable reports showing where tests validate shapes but not behavior.

## When to Use

- During the `wf-grooming` planning route to plan testing strategy for a new feature
- During the `wf-development` work route to verify test quality before marking a task done
- During the `wf-review` comprehensive-review route to assess test coverage of a PR
- Standalone to audit test quality for any test file

## Input

Provide one or more of:
- A test file path to analyze
- A source file path (the reference will find corresponding tests)
- A feature description (the reference will identify relevant test files)

## Analysis Process

### 1. Map Source to Tests

For the target source file(s):
- Find corresponding test files using project conventions (`test_*.py`, `*_test.rb`, `*.test.ts`, `*.spec.ts`, etc.)
- Identify which source functions/methods have test coverage
- Identify which source functions/methods have NO test coverage

### 2. Analyze Coverage Gaps

For each function in the source file:

| Function | Has Test? | Test Exercises Real Code Path? | Notes |
|----------|-----------|-------------------------------|-------|
| `function_name` | Yes/No | Yes/No/Partial | Details |

**Focus on:**
- Functions with no corresponding test at all
- Functions where tests exist but never execute the core logic (e.g., fail at auth before reaching the main code path)
- Functions where the happy path is untested (only error cases covered)

### 3. Assess Mock Depth

For each test, evaluate the mock strategy:

- **Level 0 (Real)**: No mocks -- test uses real objects end-to-end
- **Level 1 (Network mock)**: Mocks network layer only, library objects are real
- **Level 2 (Library mock)**: Mocks the library itself (e.g., `mock(Client)`)
- **Level 3 (Total mock)**: Everything is mocked -- test only verifies your code's logic in isolation

**Rule of thumb**: For any external library integration, at least one test should be Level 0 or Level 1. If all tests are Level 2+, the integration is unverified.

### 4. Check Integration Boundaries

For each `import` of an external library followed by a constructor or function call:
- Does any test construct a real instance of the imported class?
- Does any test pass the same arguments used in production code?
- Does any test verify the constructor/function accepts those arguments?

### 5. Evaluate Happy Path Coverage

- Is the primary success path tested end-to-end?
- Or do tests only cover error handling, edge cases, and input validation?
- A test suite that only tests "what can go wrong" but never "what should go right" proves nothing about whether the feature works.

## Output Format

```markdown
## Test Strategy Review: [filename]

### Coverage Gaps
- `function_name()` happy path: [TESTED/NOT TESTED]
  - [Details about what's missing]

### Mock Depth Issues
- [Test name]: Level [N] -- [What's mocked and why it matters]

### Boundary Coverage
- [Library.Class]: [TESTED/NOT TESTED] ([N] tests construct a real instance)
- [Library.function]: [TESTED/NOT TESTED]

### Happy Path Assessment
- Primary success flow: [TESTED/NOT TESTED]
- [Details]

### Recommendation
[Specific tests to add, ordered by impact]
```

## Example

```markdown
## Test Strategy Review: test_discover_tools.py

### Coverage Gaps
- discover_tools() happy path: NOT TESTED
  - No test reaches the Client() constructor on line 458
  - 2 endpoint tests fail at auth before hitting the client code

### Mock Depth Issues
- None (no mocks used -- but also no integration tests)

### Boundary Coverage
- fastmcp.Client: NOT TESTED (0 tests construct a Client)
- asyncio.wait_for: NOT TESTED (no timeout test)

### Happy Path Assessment
- Primary success flow: NOT TESTED
- 23 tests cover regex patterns, model fields, deduplication, and error paths
- Zero tests verify that tool discovery actually works end-to-end

### Recommendation
Add integration test that starts a FastMCP server and calls
discover_tools through the actual Client transport. This catches:
1. Constructor argument mismatches
2. Transport type dispatch issues
3. End-to-end data flow through the real library
```
