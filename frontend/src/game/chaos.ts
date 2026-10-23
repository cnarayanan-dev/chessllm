/*
  Chaos moves as the page shows them, read from the resolution the backend sent with the ply and the attempt
  (ADR 0006): the page never resolves a move itself (ADR 0001), so live play and the move history show the same.
*/
import type { Attempt, GameState, LlmTurn, Ply } from '@/api/types'

export type Resolution = NonNullable<Ply['resolution']>

/** A chaos move or spawn on the board: its red arrow, or the spawn's square. */
export type ChaosShown = {
  arrows: [string, string][]
  spawn: string | null
}

/** The resolution of a chaos move or spawn, or null for any other move or attempt. */
export function chaosResolution(of: { resolution?: Resolution | null } | null | undefined): Resolution | null {
  const resolution = of?.resolution
  return resolution && (resolution.kind === 'chaos' || resolution.kind === 'spawn') ? resolution : null
}

/** Whether the attempt was played: a legal move, or under Chaos rules a chaos move or spawn. */
export const played = (attempt: Attempt) => attempt.result === 'legal' || chaosResolution(attempt) !== null

const ILLEGAL_RESULTS: Attempt['result'][] = ['invalid', 'illegal', 'ambiguous']

/**
 * Whether the attempt was an Illegal move: badly formed, rule-breaking or ambiguous, a chaos move included. A cut-off
 * answer had no move to judge, and a timeout or failed call no answer, so neither is one (ADR 0007).
 */
export const illegalMove = (attempt: Attempt) => ILLEGAL_RESULTS.includes(attempt.result)

/** Whether the attempt was an illegal move that was not played: a chaos move is the move itself. */
export const illegalTry = (attempt: Attempt) => illegalMove(attempt) && !played(attempt)

/** What the board shows for a ply played as a chaos move or spawn, or null for any other ply. */
export function chaosShown(ply: Ply | null): ChaosShown | null {
  const resolution = chaosResolution(ply)
  if (!ply || !resolution || !resolution.to) return null
  if (resolution.kind === 'spawn' || !resolution.from) return { arrows: [], spawn: resolution.to }
  // A castle's rook moves along the same rank as its king, so it gets no arrow of its own: one would cover the other.
  return { arrows: [[resolution.from, resolution.to]], spawn: null }
}

type LegalCounterpart = NonNullable<LlmTurn['legal_counterpart']>

/** A Legal counterpart that gave a move: the position it would have left, as the backend worked it out. */
export type CounterpartMove = LegalCounterpart & { move: string; san: string; fen_after: string }

/** The Legal counterpart of the Chaos move played at ply `ply`, or null: no Chaos move, none asked, or it failed. */
export function counterpartAt(game: GameState, ply: number): CounterpartMove | null {
  const counterpart = game.llm_turns.find((turn) => turn.ply === ply)?.legal_counterpart
  return counterpart && counterpart.move !== null && counterpart.san !== null && counterpart.fen_after !== null
    ? (counterpart as CounterpartMove)
    : null
}
