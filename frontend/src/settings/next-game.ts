import type { components } from '@/api/schema'
import type { GameSettings, ModelInfo, NewGame } from '@/api/types'

export type { GameSettings, ModelInfo, NewGame }

type Schemas = components['schemas']
type LlmSide = Schemas['LlmSide']
type Side = Schemas['HumanSide'] | LlmSide

export type Mode = NewGame['mode']
export type Color = 'white' | 'black'
export type Rules = NewGame['rules']
export type LlmConstraints = LlmSide['llm_constraints']
export type RetryFeedback = LlmSide['retry_feedback']
/** The settings an LLM side plays under, besides its model. */
export type SideValues = Pick<LlmSide, 'thinking' | 'llm_constraints' | 'retry_feedback'>

/**
 * The setup for the next game, as the New game sheet changes it. Each colour keeps a model, so the LLM keeps its model when the human changes colour or
 * the Mode changes. The settings are shared by every LLM side, and both sides hold the same values, unless an LLM
 * faceoff customizes them per LLM.
 */
export type NextGame = {
  mode: Mode
  human_color: Color
  models: Record<Color, string>
  custom: boolean
  sides: Record<Color, SideValues>
  /** Chaos rules as chosen, kept while they aren't possible: the game then plays under Standard rules. */
  rules: Rules
  /** Illegal moves per turn before an LLM forfeits, the same for every LLM. */
  max_attempts: number
  /** Under Chaos rules, whether each Chaos move's Legal counterpart is asked for; kept while Standard rules are chosen. */
  legal_counterpart: boolean
}

/** The model list from GET /api/models, or null until it has loaded. */
export type Models = ModelInfo[] | null

export const COLORS: Color[] = ['white', 'black']
/** The choices for the illegal moves per turn before an LLM forfeits; the API takes the same range. */
export const MAX_ATTEMPTS_CHOICES = Array.from({ length: 25 }, (_, index) => index + 1)
export const other = (color: Color): Color => (color === 'white' ? 'black' : 'white')

// Under Enforced decoding the LLM can't play an illegal move, so Retry feedback has no effect (ADR 0003).
const ENFORCED: LlmConstraints[] = ['blind_enforced', 'listed_enforced']

const isLlm = (side: Side): side is LlmSide => side.player === 'llm'
const sideValues = (side: SideValues): SideValues => ({
  thinking: side.thinking,
  llm_constraints: side.llm_constraints,
  retry_feedback: side.retry_feedback,
})
const sameSide = (a: object, b: object) => {
  const [x, y] = [a as Record<string, unknown>, b as Record<string, unknown>]
  return Object.keys({ ...x, ...y }).every((key) => x[key] === y[key])
}

/**
 * The next game, set up as `settings` were: the New game sheet opens with the last game's, or with no game, the API's
 * defaults for a new game.
 */
export function nextGameFrom(settings: GameSettings | NewGame): NextGame {
  const first = COLORS.map((color) => settings[color]).find(isLlm)
  if (!first) throw new Error('A game has at least one LLM side')
  const of = (color: Color) => {
    const side = settings[color]
    return isLlm(side) ? side : first
  }
  const sides = { white: sideValues(of('white')), black: sideValues(of('black')) }
  return {
    mode: settings.mode,
    human_color: COLORS.find((color) => settings[color].player === 'human') ?? 'white',
    models: { white: of('white').model, black: of('black').model },
    custom: settings.mode === 'llm_faceoff' && !sameSide(sides.white, sides.black),
    sides,
    rules: settings.rules ?? 'standard', // the API leaves out Standard rules
    max_attempts: settings.max_attempts,
    legal_counterpart: settings.legal_counterpart ?? true, // the API leaves it out under Standard rules
  }
}

/** The colours the LLMs play in the next game. */
export const llmColors = (next: NextGame): Color[] =>
  next.mode === 'llm_faceoff' ? COLORS : [other(next.human_color)]

/** Whether a model can think. A model not listed (yet) is given the benefit of the doubt. */
export const canThink = (models: Models, name: string) =>
  models?.find((model) => model.name === name)?.thinking ?? true

/** Shared thinking only when every LLM can think, so it never means different things for the two sides. */
export const thinkingAllowed = (next: NextGame, models: Models) =>
  llmColors(next).every((color) => canThink(models, next.models[color]))

/** A side's setting: its own when customizing, else the shared one, which both sides hold. */
export const value = <K extends keyof SideValues>(next: NextGame, color: Color, key: K): SideValues[K] =>
  next.sides[next.custom ? color : 'white'][key]

export const thinkingOn = (next: NextGame, models: Models, color: Color) =>
  value(next, color, 'thinking') &&
  (next.custom ? canThink(models, next.models[color]) : thinkingAllowed(next, models))

export const enforced = (next: NextGame, color: Color) => ENFORCED.includes(value(next, color, 'llm_constraints'))

/** Every LLM under Enforced decoding: then Retry feedback and the forfeit limit have no effect (ADR 0003). */
export const everyLlmEnforced = (next: NextGame) => llmColors(next).every((color) => enforced(next, color))

/** Chaos rules need an LLM that can play an illegal move: every LLM side under Free or Listed. */
export const chaosAllowed = (next: NextGame) => llmColors(next).every((color) => !enforced(next, color))

export const chooseRules = (next: NextGame, rules: Rules): NextGame => ({ ...next, rules })

export const toggleLegalCounterpart = (next: NextGame): NextGame => ({ ...next, legal_counterpart: !next.legal_counterpart })

export const chooseMaxAttempts = (next: NextGame, max_attempts: number): NextGame => ({ ...next, max_attempts })

/** Sets a side's setting: that side's alone when customizing, else both sides'. */
export function setValue<K extends keyof SideValues>(
  next: NextGame,
  color: Color,
  key: K,
  choice: SideValues[K],
): NextGame {
  const sides = { ...next.sides }
  for (const side of next.custom ? [color] : COLORS) sides[side] = { ...sides[side], [key]: choice }
  return { ...next, sides }
}

export const toggleThinking = (next: NextGame, models: Models, color: Color) =>
  setValue(next, color, 'thinking', !thinkingOn(next, models, color))

/** On, each side starts from the shared values; off, both sides take White's. */
export function toggleCustomize(next: NextGame, models: Models): NextGame {
  if (next.custom) return { ...next, custom: false, sides: { white: next.sides.white, black: { ...next.sides.white } } }
  const thinking = thinkingOn(next, models, 'white')
  return {
    ...next,
    custom: true,
    sides: { white: { ...next.sides.white, thinking }, black: { ...next.sides.black, thinking } },
  }
}

/** Customizing is a faceoff's alone: picking Play LLM turns it off, so each side's settings never part from its model. */
export function chooseMode(next: NextGame, models: Models, mode: Mode): NextGame {
  const from = mode === 'play_llm' && next.custom ? toggleCustomize(next, models) : next
  return { ...from, mode }
}

const swapModels = (next: NextGame): NextGame => ({
  ...next,
  models: { white: next.models.black, black: next.models.white },
})

/** The human's colour in Play LLM. The LLM keeps its model. */
export const chooseHumanColor = (next: NextGame, color: Color): NextGame =>
  color === next.human_color ? next : { ...swapModels(next), human_color: color }

export const chooseModel = (next: NextGame, color: Color, name: string): NextGame => ({
  ...next,
  models: { ...next.models, [color]: name },
})

/** ⇄ in a faceoff: each LLM takes its customized settings to the other colour. */
export const swapSides = (next: NextGame): NextGame => ({
  ...swapModels(next),
  sides: { white: next.sides.black, black: next.sides.white },
})

/** The new-game request: the Mode and each side, in the shape of the game's settings. */
export function newGameRequest(next: NextGame, models: Models): NewGame {
  const llm = (color: Color): LlmSide => ({
    player: 'llm',
    model: next.models[color],
    thinking: thinkingOn(next, models, color),
    llm_constraints: value(next, color, 'llm_constraints'),
    retry_feedback: value(next, color, 'retry_feedback'),
  })
  const side = (color: Color): Side =>
    next.mode === 'play_llm' && color === next.human_color ? { player: 'human' } : llm(color)
  const rules = next.rules === 'chaos' && chaosAllowed(next) ? 'chaos' : 'standard'
  const request: NewGame = { mode: next.mode, white: side('white'), black: side('black'), rules, max_attempts: next.max_attempts }
  // Standard rules ignore the switch, so it is sent only under Chaos rules.
  return rules === 'chaos' ? { ...request, legal_counterpart: next.legal_counterpart } : request
}
