import { expect, test } from 'vitest'
import type { GameState } from '@/api/types'
import { gameSettings, resultText } from '@/game/wording'
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

test('a chaos move that leaves its own king in check loses, naming the LLM that played it', () => {
  expect(resultText(kingCaptured({ result: '1-0', end_reason: 'king_left_in_check' }))).toEqual({
    result: 'White wins by a king left in check',
    detail: 'qwen3.5:9b left its own king in check',
  })
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

/** The Game card's settings, each as its setting and value, and its side when the two LLMs differ in it. */
const shown = (game: GameState) =>
  gameSettings(game).map(({ setting, value, color }) => `${setting}=${value}${color ? ` (${color})` : ''}`)

test("the Game card's settings: the LLM constraints, the rules, the Retry feedback, thinking and the forfeit limit", () => {
  expect(shown(aGame())).toEqual([
    'llm_constraints=free',
    'rules=standard',
    'retry_feedback=explained',
    'thinking=off',
    'max_attempts=5',
  ])
  expect(shown(chaosGame(1))).toContain('rules=chaos')
})

test('each setting has its short name and what it means', () => {
  const game = aGame({ settings: { ...aGame().settings, max_attempts: 3 } })

  expect(gameSettings(game).map(({ name, description }) => [name, description])).toEqual([
    ['Board only (Free)', 'The LLM finds its own moves and can play an illegal one.'],
    ['Standard rules', 'Normal chess. Rated.'],
    ['Explained feedback', 'After an illegal move the LLM is told the move and the kind of failure.'],
    ['Thinking off', 'The LLM answers without reasoning first.'],
    ['Forfeit after 3 illegal moves', 'An LLM loses after 3 illegal moves in one turn.'],
  ])
  const one = aGame({ settings: { ...aGame().settings, max_attempts: 1 } })
  expect(gameSettings(one).at(-1)).toMatchObject({
    name: 'Forfeit after 1 illegal move',
    description: 'An LLM loses after 1 illegal move in one turn.',
  })
})

test('an LLM under an enforced constraint has no Retry feedback; with no other LLM there is no forfeit limit', () => {
  expect(shown(faceoffOf({ llm_constraints: 'blind_enforced' }, { llm_constraints: 'listed_enforced' }))).toEqual([
    'llm_constraints=blind_enforced (white)',
    'llm_constraints=listed_enforced (black)',
    'rules=standard',
    'thinking=off',
  ])
  expect(shown(faceoffOf({ llm_constraints: 'listed_enforced' }, { retry_feedback: 'hinted' }))).toEqual([
    'llm_constraints=listed_enforced (white)',
    'llm_constraints=free (black)',
    'rules=standard',
    'retry_feedback=hinted (black)',
    'thinking=off',
    'max_attempts=5',
  ])
})

test('in a faceoff a setting the LLMs share is one item; one that differs is one per side, named by its side', () => {
  const game = faceoffOf({ thinking: false, llm_constraints: 'listed' }, { thinking: true, llm_constraints: 'listed' })

  expect(shown(game)).toEqual([
    'llm_constraints=listed',
    'rules=standard',
    'retry_feedback=explained',
    'thinking=off (white)',
    'thinking=on (black)',
    'max_attempts=5',
  ])
  expect(gameSettings(game).filter((item) => item.setting === 'thinking').map((item) => item.name)).toEqual([
    'White: Thinking off',
    'Black: Thinking on',
  ])
})

test("each setting also has its name without the side, for where the side is already shown", () => {
  const game = faceoffOf({ thinking: false }, { thinking: true })

  expect(gameSettings(game).map((item) => item.plainName)).toEqual([
    'Board only (Free)',
    'Standard rules',
    'Explained feedback',
    'Thinking off',
    'Thinking on',
    'Forfeit after 5 illegal moves',
  ])
})
