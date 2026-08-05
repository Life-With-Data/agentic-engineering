import { describe, expect, test } from "bun:test";
import { existsSync, promises as fs } from "fs";
import path from "path";
import os from "os";
import { runGit } from "./helpers";

describe("CLI", () => {
  test("install converts fixture plugin to OpenCode output", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-opencode-"));
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "install",
        fixtureRoot,
        "--to",
        "opencode",
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");
    expect(existsSync(path.join(tempRoot, "opencode.json"))).toBe(true);
    expect(
      existsSync(
        path.join(tempRoot, ".opencode", "agents", "repo-research-analyst.md")
      )
    ).toBe(true);
    expect(
      existsSync(
        path.join(tempRoot, ".opencode", "agents", "security-sentinel.md")
      )
    ).toBe(true);
    expect(
      existsSync(
        path.join(tempRoot, ".opencode", "skills", "skill-one", "SKILL.md")
      )
    ).toBe(true);
    expect(
      existsSync(
        path.join(tempRoot, ".opencode", "plugins", "converted-hooks.ts")
      )
    ).toBe(true);
  });

  test("install copies fixture plugin for Claude passthrough output", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-claude-install-"));
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      ["bun", "run", "src/index.ts", "install", fixtureRoot, "--to", "claude", "--output", tempRoot],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");
    expect(existsSync(path.join(tempRoot, "agentic-engineering", ".claude-plugin", "plugin.json"))).toBe(true);
    expect(existsSync(path.join(tempRoot, "agentic-engineering", "agents", "agent-one.md"))).toBe(true);
  });

  test("install converts fixture plugin to Cursor output", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-cursor-"));
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "install",
        fixtureRoot,
        "--to",
        "cursor",
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");
    expect(existsSync(path.join(tempRoot, ".cursor", "rules", "repo-research-analyst.mdc"))).toBe(true);
    expect(existsSync(path.join(tempRoot, ".cursor", "rules", "security-sentinel.mdc"))).toBe(true);
    expect(existsSync(path.join(tempRoot, ".cursor", "commands", "review.md"))).toBe(true);
    expect(existsSync(path.join(tempRoot, ".cursor", "skills", "skill-one", "SKILL.md"))).toBe(true);
    expect(existsSync(path.join(tempRoot, ".cursor", "mcp.json"))).toBe(true);
  });

  test("install defaults output to ~/.config/opencode", async () => {
    const tempRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-local-default-")
    );
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const repoRoot = path.join(import.meta.dir, "..");
    const proc = Bun.spawn(
      [
        "bun",
        "run",
        path.join(repoRoot, "src", "index.ts"),
        "install",
        fixtureRoot,
        "--to",
        "opencode",
      ],
      {
        cwd: tempRoot,
        stdout: "pipe",
        stderr: "pipe",
        env: {
          ...process.env,
          HOME: tempRoot,
        },
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");
    // OpenCode global config lives at ~/.config/opencode per XDG spec
    expect(
      existsSync(path.join(tempRoot, ".config", "opencode", "opencode.json"))
    ).toBe(true);
    expect(
      existsSync(
        path.join(
          tempRoot,
          ".config",
          "opencode",
          "agents",
          "repo-research-analyst.md"
        )
      )
    ).toBe(true);
  });

  test("list returns plugins in a temp workspace", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-list-"));
    const pluginsRoot = path.join(
      tempRoot,
      "plugins",
      "demo-plugin",
      ".claude-plugin"
    );
    await fs.mkdir(pluginsRoot, { recursive: true });
    await fs.writeFile(
      path.join(pluginsRoot, "plugin.json"),
      '{\n  "name": "demo-plugin",\n  "version": "1.0.0"\n}\n'
    );

    const repoRoot = path.join(import.meta.dir, "..");
    const proc = Bun.spawn(
      ["bun", "run", path.join(repoRoot, "src", "index.ts"), "list"],
      {
        cwd: tempRoot,
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("demo-plugin");
  });

  test("install pulls from GitHub when local path is missing", async () => {
    const tempRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-github-install-")
    );
    const workspaceRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-github-workspace-")
    );
    const repoRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-github-repo-")
    );
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");
    const pluginRoot = path.join(repoRoot, "plugins", "agentic-engineering");

    await fs.mkdir(path.dirname(pluginRoot), { recursive: true });
    await fs.cp(fixtureRoot, pluginRoot, { recursive: true });

    await runGit(["init"], repoRoot);
    await runGit(["add", "."], repoRoot);
    await runGit(["commit", "-m", "fixture"], repoRoot);

    const projectRoot = path.join(import.meta.dir, "..");
    const proc = Bun.spawn(
      [
        "bun",
        "run",
        path.join(projectRoot, "src", "index.ts"),
        "install",
        "agentic-engineering",
        "--to",
        "opencode",
      ],
      {
        cwd: workspaceRoot,
        stdout: "pipe",
        stderr: "pipe",
        env: {
          ...process.env,
          HOME: tempRoot,
          AGENTIC_PLUGIN_GITHUB_SOURCE: repoRoot,
        },
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");
    // OpenCode global config lives at ~/.config/opencode per XDG spec
    expect(
      existsSync(path.join(tempRoot, ".config", "opencode", "opencode.json"))
    ).toBe(true);
    expect(
      existsSync(
        path.join(
          tempRoot,
          ".config",
          "opencode",
          "agents",
          "repo-research-analyst.md"
        )
      )
    ).toBe(true);
  });

  test("install by name ignores same-named local directory", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-shadow-"));
    const workspaceRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-shadow-workspace-")
    );
    const repoRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-shadow-repo-")
    );

    // Create a directory with the plugin name that is NOT a valid plugin
    const shadowDir = path.join(workspaceRoot, "agentic-engineering");
    await fs.mkdir(shadowDir, { recursive: true });
    await fs.writeFile(path.join(shadowDir, "README.md"), "Not a plugin");

    // Set up a fake GitHub source with a valid plugin
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");
    const pluginRoot = path.join(repoRoot, "plugins", "agentic-engineering");
    await fs.mkdir(path.dirname(pluginRoot), { recursive: true });
    await fs.cp(fixtureRoot, pluginRoot, { recursive: true });

    await runGit(["init"], repoRoot);
    await runGit(["add", "."], repoRoot);
    await runGit(["commit", "-m", "fixture"], repoRoot);

    const projectRoot = path.join(import.meta.dir, "..");
    const proc = Bun.spawn(
      [
        "bun",
        "run",
        path.join(projectRoot, "src", "index.ts"),
        "install",
        "agentic-engineering",
        "--to",
        "opencode",
        "--output",
        tempRoot,
      ],
      {
        cwd: workspaceRoot,
        stdout: "pipe",
        stderr: "pipe",
        env: {
          ...process.env,
          HOME: tempRoot,
          AGENTIC_PLUGIN_GITHUB_SOURCE: repoRoot,
        },
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    // Should succeed by fetching from GitHub, NOT failing on the local shadow directory
    expect(stdout).toContain("Installed agentic-engineering");
    expect(existsSync(path.join(tempRoot, "opencode.json"))).toBe(true);
  });

  test("convert writes OpenCode output", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-convert-"));
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "convert",
        fixtureRoot,
        "--to",
        "opencode",
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Converted agentic-engineering");
    expect(existsSync(path.join(tempRoot, "opencode.json"))).toBe(true);
  });

  test("convert supports explicit Claude passthrough target", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-claude-convert-"));
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "convert",
        fixtureRoot,
        "--to",
        "claude",
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Converted agentic-engineering to claude");
    expect(existsSync(path.join(tempRoot, "agentic-engineering", ".claude-plugin", "plugin.json"))).toBe(true);
    expect(existsSync(path.join(tempRoot, "agentic-engineering", "commands", "command-one.md"))).toBe(true);
  });

  test("convert supports --codex-home for codex output", async () => {
    const tempRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-codex-home-")
    );
    const codexRoot = path.join(tempRoot, ".codex");
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "convert",
        fixtureRoot,
        "--to",
        "codex",
        "--codex-home",
        codexRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Converted agentic-engineering");
    expect(stdout).toContain(codexRoot);
    expect(
      existsSync(path.join(codexRoot, "prompts", "workflows-review.md"))
    ).toBe(true);
    expect(
      existsSync(
        path.join(codexRoot, "skills", "workflows-review", "SKILL.md")
      )
    ).toBe(true);
    expect(existsSync(path.join(codexRoot, "AGENTS.md"))).toBe(true);
  });

  test("install supports --also with codex output", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-also-"));
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");
    const codexRoot = path.join(tempRoot, ".codex");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "install",
        fixtureRoot,
        "--to",
        "opencode",
        "--also",
        "codex",
        "--codex-home",
        codexRoot,
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");
    expect(stdout).toContain(codexRoot);
    expect(
      existsSync(path.join(codexRoot, "prompts", "workflows-review.md"))
    ).toBe(true);
    expect(
      existsSync(
        path.join(codexRoot, "skills", "workflows-review", "SKILL.md")
      )
    ).toBe(true);
    expect(
      existsSync(path.join(codexRoot, "skills", "skill-one", "SKILL.md"))
    ).toBe(true);
    expect(existsSync(path.join(codexRoot, "AGENTS.md"))).toBe(true);
  });

  test("convert supports --pi-home for pi output", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-pi-home-"));
    const piRoot = path.join(tempRoot, ".pi");
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "convert",
        fixtureRoot,
        "--to",
        "pi",
        "--pi-home",
        piRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Converted agentic-engineering");
    expect(stdout).toContain(piRoot);
    expect(
      existsSync(path.join(piRoot, "prompts", "workflows-review.md"))
    ).toBe(true);
    expect(
      existsSync(
        path.join(piRoot, "skills", "repo-research-analyst", "SKILL.md")
      )
    ).toBe(true);
    expect(
      existsSync(
        path.join(piRoot, "extensions", "agentic-engineering-compat.ts")
      )
    ).toBe(true);
    expect(
      existsSync(path.join(piRoot, "agentic-engineering", "mcporter.json"))
    ).toBe(true);
  });

  test("install supports --also with pi output", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "cli-also-pi-"));
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");
    const piRoot = path.join(tempRoot, ".pi");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "install",
        fixtureRoot,
        "--to",
        "opencode",
        "--also",
        "pi",
        "--pi-home",
        piRoot,
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");
    expect(stdout).toContain(piRoot);
    expect(
      existsSync(path.join(piRoot, "prompts", "workflows-review.md"))
    ).toBe(true);
    expect(
      existsSync(
        path.join(piRoot, "extensions", "agentic-engineering-compat.ts")
      )
    ).toBe(true);
  });

  test("install --to opencode uses permissions:none by default", async () => {
    const tempRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-perms-none-")
    );
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "install",
        fixtureRoot,
        "--to",
        "opencode",
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");

    const opencodeJsonPath = path.join(tempRoot, "opencode.json");
    const content = await fs.readFile(opencodeJsonPath, "utf-8");
    const json = JSON.parse(content);

    expect(json).not.toHaveProperty("permission");
    expect(json).not.toHaveProperty("tools");
  });

  test("install --to opencode --permissions broad writes permission block", async () => {
    const tempRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "cli-perms-broad-")
    );
    const fixtureRoot = path.join(import.meta.dir, "fixtures", "sample-plugin");

    const proc = Bun.spawn(
      [
        "bun",
        "run",
        "src/index.ts",
        "install",
        fixtureRoot,
        "--to",
        "opencode",
        "--permissions",
        "broad",
        "--output",
        tempRoot,
      ],
      {
        cwd: path.join(import.meta.dir, ".."),
        stdout: "pipe",
        stderr: "pipe",
      }
    );

    const exitCode = await proc.exited;
    const stdout = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();

    if (exitCode !== 0) {
      throw new Error(
        `CLI failed (exit ${exitCode}).\nstdout: ${stdout}\nstderr: ${stderr}`
      );
    }

    expect(stdout).toContain("Installed agentic-engineering");

    const opencodeJsonPath = path.join(tempRoot, "opencode.json");
    const content = await fs.readFile(opencodeJsonPath, "utf-8");
    const json = JSON.parse(content);

    expect(json).toHaveProperty("permission");
    expect(json.permission).not.toBeNull();
  });
});
