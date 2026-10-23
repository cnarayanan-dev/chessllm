// Rematch (CONTEXT.md): a new game with the same Mode and settings as the game just played, the colours swapped.
import type { GameSettings, NewGame } from '@/api/types'
import { COLOR_NAMES } from '@/game/wording'

type Side = GameSettings['white']

/** With Prompt lab off, an LLM side plays the Default of its LLM constraints, whatever it played before. */
function withDefaultTemplate(side: Side): Side {
  if (side.player !== 'llm') return side
  const { prompt_template_id: _, ...rest } = side
  return rest
}

/**
 * The rematch's new-game request: each side, the human or an LLM with its model and the settings it played under,
 * its Prompt template too with Prompt lab on, takes the other colour.
 */
export const rematchOf = (settings: GameSettings, promptLab: boolean): NewGame => ({
  mode: settings.mode,
  white: promptLab ? settings.black : withDefaultTemplate(settings.black),
  black: promptLab ? settings.white : withDefaultTemplate(settings.white),
  rules: settings.rules ?? 'standard', // the API leaves out Standard rules
  max_attempts: settings.max_attempts,
  // Only a Chaos game has the Legal counterpart switch.
  ...(settings.legal_counterpart != null && { legal_counterpart: settings.legal_counterpart }),
})

/** What Rematch does, for its tooltip: the colour you will play, or that the LLMs swap. */
export function rematchDescription(settings: GameSettings): string {
  if (settings.mode === 'llm_faceoff') return 'Same settings, the LLMs swap colours'
  const yours = settings.white.player === 'human' ? 'black' : 'white'
  return `Same settings, you play ${COLOR_NAMES[yours]}`
}
