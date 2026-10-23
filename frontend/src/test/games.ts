// Game states as the API sends them, for tests.
import type { Attempt, GameState, LlmTurn, Ply } from '@/api/types'

type Resolution = NonNullable<Ply['resolution']>

export const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
export const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
export const AFTER_E5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
export const AFTER_NF3 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2'
export const AFTER_NC6 = 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3'

type PlyGiven = [move: string, written: string, fenAfter: string, resolution?: Resolution]

/**
 * The plies of a game from the start position, each given as [UCI, as written, FEN after it], and a chaos move's
 * resolution: each ply's position before it is the one the ply before left, as the backend sends them.
 */
export function plies(...moves: PlyGiven[]): Ply[] {
  return moves.map(([move, written, fenAfter, resolution], index) => ({
    ply: index + 1,
    color: index % 2 === 0 ? 'white' : 'black',
    move,
    written,
    fen_before: index === 0 ? START : moves[index - 1][2],
    fen_after: fenAfter,
    check: false,
    time_s: 0,
    ...(resolution ? { resolution } : {}),
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
      max_attempts: 5,
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
    time_used: { white: 0, black: 0 },
    running_s: 0,
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

/** The Reasoning the fixtures' LLMs give for a move, with thinking off. */
export const reasoningFor = (move: string) => `Reasoning for ${move}.`

/** The raw reply with thinking off: the Reasoning, then the move. */
const replyWith = (move: string) => JSON.stringify({ reasoning: reasoningFor(move), move })

/** An LLM turn whose only attempt is the legal move given, with thinking off. */
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
        raw_reply: replyWith(move),
        thinking: null,
        reasoning: reasoningFor(move),
        error: null,
        latency_s: 1.2,
      },
    ],
    time_s: 1.2,
    thinking: null,
    reasoning: reasoningFor(move),
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

// A Chaos rules game, as the backend played it: 1. e4 Bb4 (the bishop jumps over its own pawn) 2. c3 Qg5
// 3. d4 e5 4. Bxg5 Qd5 (a spawn: the queen is gone) 5. Nf3 O-O (illegal: the knight is still on g8) 6. Nbd2 Kh6
// 7. Bxh6, a King capture.
export const CHAOS_PLIES: PlyGiven[] = [
  E4,
  ['f8b4', 'Bb4', 'rnbqk1nr/pppppppp/8/8/1b2P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2',
    { kind: 'chaos', from: 'f8', to: 'b4', piece: 'b', rook: null, reason: 'the bishop on f8 moves' }],
  ['c2c3', 'c3', 'rnbqk1nr/pppppppp/8/8/1b2P3/2P5/PP1P1PPP/RNBQKBNR b KQkq - 0 2'],
  ['d8g5', 'Qg5', 'rnb1k1nr/pppppppp/8/6q1/1b2P3/2P5/PP1P1PPP/RNBQKBNR w KQkq - 1 3',
    { kind: 'chaos', from: 'd8', to: 'g5', piece: 'q', rook: null, reason: 'the queen on d8 moves' }],
  ['d2d4', 'd4', 'rnb1k1nr/pppppppp/8/6q1/1b1PP3/2P5/PP3PPP/RNBQKBNR b KQkq - 0 3'],
  ['e7e5', 'e5', 'rnb1k1nr/pppp1ppp/8/4p1q1/1b1PP3/2P5/PP3PPP/RNBQKBNR w KQkq - 0 4'],
  ['c1g5', 'Bxg5', 'rnb1k1nr/pppp1ppp/8/4p1B1/1b1PP3/2P5/PP3PPP/RN1QKBNR b KQkq - 0 4'],
  ['Q@d5', 'Qd5', 'rnb1k1nr/pppp1ppp/8/3qp1B1/1b1PP3/2P5/PP3PPP/RN1QKBNR w KQkq - 1 5',
    { kind: 'spawn', from: null, to: 'd5', piece: 'q', rook: null, reason: 'no queen on the board; one appears on d5' }],
  ['g1f3', 'Nf3', 'rnb1k1nr/pppp1ppp/8/3qp1B1/1b1PP3/2P2N2/PP3PPP/RN1QKB1R b KQkq - 2 5'],
  ['e8g8', 'O-O', 'rnb2rk1/pppp1ppp/8/3qp1B1/1b1PP3/2P2N2/PP3PPP/RN1QKB1R w KQ - 0 6',
    { kind: 'chaos', from: 'e8', to: 'g8', piece: 'k', rook: ['h8', 'f8'], reason: 'illegal O-O: king e8→g8, rook h8→f8' }],
  ['b1d2', 'Nbd2', 'rnb2rk1/pppp1ppp/8/3qp1B1/1b1PP3/2P2N2/PP1N1PPP/R2QKB1R b KQ - 1 6'],
  ['g8h6', 'Kh6', 'rnb2r2/pppp1ppp/7k/3qp1B1/1b1PP3/2P2N2/PP1N1PPP/R2QKB1R w KQ - 2 7',
    { kind: 'chaos', from: 'g8', to: 'h6', piece: 'k', rook: null, reason: 'no king can reach h6 by its movement; g8 is nearest' }],
  ['g5h6', 'Bxh6', 'rnb2r2/pppp1ppp/7B/3qp3/1b1PP3/2P2N2/PP1N1PPP/R2QKB1R b KQ - 0 7'],
]

/** An attempt that the backend played as a chaos move or spawn: an illegal move, with its resolution. */
export function chaosAttempt(move: string, resolution: Resolution, overrides: Partial<Attempt> = {}): Attempt {
  return {
    move,
    san: null,
    notation_slip: false,
    result: 'illegal',
    feedback_sent: null,
    raw_reply: replyWith(move),
    thinking: null,
    reasoning: reasoningFor(move),
    error: null,
    latency_s: 1.2,
    resolution,
    ...overrides,
  }
}

/**
 * The Chaos rules game above after its first `count` plies, each LLM turn as the backend logged it: its move,
 * played as a chaos move or spawn when it has a resolution.
 */
export function chaosGame(count: number, overrides: Partial<GameState> = {}): GameState {
  const given = CHAOS_PLIES.slice(0, count)
  const turns: LlmTurn[] = given.flatMap(([, written, , resolution], index) =>
    index % 2 === 0
      ? []
      : [
          resolution
            ? {
                ply: index + 1,
                color: 'black' as const,
                attempts: [chaosAttempt(written, resolution)],
                time_s: 1.2,
                thinking: null,
                reasoning: reasoningFor(written),
              }
            : aTurn(written, { ply: index + 1 }),
        ],
  )
  const last = given.at(-1)!
  const chaosMoves = given.filter(([, , , resolution]) => resolution).length
  const spawns = given.filter(([, , , resolution]) => resolution?.kind === 'spawn').length
  const base = aGame()
  return aGame({
    fen: last[2],
    pgn: given.map(([, written], index) => (index % 2 === 0 ? `${index / 2 + 1}. ${written}` : written)).join(' '),
    turn: count % 2 === 0 ? 'white' : 'black',
    // The human's next move in the game above, if any.
    human_legal_moves: count % 2 === 0 && count < CHAOS_PLIES.length ? [CHAOS_PLIES[count][0], 'a2a3'] : [],
    last_move: last[0],
    plies: plies(...given),
    llm_turn: turns.at(-1) ?? null,
    llm_turns: turns,
    settings: { ...base.settings, rules: 'chaos' },
    stats: {
      white: null,
      black: {
        legal_move_streak: 0,
        illegal_moves: { invalid: 0, illegal: chaosMoves, ambiguous: 0 },
        recovered_turns: 0,
        notation_slips: 0,
        chaos_moves: chaosMoves,
        spawns,
      },
    },
    ...overrides,
  })
}
