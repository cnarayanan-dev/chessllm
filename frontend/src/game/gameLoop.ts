/*
  The game loop, as a reducer: which game is shown, the one request to the backend in flight, and the error line.
  Every state the backend sends comes through `received`: it is shown at once and, if an LLM is to move, its turn is
  asked for. That one rule covers the human's move, a new game in which an LLM plays White, a faceoff and a reload.

  The reducer only says which request to send; useGameLoop sends it and answers with `received` or `failed`, tagged
  with the request's id. An answer to any request but the one in flight is dropped: that is how New game abandons
  the running game's requests (an LLM turn of an abandoned game still lands in that game's log, but nothing follows
  it here). It runs no chess logic (ADR 0001): who is to move and whether the game is over come from the backend.

  Pause (CONTEXT.md, with Prompt lab on) is the page's alone: in a game no human plays, the loop asks for no new LLM
  turn once the one running has landed, until Resume. The backend charges a turn's time only while it runs, so a game
  nobody is driving charges no one, and the clock stands still. Try in a running game pauses it first: the probe is
  due once no LLM turn runs (`tryDue`), so a probe never runs alongside a real turn.

  The move history lets the user look back through the game without changing it: the board shows a past position
  from the plies the backend sent, and takes no move until it is back at live. A state that lands meanwhile doesn't
  pull the view.
*/
import type { Color, GameState, LlmTurn, NewGame, Ply } from '@/api/types'
import { played } from '@/game/chaos'
import { clockAt, resynced, stopped, type Clock } from '@/game/timeUsed'

/** The one request to the backend in flight. */
export type Request =
  | { id: number; kind: 'load' } // the current game, if there is one
  | { id: number; kind: 'start'; newGame: NewGame | null } // null: the backend's default settings
  | { id: number; kind: 'move'; uci: string }
  | { id: number; kind: 'llm-turn'; game: GameState } // the turn of this game, as it was when asked for

type NewRequest = Request extends infer R ? (R extends Request ? Omit<R, 'id'> : never) : never

export type GameLoop = {
  /** The game shown: the last state the backend sent, or null before the first. */
  game: GameState | null
  /** Each side's Time used in `game`, the side to move's ticking on (`@/game/timeUsed`); null before the first game. */
  clock: Clock | null
  /** The backend has no current game (a first visit, or after it restarted): none is shown until one is started. */
  noGame: boolean
  request: Request | null
  /** The error line. */
  error: string | null
  /** Counts the moves that have landed and play the move sound: the human's, and each LLM move (not a forfeit). */
  moveSounds: number
  /** The board flashes of the last LLM turn to land, until the next one lands or New game. */
  flash: Flash | null
  /** The past position viewed in the move history, or null when the board shows the game as it is (live). */
  history: History | null
  /** Pause asked for: no new LLM turn is asked for until Resume. Only in a game no human plays (`pauseState`). */
  paused: boolean
  /**
   * The ply shown when a Try was pressed that waits for the game to pause, or null: it is due once no request is in
   * flight (`tryDue`), and the view stays on that ply's turn though the turn running lands meanwhile.
   */
  tryFor: number | null
  nextId: number
}

/** Pause: playing → pausing (the turn running finishes) → paused; no LLM turn is asked for until Resume. */
export type PauseState = 'playing' | 'pausing' | 'paused'

/** An LLM turn that landed, with the square the last move landed on; `id` tells one landing from the next. */
export type Flash = { id: number; turn: LlmTurn; landedOn: string | null }

/**
 * A past position viewed in the move history: the position after ply `ply` (0: the start position, never the last
 * ply, which is live).
 */
export type History = { ply: number }

export type GameLoopAction =
  | { type: 'new-game'; newGame: NewGame | null }
  | { type: 'human-move'; uci: string }
  | { type: 'received'; requestId: number; game: GameState; at: number } // at: when it arrived (Date.now())
  | { type: 'no-game'; requestId: number } // the load's answer when the backend has no current game
  // The game as the page polls it while an LLM turn request is pending: it sets the clock again, nothing else.
  | { type: 'polled'; requestId: number; game: GameState; at: number }
  | { type: 'failed'; requestId: number; message: string; at: number }
  // The move history: view the position after a ply (0: the start; the last ply: live), or step back or forward a ply.
  | { type: 'view'; ply: number }
  | { type: 'step'; by: -1 | 1 }
  // Pause and Resume (at: when, Date.now(), as the resumed turn's clock starts then).
  | { type: 'pause' }
  | { type: 'resume'; at: number }
  // Try: pause first, then probe once paused (`tryDue`); tried once the probe has been sent.
  | { type: 'try' }
  | { type: 'tried' }

/** idle: no game yet. human: the human to move. llm: waiting for an LLM. over: the game has ended. */
export type Phase = 'idle' | 'human' | 'llm' | 'over'

export const initialGameLoop: GameLoop = {
  game: null,
  clock: null,
  noGame: false,
  request: { id: 1, kind: 'load' },
  error: null,
  moveSounds: 0,
  flash: null,
  history: null,
  paused: false,
  tryFor: null,
  nextId: 2,
}

export const humanColor = (game: GameState): Color | null =>
  game.settings.white.player === 'human' ? 'white' : game.settings.black.player === 'human' ? 'black' : null

/** The side at the bottom of the board: the human's in Play LLM, White in an LLM faceoff. */
export const orientation = (game: GameState): Color => humanColor(game) ?? 'white'

export const llmToMove = (game: GameState): boolean =>
  game.status === 'playing' && game.settings[game.turn].player === 'llm'

export function phase(state: GameLoop): Phase {
  const game = state.game
  if (!game) return 'idle'
  if (game.status === 'over') return 'over'
  return game.turn === humanColor(game) ? 'human' : 'llm'
}

/**
 * The position the board shows: the game as it is, or the past position viewed, all as the backend sent them
 * (ADR 0001). `ply` is the ply it follows (0: the start position) and `move` that ply. `animateFrom` is set only
 * in the history: the board puts that position up first, so the move animates in from the position before it.
 */
export type Shown = {
  ply: number
  fen: string
  lastMove: string | null
  check: boolean
  animateFrom: string | null
  move: Ply | null
}

export function shownPosition(state: GameLoop): Shown | null {
  const game = state.game
  if (!game) return null
  if (!state.history) {
    const move = game.plies.at(-1) ?? null
    return { ply: game.plies.length, fen: game.fen, lastMove: game.last_move, check: game.check, animateFrom: null, move }
  }
  const ply = state.history.ply
  if (ply === 0) return { ply, fen: game.plies[0].fen_before, lastMove: null, check: false, animateFrom: null, move: null }
  const move = game.plies[ply - 1]
  return { ply, fen: move.fen_after, lastMove: move.move, check: move.check, animateFrom: move.fen_before, move }
}

/** The side whose pieces the user may move now, or null: only the human, on their turn, at the live position. */
export const boardInput = (state: GameLoop): Color | null =>
  phase(state) === 'human' && !state.history ? humanColor(state.game!) : null

/** The history after viewing the position after `ply`, kept within the game: the last ply is live. */
function view(state: GameLoop, ply: number): GameLoop {
  const plies = state.game?.plies.length ?? 0
  const target = Math.max(ply, 0)
  const history = target >= plies ? null : { ply: target }
  if (history?.ply === state.history?.ply) return state
  return { ...state, history }
}

/** Whether the LLM's turn is running: asked for and not yet answered. */
export const waitingForLlm = (state: GameLoop): boolean => state.request?.kind === 'llm-turn'

/** Whether the game can be paused: one being played in which LLMs move on their own, not Play LLM. */
const pausable = (game: GameState | null): boolean => game?.status === 'playing' && humanColor(game) === null

/** Where Pause stands in the game shown, or null when it has none (Play LLM, or the game is over). */
export function pauseState(state: GameLoop): PauseState | null {
  if (!pausable(state.game)) return null
  if (!state.paused) return 'playing'
  return waitingForLlm(state) ? 'pausing' : 'paused'
}

/**
 * Whether a Try may probe now: one was asked for and no request is in flight (in a running game, it has paused; a
 * New game being started may yet replace the game).
 */
export const tryDue = (state: GameLoop): boolean => state.tryFor !== null && state.request === null

/** Whether the page asks for the LLM's turn in `game` as it is shown: an LLM is to move and the game isn't paused. */
const asksTurn = (state: GameLoop, game: GameState): boolean => llmToMove(game) && !(state.paused && pausable(game))

/** Whether an LLM turn of the same game has landed in `next`, played or forfeited. */
function llmTurnLanded(game: GameState | null, next: GameState): boolean {
  return game !== null && next.game_id === game.game_id && next.llm_turns.length > game.llm_turns.length
}

/** Whether an LLM turn of the same game has landed in `next`, and played a move (a chaos move too) rather than forfeiting. */
function movedByLlm(game: GameState | null, next: GameState): boolean {
  return llmTurnLanded(game, next) && (next.llm_turn?.attempts.some(played) ?? false)
}

function send(state: GameLoop, request: NewRequest): GameLoop {
  return { ...state, request: { ...request, id: state.nextId }, nextId: state.nextId + 1 }
}

// A game is shown and, if an LLM is to move and the game isn't paused, its turn is asked for. Starting a turn clears the error line, unless
// keepError: a new game that could not start leaves its error up as the running game's turn starts again.
function show(state: GameLoop, game: GameState, keepError = false): GameLoop {
  const shown = { ...state, game, request: null }
  if (!asksTurn(state, game)) return shown
  return send({ ...shown, error: keepError ? state.error : null }, { kind: 'llm-turn', game })
}

export function gameLoop(state: GameLoop, action: GameLoopAction): GameLoop {
  switch (action.type) {
    case 'new-game': {
      // Also during an LLM turn or a human move: their answers are dropped from here on. The pause and a Try waiting
      // for it stay until the new game arrives: one that cannot start leaves the running game as it was.
      const fresh = { ...state, error: null, flash: null, history: null }
      return send(fresh, { kind: 'start', newGame: action.newGame })
    }
    case 'human-move':
      if (!boardInput(state) || state.request) return state
      return send({ ...state, error: null }, { kind: 'move', uci: action.uci })
    case 'received': {
      const request = state.request
      if (request?.id !== action.requestId) return state
      const sound = request.kind === 'move' || (request.kind === 'llm-turn' && movedByLlm(state.game, action.game))
      const turn = request.kind === 'llm-turn' && llmTurnLanded(state.game, action.game) ? action.game.llm_turn : null
      const flash = turn
        ? { id: request.id, turn, landedOn: action.game.last_move?.slice(2, 4) ?? null }
        : state.flash
      // The view stays where it is in the same game, or on the turn a waiting Try was pressed for; another game is
      // shown live, playing, and a Try waiting for the old one's pause is dropped.
      const same = state.game?.game_id === action.game.game_id
      const held = same && state.tryFor !== null && state.tryFor < action.game.plies.length
      const history = same ? (state.history ?? (held ? { ply: state.tryFor! } : null)) : null
      const kept = same ? state : { ...state, paused: false, tryFor: null }
      const moveSounds = state.moveSounds + (sound ? 1 : 0)
      // The page asks for the LLM's turn as the state arrives (show), so the LLM ticks from then; paused, nobody does.
      const clock = clockAt(action.game, action.at, asksTurn(kept, action.game))
      return show({ ...kept, clock, noGame: false, moveSounds, flash, history }, action.game)
    }
    case 'polled': {
      const { request, game, clock } = state
      if (request?.id !== action.requestId || request.kind !== 'llm-turn' || !game || !clock) return state
      if (action.game.game_id !== game.game_id) return state
      return { ...state, clock: resynced(clock, game, action.game, action.at) }
    }
    case 'no-game':
      if (state.request?.id !== action.requestId) return state
      return { ...state, noGame: true, request: null }
    case 'failed': {
      const request = state.request
      if (request?.id !== action.requestId) return state
      // Nobody drives the game after its LLM turn failed: the clock stands where it was. A new game that could not
      // start leaves the running game's clock as it was, its turn asked for again.
      const clock = request.kind === 'llm-turn' && state.clock ? stopped(state.clock, action.at) : state.clock
      const failed = { ...state, request: null, error: action.message, clock }
      // The running game goes on, its LLM turn included.
      if (request.kind === 'start' && state.game) return show(failed, state.game, true)
      // The same position again, as a new object, so the board snaps a rejected move's piece back.
      if (request.kind === 'move' && state.game) return { ...failed, game: { ...state.game } }
      return failed
    }
    case 'view':
      return view(state, action.ply)
    case 'step':
      return view(state, (state.history?.ply ?? state.game?.plies.length ?? 0) + action.by)
    case 'pause':
      return pauseState(state) === 'playing' ? { ...state, paused: true } : state
    case 'resume': {
      if (!state.paused) return state
      // Also while the turn running finishes: the pause is taken back, and a Try waiting for it dropped.
      const resumed = { ...state, paused: false, tryFor: null }
      const game = state.game
      if (state.request || !game || !asksTurn(resumed, game)) return resumed
      return show({ ...resumed, clock: clockAt(game, action.at, true) }, game)
    }
    case 'try':
      return {
        ...state,
        tryFor: state.history?.ply ?? state.game?.plies.length ?? 0,
        paused: state.paused || pausable(state.game),
      }
    case 'tried':
      return { ...state, tryFor: null }
  }
}
