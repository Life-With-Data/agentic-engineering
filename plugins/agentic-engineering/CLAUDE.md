# Agentic Engineering Plugin Development

## Versioning

Version and `CHANGELOG.md` are computed by release-please from Conventional
Commit-typed PR titles — do **not** hand-bump `.claude-plugin/plugin.json`
or hand-write CHANGELOG.md entries. See root `AGENTS.md` and
`docs/solutions/plugin-versioning-requirements.md`.

### Pre-Commit Checklist

Before committing ANY changes:

- [ ] PR title uses a Conventional Commit type (`feat:`/`fix:`/`docs:`/`refactor:`/`chore:`/`perf:`)
- [ ] plugin.json / marketplace.json descriptions match current component counts (`bun test` enforces this)
- [ ] Did NOT hand-edit plugin.json's version or CHANGELOG.md

## Skill Naming Convention

The plugin has exactly nine public workflow-policy skills, all using the `wf-` prefix.

Treat that set as closed. Do not add another public skill for a narrower procedure. Add it as a progressive-disclosure reference under the owning router. Cross-stage policy (routing, delivery posture, escalation, sub-agent delegation) belongs to `wf-orchestrate` references; stage-internal procedure belongs to the stage router. Repository-specific operational knowledge is not part of this plugin: consumer repositories provide it through the fixed root `AGENTS.md` capability contract and existing repository-owned skills or documentation. See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md).

## Skill Compliance Checklist

When adding or modifying skills, verify compliance with skill-creator spec:

### YAML Frontmatter (Required)

- [ ] `name:` present and matches directory name (lowercase-with-hyphens)
- [ ] `description:` present and describes **what it does and when to use it** (per official spec: "Explains code with diagrams. Use when exploring how code works.")

### Reference Links (Required if references/ exists)

- [ ] All files in `references/` are linked as `[filename.md](./references/filename.md)`
- [ ] All files in `assets/` are linked as `[filename](./assets/filename)`
- [ ] All files in `scripts/` are linked as `[filename](./scripts/filename)`
- [ ] No bare backtick references like `` `references/file.md` `` - use proper markdown links

### Writing Style

- [ ] Use imperative/infinitive form (verb-first instructions)
- [ ] Avoid second person ("you should") - use objective language ("To accomplish X, do Y")

### Quick Validation Command

```bash
# Check for unlinked references in a public skill
grep -E '`(references|assets|scripts)/[^`]+`' skills/wf-*/SKILL.md
# Should return nothing if all refs are properly linked

# Check description format - should describe what + when
grep -E '^description:' skills/wf-*/SKILL.md
```

## Documentation

See `docs/solutions/plugin-versioning-requirements.md` for detailed versioning workflow.
