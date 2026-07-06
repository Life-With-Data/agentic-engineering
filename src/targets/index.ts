import type { ClaudePlugin } from "../types/claude"
import { convertClaudeToOpenCode, type ClaudeToOpenCodeOptions } from "../converters/claude-to-opencode"
import { convertClaudeToClaude } from "../converters/claude-to-claude"
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

export type TargetHandler<TBundle = unknown> = {
  name: string
  implemented: boolean
  convert: (plugin: ClaudePlugin, options: ClaudeToOpenCodeOptions) => TBundle | null
  write: (outputRoot: string, bundle: TBundle) => Promise<void>
}

// The registry maps target names to handlers with heterogeneous bundle types,
// which the Record value type can't express — each entry erases TBundle here,
// after inference has verified that convert's output matches write's input.
function defineTarget<TBundle>(handler: TargetHandler<TBundle>): TargetHandler {
  return handler as unknown as TargetHandler
}

export const targets: Record<string, TargetHandler> = {
  claude: defineTarget({
    name: "claude",
    implemented: true,
    convert: convertClaudeToClaude,
    write: writeClaudeBundle,
  }),
  opencode: defineTarget({
    name: "opencode",
    implemented: true,
    convert: convertClaudeToOpenCode,
    write: writeOpenCodeBundle,
  }),
  codex: defineTarget({
    name: "codex",
    implemented: true,
    convert: convertClaudeToCodex,
    write: writeCodexBundle,
  }),
  cursor: defineTarget({
    name: "cursor",
    implemented: true,
    convert: convertClaudeToCursor,
    write: writeCursorBundle,
  }),
  droid: defineTarget({
    name: "droid",
    implemented: true,
    convert: convertClaudeToDroid,
    write: writeDroidBundle,
  }),
  pi: defineTarget({
    name: "pi",
    implemented: true,
    convert: convertClaudeToPi,
    write: writePiBundle,
  }),
  copilot: defineTarget({
    name: "copilot",
    implemented: true,
    convert: convertClaudeToCopilot,
    write: writeCopilotBundle,
  }),
  gemini: defineTarget({
    name: "gemini",
    implemented: true,
    convert: convertClaudeToGemini,
    write: writeGeminiBundle,
  }),
  kiro: defineTarget({
    name: "kiro",
    implemented: true,
    convert: convertClaudeToKiro,
    write: writeKiroBundle,
  }),
}
