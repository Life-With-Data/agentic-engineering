# Adopt agentic-engineering in a repository

Setup is an inventory-first interview that connects workflow policy to existing
repository operations. It must finish with a complete, validated capability
contract and must not manufacture repository conventions.

## 1. Inventory before asking

Read [the repository context contract](repository-context-contract.md). Inspect
root instructions, repository documentation, existing skills, development and
test scripts, CI configuration, runbooks, and security guidance. Draft the ten
capability mappings from evidence already present.

## 2. Interview only for gaps

Review the draft by operational journey:

- orient and build;
- test and reproduce bugs;
- observe, operate, access, and handle data;
- deliver and document.

Ask about missing or ambiguous commands, environment boundaries, access
procedures, observable success evidence, prohibited actions, and proposed
`not-applicable` declarations. Do not ask the user to redesign adequate existing
guidance or adopt a naming convention.

## 3. Write the contract

Add or repair the fixed `## Agentic Engineering Repository Contract` section in
root `AGENTS.md`. Map each capability directly to one or more existing assets in
primary-first reading order. An asset may serve multiple capabilities. Create a
new repository-owned document or skill only when operational knowledge is
genuinely absent—not as a pass-through wrapper.

## 4. Validate strictly

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repository-context.py"
```

Setup is incomplete until validation succeeds for all ten capabilities,
including evidence-backed `not-applicable` entries.

## 5. Configure optional plugin features

After the contract is valid, configure only the features the repository chooses:

- [configuration flags](config-flags.md);
- [lifecycle integration](lifecycle.md);
- [hooks](install-hooks.md).

These features may add plugin-owned configuration, but they must not redefine
the repository capability map or install unrelated repository tooling.
