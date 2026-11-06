// Who plays a side (CONTEXT.md): a human, or a Model player, an LLM or a System 1 model. The one place the page tells
// them apart by the side's `player`.
import type { GameSettings, LlmSide, System1Side } from '@/api/types'

/** A side of a game or of a new game's request. */
export type Side = GameSettings['white']

export const isLlm = (side: Side): side is LlmSide => side.player === 'llm'
export const isSystem1 = (side: Side): side is System1Side => side.player === 'system1'
/** Whether a Model player plays the side, an LLM or a System 1 model: its turn is asked for, one request each. */
export const isModelPlayer = (side: Side): side is LlmSide | System1Side => side.player !== 'human'
