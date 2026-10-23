// Names for the generated API types (schema.ts), as the page uses them.
import type { components } from '@/api/schema'

type Schemas = components['schemas']

// The page only shows games it starts, Play LLM and LLM faceoffs: an Anchor match is played from the command
// line, so its Mode and Anchor side never reach the page.
// An LLM side's Turn memory is left out of the API's output when fresh, and may be left out of a request, which the
// generated type, required from its default, doesn't say.
export type LlmSide = Omit<Schemas['LlmSide'], 'turn_memory'> & { turn_memory?: TurnMemory }
export type TurnMemory = Schemas['LlmSide']['turn_memory']
type PageSide = Schemas['HumanSide'] | LlmSide
export type GameSettings = Omit<Schemas['GameSettings'], 'mode' | 'white' | 'black'> & {
  mode: NewGame['mode']
  white: PageSide
  black: PageSide
}
export type GameState = Omit<Schemas['GameState'], 'settings'> & { settings: GameSettings }
export type LlmTurn = Schemas['LlmTurn']
export type Attempt = Schemas['Attempt']
export type PromptMessage = Schemas['PromptMessage']
export type Ply = Schemas['Ply']
/** Stockfish's judgement of the position after a ply, from White's point of view; `unjudged` says why there is none. */
export type Evaluation = NonNullable<Ply['evaluation']>
/** How much a Chaos move gained its mover, from its point of view; `vs_best` is recorded, never shown. */
export type ChaosGain = NonNullable<LlmTurn['chaos_gain']>
// The Legal counterpart switch may be left out of a request: Standard rules ignore it, and the API defaults it to on.
export type NewGame = Omit<Schemas['NewGame'], 'legal_counterpart' | 'white' | 'black'> & {
  white: PageSide
  black: PageSide
  legal_counterpart?: boolean
}
export type ModelInfo = Schemas['ModelInfo']
/** A Prompt template of the Prompt library, with the LLM constraints and Turn memories it fits, and the LLM constraints it is the Default of. */
export type PromptTemplateInfo = Schemas['PromptTemplateInfo']
/** A Prompt template to save: its text, its name if any, and the LLM constraints it is written for. */
export type NewPromptTemplate = Schemas['NewPromptTemplate']
export type Color = GameState['turn']
/** A Probe of a past LLM turn (CONTEXT.md): its position, the side's settings, the template and the attempt. */
export type Probe = Schemas['Probe']
/** What Try asks for: the turn, by its ply and colour, and the Prompt template, by its ID in the Prompt library or as
 * unsaved text. */
export type ProbeRequest = Schemas['ProbeRequest']
