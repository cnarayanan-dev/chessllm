// Runs the game loop: sends the request the reducer asks for and answers it with the backend's state or error.
// A request the reducer no longer waits for is aborted, and its answer, should one arrive, is dropped.
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { ApiError, getGame, playLlmTurn, playMove, startGame } from '@/api/client'
import type { GameState, NewGame } from '@/api/types'
import { playMoveSound } from '@/components/board/moveSound'
import { gameLoop, initialGameLoop, llmToMove, tryDue, type Request } from '@/game/gameLoop'

// A Try that waited for a pause the game no longer takes: resumed, or another game started.
const TRY_DROPPED = 'The probe was not asked: the game was resumed, or a new one started, before it paused.'
const TRY_LEFT = 'The probe was not asked: the page was left before the game paused.'
const POLL_MS = 2000
const CLOCK_POLL_MS = 1000

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    })
  })
}

/** Hands `onPoll` the game every second until aborted; a check that fails is skipped. */
async function pollEverySecond(signal: AbortSignal, onPoll: (game: GameState) => void): Promise<void> {
  while (!signal.aborted) {
    try {
      await wait(CLOCK_POLL_MS, signal)
      onPoll(await getGame(signal))
    } catch {
      // Aborted, or this check failed: the next one may not.
    }
  }
}

/**
 * Asks for the LLM's turn in `game`. Its answer only comes once the turn and what follows it are over, so meanwhile
 * the game is checked every second and handed to `onPoll`, for the LLM's Time used. A 409 means the backend won't
 * start the turn, most often because one is already running (another tab, or this page before a reload). The page
 * can't attach to that turn, so it checks the game every 2 s until the turn has landed, each check handed to `onPoll`
 * too. A stale state also gets a 409, and the first check settles it.
 */
export async function requestLlmTurn(
  game: GameState,
  signal: AbortSignal,
  onPoll: (game: GameState) => void = () => {},
): Promise<GameState> {
  const polling = new AbortController()
  signal.addEventListener('abort', () => polling.abort())
  void pollEverySecond(polling.signal, onPoll)
  try {
    return await playLlmTurn(signal)
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) throw error
    polling.abort() // the checks below take over
    for (;;) {
      await wait(POLL_MS, signal)
      const current = await getGame(signal)
      onPoll(current)
      const moved = current.llm_turns.length > game.llm_turns.length
      if (current.game_id !== game.game_id || moved || !llmToMove(current)) return current
    }
  } finally {
    polling.abort()
  }
}

// After a reload the current game is shown again, and its LLM turn started, or waited for if one is running. With no
// current game (404: a first visit, or the backend restarted), null: none is started until the visitor starts one.
async function load(signal: AbortSignal): Promise<GameState | null> {
  try {
    return await getGame(signal)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

function perform(request: Request, signal: AbortSignal, onPoll: (game: GameState) => void): Promise<GameState | null> {
  switch (request.kind) {
    case 'load':
      return load(signal)
    case 'start':
      return startGame(request.newGame, signal)
    case 'move':
      return playMove(request.uci, signal)
    case 'llm-turn':
      return requestLlmTurn(request.game, signal, onPoll)
  }
}

export function useGameLoop() {
  const [state, dispatch] = useReducer(gameLoop, initialGameLoop)
  const request = state.request
  useEffect(() => {
    if (!request) return
    const controller = new AbortController()
    // The game as polled during an LLM turn request: it only sets the clock.
    const onPoll = (game: GameState) => {
      if (!controller.signal.aborted) dispatch({ type: 'polled', requestId: request.id, game, at: Date.now() })
    }
    perform(request, controller.signal, onPoll).then(
      (received) => {
        if (controller.signal.aborted) return
        dispatch(
          received
            ? { type: 'received', requestId: request.id, game: received, at: Date.now() }
            : { type: 'no-game', requestId: request.id },
        )
      },
      (error: unknown) => {
        if (controller.signal.aborted) return
        const message = error instanceof Error ? error.message : String(error)
        dispatch({ type: 'failed', requestId: request.id, message, at: Date.now() })
      },
    )
    return () => controller.abort()
  }, [request])

  // Once the backend has taken a move, so a rejected one stays silent.
  const sounds = useRef(state.moveSounds)
  useEffect(() => {
    if (state.moveSounds === sounds.current) return
    sounds.current = state.moveSounds
    playMoveSound()
  }, [state.moveSounds])

  // The Tries waiting for the game to pause: each is let go once no LLM turn runs, or failed once dropped.
  const tries = useRef<{ resolve: () => void; reject: (error: Error) => void }[]>([])
  const due = tryDue(state)
  const asked = state.tryFor !== null
  useEffect(() => {
    if (tries.current.length === 0 || (asked && !due)) return
    const waiting = tries.current
    tries.current = []
    if (due) {
      dispatch({ type: 'tried' })
      for (const { resolve } of waiting) resolve()
    } else {
      for (const { reject } of waiting) reject(new Error(TRY_DROPPED))
    }
  }, [asked, due])
  // Left with a Try still waiting: it fails, so nothing waits on it.
  useEffect(
    () => () => {
      const waiting = tries.current
      tries.current = []
      for (const { reject } of waiting) reject(new Error(TRY_LEFT))
    },
    [],
  )

  const newGame = useCallback((settings: NewGame | null) => dispatch({ type: 'new-game', newGame: settings }), [])
  const humanMove = useCallback((uci: string) => dispatch({ type: 'human-move', uci }), [])
  const viewPly = useCallback((ply: number) => dispatch({ type: 'view', ply }), [])
  const step = useCallback((by: -1 | 1) => dispatch({ type: 'step', by }), [])

  const pause = useCallback(() => dispatch({ type: 'pause' }), [])
  const resume = useCallback(() => dispatch({ type: 'resume', at: Date.now() }), [])
  /** Pauses a running game no human plays, and resolves once no LLM turn runs, so a probe may be asked then. */
  const pausedForTry = useCallback(
    () =>
      new Promise<void>((resolve, reject) => {
        tries.current.push({ resolve, reject })
        dispatch({ type: 'try' })
      }),
    [],
  )

  return { state, newGame, humanMove, viewPly, step, pause, resume, pausedForTry }
}
