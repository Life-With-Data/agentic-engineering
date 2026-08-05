import { promises as fs } from "fs"
import path from "path"

export async function backupFile(filePath: string): Promise<string | null> {
  if (!(await pathExists(filePath))) return null

  try {
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-")
    const backupPath = `${filePath}.bak.${timestamp}`
    await fs.copyFile(filePath, backupPath)
    return backupPath
  } catch {
    return null
  }
}

export async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath)
    return true
  } catch {
    return false
  }
}

export async function ensureDir(dirPath: string): Promise<void> {
  await fs.mkdir(dirPath, { recursive: true })
}

export async function readText(filePath: string): Promise<string> {
  return fs.readFile(filePath, "utf8")
}

export async function readJson<T>(filePath: string): Promise<T> {
  const raw = await readText(filePath)
  return JSON.parse(raw) as T
}

export async function writeText(filePath: string, content: string): Promise<void> {
  await ensureDir(path.dirname(filePath))
  await fs.writeFile(filePath, content, "utf8")
}

export async function writeJson(filePath: string, data: unknown): Promise<void> {
  const content = JSON.stringify(data, null, 2)
  await writeText(filePath, content + "\n")
}

export async function walkFiles(root: string): Promise<string[]> {
  const entries = await fs.readdir(root, { withFileTypes: true, recursive: true })
  return entries.filter((entry) => entry.isFile()).map((entry) => path.join(entry.parentPath, entry.name))
}

export async function copyDir(sourceDir: string, targetDir: string): Promise<void> {
  await fs.cp(sourceDir, targetDir, { recursive: true })
}
