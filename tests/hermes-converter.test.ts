import { describe, expect, test } from "bun:test";
import path from "path";
import { load } from "js-yaml";
import { loadClaudePlugin } from "../src/parsers/claude";
import {
  convertClaudeToHermes,
  convertMcpToConfigBlock,
} from "../src/converters/claude-to-hermes";
import { parseFrontmatter } from "../src/utils/frontmatter";
import type { ClaudePlugin } from "../src/types/claude";

const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

const options = {
  agentMode: "subagent",
  inferTemperature: false,
  permissions: "none",
} as const;

describe("convertClaudeToHermes", () => {
  test("converts skills, commands, agents, and the MCP snippet", async () => {
    const plugin = await loadClaudePlugin(fixtureRoot);
    const bundle = convertClaudeToHermes(plugin, options);

    // Shipped skills pass through
    expect(bundle.skillDirs.some((skill) => skill.name === "skill-one")).toBe(
      true
    );

    // Commands become generated skills with normalized names
    const review = bundle.generatedSkills.find(
      (skill) => skill.name === "workflows-review"
    );
    expect(review).toBeDefined();
    const parsed = parseFrontmatter(review!.content);
    expect(parsed.data.name).toBe("workflows-review");
    expect(parsed.data.description).toBe("Run a multi-agent review workflow");

    // Commands with disable-model-invocation are excluded
    expect(
      bundle.generatedSkills.some((skill) => skill.name === "deploy-docs")
    ).toBe(false);

    // Agents become generated skills too
    expect(
      bundle.generatedSkills.some(
        (skill) => skill.name === "repo-research-analyst"
      )
    ).toBe(true);

    // MCP servers pass through as a mcp_servers YAML block
    expect(bundle.mcpServersYaml).toBeDefined();
    const snippet = load(bundle.mcpServersYaml!) as {
      mcp_servers: Record<string, Record<string, unknown>>;
    };
    expect(snippet.mcp_servers.context7?.url).toBe(
      "https://mcp.context7.com/mcp"
    );
    expect(snippet.mcp_servers["local-tooling"]?.command).toBe("echo");
  });

  test("rewrites namespaced slash commands to /skill loads", () => {
    const plugin: ClaudePlugin = {
      root: "/tmp/plugin",
      manifest: { name: "fixture", version: "1.0.0" },
      agents: [],
      commands: [
        {
          name: "workflows:plan",
          description: "Plan workflow",
          body: "Then run /workflows:review and /skill:file-todos.",
          sourcePath: "/tmp/plugin/commands/plan.md",
        },
      ],
      skills: [],
    };

    const bundle = convertClaudeToHermes(plugin, options);
    const skill = bundle.generatedSkills[0];
    expect(skill.name).toBe("workflows-plan");
    expect(skill.content).toContain("/skill workflows-review");
    expect(skill.content).toContain("/skill file-todos");
  });

  test("resolves name collisions between skills, commands, and agents", () => {
    const plugin: ClaudePlugin = {
      root: "/tmp/plugin",
      manifest: { name: "fixture", version: "1.0.0" },
      agents: [
        {
          name: "review",
          description: "Reviewer agent",
          body: "Review things.",
          sourcePath: "/tmp/plugin/agents/review.md",
        },
      ],
      commands: [
        {
          name: "review",
          description: "Review command",
          body: "Review.",
          sourcePath: "/tmp/plugin/commands/review.md",
        },
      ],
      skills: [],
    };

    const bundle = convertClaudeToHermes(plugin, options);
    const names = bundle.generatedSkills.map((skill) => skill.name).sort();
    expect(names).toEqual(["review", "review-2"]);
  });
});

describe("convertMcpToConfigBlock", () => {
  test("prunes undefined fields and keeps Claude snippet shape", () => {
    const yaml = convertMcpToConfigBlock({
      stdio: { command: "bunx", args: ["server"] },
      http: { url: "https://example.com/mcp", headers: { A: "b" } },
    });
    const parsed = load(yaml) as {
      mcp_servers: Record<string, Record<string, unknown>>;
    };
    expect(parsed.mcp_servers.stdio).toEqual({
      command: "bunx",
      args: ["server"],
    });
    expect(parsed.mcp_servers.http).toEqual({
      url: "https://example.com/mcp",
      headers: { A: "b" },
    });
  });
});
