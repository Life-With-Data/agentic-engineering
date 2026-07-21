# Deliver documentation changes

Ship completed documentation through the repository's established delivery
path. The mapped `documentation` capability defines valid content locations and
checks; `delivery` defines branch, PR, merge, and publication mechanics.

## Scope gate

1. Identify the exact documentation paths owned by this run.
2. Confirm no product, configuration, generated, or unrelated documentation
   path would be swept into the change.
3. Stage only the owned paths and inspect the staged diff.
4. Run the repository's documentation validation.

Stop on ambiguous ownership or non-documentation changes. Route product changes
through the normal development workflow.

## Deliver

Use the repository's mapped branch, commit, push, PR, review, CI, and merge
procedure. Detect an existing PR for the same work before opening another. Do
not assume auto-merge, a hosting provider, or authority to publish.

When documentation compounds engineering work whose implementation PR is still
open, return the changes to its owning development/delivery workflow and amend
that same PR; do not use this documentation-only delivery lane. A post-merge
documentation PR is appropriate only for genuinely new knowledge discovered
after merge, not as the routine compounding path.

Report paths, checks, PR or publication state, and remaining blockers.
