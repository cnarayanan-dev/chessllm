// The words around the board: the settings, in the Game card and the New game sheet, and the result.
import type { Color, GameSettings, GameState } from '@/api/types'
import { chaosResolution } from '@/game/chaos'
import { humanColor } from '@/game/gameLoop'

export const COLORS: readonly Color[] = ['white', 'black']
export const COLOR_NAMES: Record<Color, string> = { white: 'White', black: 'Black' }
const other = (color: Color): Color => (color === 'white' ? 'black' : 'white')

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

/** A setting of the running game as the Game card shows it: one icon, its name and meaning in the tooltip. */
export type GameSetting = {
  setting: 'llm_constraints' | 'rules' | 'retry_feedback' | 'thinking' | 'max_attempts'
  /** The setting's value as the API names it ('free', 'chaos', …), 'on' / 'off' for thinking, the number of moves. */
  value: string
  /** The short name, e.g. "Board only (Free)"; in a faceoff whose LLMs differ in it, after the side ("White: …"). */
  name: string
  description: string
  /** The LLM's side, when the two LLMs of a faceoff differ in the setting; otherwise null. */
  color: Color | null
}
type Shown = Pick<GameSetting, 'value' | 'name' | 'description'>

type Words = { name: string; description: string }

/**
 * The LLM constraints in plain words, the glossary term (CONTEXT.md) kept beside the name: the New game sheet's
 * options, and in the Game card "Board only (Free)".
 */
export const LLM_CONSTRAINT_WORDS: Record<LlmSide['llm_constraints'], Words & { term: string }> = {
  free: { name: 'Board only', term: 'Free', description: 'The LLM finds its own moves and can play an illegal one.' },
  listed: {
    name: 'Board + legal moves',
    term: 'Listed',
    description: 'The LLM is shown the legal moves, but can still play an illegal one.',
  },
  blind_enforced: {
    name: 'Kept legal, not told',
    term: 'Blind enforced',
    description: 'The LLM is held to the legal moves without being shown them.',
  },
  listed_enforced: {
    name: 'Shown and kept legal',
    term: 'Listed enforced',
    description: 'The LLM is shown the legal moves and held to them.',
  },
}
/** The Rules: the New game sheet's options, and in the Game card "Standard rules". */
export const RULES_WORDS: Record<NonNullable<GameSettings['rules']>, Words> = {
  standard: { name: 'Standard', description: 'Normal chess. Rated.' },
  chaos: { name: 'Chaos', description: "The LLM's illegal moves are played anyway. Unrated." },
}
/** The Retry feedback levels: the New game sheet's options, and in the Game card "Explained feedback". */
export const RETRY_FEEDBACK_WORDS: Record<LlmSide['retry_feedback'], Words> = {
  explained: { name: 'Explained', description: 'After an illegal move the LLM is told the move and the kind of failure.' },
  bare: { name: 'Bare', description: 'After an illegal move the LLM is told only that it was illegal.' },
  hinted: { name: 'Hinted', description: 'After an illegal move the LLM is also told the legal moves.' },
}
const shown = <T extends string, W extends Words>(words: Record<T, W>, name: (word: W) => string) =>
  Object.fromEntries(
    Object.entries<W>(words).map(([value, word]) => [value, { value, name: name(word), description: word.description }]),
  ) as Record<T, Shown>
const LLM_CONSTRAINTS = shown(LLM_CONSTRAINT_WORDS, ({ name, term }) => `${name} (${term})`)
const RULES = shown(RULES_WORDS, ({ name }) => `${name} rules`)
const RETRY_FEEDBACK = shown(RETRY_FEEDBACK_WORDS, ({ name }) => `${name} feedback`)
const THINKING: Record<'on' | 'off', Shown> = {
  on: { value: 'on', name: 'Thinking on', description: 'The LLM reasons before each move.' },
  off: { value: 'off', name: 'Thinking off', description: 'The LLM answers without reasoning first.' },
}
/** Under Enforced decoding the LLM cannot play an illegal move, so it is never retried (ADR 0003). */
const enforced = (side: LlmSide) => side.llm_constraints === 'blind_enforced' || side.llm_constraints === 'listed_enforced'

/**
 * The Game card's settings, one item each: the LLM constraints, the rules, the Retry feedback, thinking and the
 * illegal moves before forfeit. An LLM under an enforced constraint has no Retry feedback, and when every LLM is, there
 * is no forfeit limit. A setting that differs between the two LLMs of a faceoff gives one item per side.
 */
export function gameSettings(game: GameState): GameSetting[] {
  const colors = llmColors(game)
  const sides = colors.map((color) => llmSide(game, color))
  const perSide = (setting: GameSetting['setting'], shown: (side: LlmSide) => Shown | null): GameSetting[] => {
    const values = sides.map(shown)
    if (new Set(values).size === 1) return values[0] ? [{ setting, ...values[0], color: null }] : []
    return colors.flatMap((color, i) => {
      const value = values[i]
      return value ? [{ setting, ...value, name: `${COLOR_NAMES[color]}: ${value.name}`, color }] : []
    })
  }
  const attempts = game.settings.max_attempts
  const moves = `${attempts} illegal ${attempts === 1 ? 'move' : 'moves'}`
  return [
    ...perSide('llm_constraints', (side) => LLM_CONSTRAINTS[side.llm_constraints]),
    { setting: 'rules', ...RULES[game.settings.rules ?? 'standard'], color: null },
    ...perSide('retry_feedback', (side) => (enforced(side) ? null : RETRY_FEEDBACK[side.retry_feedback])),
    ...perSide('thinking', (side) => THINKING[side.thinking ? 'on' : 'off']),
    ...(sides.some((side) => !enforced(side))
      ? [
          {
            setting: 'max_attempts' as const,
            value: String(attempts),
            name: `Forfeit after ${moves}`,
            description: `An LLM loses after ${moves} in one turn.`,
            color: null,
          },
        ]
      : []),
  ]
}
