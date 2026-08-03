---
title: "A test directory without __init__.py loses to any installed package of the same name"
category: testing-patterns
tags: [python, unittest, namespace-packages, sys-path, editable-install, dev-environment]
module: plugin-tests
symptom: "`python3 -m unittest tests.<module>` reports ModuleNotFoundError for a file that plainly exists; CI passes"
root_cause: "Without __init__.py the directory is only a namespace portion, and Python lets a regular package on a later sys.path entry win — position on sys.path does not decide it"
---

# Namespace Test Dirs Are Shadowed By Installed Packages

## Problem

Ten modules under `plugins/agentic-engineering/tests/` documented their own run
command:

```
Run with: ``python3 -m unittest tests.prevent_main_commit_test``.
```

On a developer machine that command failed:

```
ModuleNotFoundError: No module named 'tests.prevent_main_commit_test'
```

The file was right there. CI was green. The obvious readings were all wrong:

- **"`PYTHONPATH` is misconfigured."** It was unset.
- **"The current directory isn't on `sys.path`."** It was — `sys.path[0]` was `''`.
- **"CI must run it differently, so the command is just stale."** True but not the
  cause, and it hides the real one.

The diagnostic that actually resolved it was one line:

```console
$ python3 -c "import tests; print(tests.__path__)"
['/Users/<user>/code/ant/packages/todoist/tests']
```

`tests` was resolving to an unrelated project's package, pulled onto `sys.path`
by an editable install (`site-packages/_todoist_sdk.pth`).

## Root cause

`plugins/agentic-engineering/tests/` had no `__init__.py`, so it was only a
**namespace portion**. Python's import machinery records a namespace portion and
**keeps scanning `sys.path`**; a *regular* package (one with `__init__.py`) found
on any later entry wins outright.

Being first on `sys.path` does not help. Precedence of a regular package over a
namespace portion is not positional — this is the part that makes the failure
feel impossible and sends you chasing `PYTHONPATH`.

CI never saw it because `.github/workflows/ci.yml` uses the `discover` form,
which sets the start directory as the top level and imports modules by bare
name — it never resolves a `tests` package at all. So the environment that ran
the documented command was exactly the environment that never ran CI.

## Solution

Add an empty `plugins/agentic-engineering/tests/__init__.py`.

That makes the directory a regular package, so it wins the `sys.path[0]` lookup
immediately and no later entry is consulted. One file; all ten docstrings become
true as written; no docstring edits needed.

Verification:

```bash
# the documented per-module form now works
cd plugins/agentic-engineering && python3 -m unittest tests.prevent_main_commit_test

# and discovery is unchanged — same collected count as before
python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'
```

Expected: the first passes; the second still collects and passes the full suite
(588 tests when this was written). Confirming the second matters — a packaging
change that "fixes" the per-module form while quietly changing what CI collects
would be a worse bug than the one being fixed.

## Prevention

- **A documented run command is a claim that must be verified in a dirty
  environment.** CI is a clean room; developer machines carry editable installs
  of other projects. A command only CI can run is a command that will mislead
  the next person, and the failure it produces names *your* module, not the
  package that shadowed it.
- **Give test directories an `__init__.py`** when anything imports them by
  package path. `tests`, `utils`, `scripts`, `common` are all names other
  projects install; a bare directory is not a namespace you own.
- **When an import error names a file you can see, print the package's
  `__path__`** before touching `PYTHONPATH` or `sys.path`. One line separates
  "shadowed by another distribution" from every other hypothesis.

## Resources

- Fixed in: PR #362 (issue #363), found while landing issue #359
- Related: [compounded learnings go stale silently](../compounded-learnings-go-stale-silently.md)
