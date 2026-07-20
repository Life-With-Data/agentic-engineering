# Prepare a groomable bug report

Use the repository's configured GitHub issue tracker. This reference owns report
completeness; repository capability targets own reproduction mechanics and any
environment-specific evidence.

## Required fields

- Concise summary of the observable failure.
- Expected and actual behavior.
- Minimal verified reproduction steps.
- Environment and starting-state details needed to repeat the result.
- Evidence from the reproduction, with secrets and personal data removed.
- Impact and affected scope.
- Known frequency or intermittency.
- Acceptance criteria for the corrected behavior.
- Validation requirement that reruns the original reproduction.

Separate facts from hypotheses. A suggested fix may be included as a lead, but
must not be presented as root cause before development establishes it.

## Tracker action

Search for an existing issue before creating a duplicate. When creating or
updating the GitHub issue, preserve the repository's labels, templates,
ownership rules, and project linkage. If the tracker cannot be accessed, return
the completed report body and state the blocker; do not silently choose another
tracker.

The report is ready for continued grooming only when reproduction evidence is
present or the user has explicitly changed the work from a bug to an
investigation.
