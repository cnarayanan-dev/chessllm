import type {
  GameSettings,
  LlmSide,
  ModelInfo,
  NewGame,
  PromptTemplateInfo,
  System1Side,
  System1TemplateInfo,
  TurnMemory,
} from '@/api/types'
import { isLlm, isModelPlayer, isSystem1, type Side } from '@/game/sides'

export type { GameSettings, ModelInfo, NewGame, TurnMemory }

export type Mode = NewGame['mode']
export type Color = 'white' | 'black'
export type Rules = NewGame['rules']
export type LlmConstraints = LlmSide['llm_constraints']
export type RetryFeedback = LlmSide['retry_feedback']
/**
 * The settings an LLM side plays under, besides its model. Its Prompt template is given by its ID in the Prompt
 * library, null for the Default of its LLM constraints; one is chosen only with Prompt lab on.
 */
export type SideValues = Pick<LlmSide, 'thinking' | 'llm_constraints' | 'retry_feedback'> & {
  prompt_template_id: string | null
  turn_memory: TurnMemory
}
/** Who plays a Model player's side: an LLM or a System 1 model (CONTEXT.md). */
export type Kind = 'llm' | 'system1'
/**
 * The settings a System 1 side plays under. The Choice temperature is kept as typed, so a half-typed number isn't
 * lost; the Prompt template is given by its ID, null for the default System 1 template.
 */
export type System1Values = {
  model: string
  base_url: string
  choice_temperature: string
  prompt_template_id: string | null
}
/** The Prompt library, or null until it has loaded. */
export type Library = PromptTemplateInfo[] | null

/**
 * The setup for the next game, as the New game sheet changes it. Each colour keeps a model, so the LLM keeps its model when the human changes colour or
 * the Mode changes. The settings are shared by every LLM side, and both sides hold the same values, unless an LLM
 * faceoff customizes them per LLM.
 */
export type NextGame = {
  mode: Mode
  human_color: Color
  /** Whether each colour's Model player is an LLM or a System 1 model; the human's colour keeps the other's. */
  kinds: Record<Color, Kind>
  models: Record<Color, string>
  /** The settings of a System 1 side; a colour that isn't one keeps them, for when it becomes one. */
  system1: Record<Color, System1Values>
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

/** The model a new System 1 side starts as: the one of the first experiment (docs/research/system-1-models.md). */
export const DEFAULT_SYSTEM1_MODEL = 'd3:2b'
/**
 * What a new System 1 side starts as. Its server is the API's default (GET /api/system1/options), which the sheet
 * puts in (withSystem1Url) once it has it: until then the URL is empty.
 */
const DEFAULT_SYSTEM1: System1Side = {
  player: 'system1',
  model: DEFAULT_SYSTEM1_MODEL,
  base_url: '',
  choice_temperature: 1,
}
/** What an LLM side starts as when none was played, as the API's default LLM. */
const DEFAULT_LLM: LlmSide = {
  player: 'llm',
  model: 'llama3:8b',
  thinking: false,
  llm_constraints: 'free',
  retry_feedback: 'explained',
  turn_memory: 'fresh',
}
const system1Values = (side: System1Side): System1Values => ({
  model: side.model,
  base_url: side.base_url,
  choice_temperature: String(side.choice_temperature),
  prompt_template_id: side.prompt_template_id ?? null,
})
const sideValues = (side: LlmSide): SideValues => ({
  thinking: side.thinking,
  llm_constraints: side.llm_constraints,
  retry_feedback: side.retry_feedback,
  prompt_template_id: side.prompt_template_id ?? null,
  turn_memory: side.turn_memory,
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
  const sides = COLORS.map((color) => settings[color])
  const first = sides.find(isModelPlayer)
  if (!first) throw new Error('A game has at least one Model player side')
  const llmSide = sides.find(isLlm) ?? DEFAULT_LLM
  const system1Side = sides.find(isSystem1) ?? DEFAULT_SYSTEM1
  // The human's colour holds the settings of the Model player's, for when the human changes colour.
  const llmOf = (color: Color) => {
    const side = settings[color]
    return isLlm(side) ? side : llmSide
  }
  const system1Of = (color: Color) => {
    const side = settings[color]
    return isSystem1(side) ? side : system1Side
  }
  const kindOf = (color: Color): Kind => {
    const side = settings[color]
    return isSystem1(side) ? 'system1' : isLlm(side) ? 'llm' : isSystem1(first) ? 'system1' : 'llm'
  }
  const values = { white: sideValues(llmOf('white')), black: sideValues(llmOf('black')) }
  const bothLlm = isLlm(settings.white) && isLlm(settings.black)
  return {
    mode: settings.mode,
    human_color: COLORS.find((color) => settings[color].player === 'human') ?? 'white',
    kinds: { white: kindOf('white'), black: kindOf('black') },
    models: { white: llmOf('white').model, black: llmOf('black').model },
    system1: { white: system1Values(system1Of('white')), black: system1Values(system1Of('black')) },
    custom: settings.mode === 'llm_faceoff' && bothLlm && !sameSide(values.white, values.black),
    sides: values,
    rules: settings.rules ?? 'standard', // the API leaves out Standard rules
    max_attempts: settings.max_attempts,
    legal_counterpart: settings.legal_counterpart ?? true, // the API leaves it out under Standard rules
  }
}

/** The colours the Model players play in the next game, of either kind. */
export const modelColors = (next: NextGame): Color[] =>
  next.mode === 'llm_faceoff' ? COLORS : [other(next.human_color)]

/** The colours the LLMs play in the next game. */
export const llmColors = (next: NextGame): Color[] => modelColors(next).filter((color) => next.kinds[color] === 'llm')

/** The colours the System 1 models play in the next game. */
export const system1Colors = (next: NextGame): Color[] =>
  modelColors(next).filter((color) => next.kinds[color] === 'system1')

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

/**
 * Chaos rules need an LLM that can play an illegal move: every LLM side under Free or Listed. A System 1 model plays
 * only legal moves, under Standard rules.
 */
export const chaosAllowed = (next: NextGame) =>
  system1Colors(next).length === 0 && llmColors(next).every((color) => !enforced(next, color))

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
  kinds: { white: next.kinds.black, black: next.kinds.white },
  models: { white: next.models.black, black: next.models.white },
  system1: { white: next.system1.black, black: next.system1.white },
})

/** The human's colour in Play LLM. The LLM keeps its model. */
export const chooseHumanColor = (next: NextGame, color: Color): NextGame =>
  color === next.human_color ? next : { ...swapModels(next), human_color: color }

export const chooseModel = (next: NextGame, color: Color, name: string): NextGame => ({
  ...next,
  models: { ...next.models, [color]: name },
})

/**
 * Whether a side is an LLM or a System 1 model. Customizing per LLM ends when fewer than two LLMs are left: the
 * LLM left keeps its settings for both sides. A side that becomes an LLM and has a model not in the list takes the
 * first listed.
 */
export function chooseKind(next: NextGame, models: Models, color: Color, kind: Kind): NextGame {
  let chosen: NextGame = { ...next, kinds: { ...next.kinds, [color]: kind } }
  if (kind === 'llm' && models?.length && !models.some((model) => model.name === next.models[color])) {
    chosen = chooseModel(chosen, color, models[0].name)
  }
  if (chosen.custom && llmColors(chosen).length < 2) {
    const kept = chosen.sides[llmColors(chosen)[0] ?? 'white']
    chosen = { ...chosen, custom: false, sides: { white: kept, black: { ...kept } } }
  }
  return chosen
}

/** The next game with the API's default server in every System 1 side that has none yet. */
export const withSystem1Url = (next: NextGame, url: string): NextGame => {
  const fill = (values: System1Values): System1Values => (values.base_url === '' ? { ...values, base_url: url } : values)
  return { ...next, system1: { white: fill(next.system1.white), black: fill(next.system1.black) } }
}

/** Sets a System 1 side's setting. */
export const setSystem1 = <K extends keyof System1Values>(
  next: NextGame,
  color: Color,
  key: K,
  choice: System1Values[K],
): NextGame => ({ ...next, system1: { ...next.system1, [color]: { ...next.system1[color], [key]: choice } } })

/** Picks a System 1 side's Prompt template; the default, the first listed, is kept as null, as the API takes it. */
export const chooseSystem1Template = (
  next: NextGame,
  templates: System1TemplateInfo[],
  color: Color,
  id: string,
): NextGame => setSystem1(next, color, 'prompt_template_id', id === templates[0]?.id ? null : id)

/** The template a System 1 side plays: the one chosen, else the default, the first listed; undefined until listed. */
export const chosenSystem1Template = (next: NextGame, templates: System1TemplateInfo[], color: Color) => {
  const id = next.system1[color].prompt_template_id
  return id === null ? templates[0] : templates.find((template) => template.id === id)
}

const choiceTemperature = (values: System1Values) =>
  values.choice_temperature.trim() === '' ? Number.NaN : Number(values.choice_temperature)

/** Why the game can't start yet, or null: a System 1 side needs a model, a server and a Choice temperature of 0 or more. */
export function startBlocked(next: NextGame): string | null {
  for (const color of system1Colors(next)) {
    const side = next.system1[color]
    const who = next.mode === 'llm_faceoff' ? `${color === 'white' ? 'White' : 'Black'}: ` : ''
    if (side.model.trim() === '') return `${who}A System 1 model needs a model name.`
    if (side.base_url.trim() === '') return `${who}A System 1 model needs the URL of its server.`
    if (!(choiceTemperature(side) >= 0)) return `${who}Choice temperature must be a number, 0 or more.`
  }
  return null
}

/** ⇄ in a faceoff: each LLM takes its customized settings to the other colour. */
export const swapSides = (next: NextGame): NextGame => ({
  ...swapModels(next),
  sides: { white: next.sides.black, black: next.sides.white },
})

/**
 * The Prompt templates of the library a side can play under these LLM constraints and Turn memory, in the library's
 * order: Moves only under Chat with moves. Fresh by default, as a Probe's Prompt always is.
 */
export const fittingTemplates = (
  library: PromptTemplateInfo[],
  constraints: LlmConstraints,
  turnMemory: TurnMemory = 'fresh',
) => library.filter((template) => template.fits.includes(constraints) && template.turn_memories.includes(turnMemory))

/** Whether a template is the Default of a side's LLM constraints under its Turn memory: Moves under Chat with moves. */
const isDefaultOf = (template: PromptTemplateInfo, next: NextGame, color: Color) =>
  template.default_for.includes(value(next, color, 'llm_constraints')) &&
  template.turn_memories.includes(value(next, color, 'turn_memory'))

/** The template a side plays: the one chosen, or else the Default of its LLM constraints; undefined until listed. */
export function chosenTemplate(next: NextGame, library: PromptTemplateInfo[], color: Color) {
  const id = value(next, color, 'prompt_template_id')
  return library.find((template) => (id === null ? isDefaultOf(template, next, color) : template.id === id))
}

/** Picks a side's Prompt template; the Default of its LLM constraints is kept as null, as the API takes it. */
export function choosePromptTemplate(next: NextGame, library: PromptTemplateInfo[], color: Color, id: string): NextGame {
  const isDefault = library.some((template) => template.id === id && isDefaultOf(template, next, color))
  return setValue(next, color, 'prompt_template_id', isDefault ? null : id)
}

/**
 * A side's Prompt template back to the Default if it no longer fits the side's LLM constraints and Turn memory, so
 * the game can't be refused for it; while the library isn't listed, the choice is kept.
 */
function keepFitting(next: NextGame, library: Library, color: Color): NextGame {
  const id = value(next, color, 'prompt_template_id')
  const fitting = fittingTemplates(library ?? [], value(next, color, 'llm_constraints'), value(next, color, 'turn_memory'))
  const fits = id === null || !library || fitting.some((template) => template.id === id)
  return fits ? next : setValue(next, color, 'prompt_template_id', null)
}

/** Sets a side's LLM constraints; a Prompt template that doesn't fit them goes back to their Default. */
export const chooseConstraints = (next: NextGame, library: Library, color: Color, constraints: LlmConstraints) =>
  keepFitting(setValue(next, color, 'llm_constraints', constraints), library, color)

/**
 * Sets a side's Turn memory; a Prompt template that doesn't fit it goes back to the Default, which under Chat with
 * moves is Moves.
 */
export const chooseTurnMemory = (next: NextGame, library: Library, color: Color, turnMemory: TurnMemory) =>
  keepFitting(setValue(next, color, 'turn_memory', turnMemory), library, color)

/** With Prompt lab off, every side plays the Default of its LLM constraints, whatever the last game played. */
export const withDefaultTemplates = (next: NextGame): NextGame => ({
  ...next,
  sides: {
    white: { ...next.sides.white, prompt_template_id: null },
    black: { ...next.sides.black, prompt_template_id: null },
  },
})

/** The new-game request: the Mode and each side, in the shape of the game's settings. */
export function newGameRequest(next: NextGame, models: Models): NewGame {
  const system1 = (color: Color): System1Side => {
    const values = next.system1[color]
    return {
      player: 'system1',
      model: values.model.trim(),
      base_url: values.base_url.trim(),
      choice_temperature: choiceTemperature(values),
      // Left out for the default, so a request is as small as an LLM's.
      ...(values.prompt_template_id !== null && { prompt_template_id: values.prompt_template_id }),
    }
  }
  const llm = (color: Color): LlmSide => {
    const prompt_template_id = value(next, color, 'prompt_template_id')
    return {
      player: 'llm',
      model: next.models[color],
      thinking: thinkingOn(next, models, color),
      llm_constraints: value(next, color, 'llm_constraints'),
      retry_feedback: value(next, color, 'retry_feedback'),
      turn_memory: value(next, color, 'turn_memory'),
      // Left out for the Default, so a request without Prompt lab is as before.
      ...(prompt_template_id !== null && { prompt_template_id }),
    }
  }
  const side = (color: Color): Side =>
    next.mode === 'play_llm' && color === next.human_color
      ? { player: 'human' }
      : next.kinds[color] === 'system1'
        ? system1(color)
        : llm(color)
  const rules = next.rules === 'chaos' && chaosAllowed(next) ? 'chaos' : 'standard'
  const request: NewGame = { mode: next.mode, white: side('white'), black: side('black'), rules, max_attempts: next.max_attempts }
  // Standard rules ignore the switch, so it is sent only under Chaos rules.
  return rules === 'chaos' ? { ...request, legal_counterpart: next.legal_counterpart } : request
}
