import { describe, expect, test } from 'vitest'
import type { System1Side } from '@/api/types'
import type { GameSettings, ModelInfo, SideValues } from '@/settings/next-game'
import {
  chaosAllowed,
  chooseKind,
  llmColors,
  setSystem1,
  startBlocked,
  chooseHumanColor,
  chooseMaxAttempts,
  chooseRules,
  chooseMode,
  chooseModel,
  everyLlmEnforced,
  newGameRequest,
  nextGameFrom,
  setValue,
  swapSides,
  toggleCustomize,
  toggleThinking,
  withSystem1Url,
} from '@/settings/next-game'

const qwen: ModelInfo = { name: 'qwen3.5:9b', thinking: true, sampling: { temperature: 0.6 } }
const gemma: ModelInfo = { name: 'gemma3:4b', thinking: false, sampling: null }
const models = [qwen, gemma]

const llm = (model: string, more: Partial<SideValues> = {}) => ({
  player: 'llm' as const,
  model,
  thinking: false,
  llm_constraints: 'free' as const,
  retry_feedback: 'explained' as const,
  turn_memory: 'fresh' as const,
  ...more,
})

const playLlm: GameSettings = {
  mode: 'play_llm',
  white: { player: 'human' },
  black: llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
  sampling: { temperature: 0.6 },
  rules: 'standard',
  max_attempts: 5,
}

const faceoff: GameSettings = {
  mode: 'llm_faceoff',
  white: llm('qwen3.5:9b', { thinking: true }),
  black: llm('gemma3:4b', { llm_constraints: 'listed_enforced', retry_feedback: 'bare', turn_memory: 'fresh' }),
  sampling: {},
  rules: 'standard',
  max_attempts: 5,
}

describe('the sheet opens with the last game\'s settings, which start the same game again', () => {
  test('in Play LLM', () => {
    const next = nextGameFrom(playLlm)

    expect(newGameRequest(next, models)).toEqual({
      mode: 'play_llm',
      rules: 'standard',
      max_attempts: 5,
      white: { player: 'human' },
      black: llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
    })
  })

  test('in an LLM faceoff, customized per LLM when the sides differ', () => {
    const next = nextGameFrom(faceoff)

    expect(next.custom).toBe(true)
    expect(newGameRequest(next, models)).toEqual({ mode: 'llm_faceoff', rules: 'standard', max_attempts: 5, white: faceoff.white, black: faceoff.black })
  })

  test('in an LLM faceoff, shared when both sides play under the same settings', () => {
    const shared: GameSettings = { ...faceoff, white: llm('qwen3.5:9b'), black: llm('gemma3:4b') }

    expect(nextGameFrom(shared).custom).toBe(false)
  })
})

describe('Illegal moves before forfeit', () => {
  test("the next game keeps the last game's limit, or the one chosen", () => {
    const next = nextGameFrom({ ...playLlm, max_attempts: 9 })

    expect(newGameRequest(next, models)).toMatchObject({ max_attempts: 9 })
    expect(newGameRequest(chooseMaxAttempts(next, 25), models)).toMatchObject({ max_attempts: 25 })
  })
})

describe('Chaos rules', () => {
  test("the next game keeps the last game's Chaos rules", () => {
    const next = nextGameFrom({ ...playLlm, rules: 'chaos' })

    expect(newGameRequest(next, models)).toMatchObject({ rules: 'chaos' })
  })

  test('switched on, the next game plays under Chaos rules', () => {
    const next = chooseRules(nextGameFrom(playLlm), 'chaos')

    expect(newGameRequest(next, models)).toMatchObject({ rules: 'chaos' })
  })

  test('possible only when every LLM plays under Free or Listed', () => {
    const next = chooseRules(nextGameFrom(playLlm), 'chaos')
    const enforcedNext = setValue(next, 'black', 'llm_constraints', 'blind_enforced')

    expect(chaosAllowed(next)).toBe(true)
    expect(chaosAllowed(enforcedNext)).toBe(false)
    // The choice is kept, but the game plays under Standard rules, as the backend would refuse it.
    expect(newGameRequest(enforcedNext, models)).toMatchObject({ rules: 'standard' })
    expect(newGameRequest(setValue(enforcedNext, 'black', 'llm_constraints', 'listed'), models)).toMatchObject({
      rules: 'chaos',
      max_attempts: 5,
    })
  })

  test('customized per LLM, one enforced side is enough to rule it out', () => {
    // White under Free, Black under Listed enforced.
    let next = chooseRules(nextGameFrom(faceoff), 'chaos')
    expect(next.custom).toBe(true)
    expect(chaosAllowed(next)).toBe(false)
    expect(newGameRequest(next, models)).toMatchObject({ rules: 'standard' })

    next = setValue(next, 'black', 'llm_constraints', 'listed')
    expect(chaosAllowed(next)).toBe(true)
    expect(newGameRequest(next, models)).toMatchObject({ rules: 'chaos' })
  })
})

test('every LLM under Enforced decoding: in Play LLM the one LLM, in a faceoff both, customized or not', () => {
  const play = nextGameFrom(playLlm)
  expect(everyLlmEnforced(play)).toBe(false)
  expect(everyLlmEnforced(setValue(play, 'black', 'llm_constraints', 'blind_enforced'))).toBe(true)

  const custom = nextGameFrom(faceoff) // White under Free, Black under Listed enforced
  expect(everyLlmEnforced(custom)).toBe(false)
  expect(everyLlmEnforced(setValue(custom, 'white', 'llm_constraints', 'listed_enforced'))).toBe(true)
})

test('a running game whose settings leave out the rules plays under Standard rules', () => {
  const { rules: _, ...unnamed } = playLlm

  expect(newGameRequest(nextGameFrom(unnamed), models)).toMatchObject({ rules: 'standard' })
})

test('the human changing colour leaves the LLM its model', () => {
  const next = chooseHumanColor(nextGameFrom(playLlm), 'black')

  expect(newGameRequest(next, models)).toEqual({
    mode: 'play_llm',
    rules: 'standard',
    max_attempts: 5,
    white: llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
    black: { player: 'human' },
  })
})

test('switching from Play LLM to an LLM faceoff gives both LLMs the shared settings', () => {
  let next = chooseMode(nextGameFrom(playLlm), models, 'llm_faceoff')
  next = chooseModel(next, 'white', 'qwen3.5:9b')

  expect(newGameRequest(next, models)).toEqual({
    mode: 'llm_faceoff',
    rules: 'standard',
    max_attempts: 5,
    white: llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
    black: llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
  })
})

describe('Customize per LLM', () => {
  const shared: GameSettings = { ...faceoff, white: llm('qwen3.5:9b'), black: llm('qwen3.5:9b') }

  test('on, each LLM is set separately', () => {
    let next = toggleCustomize(nextGameFrom(shared), models)
    next = setValue(next, 'black', 'llm_constraints', 'blind_enforced')
    next = toggleThinking(next, models, 'white')

    expect(newGameRequest(next, models)).toEqual({
      mode: 'llm_faceoff',
      rules: 'standard',
      max_attempts: 5,
      white: llm('qwen3.5:9b', { thinking: true }),
      black: llm('qwen3.5:9b', { llm_constraints: 'blind_enforced' }),
    })
  })

  test("off, both LLMs take White's values again", () => {
    const next = toggleCustomize(nextGameFrom(faceoff), models)

    expect(newGameRequest(next, models)).toEqual({
      mode: 'llm_faceoff',
      rules: 'standard',
      max_attempts: 5,
      white: llm('qwen3.5:9b'),
      black: llm('gemma3:4b'),
    })
  })

  test("on again, each LLM starts from the shared values, not its old ones", () => {
    const next = toggleCustomize(toggleCustomize(nextGameFrom(faceoff), models), models)

    expect(newGameRequest(next, models)).toEqual({
      mode: 'llm_faceoff',
      rules: 'standard',
      max_attempts: 5,
      white: llm('qwen3.5:9b'),
      black: llm('gemma3:4b'),
    })
  })

  test('off, a shared change applies to both LLMs', () => {
    const next = setValue(nextGameFrom(shared), 'black', 'retry_feedback', 'hinted')

    expect(newGameRequest(next, models)).toMatchObject({
      white: { retry_feedback: 'hinted', turn_memory: 'fresh' },
      black: { retry_feedback: 'hinted', turn_memory: 'fresh' },
    })
  })

  test('on, each side starts from the shared thinking, off when not both LLMs can think', () => {
    const thinkingShared: GameSettings = { ...shared, white: llm('qwen3.5:9b', { thinking: true }) }
    let next = chooseModel(nextGameFrom({ ...thinkingShared, black: thinkingShared.white }), 'black', 'gemma3:4b')
    next = toggleCustomize(next, models)

    expect(newGameRequest(next, models)).toMatchObject({ white: { thinking: false }, black: { thinking: false } })
  })

  test('picking Play LLM turns it off', () => {
    const next = chooseMode(nextGameFrom(faceoff), models, 'play_llm')

    expect(next.custom).toBe(false)
    expect(newGameRequest(next, models)).toEqual({
      mode: 'play_llm',
      rules: 'standard',
      max_attempts: 5,
      white: { player: 'human' },
      black: llm('gemma3:4b'),
    })
  })

  test('⇄ takes each LLM with its settings to the other colour', () => {
    const next = swapSides(nextGameFrom(faceoff))

    expect(newGameRequest(next, models)).toEqual({ mode: 'llm_faceoff', rules: 'standard', max_attempts: 5, white: faceoff.black, black: faceoff.white })
  })
})

describe('thinking', () => {
  test('is off for a model that cannot think, whatever the switch held', () => {
    const next = chooseModel(nextGameFrom(playLlm), 'black', 'gemma3:4b')

    expect(newGameRequest(next, models)).toMatchObject({ black: { model: 'gemma3:4b', thinking: false } })
  })

  test('comes back on when the model can think again', () => {
    let next = chooseModel(nextGameFrom(playLlm), 'black', 'gemma3:4b')
    next = chooseModel(next, 'black', 'qwen3.5:9b')

    expect(newGameRequest(next, models)).toMatchObject({ black: { thinking: true } })
  })

  test('shared in a faceoff only when both models can think', () => {
    const both: GameSettings = { ...faceoff, white: llm('qwen3.5:9b', { thinking: true }) }
    const next = chooseModel(nextGameFrom({ ...both, black: both.white }), 'black', 'gemma3:4b')

    expect(newGameRequest(next, models)).toMatchObject({ white: { thinking: false }, black: { thinking: false } })
  })

  test('customized, each LLM thinks if its own model can', () => {
    const next = nextGameFrom({ ...faceoff, black: llm('gemma3:4b', { thinking: true, retry_feedback: 'bare', turn_memory: 'fresh' }) })

    expect(newGameRequest(next, models)).toMatchObject({ white: { thinking: true }, black: { thinking: false } })
  })

  test('is taken as possible while the models are not listed yet', () => {
    const next = chooseModel(nextGameFrom(playLlm), 'black', 'gemma3:4b')

    expect(newGameRequest(next, null)).toMatchObject({ black: { thinking: true } })
  })
})

describe('a System 1 model as a side', () => {
  const system1 = (model: string, more: Partial<System1Side> = {}): System1Side => ({
    player: 'system1',
    model,
    base_url: 'http://localhost:11434',
    choice_temperature: 1,
    ...more,
  })
  const againstSystem1: GameSettings = { ...playLlm, black: system1('d3:2b', { choice_temperature: 0.5 }) }

  test('the sheet opens with it in Play LLM, and starts the same game again', () => {
    const next = nextGameFrom(againstSystem1)

    expect(next.kinds).toEqual({ white: 'system1', black: 'system1' })
    expect(newGameRequest(next, models)).toEqual({
      mode: 'play_llm',
      rules: 'standard',
      max_attempts: 5,
      white: { player: 'human' },
      black: system1('d3:2b', { choice_temperature: 0.5 }),
    })
  })

  test('a faceoff keeps an LLM on one side and a System 1 model with its Prompt template on the other', () => {
    const settings: GameSettings = {
      ...faceoff,
      white: llm('qwen3.5:9b', { thinking: true }),
      black: system1('d1:2b', { prompt_template_id: 'system1-position-only@4e096016' }),
    }
    const next = nextGameFrom(settings)

    expect(next.custom).toBe(false)
    expect(llmColors(next)).toEqual(['white'])
    expect(newGameRequest(next, models)).toMatchObject({ white: settings.white, black: settings.black })
  })

  test('a Prompt template left at the default is not sent, as for an LLM', () => {
    const next = nextGameFrom(againstSystem1)

    expect(newGameRequest(next, models).black).not.toHaveProperty('prompt_template_id')
  })

  test('the human changing colour takes the System 1 side with them', () => {
    const swapped = chooseHumanColor(nextGameFrom(againstSystem1), 'black')

    expect(newGameRequest(swapped, models)).toMatchObject({
      white: system1('d3:2b', { choice_temperature: 0.5 }),
      black: { player: 'human' },
    })
  })

  test('swapping colours in a faceoff swaps every side with its settings, whichever kind', () => {
    const next = nextGameFrom({ ...faceoff, black: system1('d1:2b', { choice_temperature: 2 }) })

    const swapped = swapSides(next)

    expect(newGameRequest(swapped, models)).toMatchObject({
      white: system1('d1:2b', { choice_temperature: 2 }),
      black: llm('qwen3.5:9b', { thinking: true }),
    })
  })

  test('the Choice temperature is what was typed, as a number', () => {
    const next = setSystem1(nextGameFrom(againstSystem1), 'black', 'choice_temperature', '0')

    expect(newGameRequest(next, models).black).toMatchObject({ choice_temperature: 0 })
  })

  test('choosing it for a side makes that side a System 1 model; choosing the LLM back keeps its LLM settings', () => {
    const next = nextGameFrom(playLlm)

    const system = chooseKind(next, models, 'black', 'system1')
    expect(newGameRequest(system, models).black).toMatchObject({ player: 'system1', model: 'd3:2b' })

    const back = chooseKind(system, models, 'black', 'llm')
    expect(newGameRequest(back, models).black).toEqual(newGameRequest(next, models).black)
  })

  test('customizing per LLM ends when a side stops being an LLM, the other LLM keeping its settings', () => {
    const custom = nextGameFrom(faceoff) // its sides differ, so it opens customized
    expect(custom.custom).toBe(true)

    const next = chooseKind(custom, models, 'white', 'system1')

    expect(next.custom).toBe(false)
    expect(newGameRequest(next, models).black).toEqual(faceoff.black)
  })

  test('a System 1 model plays Standard rules only, so Chaos rules are not possible, and are not sent', () => {
    const next = chooseRules(nextGameFrom(againstSystem1), 'chaos')

    expect(chaosAllowed(next)).toBe(false)
    expect(newGameRequest(next, models).rules).toBe('standard')
  })

  test('with no LLM, no LLM setting applies', () => {
    const next = nextGameFrom({ ...faceoff, white: system1('d3:2b'), black: system1('d1:2b') })

    expect(llmColors(next)).toEqual([])
    expect(newGameRequest(next, models)).toMatchObject({ white: system1('d3:2b'), black: system1('d1:2b') })
  })

  test("a System 1 side nobody played starts without a server, which the API's default fills in, only where there is none", () => {
    const next = nextGameFrom(playLlm)
    const typed = setSystem1(next, 'white', 'base_url', 'http://elsewhere:9000')

    expect(next.system1.black.base_url).toBe('')
    expect(withSystem1Url(next, 'http://api:1').system1).toMatchObject({
      white: { base_url: 'http://api:1' },
      black: { base_url: 'http://api:1' },
    })
    expect(withSystem1Url(typed, 'http://api:1').system1).toMatchObject({
      white: { base_url: 'http://elsewhere:9000' },
      black: { base_url: 'http://api:1' },
    })
  })

  test('a game cannot start without a model, a server or a Choice temperature', () => {
    const next = nextGameFrom(againstSystem1)

    expect(startBlocked(next)).toBeNull()
    expect(startBlocked(setSystem1(next, 'black', 'model', ' '))).toMatch(/model/i)
    expect(startBlocked(setSystem1(next, 'black', 'base_url', ''))).toMatch(/server/i)
    expect(startBlocked(setSystem1(next, 'black', 'choice_temperature', ''))).toMatch(/Choice temperature/)
    expect(startBlocked(setSystem1(next, 'black', 'choice_temperature', '-1'))).toMatch(/Choice temperature/)
  })
})
