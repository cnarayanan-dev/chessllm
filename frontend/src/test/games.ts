// Game states as the API sends them, for tests.
import type { GameState, LlmTurn } from '@/api/types'

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

/** A Play LLM game in which the human plays White against qwen3.5:9b, at the start, White to move. */
export function aGame(overrides: Partial<GameState> = {}): GameState {
  return {
    game_id: 'game-1',
    fen: START,
    pgn: '',
    turn: 'white',
    human_legal_moves: ['a2a3', 'b2b3', 'd2d4', 'e2e3', 'e2e4', 'g1f3'],
    last_move: null,
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
    fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
    pgn: '1. e4',
    turn: 'black',
    human_legal_moves: [],
    last_move: 'e2e4',
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
    fen: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
    pgn: '1. e4 e5',
    human_legal_moves: ['d2d4', 'f1c4', 'g1f3'],
    last_move: 'e7e5',
    llm_turn: turn,
    llm_turns: [turn],
    ...overrides,
  })
}
