import { expect, test } from 'vitest'
import type { GameState } from '@/api/types'
import { rematchDescription, rematchOf } from '@/game/rematch'
import { aGame, chaosGame } from '@/test/games'

const llm = aGame().settings.black as Extract<GameState['settings']['black'], { player: 'llm' }>

test('Play LLM: the human takes the other colour, the LLM keeps its model and settings', () => {
  const game = aGame({ settings: { ...aGame().settings, black: { ...llm, thinking: true, llm_constraints: 'listed' } } })

  expect(rematchOf(game.settings, false)).toEqual({
    mode: 'play_llm',
    white: { player: 'llm', model: 'qwen3.5:9b', thinking: true, llm_constraints: 'listed', retry_feedback: 'explained', turn_memory: 'fresh' },
    black: { player: 'human' },
    rules: 'standard',
    max_attempts: 5,
  })
})

test('LLM faceoff: each LLM takes its whole side to the other colour', () => {
  const game = aGame({
    settings: {
      ...aGame().settings,
      mode: 'llm_faceoff',
      white: { player: 'llm', model: 'gemma3:4b', thinking: false, llm_constraints: 'free', retry_feedback: 'hinted', turn_memory: 'fresh' },
      black: { player: 'llm', model: 'qwen3.5:9b', thinking: true, llm_constraints: 'listed_enforced', retry_feedback: 'bare', turn_memory: 'fresh' },
      max_attempts: 3,
    },
  })

  expect(rematchOf(game.settings, false)).toEqual({
    mode: 'llm_faceoff',
    white: { player: 'llm', model: 'qwen3.5:9b', thinking: true, llm_constraints: 'listed_enforced', retry_feedback: 'bare', turn_memory: 'fresh' },
    black: { player: 'llm', model: 'gemma3:4b', thinking: false, llm_constraints: 'free', retry_feedback: 'hinted', turn_memory: 'fresh' },
    rules: 'standard',
    max_attempts: 3,
  })
})

test('the rules stay: a Chaos game is followed by a Chaos game', () => {
  expect(rematchOf(chaosGame(1).settings, false).rules).toBe('chaos')
})

test('so does the Legal counterpart switch of a Chaos game', () => {
  const settings = { ...chaosGame(1).settings, legal_counterpart: false }

  expect(rematchOf(settings, false)).toMatchObject({ rules: 'chaos', legal_counterpart: false })
  expect(rematchOf(aGame().settings, false)).not.toHaveProperty('legal_counterpart')
})

test("with Prompt lab on, each LLM keeps its Prompt template; off, every LLM plays its default one", () => {
  const settings = {
    ...aGame().settings,
    mode: 'llm_faceoff' as const,
    white: { ...llm, prompt_template_id: 'described@1' },
    black: { ...llm, model: 'gemma3:4b' },
  }

  expect(rematchOf(settings, true)).toMatchObject({
    white: { model: 'gemma3:4b' },
    black: { model: 'qwen3.5:9b', prompt_template_id: 'described@1' },
  })
  expect(rematchOf(settings, true).white).not.toHaveProperty('prompt_template_id')
  expect(rematchOf(settings, false).black).toEqual(llm)
})

test('each LLM keeps its Turn memory, with Prompt lab on or off', () => {
  const settings = { ...aGame().settings, black: { ...llm, turn_memory: 'chat_moves' as const } }

  expect(rematchOf(settings, true).white).toMatchObject({ turn_memory: 'chat_moves' })
  expect(rematchOf(settings, false).white).toMatchObject({ turn_memory: 'chat_moves' })
})

test('the tooltip says which colour you will play, or that the LLMs swap', () => {
  const asBlack = { ...aGame().settings, white: llm, black: { player: 'human' as const } }

  expect(rematchDescription(aGame().settings)).toBe('Same settings, you play Black')
  expect(rematchDescription(asBlack)).toBe('Same settings, you play White')
  expect(rematchDescription({ ...aGame().settings, mode: 'llm_faceoff', white: llm })).toBe(
    'Same settings, the LLMs swap colours',
  )
})
