---
title: "Tests that shell out to git must scrub GIT_* : GIT_DIR silently overrides `git -C <tempdir>`"
category: testing-patterns
tags: [test-isolation, git, environment, GIT_DIR, hooks, temp-repo, order-dependence, leakage, lifecycle-board]
module: plugins/agentic-engineering/tests/lifecycle_board_test.py, plugins/agentic-engineering/scripts/lifecycle_board.py
symptom: "A suite building throwaway `git init` repos passed normally but wrote files into the developer's real .git and became order-dependent whenever GIT_DIR was set in the environment"
root_cause: "`git -C <dir>` sets the working directory, it does not select the repository; GIT_DIR in the inherited environment wins, so every temp-repo test silently resolved to the ambient repository instead"
---

# Tests That Shell Out to Git Must Scrub `GIT_*`

## Problem

`lifecycle_board.py` writes generated artifacts — work packets, and now `--decompose`
idempotency receipts — under Git's common directory, resolved by shelling out:

```python
common = _git(["-C", ctx.root, "rev-parse", "--git-common-dir"])
```

Tests for these paths build a throwaway repository per case:

```python
root = Path(tempfile.TemporaryDirectory().name)
subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, ...)
```

That reads as fully isolated. It is not. Run the same suite with `GIT_DIR` set and every case
resolves to the **ambient** repository instead:

```
GIT_DIR=$PWD/.git GIT_WORK_TREE=$PWD python3 -m unittest .../lifecycle_board_test.py
→ FAILED (failures=3, errors=1)
→ AssertionError: Lists differ: [283, 284] != [183, 184]
→ receipt files written into the real repo's .git/agentic-engineering/decompose-receipts/
```

Two failure modes at once. Every test collapses into one shared artifact namespace, so they
cross-pollute and become order-dependent — one test read a receipt another had written. And the
suite writes into the developer's actual repository.

## Investigation path

The misleading signal is that `-C` looks like it scopes the whole command. It does not:

- `git -C <dir>` **changes the working directory** before running.
- `GIT_DIR` **selects the repository**, and it is consulted regardless of the working directory.

When both are present, `GIT_DIR` wins. `git init -q` in the tempdir genuinely creates a
repository there; the later `rev-parse --git-common-dir` simply never looks at it.

The second misleading signal is that this is invisible under normal `bun test` / `unittest` runs,
because an interactive shell has no `GIT_*` set. It only appears in environments that set them —
which is exactly where CI-adjacent automation lives:

- inside any **git hook** (this repository ships them, e.g. `prevent-main-commit.py`)
- `git rebase --exec ...`
- `git bisect run ...`
- `git filter-branch`, and most tooling that invokes a subprocess mid-operation

So the exposure is reachable in normal use, not a contrived scenario.

A related detail made the leak newly harmful rather than merely untidy. About twenty sibling
decompose tests deliberately run in **plain, non-git** temp directories and rely on
`git_common_dir` failing, exercising the unguarded fallback. Under a poisoned `GIT_DIR` those
tests suddenly resolve a real common directory and start writing receipts into it — a behavior
introduced by adding the receipt, invisible until tested under that environment.

## Root cause

`_git` inherits the ambient environment, and no layer between the test and the subprocess
neutralizes repository-selecting variables. Passing `-C` addressed the working directory and left
repository selection to whatever the caller happened to export.

## Solution

Scrub the repository-selecting variables once for the whole module, not per class:

```python
def setUpModule() -> None:
    patch = mock.patch.dict(os.environ)
    patch.start()
    _GIT_ENV_PATCH.append(patch)
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_CEILING_DIRECTORIES"):
        os.environ.pop(var, None)


def tearDownModule() -> None:
    while _GIT_ENV_PATCH:
        _GIT_ENV_PATCH.pop().stop()
```

Module scope is the point. The exposure belongs to `_git`, so it applies to every class that
reaches it — including classes whose authors never thought about git isolation. A fix in one
class's `setUp` leaves the rest exposed, which is what the first attempt here did: it cleared the
new tests and left the twenty siblings leaking.

`mock.patch.dict(os.environ)` restores the full environment on stop, so the scrub does not leak
back out into the surrounding process.

The alternative — pass an explicit `env=` to every `subprocess.run` in the production code — is
more invasive, changes shipped behavior to fix a test problem, and would still miss any call site
added later.

## Verification

The check is that the suite behaves identically with the variables set and unset:

```bash
python3 -m unittest plugins/agentic-engineering/tests/lifecycle_board_test.py
GIT_DIR=$PWD/.git GIT_WORK_TREE=$PWD \
  python3 -m unittest plugins/agentic-engineering/tests/lifecycle_board_test.py

# and nothing was written into the real repository:
find "$(git rev-parse --git-common-dir)/agentic-engineering/decompose-receipts" -type f
```

Both runs: `Ran 286 tests ... OK`, and the `find` returns nothing. Before the fix the poisoned run
reported four failures and left receipt files behind. `main` reported one failure under the same
environment, so the module-scope scrub also closed a pre-existing exposure in an unrelated test
class.

## Reusable principle

**A test that shells out to a tool inherits that tool's entire environment-based configuration,
and a path argument does not override it.** Creating a fixture in a temp directory proves the
fixture exists; it does not prove the tool under test will look there.

Generalizing beyond git — the same shape appears with `GIT_CONFIG_GLOBAL`, `HOME`,
`XDG_CONFIG_HOME`, `KUBECONFIG`, `AWS_PROFILE`, `DOCKER_HOST`, `NPM_CONFIG_*`, and any
`*_CONFIG`/`*_HOME` variable. For each external command a suite invokes, ask which environment
variables can redirect it away from the fixture, and neutralize them at the widest scope the
exposure actually spans.

Two supporting rules learned here:

- **Scope the guard to the shared helper, not to the class that noticed.** The exposure lives
  wherever the helper is reached.
- **Prove isolation by running the suite under the hostile environment**, not by reading the
  fixture setup. Isolation asserted from code structure is exactly the assumption that failed.

## Links

- PR [#370](https://github.com/Life-With-Data/agentic-engineering/pull/370) — where this surfaced
- Issue [#349](https://github.com/Life-With-Data/agentic-engineering/issues/349) — the receipt
  work that made the leak harmful
- [A dedup guard is not a cache](../logic-errors/a-dedup-guard-is-not-a-cache-so-a-miss-must-not-be-swallowed.md)
- [Leaked monkeypatches and runner ordering mask real dependencies](leaked-monkeypatches-and-runner-ordering-mask-real-dependencies.md)
  — the same order-dependence failure from in-process state rather than the environment
