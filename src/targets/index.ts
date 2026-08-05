import type { ClaudePlugin } from "../types/claude"
import { convertClaudeToOpenCode, type ConvertOptions } from "../converters/claude-to-opencode"
import { convertClaudeToCodex } from "../converters/claude-to-codex"
import { convertClaudeToCursor } from "../converters/claude-to-cursor"
import { convertClaudeToDroid } from "../converters/claude-to-droid"
import { convertClaudeToPi } from "../converters/claude-to-pi"
import { convertClaudeToCopilot } from "../converters/claude-to-copilot"
import { convertClaudeToGemini } from "../converters/claude-to-gemini"
import { convertClaudeToKiro } from "../converters/claude-to-kiro"
import { writeOpenCodeBundle } from "./opencode"
import { writeClaudeBundle } from "./claude"
import { writeCodexBundle } from "./codex"
import { writeCursorBundle } from "./cursor"
import { writeDroidBundle } from "./droid"
import { writePiBundle } from "./pi"
import { writeCopilotBundle } from "./copilot"
import { writeGeminiBundle } from "./gemini"
import { writeKiroBundle } from "./kiro"

export type TargetHandler = {
  name: string
  convert: (plugin: ClaudePlugin, options: ConvertOptions) => unknown
  // Each writer takes its own bundle type; `any` keeps the registry heterogeneous.
  // Every target is exercised end-to-end by tests, which catch a mismatched pair.
  write: (outputRoot: string, bundle: any) => Promise<void>
}

export const targets: Record<string, TargetHandler> = {
  // Claude is a passthrough: the plugin itself is the bundle.
  claude: { name: "claude", convert: (plugin) => plugin, write: writeClaudeBundle },
  opencode: { name: "opencode", convert: convertClaudeToOpenCode, write: writeOpenCodeBundle },
  codex: { name: "codex", convert: convertClaudeToCodex, write: writeCodexBundle },
  cursor: { name: "cursor", convert: convertClaudeToCursor, write: writeCursorBundle },
  droid: { name: "droid", convert: convertClaudeToDroid, write: writeDroidBundle },
  pi: { name: "pi", convert: convertClaudeToPi, write: writePiBundle },
  copilot: { name: "copilot", convert: convertClaudeToCopilot, write: writeCopilotBundle },
  gemini: { name: "gemini", convert: convertClaudeToGemini, write: writeGeminiBundle },
  kiro: { name: "kiro", convert: convertClaudeToKiro, write: writeKiroBundle },
}
