# Agentic Engineering Plugin Development

## Versioning

Version and `CHANGELOG.md` are computed by release-please from Conventional
Commit-typed PR titles — do **not** hand-bump `.claude-plugin/plugin.json`
or hand-write CHANGELOG.md entries. See root `CLAUDE.md`'s "Updating the
plugin" and "Release process" sections, and
`docs/solutions/plugin-versioning-requirements.md`.

### Pre-Commit Checklist

Before committing ANY changes:

- [ ] PR title uses a Conventional Commit type (`feat:`/`fix:`/`docs:`/`refactor:`/`chore:`/`perf:`)
- [ ] README.md component counts verified
- [ ] README.md tables accurate (agents, skills)
- [ ] plugin.json description matches current counts
- [ ] Did NOT hand-edit plugin.json's version or CHANGELOG.md

### Directory Structure

```
agents/
├── review/     # Code review agents
├── research/   # Research and analysis agents
├── design/     # Design and UI agents
├── workflow/   # Workflow automation agents
└── docs/       # Documentation agents

skills/
└── <name>/SKILL.md  # All skills, one directory per skill (includes the former workflow
                      # and utility commands, e.g. workflows-plan, workflows-review)
```

## Skill Naming Convention

**Workflow skills** use a `workflows-` prefix, hyphenated (not colon-separated — skill directory names allow only lowercase letters, numbers, and hyphens):
- `workflows-plan` - Create implementation plans
- `workflows-review` - Run comprehensive code reviews
- `workflows-work` - Execute work items systematically
- `workflows-compound` - Document solved problems

**Why the prefix?** Claude Code has built-in `/plan` and `/review` slash invocations. A skill named `workflows-plan` produces `/workflows-plan` with no collision.

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
# Check for unlinked references in a skill
grep -E '`(references|assets|scripts)/[^`]+`' skills/*/SKILL.md
# Should return nothing if all refs are properly linked

# Check description format - should describe what + when
grep -E '^description:' skills/*/SKILL.md
```

## Documentation

See `docs/solutions/plugin-versioning-requirements.md` for detailed versioning workflow.
