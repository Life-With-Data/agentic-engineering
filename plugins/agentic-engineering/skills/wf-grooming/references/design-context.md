# Groom design-aware work

Apply this route when a work item has a significant UI or design aspect. Gather
visual direction and capture it into the issue so the eventual implementer starts
from concrete references, not a blank canvas. Grooming stays read-only for product
code and never fabricates visual references.

## Research inspiration for greenfield surfaces

For a screen, flow, or section that does not exist yet, dispatch the
`design-inspiration-researcher` agent to gather visual direction. Grooming already
delegates legwork; this is the same pattern. Set the sub-agent's model explicitly
at dispatch, choosing the lowest tier that fits scoped research. The agent depends
on an installed design-inspiration lookup capability; when none is connected it
falls back to web research or returns a missing-capability note rather than
inventing references. Consume its inspiration digest and embed it in the issue's
`## Visual Context` section.

## Capture visual context into the issue

Record visual references in two tiers:

- **Externally hosted references** — catalog links, Figma frames, hosted screen
  images — embed directly as markdown images or links in the issue body.
- **Locally captured current-state screenshots** — attach through the
  repository's mapped screenshot/attachment mechanism. When no such mechanism
  exists, record the links or file paths and note the gap. Never invent an upload
  provider.

Cover inspiration references, relevant current-state visuals, and any potential
future-state visuals the item already implies.

## Completion boundary

A missing inspiration or attachment capability is a recorded note, not a
fabrication and not a blocker to invent around — consistent with the grooming
completion boundary. Grooming never edits product code and never fabricates
visual references.
