import { defineCommand } from "citty"
import { promises as fs } from "fs"
import os from "os"
import path from "path"
import { loadClaudePlugin } from "../parsers/claude"
import { targets } from "../targets"
import { pathExists } from "../utils/files"
import type { ConvertOptions, PermissionMode } from "../converters/claude-to-opencode"
import { ensureCodexAgentsFile } from "../utils/codex-agents"
import { expandHome, resolveTargetHome } from "../utils/resolve-home"

const permissionModes: PermissionMode[] = ["none", "broad", "from-commands"]

// `convert` and `install` share args and run body. install additionally
// resolves plugin names against GitHub and defaults output paths relative
// to the current project instead of the source checkout.
const sharedArgs = {
  to: {
    type: "string",
    default: "opencode",
    description:
      "Target format (claude | opencode | codex | droid | cursor | pi | copilot | gemini | kiro)",
  },
  output: {
    type: "string",
    alias: "o",
    description: "Output directory (project root)",
  },
  codexHome: {
    type: "string",
    alias: "codex-home",
    description: "Write Codex output to this .codex root (ex: ~/.codex)",
  },
  piHome: {
    type: "string",
    alias: "pi-home",
    description: "Write Pi output to this Pi root (ex: ~/.pi/agent or ./.pi)",
  },
  also: {
    type: "string",
    description: "Comma-separated extra targets to generate (ex: codex)",
  },
  agentMode: {
    type: "string",
    default: "subagent",
    description: "Default agent mode: primary | subagent",
  },
  inferTemperature: {
    type: "boolean",
    default: true,
    description: "Infer agent temperature from name/description",
  },
} as const

export const convert = defineCommand({
  meta: {
    name: "convert",
    description: "Convert a Claude Code plugin into another format",
  },
  args: {
    source: {
      type: "positional",
      required: true,
      description: "Path to the Claude plugin directory",
    },
    permissions: {
      type: "string",
      default: "broad",
      description: "Permission mapping: none | broad | from-commands",
    },
    ...sharedArgs,
  },
  async run({ args }) {
    await runConversion(args, "convert")
  },
})

export const install = defineCommand({
  meta: {
    name: "install",
    description: "Install and convert a Claude plugin",
  },
  args: {
    plugin: {
      type: "positional",
      required: true,
      description: "Plugin name or path",
    },
    permissions: {
      type: "string",
      default: "none", // Default is "none" -- writing global permissions to opencode.json pollutes user config. See ADR-003.
      description:
        "Permission mapping written to opencode.json: none (default) | broad | from-command",
    },
    ...sharedArgs,
  },
  async run({ args }) {
    await runConversion(args, "install")
  },
})

type Mode = "convert" | "install"

async function runConversion(args: Record<string, unknown>, mode: Mode): Promise<void> {
  const targetName = String(args.to)
  const target = targets[targetName]
  if (!target) {
    throw new Error(`Unknown target: ${targetName}`)
  }

  const permissions = String(args.permissions)
  if (!permissionModes.includes(permissions as PermissionMode)) {
    throw new Error(`Unknown permissions mode: ${permissions}`)
  }

  const source = String(args.source ?? args.plugin)
  const resolvedPlugin =
    mode === "install" ? await resolvePluginPath(source) : { path: source }

  try {
    const plugin = await loadClaudePlugin(resolvedPlugin.path)
    const outputRoot = resolveOutputRoot(args.output, mode)
    const codexHome = resolveTargetHome(args.codexHome, path.join(os.homedir(), ".codex"))
    const piHome = resolveTargetHome(args.piHome, path.join(os.homedir(), ".pi", "agent"))

    const options: ConvertOptions = {
      agentMode: String(args.agentMode) === "primary" ? "primary" : "subagent",
      inferTemperature: Boolean(args.inferTemperature),
      permissions: permissions as PermissionMode,
    }

    // Project-relative targets (.cursor, .gemini, .kiro, .github, claude) hang
    // off the output root for convert, but off the current project for install
    // unless --output was given.
    const hasExplicitOutput = Boolean(args.output && String(args.output).trim())
    const installBase = hasExplicitOutput ? outputRoot : process.cwd()

    const report = (root: string) => {
      if (mode === "install") {
        console.log(`Installed ${plugin.manifest.name} to ${root}`)
      } else {
        console.log(`Converted ${plugin.manifest.name} to ${targetName} at ${root}`)
      }
    }

    const primaryOutputRoot = resolveTargetOutputRoot(targetName, outputRoot, {
      projectBase: mode === "install" ? installBase : outputRoot,
      codexHome,
      piHome,
    })
    const bundle = target.convert(plugin, options)
    await target.write(primaryOutputRoot, bundle)
    report(primaryOutputRoot)

    const extraTargets = parseExtraTargets(args.also)
    const allTargets = [targetName, ...extraTargets]
    for (const extra of extraTargets) {
      const handler = targets[extra]
      if (!handler) {
        console.warn(`Skipping unknown target: ${extra}`)
        continue
      }
      const extraOutputRoot = path.join(outputRoot, extra)
      const extraRoot = resolveTargetOutputRoot(extra, extraOutputRoot, {
        projectBase: mode === "install" ? installBase : extraOutputRoot,
        codexHome,
        piHome,
      })
      const extraBundle = handler.convert(plugin, options)
      await handler.write(extraRoot, extraBundle)
      if (mode === "install") {
        console.log(`Installed ${plugin.manifest.name} to ${extraRoot}`)
      } else {
        console.log(`Converted ${plugin.manifest.name} to ${extra} at ${extraRoot}`)
      }
    }

    if (allTargets.includes("codex")) {
      await ensureCodexAgentsFile(codexHome)
    }
  } finally {
    if (resolvedPlugin.cleanup) {
      await resolvedPlugin.cleanup()
    }
  }
}

function parseExtraTargets(value: unknown): string[] {
  if (!value) return []
  return String(value)
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function resolveOutputRoot(value: unknown, mode: Mode): string {
  if (value && String(value).trim()) {
    const expanded = expandHome(String(value).trim())
    return path.resolve(expanded)
  }
  if (mode === "install") {
    // OpenCode global config lives at ~/.config/opencode per XDG spec
    // See: https://opencode.ai/docs/config/
    return path.join(os.homedir(), ".config", "opencode")
  }
  return process.cwd()
}

function resolveTargetOutputRoot(
  targetName: string,
  outputRoot: string,
  roots: { projectBase: string; codexHome: string; piHome: string },
): string {
  switch (targetName) {
    case "codex":
      return roots.codexHome
    case "pi":
      return roots.piHome
    case "droid":
      return path.join(os.homedir(), ".factory")
    case "cursor":
      return path.join(roots.projectBase, ".cursor")
    case "gemini":
      return path.join(roots.projectBase, ".gemini")
    case "copilot":
      return path.join(roots.projectBase, ".github")
    case "kiro":
      return path.join(roots.projectBase, ".kiro")
    case "claude":
      return roots.projectBase
    default:
      return outputRoot
  }
}

type ResolvedPluginPath = {
  path: string
  cleanup?: () => Promise<void>
}

async function resolvePluginPath(input: string): Promise<ResolvedPluginPath> {
  // Only treat as a local path if it explicitly looks like one
  if (input.startsWith(".") || input.startsWith("/") || input.startsWith("~")) {
    const expanded = expandHome(input)
    const directPath = path.resolve(expanded)
    if (await pathExists(directPath)) return { path: directPath }
    throw new Error(`Local plugin path not found: ${directPath}`)
  }

  // Otherwise, always fetch the latest from GitHub
  return await resolveGitHubPluginPath(input)
}

async function resolveGitHubPluginPath(pluginName: string): Promise<ResolvedPluginPath> {
  const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "agentic-plugin-"))
  const source = resolveGitHubSource()
  try {
    await cloneGitHubRepo(source, tempRoot)
  } catch (error) {
    await fs.rm(tempRoot, { recursive: true, force: true })
    throw error
  }

  const pluginPath = path.join(tempRoot, "plugins", pluginName)
  if (!(await pathExists(pluginPath))) {
    await fs.rm(tempRoot, { recursive: true, force: true })
    throw new Error(`Could not find plugin ${pluginName} in ${source}.`)
  }

  return {
    path: pluginPath,
    cleanup: async () => {
      await fs.rm(tempRoot, { recursive: true, force: true })
    },
  }
}

function resolveGitHubSource(): string {
  const override = process.env.AGENTIC_PLUGIN_GITHUB_SOURCE
  if (override && override.trim()) return override.trim()
  return "https://github.com/aagnone3/agentic-engineering"
}

async function cloneGitHubRepo(source: string, destination: string): Promise<void> {
  const proc = Bun.spawn(["git", "clone", "--depth", "1", source, destination], {
    stdout: "pipe",
    stderr: "pipe",
  })
  const exitCode = await proc.exited
  const stderr = await new Response(proc.stderr).text()
  if (exitCode !== 0) {
    throw new Error(`Failed to clone ${source}. ${stderr.trim()}`)
  }
}
