/*
  Chaos moves as the page shows them, read from the resolution the backend sent with the ply and the attempt
  (ADR 0006): the page never resolves a move itself (ADR 0001), so live play and the move history show the same.
*/
import type { Attempt, Ply } from '@/api/types'

export type Resolution = NonNullable<Ply['resolution']>

/** A chaos move or spawn on the board: its caption, and its red arrow or the spawn's square. */
export type ChaosShown = {
  kind: 'chaos' | 'spawn'
  caption: string
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

/**
 * What the board shows for a ply played as a chaos move or spawn, or null for any other ply. The caption is the
 * move, then the resolver's reason: "Qd8→f2: the queen on d8 moves". A spawn and a castle lead with the LLM's own
 * spelling instead, "Qd5: no queen on the board; one appears on d5", as the reason names the squares.
 */
export function chaosShown(ply: Ply | null): ChaosShown | null {
  const resolution = chaosResolution(ply)
  if (!ply || !resolution || !resolution.to) return null
  if (resolution.kind === 'spawn' || !resolution.from) {
    return { kind: 'spawn', caption: `${ply.written}: ${resolution.reason}`, arrows: [], spawn: resolution.to }
  }
  // A castle's rook moves along the same rank as its king, so it gets no arrow of its own: one would cover the other.
  const arrows: [string, string][] = [[resolution.from, resolution.to]]
  if (resolution.rook) return { kind: 'chaos', caption: `${ply.written}: ${resolution.reason}`, arrows, spawn: null }
  const letter = (resolution.piece ?? '').toUpperCase()
  const move = `${letter === 'P' ? '' : letter}${resolution.from}→${resolution.to}`
  return { kind: 'chaos', caption: `${move}: ${resolution.reason}`, arrows, spawn: null }
}
