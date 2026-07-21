import { defineCommand } from "citty";
import path from "path";
import { pathExists } from "../utils/files";

// The worktree manager ships with the package as a self-contained bash
// script bundled in the wf-development skill. Resolve it relative to this
// file so the command works from a checkout, a git install
// (npx github:Life-With-Data/agentic-engineering), or a linked package.
function resolveScriptPath(): string {
  const override = process.env.AGENTIC_PLUGIN_WORKTREE_SCRIPT;
  if (override && override.trim()) return path.resolve(override.trim());
  const packageRoot = path.resolve(import.meta.dir, "..", "..");
  return path.join(
    packageRoot,
    "plugins",
    "agentic-engineering",
    "skills",
    "wf-development",
    "scripts",
    "worktree-manager.sh"
  );
}

export default defineCommand({
  meta: {
    name: "worktrees",
    description:
      "Run the bundled git worktree manager against the current repository " +
      "(sync | finish <name> | gc | list | create | ...)",
  },
  async run({ rawArgs }) {
    const scriptPath = resolveScriptPath();
    if (!(await pathExists(scriptPath))) {
      throw new Error(
        `worktree-manager.sh not found at ${scriptPath}. ` +
          "The package installation looks incomplete; reinstall from " +
          "github:Life-With-Data/agentic-engineering."
      );
    }

    const bash = Bun.which("bash");
    if (!bash) {
      throw new Error(
        "bash is required to run the worktree manager but was not found on PATH."
      );
    }

    // Pass every argument through verbatim; the script owns its own CLI
    // (subcommands, flags like --force, positional base branches).
    const passthrough = rawArgs[0] === "--" ? rawArgs.slice(1) : rawArgs;
    const proc = Bun.spawn([bash, scriptPath, ...passthrough], {
      cwd: process.cwd(),
      stdin: "inherit",
      stdout: "inherit",
      stderr: "inherit",
    });
    process.exit(await proc.exited);
  },
});
