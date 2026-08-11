import { describe, expect, test } from "bun:test";
import { existsSync, promises as fs } from "fs";
import path from "path";
import os from "os";
import { writeHermesBundle } from "../src/targets/hermes";
import type { HermesBundle } from "../src/types/hermes";

describe("writeHermesBundle", () => {
  test("writes skills, generated skills, and the MCP snippet", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "hermes-writer-"));
    const outputRoot = path.join(tempRoot, ".hermes");

    const bundle: HermesBundle = {
      skillDirs: [
        {
          name: "skill-one",
          sourceDir: path.join(
            import.meta.dir,
            "fixtures",
            "sample-plugin",
            "skills",
            "skill-one"
          ),
        },
      ],
      generatedSkills: [
        {
          name: "workflows-review",
          content: "---\nname: workflows-review\n---\n\nBody",
        },
      ],
      mcpServersYaml: "mcp_servers:\n  context7:\n    url: https://mcp.context7.com/mcp\n",
    };

    await writeHermesBundle(outputRoot, bundle);

    expect(
      existsSync(path.join(outputRoot, "skills", "skill-one", "SKILL.md"))
    ).toBe(true);
    expect(
      existsSync(
        path.join(outputRoot, "skills", "workflows-review", "SKILL.md")
      )
    ).toBe(true);
    const snippetPath = path.join(
      outputRoot,
      "agentic-engineering",
      "mcp-servers.yaml"
    );
    expect(existsSync(snippetPath)).toBe(true);
    expect(await fs.readFile(snippetPath, "utf8")).toContain("mcp_servers:");
  });

  test("nests under .hermes when the output root is a plain directory", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "hermes-nest-"));

    const bundle: HermesBundle = {
      skillDirs: [],
      generatedSkills: [{ name: "one", content: "---\nname: one\n---\n\nX" }],
    };

    await writeHermesBundle(tempRoot, bundle);

    expect(
      existsSync(path.join(tempRoot, ".hermes", "skills", "one", "SKILL.md"))
    ).toBe(true);
  });
});
