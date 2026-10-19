// The words around the board, as the old page has them: the chips, the status line and the end-of-game banner.
import type { Color, GameSettings, GameState, NewGame } from '@/api/types'
import { humanColor } from '@/game/gameLoop'

export const COLORS: readonly Color[] = ['white', 'black']
export const COLOR_NAMES: Record<Color, string> = { white: 'White', black: 'Black' }
export const ICON: Record<Color, string> = { white: '♔', black: '♚' }
const other = (color: Color): Color => (color === 'white' ? 'black' : 'white')

export const LLM_CONSTRAINTS_NAMES = {
  free: 'Free',
  listed: 'Listed',
  blind_enforced: 'Blind enforced',
  listed_enforced: 'Listed enforced',
} as const
export const FEEDBACK_NAMES = { explained: 'Explained', bare: 'Bare', hinted: 'Hinted' } as const

const RESULT_TITLES: Record<string, string> = { '1-0': 'White wins', '0-1': 'Black wins', '1/2-1/2': 'Draw' }
const END_REASONS: Record<string, string> = {
  checkmate: 'by checkmate',
  stalemate: 'by stalemate',
  threefold_repetition: 'by threefold repetition',
  fifty_moves: 'by the fifty-move rule',
  insufficient_material: 'by insufficient material',
  forfeit: 'by forfeit',
  move_cap: 'at the move cap of 150 moves each',
}

type LlmSide = Extract<GameSettings['white'], { player: 'llm' }>

export const faceoff = (game: GameState) => game.settings.mode === 'llm_faceoff'
export const llmColors = (game: GameState) => COLORS.filter((color) => game.settings[color].player === 'llm')
const llmSide = (game: GameState, color: Color) => game.settings[color] as LlmSide

/** The LLM as the status names it: the model, and in a faceoff its side too, as two LLMs can share a model. */
export function llmName(game: GameState, color: Color): string {
  const model = llmSide(game, color).model
  return faceoff(game) ? `${ICON[color]} ${COLOR_NAMES[color]} · ${model}` : model
}

/** The status line, `seconds` into the LLM's turn while one is running. */
export function statusText(game: GameState | null, failed: boolean, seconds: number | null): string {
  if (!game) return failed ? 'Could not start a game' : 'Loading…'
  if (game.status === 'over') return 'Game over'
  const human = humanColor(game)
  if (game.turn === human) return `Your move (${COLOR_NAMES[human]})`
  if (seconds !== null) {
    const doing = llmSide(game, game.turn).thinking ? 'is thinking…' : 'is choosing a move…'
    return `${llmName(game, game.turn)} ${doing} ${seconds}s`
  }
  return `Waiting for ${faceoff(game) ? llmName(game, game.turn) : COLOR_NAMES[game.turn]}…`
}

/** The end-of-game banner's title and reason. */
export function bannerText(game: GameState): { title: string; reason: string } {
  // In a faceoff the result names the models, e.g. "qwen3.5:9b (White) wins".
  const winner = ({ '1-0': 'white', '0-1': 'black' } as const)[game.result as '1-0' | '0-1'] as Color | undefined
  const title =
    faceoff(game) && winner
      ? `${llmSide(game, winner).model} (${COLOR_NAMES[winner]}) wins`
      : (RESULT_TITLES[game.result ?? ''] ?? game.result ?? '')
  const endReason = game.end_reason ?? ''
  let reason = END_REASONS[endReason] ?? `by ${endReason.replaceAll('_', ' ')}`
  // A forfeit with no answer says why here too, since the switch can hide the move list's chips.
  const error = game.llm_turn?.attempts.at(-1)?.error
  if (endReason === 'forfeit' && error) reason += `: ${error}`
  else if (endReason === 'forfeit' && faceoff(game) && winner) {
    const tries = game.llm_turn?.attempts.length ?? 0
    reason += `: ${llmSide(game, other(winner)).model} gave no legal move in ${tries} tries`
  }
  return { title, reason }
}

/** The top bar's chips: who plays whom, then each LLM setting, naming the side when the two LLMs' values differ. */
export function settingsChips(game: GameState): string[] {
  const colors = llmColors(game)
  const sides = colors.map((color) => llmSide(game, color))
  const perSide = (format: (side: LlmSide) => string) => {
    const values = sides.map(format)
    return new Set(values).size === 1 ? [values[0]] : [colors.map((color, i) => `${color} ${values[i]}`).join(' · ')]
  }
  const human = humanColor(game)
  const players =
    faceoff(game) || !human
      ? [sides.map((side) => side.model + (side.thinking ? ' (thinking)' : '')).join(' vs ')]
      : [`you play ${COLOR_NAMES[human]}`, sides[0].model, `thinking ${sides[0].thinking ? 'on' : 'off'}`]
  return [
    ...players,
    ...perSide((side) => LLM_CONSTRAINTS_NAMES[side.llm_constraints].toLowerCase()),
    ...perSide((side) => `${FEEDBACK_NAMES[side.retry_feedback].toLowerCase()} feedback`),
  ]
}

/** The new-game request for another game under the same settings, as New game sends with no changes in the modal. */
export function newGameFrom(settings: GameSettings): NewGame {
  return { mode: settings.mode, white: settings.white, black: settings.black, rules: settings.rules ?? 'standard' }
}
