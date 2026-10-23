import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { GameLoop } from '@/game/gameLoop'
import { liveTotal } from '@/game/timeUsed'
import { requestLlmTurn, useGameLoop } from '@/game/useGameLoop'
import { fakeBackend, later } from '@/test/fakeBackend'
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

describe("the LLM's Time used", () => {
  /** A side's Time used now, as the page shows it. */
  const now = (state: GameLoop, color: 'white' | 'black') => liveTotal(state.clock!, color, Date.now())
  const asked = afterE4({ time_used: { white: 3, black: 0 }, running_s: null })

  test('ticks during a pending llm-turn, from when the page asked for it', async () => {
    fakeBackend()
      .on('GET /api/games/current', Response.json(asked))
      .on('POST /api/games/current/llm-turn', later().promise)
    const { result } = renderHook(() => useGameLoop())
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(result.current.state.request).toMatchObject({ kind: 'llm-turn' })

    await act(() => vi.advanceTimersByTimeAsync(7000))

    expect(now(result.current.state, 'black')).toBe(7)
    expect(now(result.current.state, 'white')).toBe(3)
  })

  test("meanwhile polls the game every second and follows the backend's total, which stops with the Turn", async () => {
    const backend = fakeBackend()
      .on(
        'GET /api/games/current',
        Response.json(asked),
        Response.json({ ...asked, running_s: 0.8 }),
        Response.json({ ...asked, running_s: 1.8 }),
        // The Turn is over: the backend holds running_s while the Legal counterpart is asked for.
        Response.json({ ...asked, running_s: 1.8 }),
      )
      .on('POST /api/games/current/llm-turn', later().promise)
    const { result } = renderHook(() => useGameLoop())
    await act(() => vi.advanceTimersByTimeAsync(0))

    await act(() => vi.advanceTimersByTimeAsync(1500))
    expect(now(result.current.state, 'black')).toBe(1.3)
    await act(() => vi.advanceTimersByTimeAsync(1500))
    expect(now(result.current.state, 'black')).toBe(1.8)
    await act(() => vi.advanceTimersByTimeAsync(5000))

    expect(now(result.current.state, 'black')).toBe(1.8)
    expect(result.current.state.game).toEqual(asked)
    expect(backend.sentTo('GET /api/games/current').length).toBeGreaterThanOrEqual(8)
  })

  test("after a reload mid-turn, resumes from the time the Turn has run, and follows the backend's checks", async () => {
    const midTurn = afterE4({ time_used: { white: 3, black: 20 }, running_s: 42.5 })
    fakeBackend()
      .on('GET /api/games/current', Response.json(midTurn), Response.json({ ...midTurn, running_s: 45 }))
      .on('POST /api/games/current/llm-turn', refused())
    const { result } = renderHook(() => useGameLoop())
    await act(() => vi.advanceTimersByTimeAsync(0)) // the game loads
    expect(now(result.current.state, 'black')).toBe(62.5)
    await act(() => vi.advanceTimersByTimeAsync(0)) // the turn is refused: one is running

    await act(() => vi.advanceTimersByTimeAsync(3000))

    expect(result.current.state.request).toMatchObject({ kind: 'llm-turn' })
    expect(now(result.current.state, 'black')).toBe(66)
  })

  test('after a reload mid-turn whose waiting fails, it stops where it was', async () => {
    const midTurn = afterE4({ time_used: { white: 3, black: 20 }, running_s: 42.5 })
    fakeBackend()
      .on('GET /api/games/current', Response.json(midTurn), new TypeError('Failed to fetch'))
      .on('POST /api/games/current/llm-turn', refused())
    const { result } = renderHook(() => useGameLoop())
    await act(() => vi.advanceTimersByTimeAsync(0)) // the game loads
    await act(() => vi.advanceTimersByTimeAsync(0)) // the turn is refused: one is running
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(result.current.state.error).toBe('Failed to fetch')

    await act(() => vi.advanceTimersByTimeAsync(10_000))

    expect(now(result.current.state, 'black')).toBe(64.5)
  })
})
