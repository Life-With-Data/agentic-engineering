// Shared naming/text helpers used by every claude-to-* converter.

export function normalizeName(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return "item"
  const normalized = trimmed
    .toLowerCase()
    .replace(/[\\/]+/g, "-")
    .replace(/[:\s]+/g, "-")
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
  return normalized || "item"
}

export function uniqueName(base: string, used: Set<string>): string {
  if (!used.has(base)) {
    used.add(base)
    return base
  }
  let index = 2
  while (used.has(`${base}-${index}`)) {
    index += 1
  }
  const name = `${base}-${index}`
  used.add(name)
  return name
}

export function sanitizeDescription(value: string, maxLength = 1024): string {
  const normalized = value.replace(/\s+/g, " ").trim()
  if (normalized.length <= maxLength) return normalized
  const ellipsis = "..."
  return normalized.slice(0, Math.max(0, maxLength - ellipsis.length)).trimEnd() + ellipsis
}

/**
 * Flatten a command name by stripping the namespace prefix.
 * "workflows:plan" -> "plan"
 */
export function flattenCommandName(name: string): string {
  const colonIndex = name.lastIndexOf(":")
  const base = colonIndex >= 0 ? name.slice(colonIndex + 1) : name
  return normalizeName(base)
}

/**
 * Rewrite slash-command references (/command-name, /ns:command) in prose,
 * skipping file paths and common absolute-path roots. The target-specific
 * replacement is supplied by the caller.
 */
export function replaceSlashCommands(body: string, rewrite: (commandName: string) => string): string {
  const slashCommandPattern = /(?<![:\w])\/([a-z][a-z0-9_:-]*?)(?=[\s,."')\]}`]|$)/gi
  return body.replace(slashCommandPattern, (match, commandName: string) => {
    if (commandName.includes("/")) return match
    if (["dev", "tmp", "etc", "usr", "var", "bin", "home"].includes(commandName)) return match
    return rewrite(commandName)
  })
}
