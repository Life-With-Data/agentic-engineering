# Deliver plan documentation

Use this route only when the mapped `documentation` guidance requires a plan
artifact to land through a pull request before implementation.

## Scope gate

1. Take the exact plan paths produced by the planning route.
2. Confirm each path is an approved repository documentation location.
3. Stage only those paths. Never use a blanket stage operation.
4. Stop if unrelated documentation at the same ownership boundary is dirty or
   if any non-plan path would enter the commit.

## Deliver

Follow the repository's mapped delivery mechanics for branch naming, commit,
push, PR creation, checks, merge policy, and cleanup. Preserve the work item's
join key when repository conventions define one. Detect an existing PR for the
same artifact before creating another.

This route does not write lifecycle stage: the caller owns `planned`. It must not
assume auto-merge, a fixed plan directory, a frontmatter schema, or permission to
merge. Report the artifact paths, PR state, validation results, and any blocker.
