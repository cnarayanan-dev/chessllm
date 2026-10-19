/*
  The game loop, as a reducer: which game is shown, the one request to the backend in flight, and the error line.
  Every state the backend sends comes through `received`: it is shown at once and, if an LLM is to move, its turn is
  asked for. That one rule covers the human's move, a new game in which an LLM plays White, a faceoff and a reload.

  The reducer only says which request to send; useGameLoop sends it and answers with `received` or `failed`, tagged
  with the request's id. An answer to any request but the one in flight is dropped: that is how New game abandons
  the running game's requests (an LLM turn of an abandoned game still lands in that game's log, but nothing follows
  it here). It runs no chess logic (ADR 0001): who is to move and whether the game is over come from the backend.
*/
import type { Color, GameState, NewGame } from '@/api/types'
import { nextGameFrom, type NextGame } from '@/settings/next-game'

/** The one request to the backend in flight. */
export type Request =
  | { id: number; kind: 'load' } // the current game, or a default one if there is none
  | { id: number; kind: 'start'; newGame: NewGame | null } // null: the backend's default settings
  | { id: number; kind: 'move'; uci: string }
  | { id: number; kind: 'llm-turn'; game: GameState } // the turn of this game, as it was when asked for

type NewRequest = Request extends infer R ? (R extends Request ? Omit<R, 'id'> : never) : never

export type GameLoop = {
  /** The game shown: the last state the backend sent, or null before the first. */
  game: GameState | null
  request: Request | null
  /** The error line. */
  error: string | null
  /**
   * The next game's setup, as the Settings modal changes it: set up as the first game shown was, then kept, so the
   * running game keeps its own settings and the changes apply once the next game starts. Null before the first game.
   */
  next: NextGame | null
  /** Counts the moves that have landed and play the move sound: the human's, and each LLM move (not a forfeit). */
  moveSounds: number
  nextId: number
}

export type GameLoopAction =
  | { type: 'new-game'; newGame: NewGame | null }
  | { type: 'human-move'; uci: string }
  | { type: 'next-game'; next: NextGame }
  | { type: 'received'; requestId: number; game: GameState }
  | { type: 'failed'; requestId: number; message: string }

/** idle: no game yet. human: the human to move. llm: waiting for an LLM. over: the game has ended. */
export type Phase = 'idle' | 'human' | 'llm' | 'over'

export const initialGameLoop: GameLoop = {
  game: null,
  request: { id: 1, kind: 'load' },
  error: null,
  next: null,
  moveSounds: 0,
  nextId: 2,
}

export const humanColor = (game: GameState): Color | null =>
  game.settings.white.player === 'human' ? 'white' : game.settings.black.player === 'human' ? 'black' : null

export const llmToMove = (game: GameState): boolean =>
  game.status === 'playing' && game.settings[game.turn].player === 'llm'

export function phase(state: GameLoop): Phase {
  const game = state.game
  if (!game) return 'idle'
  if (game.status === 'over') return 'over'
  return game.turn === humanColor(game) ? 'human' : 'llm'
}

/** Whether the LLM's turn is running: asked for and not yet answered. */
export const waitingForLlm = (state: GameLoop): boolean => state.request?.kind === 'llm-turn'

/** Whether an LLM turn of the same game has landed in `next`, and played a move rather than forfeiting. */
function movedByLlm(game: GameState | null, next: GameState): boolean {
  const landed = game !== null && next.game_id === game.game_id && next.llm_turns.length > game.llm_turns.length
  return landed && (next.llm_turn?.attempts.some((attempt) => attempt.result === 'legal') ?? false)
}

function send(state: GameLoop, request: NewRequest): GameLoop {
  return { ...state, request: { ...request, id: state.nextId }, nextId: state.nextId + 1 }
}

// A game is shown and, if an LLM is to move, its turn is asked for. Starting a turn clears the error line, unless
// keepError: a new game that could not start leaves its error up as the running game's turn starts again.
function show(state: GameLoop, game: GameState, keepError = false): GameLoop {
  const shown = { ...state, game, request: null, next: state.next ?? nextGameFrom(game.settings) }
  if (!llmToMove(game)) return shown
  return send({ ...shown, error: keepError ? state.error : null }, { kind: 'llm-turn', game })
}

export function gameLoop(state: GameLoop, action: GameLoopAction): GameLoop {
  switch (action.type) {
    case 'new-game':
      // Also during an LLM turn or a human move: their answers are dropped from here on.
      return send({ ...state, error: null }, { kind: 'start', newGame: action.newGame })
    case 'human-move':
      if (phase(state) !== 'human' || state.request) return state
      return send({ ...state, error: null }, { kind: 'move', uci: action.uci })
    case 'next-game':
      return { ...state, next: action.next }
    case 'received': {
      const request = state.request
      if (request?.id !== action.requestId) return state
      const sound = request.kind === 'move' || (request.kind === 'llm-turn' && movedByLlm(state.game, action.game))
      return show({ ...state, moveSounds: state.moveSounds + (sound ? 1 : 0) }, action.game)
    }
    case 'failed': {
      const request = state.request
      if (request?.id !== action.requestId) return state
      const failed = { ...state, request: null, error: action.message }
      // The running game goes on, its LLM turn included.
      if (request.kind === 'start' && state.game) return show(failed, state.game, true)
      // The same position again, as a new object, so the board snaps a rejected move's piece back.
      if (request.kind === 'move' && state.game) return { ...failed, game: { ...state.game } }
      return failed
    }
  }
}
