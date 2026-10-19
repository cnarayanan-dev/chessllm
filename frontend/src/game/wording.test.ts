import { expect, test } from 'vitest'
import type { GameState } from '@/api/types'
import { bannerText, settingsChips } from '@/game/wording'
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

test('King capture by the human: the LLM left its king hanging', () => {
  expect(bannerText(kingCaptured({ result: '1-0' }))).toEqual({
    title: 'White wins',
    reason: 'by King capture: qwen3.5:9b left its king hanging',
  })
})

test("King capture by the LLM's chaos move: it took the human's king", () => {
  const game = kingCaptured({ result: '0-1', plies: plies(...CHAOS_PLIES.slice(0, 11), QXE1) })

  expect(bannerText(game).reason).toBe('by King capture: qwen3.5:9b took your king')
})

test('a chaos move that takes its own king loses', () => {
  const ownKing: (typeof CHAOS_PLIES)[number] = [
    'd5h6',
    'Qxh6',
    'rnb2r2/pppp1ppp/7q/4p1B1/1b1PP3/2P2N2/PP1N1PPP/R2QKB1R w KQ - 0 7',
    { kind: 'chaos', from: 'd5', to: 'h6', piece: 'q', rook: null, reason: 'the queen on d5 moves' },
  ]
  const game = kingCaptured({ result: '1-0', plies: plies(...CHAOS_PLIES.slice(0, 11), ownKing) })

  expect(bannerText(game).reason).toBe('by King capture: qwen3.5:9b took its own king')
})

test('in a faceoff the King capture names both LLMs by their side', () => {
  const llm = aGame().settings.black
  const faceoff = { mode: 'llm_faceoff' as const, white: { ...llm, model: 'gemma3:4b' }, black: llm, sampling: {}, rules: 'chaos' as const, max_attempts: 5 }

  expect(bannerText(kingCaptured({ result: '1-0', settings: faceoff }))).toEqual({
    title: 'gemma3:4b (White) wins',
    reason: 'by King capture: qwen3.5:9b (Black) left its king hanging',
  })
  const byChaos = kingCaptured({ result: '0-1', settings: faceoff, plies: plies(...CHAOS_PLIES.slice(0, 11), QXE1) })
  expect(bannerText(byChaos).reason).toBe('by King capture: qwen3.5:9b (Black) took the king of gemma3:4b (White)')
})

test('the top bar shows a Chaos rules chip only under Chaos rules', () => {
  expect(settingsChips(chaosGame(1))).toContain('Chaos rules')
  expect(settingsChips(aGame())).not.toContain('Chaos rules')
})
