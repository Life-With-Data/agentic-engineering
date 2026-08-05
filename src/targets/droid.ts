import path from "path"
import { copyDir, ensureDir, writeText } from "../utils/files"
import type { DroidBundle } from "../types/droid"

export async function writeDroidBundle(outputRoot: string, bundle: DroidBundle): Promise<void> {
  const paths = resolveDroidPaths(outputRoot)
  await ensureDir(paths.root)

  if (bundle.commands.length > 0) {
    await ensureDir(paths.commandsDir)
    for (const command of bundle.commands) {
      await writeText(path.join(paths.commandsDir, `${command.name}.md`), command.content + "\n")
    }
  }

  if (bundle.droids.length > 0) {
    await ensureDir(paths.droidsDir)
    for (const droid of bundle.droids) {
      await writeText(path.join(paths.droidsDir, `${droid.name}.md`), droid.content + "\n")
    }
  }

  if (bundle.skillDirs.length > 0) {
    await ensureDir(paths.skillsDir)
    for (const skill of bundle.skillDirs) {
      await copyDir(skill.sourceDir, path.join(paths.skillsDir, skill.name))
    }
  }
}

function resolveDroidPaths(outputRoot: string) {
  // Write directly into a .factory root; otherwise nest under .factory.
  const dir = path.basename(outputRoot) === ".factory" ? outputRoot : path.join(outputRoot, ".factory")
  return {
    root: outputRoot,
    commandsDir: path.join(dir, "commands"),
    droidsDir: path.join(dir, "droids"),
    skillsDir: path.join(dir, "skills"),
  }
}
