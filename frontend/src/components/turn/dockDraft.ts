// The text in the Prompt lab's dock (PromptDock), which the Turn panel keeps while its tabs come and go.
import type { Color, LlmTurn, PromptTemplateInfo } from '@/api/types'

/** The dock's text, for the turn it was opened on: the template it started from, and the text as it is now. */
export type DockDraft = {
  gameId: string
  ply: number
  color: Color
  from: PromptTemplateInfo
  systemPrompt: string
  turnTemplate: string
  /** The name for the next version saved, if any. */
  name: string
  /** Which part the text box shows. */
  part: 'system' | 'turn'
  /** Whether the dock shows it: a closed one is opened again as it was, for the same template and turn of the game. */
  open: boolean
}

/** A draft of the template, unchanged, for the turn of the game. */
export const draftOf = (template: PromptTemplateInfo, gameId: string, turn: LlmTurn): DockDraft => ({
  gameId,
  ply: turn.ply,
  color: turn.color,
  from: template,
  systemPrompt: template.system_prompt,
  turnTemplate: template.turn_template,
  name: '',
  part: 'system',
  open: true,
})

/** Whether the draft is for this turn of this game. */
export const draftFor = (draft: DockDraft, gameId: string, turn: { ply: number; color: Color }) =>
  draft.gameId === gameId && draft.ply === turn.ply && draft.color === turn.color
