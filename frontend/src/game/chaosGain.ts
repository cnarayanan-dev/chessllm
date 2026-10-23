/*
  Chaos gains as the page shows them (CONTEXT.md): the backend works each one out (ADR 0001), the page only shows the
  gain over the Legal counterpart, and only when the game asks for Legal counterparts. The gain over Stockfish's
  best move is never shown.
*/
import type { Color, GameState, LlmTurn } from '@/api/types'

const MINUS = '−'

/** Whether the game shows Chaos gains: under Chaos rules with its Legal counterpart switch on. */
export const showsChaosGains = (game: GameState) => game.settings.rules === 'chaos' && game.settings.legal_counterpart === true

/** Whether the turn's Legal counterpart gave a move: a failed one has no move and no gain (CONTEXT.md). */
const counterpartMoved = (turn: LlmTurn) => turn.legal_counterpart?.move != null

/** The gain over the Legal counterpart of the turn's Chaos move, to show; undefined when there is none to show. */
export const shownGain = (game: GameState, turn: LlmTurn) =>
  showsChaosGains(game) && counterpartMoved(turn) ? (turn.chaos_gain ?? undefined) : undefined

/** Pawns as shown: "+6.6", "−19.6", "0.0". */
export function gainText(pawns: number): string {
  const tenths = Math.round(pawns * 10)
  if (tenths === 0) return '0.0'
  return (tenths > 0 ? '+' : MINUS) + (Math.abs(tenths) / 10).toFixed(1)
}

/** A side's Chaos gain score: its judged gains added up, the Chaos moves it covers and those not judged among them. */
export type GainScore = { total: number; moves: number; unjudged: number }

export function gainScore(game: GameState, color: Color): GainScore {
  const gains = game.llm_turns.filter((turn) => turn.color === color && counterpartMoved(turn)).flatMap((turn) => (turn.chaos_gain ? [turn.chaos_gain.vs_counterpart] : []))
  const judged = gains.filter((gain): gain is number => gain !== null)
  return { total: judged.reduce((sum, gain) => sum + gain, 0), moves: gains.length, unjudged: gains.length - judged.length }
}
