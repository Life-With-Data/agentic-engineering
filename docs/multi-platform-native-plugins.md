# Extending a Claude Code Plugin to Codex and Cursor

Use one plugin directory as the source of truth, then add thin native manifests
and hook configurations for each harness. Do not copy the skills, scripts, or
MCP configuration into three independent packages.

## 1. Start with a shared plugin root

```text
repo/
├── .claude-plugin/marketplace.json
├── .cursor-plugin/marketplace.json
├── .agents/plugins/marketplace.json
└── plugins/my-plugin/
    ├── .claude-plugin/plugin.json
    ├── .cursor-plugin/plugin.json
    ├── .codex-plugin/plugin.json
    ├── agents/
    ├── commands/
    ├── skills/
    ├── hooks/
    │   ├── hooks-claude.json
    │   ├── hooks-cursor.json
    │   └── hooks-codex.json
    ├── scripts/
    └── .mcp.json
```

Keep reusable workflows in `skills/`, deterministic hook logic in `scripts/`,
and MCP configuration in `.mcp.json`. The manifests should only describe how
each platform discovers those shared files.

| Capability | Claude Code | Cursor | Native Codex |
|------------|-------------|--------|--------------|
| Skills | Yes | Yes | Yes |
| Agents | Yes | Yes | No |
| Commands | Yes | Yes | No |
| MCP | Yes | Yes | Yes |
| Hooks | Yes | Yes | Yes, after user trust |

If an agent or command is essential in Codex, adapt it into a skill or provide a
separate conversion/install path. Do not claim native parity that the target
format does not provide.

## 2. Add the three plugin manifests

Use the same `name`, `version`, and description facts in every manifest.

Claude Code, `plugins/my-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Shared engineering workflows",
  "skills": "./skills/",
  "agents": "./agents/",
  "commands": "./commands/",
  "hooks": "./hooks/hooks-claude.json",
  "mcpServers": "./.mcp.json"
}
```

Cursor, `plugins/my-plugin/.cursor-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "displayName": "My Plugin",
  "version": "1.0.0",
  "description": "Shared engineering workflows",
  "skills": "./skills/",
  "agents": "./agents/",
  "commands": "./commands/",
  "hooks": "./hooks/hooks-cursor.json",
  "mcpServers": "./.mcp.json"
}
```

Codex, `plugins/my-plugin/.codex-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Shared engineering workflows",
  "skills": "./skills/",
  "hooks": "./hooks/hooks-codex.json",
  "mcpServers": "./.mcp.json",
  "interface": {
    "displayName": "My Plugin",
    "shortDescription": "Skills, MCP, and safety hooks"
  }
}
```

All component paths are relative to the nested plugin root. Keep files needed at
runtime inside that root because plugin installers copy or cache the package.

## 3. Add root marketplace catalogs

Each catalog should resolve to the same nested plugin directory.

Claude Code, `.claude-plugin/marketplace.json`:

```json
{
  "name": "acme-plugins",
  "owner": { "name": "Acme" },
  "plugins": [
    { "name": "my-plugin", "source": "./plugins/my-plugin" }
  ]
}
```

Cursor, `.cursor-plugin/marketplace.json`:

```json
{
  "name": "acme-plugins",
  "owner": { "name": "Acme" },
  "metadata": { "pluginRoot": "plugins" },
  "plugins": [
    { "name": "my-plugin", "source": "my-plugin" }
  ]
}
```

Codex, `.agents/plugins/marketplace.json`:

```json
{
  "name": "acme-plugins",
  "interface": { "displayName": "Acme Plugins" },
  "plugins": [
    {
      "name": "my-plugin",
      "source": { "source": "local", "path": "./plugins/my-plugin" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Developer Tools"
    }
  ]
}
```

## 4. Share hook logic, not hook protocols

Keep the policy in one script, but give each platform its own configuration.

| Harness | Script root | Important input differences |
|---------|-------------|-----------------------------|
| Claude Code | `${CLAUDE_PLUGIN_ROOT}` | Claude tool names such as `Bash`, `Write`, and `Edit` |
| Cursor | `./scripts/...` | `beforeShellExecution` sends a top-level `command`; security hooks should set `failClosed: true` |
| Codex | `${PLUGIN_ROOT}` | Uses canonical names such as `apply_patch`; its patch is in `tool_input.command` |

Example Cursor shell gate:

```json
{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      {
        "command": "python3 ./scripts/guard.py",
        "failClosed": true
      }
    ]
  }
}
```

Claude Code and Codex use `PreToolUse` hook groups, but use their respective
root variables in the command. Exit code `0` allows and exit code `2` blocks.

Add a small input adapter before shared hook logic:

- Convert Cursor `{ "command": "..." }` into a common Bash envelope.
- Normalize Cursor's `Shell` alias to `Bash` when needed.
- Preserve Codex's canonical `apply_patch` name. For file-content policies,
  inspect added patch lines in `tool_input.command`; do not pretend the payload
  is Claude `Write` or `Edit` input.
- Fail closed for security enforcement and fail open only for explicitly
  non-critical helpers such as caches or telemetry.

## 5. Document native installation accurately

Claude Code:

```text
/plugin marketplace add https://github.com/acme/plugins
/plugin install my-plugin@acme-plugins
```

Cursor, from a multi-plugin repository:

```text
/add-plugin my-plugin@https://github.com/acme/plugins
```

For local Cursor development, symlink the nested plugin directory, not the
repository root:

```bash
mkdir -p ~/.cursor/plugins/local
ln -s /absolute/path/to/repo/plugins/my-plugin ~/.cursor/plugins/local/my-plugin
```

Codex:

```bash
codex plugin marketplace add acme/plugins
codex plugin add my-plugin --marketplace acme-plugins
```

Tell users to review and trust Codex hooks. Invoke installed Codex skills with
`$skill-name` or through `/skills`, not as Claude-style slash commands.

## 6. Test contracts, not just file existence

At minimum, automate these checks:

1. All three manifest versions match.
2. Every manifest component path exists and remains inside the plugin root.
3. Every marketplace entry resolves to the intended nested plugin.
4. Every hook command references a real script.
5. Cursor security hooks use `failClosed: true`.
6. Real subprocess fixtures cover Claude Bash/Write, Cursor top-level shell and
   `preToolUse`, and Codex Bash/`apply_patch` payloads.
7. Documentation contains real install commands and platform-correct invocation
   syntax.

Also run the platform validators instead of relying solely on home-grown schema
checks:

```bash
# Claude marketplace and nested plugin
claude plugin validate .
claude plugin validate ./plugins/my-plugin

# Cursor official plugin-template validator
node /path/to/cursor/plugin-template/scripts/validate-template.mjs .

# Codex smoke test without modifying the user's normal configuration
tmp="$(mktemp -d)"
mkdir -p "$tmp/codex"
CODEX_HOME="$tmp/codex" codex plugin marketplace add "$PWD"
CODEX_HOME="$tmp/codex" codex plugin add my-plugin --marketplace acme-plugins
```

Before release, install once in each real client and verify component discovery,
MCP registration, one allowed hook action, and one blocked hook action.

## Common mistakes

- Duplicating the plugin tree per platform and letting the copies drift.
- Advertising native Codex agents or commands when only skills are packaged.
- Using `codex plugin install`; the command is `codex plugin add`.
- Treating Codex `apply_patch` as Claude `Write` and silently bypassing file
  guards.
- Leaving Cursor security hooks fail-open.
- Pointing Cursor local installation at the repository root instead of the
  nested plugin root.
- Testing only JSON syntax, hard-coded strings, or file existence.

## References

- [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Cursor plugins](https://cursor.com/docs/plugins)
- [Cursor plugin reference](https://cursor.com/docs/reference/plugins)
- [Cursor hooks](https://cursor.com/docs/hooks)
- [Codex plugin authoring](https://developers.openai.com/codex/plugins/build)
- [Codex skills](https://developers.openai.com/codex/skills)
