# Security Policy

## Supported versions

`agentic-engineering` is a Claude Code plugin distributed through the
[marketplace](https://github.com/Life-With-Data/agentic-engineering) as a
rolling release. There are no maintained release branches — only the **latest
published version** receives security fixes. If you installed the plugin some
time ago, update to the newest version before reporting a suspected issue, as it
may already be resolved.

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| Older   | :x:                |

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report privately through either channel:

1. **GitHub private vulnerability reporting (preferred).** Open the repository's
   [**Security** tab](https://github.com/Life-With-Data/agentic-engineering/security/advisories)
   and click **Report a vulnerability**. This keeps the report private to the
   maintainers and lets us coordinate a fix and advisory in one place.
2. **Email.** Write to **hello@lifewithdata.org** with enough detail to
   reproduce the issue. Encrypting is optional; if you need a secure channel,
   say so and we'll arrange one.

Please include, as far as you can:

- The affected component (agent, command, skill, hook, or docs tooling) and
  file path.
- A description of the vulnerability and its impact.
- Step-by-step reproduction instructions or a proof of concept.
- Any suggested remediation.

## What to expect

- **Acknowledgement** within 5 business days.
- An initial **assessment** and severity triage shortly after.
- Coordinated disclosure: we'll agree on a timeline with you and credit you in
  the advisory unless you prefer to remain anonymous.

Because this project ships prompts, skills, and automation that run inside a
user's Claude Code environment, we're especially interested in reports involving
prompt injection, command execution via hooks, exfiltration paths, or any
component that escalates beyond its documented scope.
