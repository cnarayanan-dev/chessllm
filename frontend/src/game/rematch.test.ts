import { expect, test } from 'vitest'
import type { GameState } from '@/api/types'
import { rematchDescription, rematchOf } from '@/game/rematch'
import { aGame, chaosGame } from '@/test/games'

const llm = aGame().settings.black as Extract<GameState['settings']['black'], { player: 'llm' }>

test('Play LLM: the human takes the other colour, the LLM keeps its model and settings', () => {
  const game = aGame({ settings: { ...aGame().settings, black: { ...llm, thinking: true, llm_constraints: 'listed' } } })

  expect(rematchOf(game.settings)).toEqual({
    mode: 'play_llm',
    white: { player: 'llm', model: 'qwen3.5:9b', thinking: true, llm_constraints: 'listed', retry_feedback: 'explained' },
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
      white: { player: 'llm', model: 'gemma3:4b', thinking: false, llm_constraints: 'free', retry_feedback: 'hinted' },
      black: { player: 'llm', model: 'qwen3.5:9b', thinking: true, llm_constraints: 'listed_enforced', retry_feedback: 'bare' },
      max_attempts: 3,
    },
  })

  expect(rematchOf(game.settings)).toEqual({
    mode: 'llm_faceoff',
    white: { player: 'llm', model: 'qwen3.5:9b', thinking: true, llm_constraints: 'listed_enforced', retry_feedback: 'bare' },
    black: { player: 'llm', model: 'gemma3:4b', thinking: false, llm_constraints: 'free', retry_feedback: 'hinted' },
    rules: 'standard',
    max_attempts: 3,
  })
})

test('the rules stay: a Chaos game is followed by a Chaos game', () => {
  expect(rematchOf(chaosGame(1).settings).rules).toBe('chaos')
})

test('the tooltip says which colour you will play, or that the LLMs swap', () => {
  const asBlack = { ...aGame().settings, white: llm, black: { player: 'human' as const } }

  expect(rematchDescription(aGame().settings)).toBe('Same settings, you play Black')
  expect(rematchDescription(asBlack)).toBe('Same settings, you play White')
  expect(rematchDescription({ ...aGame().settings, mode: 'llm_faceoff', white: llm })).toBe(
    'Same settings, the LLMs swap colours',
  )
})
