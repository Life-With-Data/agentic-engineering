---
name: reflect-for-skill-updates
description: Skill and documentation improvement through gap analysis — when bugs reveal missing docs, debugging exposes skill gaps, workflows have missing steps, or gotchas need capturing. Use after debugging sessions, workflow gaps, or when discovering lessons worth preserving.
allowed-tools:
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Bash
---

# Reflect for Skill Updates

> **Purpose**: Turn debugging sessions and mistakes into permanent improvements by updating skills, documentation, and automation.

This skill operationalizes the **compounding engineering** philosophy at the skill level: just as `compound-docs` captures solved problems as searchable solution docs, this skill captures lessons as improvements *to the operational tools themselves* — so the next session starts smarter, not just more informed.

## Quick Reference

| Fix Category | Where to Update |
| ------------ | --------------- |
| Incomplete skill | `.claude/skills/<skill>/SKILL.md` (project-local) |
| Common troubleshooting | Add to skill's Troubleshooting section |
| Missing workflow step | Update skill's workflow steps |
| Plugin skill gap | Submit a PR to `aagnone3/agentic-engineering` |
| Missing automation | Add a script or hook |
| Missing validation | Add pre-commit hook or setup check |

## Reflection Process

### Step 1: Identify the Root Cause

Ask:

1. **What went wrong?** (Symptom)
2. **Why did it go wrong?** (Root cause)
3. **What knowledge would have prevented it?** (Missing documentation)
4. **Where should that knowledge live?** (Skill, CLAUDE.md, hook, script, etc.)

### Step 2: Categorize the Fix

| Category | Example | Where to Fix |
| -------- | ------- | ------------ |
| **Incomplete skill** | Skill didn't cover an edge case | `.claude/skills/<skill>/SKILL.md` |
| **Missing troubleshooting** | Common error not documented | Add to skill's troubleshooting section |
| **Missing workflow step** | Forgot to run a prerequisite command | Update skill's workflow steps |
| **Missing automation** | A repetitive check could be scripted | Add a script or hook |
| **Missing validation** | No check for a common misconfiguration | Add pre-commit hook or setup script check |
| **Configuration drift** | Two components used different values for the same thing | Add consistency check |

### Step 3: Implement the Fix

#### For Project-Local Skill Updates

If the gap is in YOUR project's local skills (`.claude/skills/`):

```bash
# Find the relevant skill
ls .claude/skills/

# Read the current skill
cat .claude/skills/<skill-name>/SKILL.md

# Update with new information:
# - Add to troubleshooting section
# - Add to edge cases
# - Update workflow steps
# - Add warnings or notes
```

#### For Plugin Skill Gaps

If the gap is in the agentic-engineering plugin itself:

1. Fork `aagnone3/agentic-engineering`
2. Edit `plugins/agentic-engineering/skills/<skill-name>/SKILL.md`
3. Submit a PR with a clear description of the gap and the fix

#### For CLAUDE.md Updates

```bash
# Update project-level documentation
# Add to relevant section
# Cross-reference related skills
```

### Step 4: Verify the Fix

1. **Would this have prevented the original issue?**
2. **Is the fix in the right place?** (Where would someone look for this?)
3. **Is it discoverable?** (Clear headings, keywords, troubleshooting sections)
4. **Does it explain the "why"?** (Not just what to do, but why it matters)

## Reflection Template

```markdown
## Issue Encountered
[Brief description of what went wrong]

## Root Cause
[Why it happened — the underlying reason]

## Impact
[Time wasted, confusion caused, potential for recurrence]

## Fix Applied
[What was changed and where]

## Prevention
[How this fix prevents future occurrences]
```

## Common Patterns to Watch For

### Undocumented Dependencies

**Pattern**: A feature only works if something else is configured, but that dependency isn't mentioned.
**Fix**: Document the dependency explicitly, with a check or a clear prerequisite.

### Missing Prerequisites

**Pattern**: A skill assumes something exists but doesn't verify it.
**Fix**: Add prerequisite checks and helpful error messages.

### Silent Failures

**Pattern**: Something fails but there's no error message or indication.
**Fix**: Add logging, monitoring, or validation that surfaces the issue early.

### Workflow Gaps

**Pattern**: Steps are missing from documented procedures.
**Example**: "Run dev server" but doesn't mention stopping old processes first.
**Fix**: Update workflow with complete, ordered steps.

### Configuration Consistency

**Pattern**: Different components use different values for the same setting.
**Fix**: Add a consistency check in setup scripts or pre-commit hooks.

## Example Reflection

**Issue**: A command failed silently because a required environment variable wasn't set.

**Root Cause**: The skill documented the command but not the prerequisite env var.

**Impact**: ~15 minutes debugging, easy to hit again.

**Fix Applied**: Added a "Prerequisites" section to the relevant skill listing all required environment variables.

**Prevention**: Future sessions will see the prerequisites upfront and verify them before running.

## When to Use This Skill

Invoke this skill when:

- A bug or issue was caused by **missing or incomplete documentation**
- You had to **debug something that a skill should have prevented**
- A workflow step was **missing** from documented procedures
- You discovered a **gotcha** that others will likely hit too
- The user explicitly asks: "Any skills need updating?"

**Activation keywords**: reflect, skill update, documentation gap, prevent this mistake, improve skills, lessons learned, skill improvement, update skill, skill gap, gotcha, post-mortem, post-implementation review, knowledge capture, what did we learn, update SKILL.md, missing documentation

## How This Differs from `compound-docs`

| | `compound-docs` | `reflect-for-skill-updates` |
|---|---|---|
| **Captures** | Solved problems as searchable solution docs | Gaps in operational tools (skills, workflows, hooks) |
| **Output** | `docs/solutions/<category>/<file>.md` | Updated `SKILL.md` files or new local skills |
| **Trigger** | After confirming a fix worked | After noticing a skill missed something |
| **Purpose** | Build institutional memory of solutions | Improve the tools themselves |

Both are part of compounding engineering — use them together.

## Related Skills

- **compound-docs**: Capture solved problems as searchable knowledge
- **create-agent-skills**: Expert guidance for creating Claude Code skills
- **skill-creator**: Guide for creating effective Claude Code skills
- **setup**: Configure which review agents run for your project
