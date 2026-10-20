// Rematch (CONTEXT.md): a new game with the same Mode and settings as the game just played, the colours swapped.
import type { GameSettings, NewGame } from '@/api/types'
import { COLOR_NAMES } from '@/game/wording'

/**
 * The rematch's new-game request: each side, the human or an LLM with its model and the settings it played under,
 * takes the other colour.
 */
export const rematchOf = (settings: GameSettings): NewGame => ({
  mode: settings.mode,
  white: settings.black,
  black: settings.white,
  rules: settings.rules ?? 'standard', // the API leaves out Standard rules
  max_attempts: settings.max_attempts,
})

/** What Rematch does, for its tooltip: the colour you will play, or that the LLMs swap. */
export function rematchDescription(settings: GameSettings): string {
  if (settings.mode === 'llm_faceoff') return 'Same settings, the LLMs swap colours'
  const yours = settings.white.player === 'human' ? 'black' : 'white'
  return `Same settings, you play ${COLOR_NAMES[yours]}`
}
