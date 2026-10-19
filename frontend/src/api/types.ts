// Names for the generated API types (schema.ts), as the page uses them.
import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type GameState = Schemas['GameState']
export type GameSettings = Schemas['GameSettings']
export type LlmTurn = Schemas['LlmTurn']
export type Attempt = Schemas['Attempt']
export type NewGame = Schemas['NewGame']
export type ModelInfo = Schemas['ModelInfo']
export type Color = GameState['turn']
