// Runs the game loop: sends the request the reducer asks for and answers it with the backend's state or error.
// A request the reducer no longer waits for is aborted, and its answer, should one arrive, is dropped.
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { ApiError, getGame, playLlmTurn, playMove, startGame } from '@/api/client'
import type { GameState, NewGame } from '@/api/types'
import { playMoveSound } from '@/components/board/moveSound'
import { gameLoop, initialGameLoop, llmToMove, type Request } from '@/game/gameLoop'

const POLL_MS = 2000

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    })
  })
}

/**
 * Asks for the LLM's turn in `game`. A 409 means the backend won't start the turn, most often because one is already
 * running (another tab, or this page before a reload). The page can't attach to that turn, so it checks the game every
 * 2 s until the turn has landed. A stale state also gets a 409, and the first check settles it.
 */
export async function requestLlmTurn(game: GameState, signal: AbortSignal): Promise<GameState> {
  try {
    return await playLlmTurn(signal)
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) throw error
    for (;;) {
      await wait(POLL_MS, signal)
      const current = await getGame(signal)
      const moved = current.llm_turns.length > game.llm_turns.length
      if (current.game_id !== game.game_id || moved || !llmToMove(current)) return current
    }
  }
}

// After a reload the current game is shown again, and its LLM turn started, or waited for if one is running.
async function load(signal: AbortSignal): Promise<GameState> {
  try {
    return await getGame(signal)
  } catch (error) {
    if (signal.aborted) throw error
    return startGame(null, signal)
  }
}

function perform(request: Request, signal: AbortSignal): Promise<GameState> {
  switch (request.kind) {
    case 'load':
      return load(signal)
    case 'start':
      return startGame(request.newGame, signal)
    case 'move':
      return playMove(request.uci, signal)
    case 'llm-turn':
      return requestLlmTurn(request.game, signal)
  }
}

export function useGameLoop() {
  const [state, dispatch] = useReducer(gameLoop, initialGameLoop)
  const request = state.request
  useEffect(() => {
    if (!request) return
    const controller = new AbortController()
    perform(request, controller.signal).then(
      (received) => {
        if (controller.signal.aborted) return
        dispatch({ type: 'received', requestId: request.id, game: received })
      },
      (error: unknown) => {
        if (controller.signal.aborted) return
        dispatch({ type: 'failed', requestId: request.id, message: error instanceof Error ? error.message : String(error) })
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

  const newGame = useCallback((settings: NewGame | null) => dispatch({ type: 'new-game', newGame: settings }), [])
  const humanMove = useCallback((uci: string) => dispatch({ type: 'human-move', uci }), [])

  return { state, newGame, humanMove }
}
