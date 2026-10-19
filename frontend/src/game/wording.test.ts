import { expect, test } from 'vitest'
import type { GameState } from '@/api/types'
import { resultText, settingsLine } from '@/game/wording'
import { CHAOS_PLIES, aGame, chaosGame, plies } from '@/test/games'

const kingCaptured = (overrides: Partial<GameState>) =>
  chaosGame(13, { status: 'over', end_reason: 'king_capture', human_legal_moves: [], ...overrides })

// The LLM, Black, takes White's king on e1 with a chaos move: Qd5 jumps there.
const QXE1: (typeof CHAOS_PLIES)[number] = [
  'd5e1',
  'Qxe1',
  'rnb2r2/pppp1ppp/7k/4p1B1/1b1PP3/2P2N2/PP1N1PPP/R2QqB1R w - - 0 7',
  { kind: 'chaos', from: 'd5', to: 'e1', piece: 'q', rook: null, reason: 'the queen on d5 moves' },
]

test('the result line: who won and how, with no detail for a checkmate or the Move cap', () => {
  expect(resultText(aGame({ status: 'over', result: '0-1', end_reason: 'checkmate' }))).toEqual({
    result: 'Black wins by checkmate',
    detail: null,
  })
  expect(resultText(aGame({ status: 'over', result: '1/2-1/2', end_reason: 'move_cap' }))).toEqual({
    result: 'Draw at the move cap of 150 moves each',
    detail: null,
  })
})

test('King capture by the human: the LLM left its king hanging', () => {
  expect(resultText(kingCaptured({ result: '1-0' }))).toEqual({
    result: 'White wins by King capture',
    detail: 'qwen3.5:9b left its king hanging',
  })
})

test("King capture by the LLM's chaos move: it took the human's king", () => {
  const game = kingCaptured({ result: '0-1', plies: plies(...CHAOS_PLIES.slice(0, 11), QXE1) })

  expect(resultText(game).detail).toBe('qwen3.5:9b took your king')
})

test('a chaos move that takes its own king loses', () => {
  const ownKing: (typeof CHAOS_PLIES)[number] = [
    'd5h6',
    'Qxh6',
    'rnb2r2/pppp1ppp/7q/4p1B1/1b1PP3/2P2N2/PP1N1PPP/R2QKB1R w KQ - 0 7',
    { kind: 'chaos', from: 'd5', to: 'h6', piece: 'q', rook: null, reason: 'the queen on d5 moves' },
  ]
  const game = kingCaptured({ result: '1-0', plies: plies(...CHAOS_PLIES.slice(0, 11), ownKing) })

  expect(resultText(game).detail).toBe('qwen3.5:9b took its own king')
})

test('in a faceoff the King capture names both LLMs by their side', () => {
  const llm = aGame().settings.black
  const faceoff = { mode: 'llm_faceoff' as const, white: { ...llm, model: 'gemma3:4b' }, black: llm, sampling: {}, rules: 'chaos' as const, max_attempts: 5 }

  expect(resultText(kingCaptured({ result: '1-0', settings: faceoff }))).toEqual({
    result: 'gemma3:4b (White) wins by King capture',
    detail: 'qwen3.5:9b (Black) left its king hanging',
  })
  const byChaos = kingCaptured({ result: '0-1', settings: faceoff, plies: plies(...CHAOS_PLIES.slice(0, 11), QXE1) })
  expect(resultText(byChaos).detail).toBe('qwen3.5:9b (Black) took the king of gemma3:4b (White)')
})

const llm = aGame().settings.black as Extract<GameState['settings']['black'], { player: 'llm' }>
const faceoffOf = (white: Partial<typeof llm>, black: Partial<typeof llm>) =>
  aGame({ settings: { ...aGame().settings, mode: 'llm_faceoff', white: { ...llm, ...white }, black: { ...llm, ...black } } })

test("the Game card's settings line: the LLM constraints, the rules, the feedback and thinking", () => {
  expect(settingsLine(aGame())).toEqual(['Free', 'Standard rules', 'explained feedback', 'thinking off'])
  expect(settingsLine(chaosGame(1))).toContain('Chaos rules')
})

test('in a faceoff a setting that differs between the two LLMs gives one item per side', () => {
  const game = faceoffOf({ thinking: false, llm_constraints: 'listed' }, { thinking: true, llm_constraints: 'listed' })

  expect(settingsLine(game)).toEqual([
    'Listed',
    'Standard rules',
    'explained feedback',
    'White thinking off',
    'Black thinking on',
  ])
})

test('the illegal moves before forfeit show only when they differ from the default 5', () => {
  expect(settingsLine(aGame()).join(' ')).not.toContain('forfeit')
  const game = aGame({ settings: { ...aGame().settings, max_attempts: 3 } })

  expect(settingsLine(game).at(-1)).toBe('3 illegal moves before forfeit')
  expect(settingsLine(aGame({ settings: { ...aGame().settings, max_attempts: 1 } })).at(-1)).toBe(
    '1 illegal move before forfeit',
  )
})
