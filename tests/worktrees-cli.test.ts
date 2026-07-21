import { describe, expect, test } from "bun:test";
import { promises as fs } from "fs";
import path from "path";
import os from "os";

const repoRoot = path.join(import.meta.dir, "..");
const cliEntry = path.join(repoRoot, "src", "index.ts");

type CliResult = {
  exitCode: number;
  stdout: string;
  stderr: string;
};

async function runWorktreesCli(
  args: string[],
  cwd: string,
  env?: NodeJS.ProcessEnv
): Promise<CliResult> {
  const proc = Bun.spawn(["bun", "run", cliEntry, "worktrees", ...args], {
    cwd,
    stdout: "pipe",
    stderr: "pipe",
    env: env ?? process.env,
  });
  const exitCode = await proc.exited;
  const stdout = await new Response(proc.stdout).text();
  const stderr = await new Response(proc.stderr).text();
  return { exitCode, stdout, stderr };
}

async function runGit(args: string[], cwd: string): Promise<void> {
  const proc = Bun.spawn(["git", ...args], {
    cwd,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: "Test",
      GIT_AUTHOR_EMAIL: "test@example.com",
      GIT_COMMITTER_NAME: "Test",
      GIT_COMMITTER_EMAIL: "test@example.com",
    },
  });
  const exitCode = await proc.exited;
  const stderr = await new Response(proc.stderr).text();
  if (exitCode !== 0) {
    throw new Error(
      `git ${args.join(" ")} failed (exit ${exitCode}).\nstderr: ${stderr}`
    );
  }
}

describe("worktrees CLI passthrough", () => {
  test("passes all arguments through to the script in the caller's cwd", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "wt-cli-args-"));
    const stubScript = path.join(tempRoot, "stub.sh");
    await fs.writeFile(
      stubScript,
      '#!/bin/bash\necho "args:$@"\necho "cwd:$(pwd -P)"\n'
    );

    const result = await runWorktreesCli(
      ["finish", "my-branch", "--force"],
      tempRoot,
      { ...process.env, AGENTIC_PLUGIN_WORKTREE_SCRIPT: stubScript }
    );

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain("args:finish my-branch --force");
    expect(result.stdout).toContain(`cwd:${await fs.realpath(tempRoot)}`);
  });

  test("propagates the script's exit code", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "wt-cli-exit-"));
    const stubScript = path.join(tempRoot, "stub.sh");
    await fs.writeFile(stubScript, "#!/bin/bash\nexit 7\n");

    const result = await runWorktreesCli(["sync"], tempRoot, {
      ...process.env,
      AGENTIC_PLUGIN_WORKTREE_SCRIPT: stubScript,
    });

    expect(result.exitCode).toBe(7);
  });

  test("fails with a clear message when the bundled script is missing", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "wt-cli-miss-"));

    const result = await runWorktreesCli(["sync"], tempRoot, {
      ...process.env,
      AGENTIC_PLUGIN_WORKTREE_SCRIPT: path.join(tempRoot, "nope.sh"),
    });

    expect(result.exitCode).not.toBe(0);
    expect(result.stderr).toContain("worktree-manager.sh not found");
  });

  test("resolves the bundled worktree-manager.sh from the package by default", async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "wt-cli-real-"));
    await runGit(["init"], tempRoot);
    await runGit(["commit", "--allow-empty", "-m", "init"], tempRoot);

    const env = { ...process.env };
    delete env.AGENTIC_PLUGIN_WORKTREE_SCRIPT;
    const result = await runWorktreesCli(["list"], tempRoot, env);

    expect(result.exitCode).toBe(0);
    // Output proves the real bundled script executed against the temp repo,
    // which has no managed worktrees yet.
    expect(result.stdout).toContain("Available worktrees");
    expect(result.stdout).toContain("No worktrees found");
  });
});
