# Reflect for durable guidance

Use this reference after a solved problem reveals reusable knowledge. The goal
is to improve the repository's existing guidance without assuming that every
repository uses skills—or that its skills follow any particular naming or
directory convention.

## Classify the learning

Ask what failed and who needs the knowledge next time:

- A repository command, environment fact, access procedure, or runbook detail
  belongs in the mapped repository asset for that capability.
- A workflow stage, gate, artifact, or handoff belongs in the owning `wf-*`
  skill and should change only when the shared policy itself was wrong.
- A one-off implementation detail belongs in code comments, tests, or the
  work item—not permanent agent guidance.
- A product or team decision belongs in the repository's established decision
  record or documentation location.

## Procedure

1. State the reusable lesson independently of the incident.
2. Identify the capability whose mapped asset should own it.
3. Read that asset and its supporting targets before editing.
4. Amend the smallest existing source that future agents already reach.
5. Avoid duplicating the same rule across instruction files, docs, and skills.
6. If no suitable asset exists, route to `wf-setup` to revise the capability
   mapping; do not create a wrapper or new repository skill by default.
7. Validate links, commands, and repository documentation checks.

## Completion

Report the lesson, owning capability, edited asset, validation evidence, and any
contract change. Do not modify installed plugin files from a consumer
repository; propose shared workflow improvements in the plugin's source
repository instead.
