// Game states as the API sends them, for tests.
import type { GameState, LlmTurn, Ply } from '@/api/types'

export const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
export const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
export const AFTER_E5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
export const AFTER_NF3 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2'
export const AFTER_NC6 = 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3'

/**
 * The plies of a game from the start position, each given as [UCI, as written, FEN after it]: each ply's position
 * before it is the one the ply before left, as the backend sends them.
 */
export function plies(...moves: [move: string, written: string, fenAfter: string][]): Ply[] {
  return moves.map(([move, written, fenAfter], index) => ({
    ply: index + 1,
    color: index % 2 === 0 ? 'white' : 'black',
    move,
    written,
    fen_before: index === 0 ? START : moves[index - 1][2],
    fen_after: fenAfter,
    check: false,
  }))
}

export const E4: [string, string, string] = ['e2e4', 'e4', AFTER_E4]
export const E5: [string, string, string] = ['e7e5', 'e5', AFTER_E5]
export const NF3: [string, string, string] = ['g1f3', 'Nf3', AFTER_NF3]
export const NC6: [string, string, string] = ['b8c6', 'Nc6', AFTER_NC6]

/** A Play LLM game in which the human plays White against qwen3.5:9b, at the start, White to move. */
export function aGame(overrides: Partial<GameState> = {}): GameState {
  return {
    game_id: 'game-1',
    fen: START,
    pgn: '',
    turn: 'white',
    human_legal_moves: ['a2a3', 'b2b3', 'd2d4', 'e2e3', 'e2e4', 'g1f3'],
    last_move: null,
    plies: [],
    check: false,
    llm_turn: null,
    llm_turns: [],
    settings: {
      mode: 'play_llm',
      white: { player: 'human' },
      black: { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
      sampling: {},
    },
    status: 'playing',
    result: null,
    end_reason: null,
    stats: {
      white: null,
      black: {
        legal_move_streak: 0,
        illegal_moves: { invalid: 0, illegal: 0, ambiguous: 0 },
        recovered_turns: 0,
        notation_slips: 0,
      },
    },
    ...overrides,
  }
}

/** The same game after the human played e2e4: Black (the LLM) to move. */
export function afterE4(overrides: Partial<GameState> = {}): GameState {
  return aGame({
    fen: AFTER_E4,
    pgn: '1. e4',
    turn: 'black',
    human_legal_moves: [],
    last_move: 'e2e4',
    plies: plies(E4),
    ...overrides,
  })
}

/** An LLM turn whose only attempt is the legal move given. */
export function aTurn(move: string, overrides: Partial<LlmTurn> = {}): LlmTurn {
  return {
    ply: 2,
    color: 'black',
    attempts: [
      {
        move,
        san: move,
        notation_slip: false,
        result: 'legal',
        feedback_sent: null,
        raw_reply: `{"move": "${move}"}`,
        thinking: null,
        error: null,
        latency_s: 1.2,
      },
    ],
    thinking: null,
    ...overrides,
  }
}

/** The game after 1. e4 e5: White (the human) to move again. */
export function afterE5(overrides: Partial<GameState> = {}): GameState {
  const turn = aTurn('e5')
  return aGame({
    fen: AFTER_E5,
    pgn: '1. e4 e5',
    human_legal_moves: ['d2d4', 'f1c4', 'g1f3'],
    last_move: 'e7e5',
    plies: plies(E4, E5),
    llm_turn: turn,
    llm_turns: [turn],
    ...overrides,
  })
}
