import { describe, expect, test } from 'vitest'
import type { GameSettings, ModelInfo, SideValues } from '@/settings/next-game'
import {
  chooseHumanColor,
  chooseMode,
  chooseModel,
  isPending,
  newGameRequest,
  nextGameFrom,
  setValue,
  swapSides,
  toggleCustomize,
  toggleThinking,
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
  ...more,
})

const playLlm: GameSettings = {
  mode: 'play_llm',
  white: { player: 'human' },
  black: llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
  sampling: { temperature: 0.6 },
  rules: 'standard',
}

const faceoff: GameSettings = {
  mode: 'llm_faceoff',
  white: llm('qwen3.5:9b', { thinking: true }),
  black: llm('gemma3:4b', { llm_constraints: 'listed_enforced', retry_feedback: 'bare' }),
  sampling: {},
  rules: 'standard',
}

describe('the next game starts as the running one', () => {
  test('in Play LLM', () => {
    const next = nextGameFrom(playLlm)

    expect(newGameRequest(next, models)).toEqual({
      mode: 'play_llm',
      rules: 'standard',
      white: { player: 'human' },
      black: llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
    })
    expect(isPending(next, models, playLlm)).toBe(false)
  })

  test('in an LLM faceoff, customized per LLM when the sides differ', () => {
    const next = nextGameFrom(faceoff)

    expect(next.custom).toBe(true)
    expect(newGameRequest(next, models)).toEqual({ mode: 'llm_faceoff', rules: 'standard', white: faceoff.white, black: faceoff.black })
    expect(isPending(next, models, faceoff)).toBe(false)
  })

  test('in an LLM faceoff, shared when both sides play under the same settings', () => {
    const shared: GameSettings = { ...faceoff, white: llm('qwen3.5:9b'), black: llm('gemma3:4b') }

    expect(nextGameFrom(shared).custom).toBe(false)
  })
})

test('a change is pending until the next game starts', () => {
  const next = setValue(nextGameFrom(playLlm), 'black', 'retry_feedback', 'hinted')

  expect(isPending(next, models, playLlm)).toBe(true)
})

test('a running Chaos rules game makes the next game a change, as it plays under Standard rules', () => {
  const chaos: GameSettings = { ...playLlm, rules: 'chaos' }

  expect(isPending(nextGameFrom(chaos), models, chaos)).toBe(true)
})

test('a running game whose settings leave out the rules plays under Standard rules', () => {
  const { rules: _, ...unnamed } = playLlm

  expect(isPending(nextGameFrom(unnamed), models, unnamed)).toBe(false)
})

test('the human changing colour leaves the LLM its model', () => {
  const next = chooseHumanColor(nextGameFrom(playLlm), 'black')

  expect(newGameRequest(next, models)).toEqual({
    mode: 'play_llm',
    rules: 'standard',
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
      white: llm('qwen3.5:9b', { thinking: true }),
      black: llm('qwen3.5:9b', { llm_constraints: 'blind_enforced' }),
    })
  })

  test("off, both LLMs take White's values again", () => {
    const next = toggleCustomize(nextGameFrom(faceoff), models)

    expect(newGameRequest(next, models)).toEqual({
      mode: 'llm_faceoff',
      rules: 'standard',
      white: llm('qwen3.5:9b'),
      black: llm('gemma3:4b'),
    })
  })

  test("on again, each LLM starts from the shared values, not its old ones", () => {
    const next = toggleCustomize(toggleCustomize(nextGameFrom(faceoff), models), models)

    expect(newGameRequest(next, models)).toEqual({
      mode: 'llm_faceoff',
      rules: 'standard',
      white: llm('qwen3.5:9b'),
      black: llm('gemma3:4b'),
    })
  })

  test('off, a shared change applies to both LLMs', () => {
    const next = setValue(nextGameFrom(shared), 'black', 'retry_feedback', 'hinted')

    expect(newGameRequest(next, models)).toMatchObject({
      white: { retry_feedback: 'hinted' },
      black: { retry_feedback: 'hinted' },
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
      white: { player: 'human' },
      black: llm('gemma3:4b'),
    })
  })

  test('⇄ takes each LLM with its settings to the other colour', () => {
    const next = swapSides(nextGameFrom(faceoff))

    expect(newGameRequest(next, models)).toEqual({ mode: 'llm_faceoff', rules: 'standard', white: faceoff.black, black: faceoff.white })
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
    const next = nextGameFrom({ ...faceoff, black: llm('gemma3:4b', { thinking: true, retry_feedback: 'bare' }) })

    expect(newGameRequest(next, models)).toMatchObject({ white: { thinking: true }, black: { thinking: false } })
  })

  test('is taken as possible while the models are not listed yet', () => {
    const next = chooseModel(nextGameFrom(playLlm), 'black', 'gemma3:4b')

    expect(newGameRequest(next, null)).toMatchObject({ black: { thinking: true } })
  })
})
