// The words around the board: the Game card's settings line and result, and the status line in the move history.
import type { Color, GameSettings, GameState } from '@/api/types'
import { chaosResolution } from '@/game/chaos'
import { humanColor, type Shown } from '@/game/gameLoop'

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
  king_capture: 'by King capture',
}

type LlmSide = Extract<GameSettings['white'], { player: 'llm' }>

export const faceoff = (game: GameState) => game.settings.mode === 'llm_faceoff'
export const llmColors = (game: GameState) => COLORS.filter((color) => game.settings[color].player === 'llm')
const llmSide = (game: GameState, color: Color) => game.settings[color] as LlmSide

/** The LLM as Show thinking names it: the model, and in a faceoff its side too, as two LLMs can share a model. */
export function llmName(game: GameState, color: Color): string {
  const model = llmSide(game, color).model
  return faceoff(game) ? `${ICON[color]} ${COLOR_NAMES[color]} · ${model}` : model
}

/** The status line while viewing a past position in the move history, e.g. "Viewing 12… Nf6 · → or Back to live". */
export function historyStatusText(shown: Shown): string {
  const move = shown.move
  const viewed = move
    ? `${Math.ceil(move.ply / 2)}${move.color === 'white' ? '.' : '…'} ${move.written}`
    : 'the start position'
  return `Viewing ${viewed} · → or Back to live`
}

/**
 * Who took whose king. A king taken by a legal move was left hanging by its side; one taken by a chaos move was
 * taken by the mover, which may even have taken its own king.
 */
function kingCapture(game: GameState, winner: Color): string {
  const loser = other(winner)
  const last = game.plies.at(-1)
  const human = humanColor(game)
  const name = (color: Color) => (faceoff(game) ? `${llmSide(game, color).model} (${COLOR_NAMES[color]})` : llmSide(game, color).model)
  if (last && chaosResolution(last)) {
    if (last.color === loser) return `${name(loser)} took its own king`
    return loser === human ? `${name(winner)} took your king` : `${name(winner)} took the king of ${name(loser)}`
  }
  return loser === human ? 'you left your king hanging' : `${name(loser)} left its king hanging`
}

/** The Game card's result line, e.g. "Black wins by checkmate", and the reason's detail under it, if any. */
export function resultText(game: GameState): { result: string; detail: string | null } {
  // In a faceoff the result names the models, e.g. "qwen3.5:9b (White) wins".
  const winner = ({ '1-0': 'white', '0-1': 'black' } as const)[game.result as '1-0' | '0-1'] as Color | undefined
  const title =
    faceoff(game) && winner
      ? `${llmSide(game, winner).model} (${COLOR_NAMES[winner]}) wins`
      : (RESULT_TITLES[game.result ?? ''] ?? game.result ?? '')
  const endReason = game.end_reason ?? ''
  const reason = END_REASONS[endReason] ?? `by ${endReason.replaceAll('_', ' ')}`
  // A forfeit with no answer says why here too, since the switch can hide the move list's chips.
  const error = game.llm_turn?.attempts.at(-1)?.error
  let detail: string | null = null
  if (endReason === 'king_capture' && winner) detail = kingCapture(game, winner)
  else if (endReason === 'forfeit' && error) detail = error
  else if (endReason === 'forfeit' && faceoff(game) && winner) {
    const tries = game.llm_turn?.attempts.length ?? 0
    detail = `${llmSide(game, other(winner)).model} gave no legal move in ${tries} tries`
  }
  return { result: `${title} ${reason}`, detail }
}

/** The attempts per turn when the game does not set them otherwise (CONTEXT.md: Retry). */
const DEFAULT_MAX_ATTEMPTS = 5

/**
 * The Game card's settings line, one item each: the LLM constraints, the rules, the feedback and thinking, then the
 * illegal moves before forfeit if not the default. A value that differs between the two LLMs in a faceoff gives one
 * item per side, e.g. "White thinking off", "Black thinking on".
 */
export function settingsLine(game: GameState): string[] {
  const colors = llmColors(game)
  const sides = colors.map((color) => llmSide(game, color))
  const perSide = (format: (side: LlmSide) => string) => {
    const values = sides.map(format)
    return new Set(values).size === 1 ? [values[0]] : colors.map((color, i) => `${COLOR_NAMES[color]} ${values[i]}`)
  }
  const attempts = game.settings.max_attempts
  return [
    ...perSide((side) => LLM_CONSTRAINTS_NAMES[side.llm_constraints]),
    game.settings.rules === 'chaos' ? 'Chaos rules' : 'Standard rules',
    ...perSide((side) => `${FEEDBACK_NAMES[side.retry_feedback].toLowerCase()} feedback`),
    ...perSide((side) => `thinking ${side.thinking ? 'on' : 'off'}`),
    ...(attempts !== DEFAULT_MAX_ATTEMPTS
      ? [`${attempts} illegal ${attempts === 1 ? 'move' : 'moves'} before forfeit`]
      : []),
  ]
}
