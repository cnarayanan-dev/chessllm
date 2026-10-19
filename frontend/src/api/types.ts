// Names for the generated API types (schema.ts), as the page uses them.
import type { components } from '@/api/schema'

type Schemas = components['schemas']

// The page only shows games it starts, Play LLM and LLM faceoffs: an Anchor match is played from the command
// line, so its Mode and Anchor side never reach the page.
type PageSide = Exclude<Schemas['GameSettings']['white'], Schemas['AnchorSide']>
export type GameSettings = Omit<Schemas['GameSettings'], 'mode' | 'white' | 'black'> & {
  mode: NewGame['mode']
  white: PageSide
  black: PageSide
}
export type GameState = Omit<Schemas['GameState'], 'settings'> & { settings: GameSettings }
export type LlmTurn = Schemas['LlmTurn']
export type Attempt = Schemas['Attempt']
export type Ply = Schemas['Ply']
export type NewGame = Schemas['NewGame']
export type ModelInfo = Schemas['ModelInfo']
export type Color = GameState['turn']
