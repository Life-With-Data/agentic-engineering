import { formatFrontmatter } from "../utils/frontmatter";
import { normalizeName, replaceSlashCommands, sanitizeDescription, uniqueName } from "../utils/names";
import type {
  ClaudeAgent,
  ClaudeCommand,
  ClaudeMcpServer,
  ClaudePlugin,
} from "../types/claude";
import type {
  PiBundle,
  PiGeneratedSkill,
  PiMcporterConfig,
  PiMcporterServer,
} from "../types/pi";
import type { ConvertOptions } from "./claude-to-opencode";
import { PI_COMPAT_EXTENSION_SOURCE } from "../templates/pi/compat-extension";

export function convertClaudeToPi(
  plugin: ClaudePlugin,
  _options: ConvertOptions
): PiBundle {
  const promptNames = new Set<string>();
  const usedSkillNames = new Set<string>(
    plugin.skills.map((skill) => normalizeName(skill.name))
  );

  const prompts = plugin.commands
    .filter((command) => !command.disableModelInvocation)
    .map((command) => convertPrompt(command, promptNames));

  const generatedSkills = plugin.agents.map((agent) =>
    convertAgent(agent, usedSkillNames)
  );

  const extensions = [
    {
      name: "agentic-engineering-compat.ts",
      content: PI_COMPAT_EXTENSION_SOURCE,
    },
  ];

  return {
    prompts,
    skillDirs: plugin.skills.map((skill) => ({
      name: skill.name,
      sourceDir: skill.sourceDir,
    })),
    generatedSkills,
    extensions,
    mcporterConfig: plugin.mcpServers
      ? convertMcpToMcporter(plugin.mcpServers)
      : undefined,
  };
}

function convertPrompt(command: ClaudeCommand, usedNames: Set<string>) {
  const name = uniqueName(normalizeName(command.name), usedNames);
  const frontmatter: Record<string, unknown> = {
    description: command.description,
    "argument-hint": command.argumentHint,
  };

  let body = transformContentForPi(command.body);
  body = appendCompatibilityNoteIfNeeded(body);

  return {
    name,
    content: formatFrontmatter(frontmatter, body.trim()),
  };
}

function convertAgent(
  agent: ClaudeAgent,
  usedNames: Set<string>
): PiGeneratedSkill {
  const name = uniqueName(normalizeName(agent.name), usedNames);
  const description = sanitizeDescription(
    agent.description ?? `Converted from Claude agent ${agent.name}`
  );

  const frontmatter: Record<string, unknown> = {
    name,
    description,
  };

  const sections: string[] = [];
  if (agent.capabilities && agent.capabilities.length > 0) {
    sections.push(
      `## Capabilities\n${agent.capabilities
        .map((capability) => `- ${capability}`)
        .join("\n")}`
    );
  }

  const body = [
    ...sections,
    agent.body.trim().length > 0
      ? agent.body.trim()
      : `Instructions converted from the ${agent.name} agent.`,
  ].join("\n\n");

  return {
    name,
    content: formatFrontmatter(frontmatter, body),
  };
}

function transformContentForPi(body: string): string {
  let result = body;

  // Task repo-research-analyst(feature_description)
  // -> Run subagent with agent="repo-research-analyst" and task="feature_description"
  const taskPattern = /^(\s*-?\s*)Task\s+([a-z][a-z0-9-]*)\(([^)]+)\)/gm;
  result = result.replace(
    taskPattern,
    (_match, prefix: string, agentName: string, args: string) => {
      const skillName = normalizeName(agentName);
      const trimmedArgs = args.trim().replace(/\s+/g, " ");
      return `${prefix}Run subagent with agent=\"${skillName}\" and task=\"${trimmedArgs}\".`;
    }
  );

  // Claude-specific tool references
  result = result.replace(/\bAskUserQuestion\b/g, "ask_user_question");
  result = result.replace(
    /\bTodoWrite\b/g,
    "file-based todos (todos/ + /skill:file-todos)"
  );
  result = result.replace(
    /\bTodoRead\b/g,
    "file-based todos (todos/ + /skill:file-todos)"
  );

  // /command-name or /workflows:command-name -> /workflows-command-name
  result = replaceSlashCommands(result, (commandName) => {
    if (commandName.startsWith("skill:")) {
      return `/skill:${normalizeName(commandName.slice("skill:".length))}`;
    }
    const withoutPrefix = commandName.startsWith("prompts:")
      ? commandName.slice("prompts:".length)
      : commandName;
    return `/${normalizeName(withoutPrefix)}`;
  });

  return result;
}

function appendCompatibilityNoteIfNeeded(body: string): string {
  if (!/\bmcp\b/i.test(body)) return body;

  const note = [
    "",
    "## Pi + MCPorter note",
    "For MCP access in Pi, use MCPorter via the generated tools:",
    "- `mcporter_list` to inspect available MCP tools",
    "- `mcporter_call` to invoke a tool",
    "",
  ].join("\n");

  return body + note;
}

export function convertMcpToMcporter(
  servers: Record<string, ClaudeMcpServer>
): PiMcporterConfig {
  const mcpServers: Record<string, PiMcporterServer> = {};

  for (const [name, server] of Object.entries(servers)) {
    if (server.command) {
      mcpServers[name] = {
        command: server.command,
        args: server.args,
        env: server.env,
        headers: server.headers,
      };
      continue;
    }

    if (server.url) {
      mcpServers[name] = {
        baseUrl: server.url,
        headers: server.headers,
      };
    }
  }

  return { mcpServers };
}
