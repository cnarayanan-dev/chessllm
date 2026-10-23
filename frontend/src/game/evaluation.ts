/*
  The Evaluation bar's reading of the backend's Evaluations (CONTEXT.md): the page judges no position itself
  (ADR 0001), it only turns each ply's Evaluation, from White's point of view, into the bar's fill and number.
*/
import type { Color, Evaluation, GameState } from '@/api/types'
import type { CounterpartMove } from '@/game/chaos'
import { faceoff, resultText } from '@/game/wording'

const MINUS = '−'
/** An Evaluation's cap, in pawns. */
const CAP = 10

/** What the bar shows. `share` is White's part of it in percent; `label` its number, at the leading side's end. */
export type Bar = {
  state: 'judged' | 'evaluating' | 'unjudged' | 'over' | 'none'
  share: number
  label: string
  /** The value as read out. */
  text: string
  leader: Color
  /** The tooltip: its title and its detail. */
  title: string
  detail: string
  /** Whether it shows a position never played, a Legal counterpart's: the bar is outlined. */
  preview?: boolean
}

const clamp = (pawns: number) => Math.max(-CAP, Math.min(CAP, pawns))

/** Pawns as shown: "+2.4", "−0.8", "0.0", "+10.0". */
function pawnsText(pawns: number): string {
  const tenths = Math.round(clamp(pawns) * 10)
  if (tenths === 0) return '0.0'
  const size = Math.abs(tenths) / 10
  return (tenths > 0 ? '+' : MINUS) + size.toFixed(1)
}

/** The Evaluation, if the position was judged: neither missing nor not judged. */
const judgedOrNull = (evaluation: Evaluation | null | undefined): Evaluation | null =>
  evaluation && evaluation.unjudged === null && (evaluation.pawns !== null || evaluation.mate !== null)
    ? evaluation
    : null

/** The Evaluation as shown: "+2.4", or a mate, "M3" when White gives it and "−M3" when Black does. */
export function evaluationText(evaluation: Evaluation): string {
  const { mate, pawns } = evaluation
  if (mate === null) return pawnsText(pawns ?? 0)
  return `${mate < 0 ? MINUS : ''}M${Math.abs(mate)}`
}

/** White's win chance in percent, as lichess works it out from the Evaluation capped at ±10; a mate fills the bar. */
export function whiteShare(evaluation: Evaluation): number {
  const { mate, pawns } = evaluation
  if (mate !== null) return mate > 0 ? 100 : 0
  const centipawns = clamp(pawns ?? 0) * 100
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * centipawns)) - 1)
}

/** The ply as the move list names it, e.g. "1. e4" or "1… e5". */
function plyName(game: GameState, ply: number): string {
  const move = game.plies[ply - 1]
  return `${Math.ceil(ply / 2)}${move.color === 'white' ? '.' : '…'} ${move.written}`
}

/** The result as the bar shows it, filled for the winner. */
const RESULTS: Record<string, { label: string; share: number }> = {
  '1-0': { label: '1-0', share: 100 },
  '0-1': { label: '0-1', share: 0 },
  '1/2-1/2': { label: '½-½', share: 50 },
}

const leaderOf = (share: number): Color => (share >= 50 ? 'white' : 'black')

/** The engine and its search as the tooltip names them, e.g. "Stockfish 19 · depth 16, 1 thread, 64 MB hash". */
function engineName(engine: NonNullable<GameState['evaluator']>): string {
  const setting = ([name, value]: [string, number]) => {
    if (name === 'depth') return `depth ${value}`
    if (name === 'threads') return `${value} thread${value === 1 ? '' : 's'}`
    if (name === 'hash_mb') return `${value} MB hash`
    return `${name.replaceAll('_', ' ')} ${value}`
  }
  const search = Object.entries(engine.search).map(setting)
  return search.length ? `${engine.version} · ${search.join(', ')}` : engine.version
}

/**
 * The bar for the position after ply `ply` (0: the start), or null where there is none: only an LLM faceoff played
 * with an evaluator has one. A ply without an Evaluation yet holds the last judged value, and so, greyed, does a
 * position not judged; the last ply of a finished game shows the result.
 */
export function evaluationBar(game: GameState, ply: number): Bar | null {
  const engine = game.evaluator
  if (!faceoff(game) || !engine) return null
  const engineLine = `White's point of view · ${engineName(engine)}`
  const result = RESULTS[game.result ?? '']
  if (game.status === 'over' && ply === game.plies.length && result) {
    const { label, share } = result
    // The game ends on the last position (checkmate, King capture …), which then has no Evaluation, or after it,
    // by a Forfeit, and the position was judged as any other.
    const last = game.plies.at(-1)?.evaluation
    const judgedLast = judgedOrNull(last)
    const position = judgedLast
      ? `The last position was judged ${evaluationText(judgedLast)}.`
      : last?.unjudged
        ? `The last position isn't judged: ${last.unjudged}.`
        : "The game ended on this position, so it isn't judged."
    const detail = `Game over: ${resultText(game).result}. ${position}`
    return { state: 'over', share, label, text: label, leader: leaderOf(share), title: label, detail }
  }
  const evaluation = ply > 0 ? game.plies[ply - 1].evaluation : null
  const judged = judgedOrNull(evaluation)
  if (judged) {
    const text = evaluationText(judged)
    const share = whiteShare(judged)
    const title = `Evaluation ${text}`
    return { state: 'judged', share, label: text, text, leader: leaderOf(share), title, detail: engineLine }
  }
  if (ply === 0) {
    return {
      state: 'none',
      share: 50,
      label: '',
      text: 'No Evaluation yet',
      leader: 'white',
      title: 'No Evaluation yet',
      detail: `The start position isn't judged. ${engineLine}`,
    }
  }
  let heldAt = ply - 1
  while (heldAt > 0 && !judgedOrNull(game.plies[heldAt - 1].evaluation)) heldAt--
  const held = heldAt > 0 ? judgedOrNull(game.plies[heldAt - 1].evaluation) : null
  const share = held ? whiteShare(held) : 50
  const heldText = held ? `${evaluationText(held)}, after ${plyName(game, heldAt)}` : 'none yet'
  if (evaluation?.unjudged) {
    return {
      state: 'unjudged',
      share,
      label: '?',
      text: 'Not judged',
      leader: leaderOf(share),
      title: 'Not judged',
      detail: `This position isn't judged: ${evaluation.unjudged}. Greyed at the last Evaluation: ${heldText}.`,
    }
  }
  const label = held ? evaluationText(held) : ''
  return {
    state: 'evaluating',
    share,
    label,
    text: label || 'Evaluating',
    leader: leaderOf(share),
    title: 'Evaluating…',
    detail: `No Evaluation of this position yet. Until then, the last one: ${heldText}. ${engineName(engine)}`,
  }
}

/**
 * The bar for the position the Chaos move at ply `ply` would have left had its Legal counterpart been played,
 * outlined as a preview, whether or not that position has an Evaluation; null where there is no bar.
 */
export function previewBar(game: GameState, ply: number, counterpart: CounterpartMove): Bar | null {
  const engine = game.evaluator
  const evaluation = counterpart.evaluation
  if (!faceoff(game) || !engine) return null
  const name = `${Math.ceil(ply / 2)}${game.plies[ply - 1].color === 'white' ? '.' : '…'} ${counterpart.san}`
  const position = `The position after the Legal counterpart ${name}, never played.`
  const judged = judgedOrNull(evaluation)
  if (judged) {
    const text = evaluationText(judged)
    const share = whiteShare(judged)
    const detail = `${position} White's point of view · ${engineName(engine)}`
    const title = `Evaluation ${text}`
    return { state: 'judged', share, label: text, text, leader: leaderOf(share), title, detail, preview: true }
  }
  // No Evaluation at all: the counterpart's move would have ended the game, so its position isn't judged.
  const why = evaluation?.unjudged ? `It isn't judged: ${evaluation.unjudged}.` : "It isn't judged."
  return {
    state: 'unjudged',
    share: 50,
    label: '?',
    text: 'Not judged',
    leader: 'white',
    title: 'Not judged',
    detail: `${position} ${why}`,
    preview: true,
  }
}
