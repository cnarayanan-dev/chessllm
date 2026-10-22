import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { requestLlmTurn } from '@/game/useGameLoop'
import { fakeBackend } from '@/test/fakeBackend'
import { aGame, aTurn, afterE4, afterE5 } from '@/test/games'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

const refused = () => Response.json({ detail: 'an LLM turn is already running' }, { status: 409 })

test('returns the state the LLM turn was played in', async () => {
  fakeBackend().on('POST /api/games/current/llm-turn', Response.json(afterE5()))

  expect(await requestLlmTurn(afterE4(), new AbortController().signal)).toEqual(afterE5())
})

test('when a turn is already running, checks the game every 2 s until it has landed', async () => {
  const backend = fakeBackend()
    .on('POST /api/games/current/llm-turn', refused())
    .on('GET /api/games/current', Response.json(afterE4()), Response.json(afterE5()))

  const turn = requestLlmTurn(afterE4(), new AbortController().signal)
  await vi.advanceTimersByTimeAsync(1999)
  expect(backend.sentTo('GET /api/games/current')).toHaveLength(0)
  await vi.advanceTimersByTimeAsync(2001)

  expect(await turn).toEqual(afterE5())
  expect(backend.sentTo('GET /api/games/current')).toHaveLength(2)
})

test('a faceoff reloaded mid-turn waits for the running turn, which the game shows only once it has landed', async () => {
  const llm = { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' } as const
  const settings = { ...aGame().settings, mode: 'llm_faceoff' as const, white: llm, black: llm }
  const e4 = aTurn('e4', { ply: 1, color: 'white' })
  const e5 = aTurn('e5')
  // As the backend sends it while Black's turn runs: White's turn landed, Black's not in the game yet.
  const midTurn = afterE4({ settings, llm_turn: e4, llm_turns: [e4] })
  const landed = afterE5({ settings, human_legal_moves: [], llm_turn: e5, llm_turns: [e4, e5] })
  const backend = fakeBackend()
    .on('POST /api/games/current/llm-turn', refused())
    .on('GET /api/games/current', Response.json(midTurn), Response.json(landed))

  const turn = requestLlmTurn(midTurn, new AbortController().signal)
  await vi.advanceTimersByTimeAsync(4000)

  expect(await turn).toEqual(landed)
  expect(backend.sentTo('GET /api/games/current')).toHaveLength(2)
})

test('stops checking once abandoned', async () => {
  const backend = fakeBackend().on('POST /api/games/current/llm-turn', refused())
  const controller = new AbortController()

  const turn = requestLlmTurn(afterE4(), controller.signal)
  const outcome = turn.catch((error: unknown) => error)
  await vi.advanceTimersByTimeAsync(1000)
  controller.abort()
  await vi.advanceTimersByTimeAsync(10000)

  expect(await outcome).toMatchObject({ name: 'AbortError' })
  expect(backend.sentTo('GET /api/games/current')).toHaveLength(0)
})

test('any other failure is the error to show', async () => {
  fakeBackend().on('POST /api/games/current/llm-turn', Response.json({ detail: 'no game started' }, { status: 404 }))

  await expect(requestLlmTurn(afterE4(), new AbortController().signal)).rejects.toThrow('no game started')
})
