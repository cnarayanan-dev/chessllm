// The Ranking's logic, apart from the page: how its numbers read, why a model has no Rating, and the Mode filter.
// The Rating and the Move-quality estimate are on the chess.com Rapid scale and never blended (ADR 0005); the order
// and the ranks come from the backend (chessllm/analytics/ranking.py).
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type Ranking = Schemas['Ranking']
export type RankingEntry = Schemas['RankingEntry']
export type ModeKey = Ranking['modes'][number]
export type NoRating = NonNullable<RankingEntry['no_rating']>

/** A Rating or a Move-quality estimate: an estimate with its 95% interval, or only one bound of it. */
type Estimate = { estimate: number | null; low: number | null; high: number | null }

/** "412", "< 70" for an upper bound, "> 1100" for a lower bound, "—" for none. */
export function estimateText(value: Estimate | null): string {
  if (value === null) return '—'
  if (value.estimate !== null) return String(value.estimate)
  if (value.high !== null) return `< ${value.high}`
  if (value.low !== null) return `> ${value.low}`
  return '—'
}

/** The Rating's 95% interval, "250 to 550"; a dash for a bound or no Rating. */
export function intervalText(rating: Estimate | null): string {
  if (rating === null || rating.estimate === null || rating.low === null || rating.high === null) return '—'
  return `${rating.low} to ${rating.high}`
}

/** The Modes, in the filter's order: each its name there and what its games give the Ranking. */
export const MODES: { key: ModeKey; name: string; explanation: string }[] = [
  {
    key: 'anchor_match',
    name: 'Anchor matches',
    explanation: 'Games against the Anchors, whose strength is fixed: they put the Rating on the chess.com scale.',
  },
  {
    key: 'llm_faceoff',
    name: 'LLM faceoffs',
    explanation: 'Games between two LLMs: they place models relative to each other, but alone reach no Anchor.',
  },
  {
    key: 'play_llm',
    name: 'Play LLM',
    explanation:
      'Games against a human, whose strength is unknown: they never give a Rating, only the record and the Move-quality estimate.',
  },
]
export const ALL_MODES: ModeKey[] = MODES.map((mode) => mode.key)

/** The Modes after a click on one: it is added or taken out, but the last one chosen stays. In the filter's order. */
export function toggleMode(modes: readonly ModeKey[], key: ModeKey): ModeKey[] {
  const next = modes.includes(key) ? modes.filter((mode) => mode !== key) : [...modes, key]
  return next.length ? ALL_MODES.filter((mode) => next.includes(mode)) : [...modes]
}

/** Why a model has no Rating, for the "—" cell's tooltip; `narrowed` when the filter leaves some Modes out. */
export function noRatingText(reason: NoRating, narrowed: boolean): string {
  switch (reason) {
    case 'no_reference_games':
      return narrowed
        ? 'No games under the Reference configuration in the Modes chosen.'
        : 'No games under the Reference configuration yet, so not ranked.'
    case 'play_llm_only':
      return 'Only Play LLM games, which never give a Rating: the human’s strength is unknown.'
    case 'no_rated_opponent':
      return 'Its rated games were all against itself or an Anchor of unknown strength, which say nothing about the scale.'
    case 'no_anchor_path':
      return 'No path to an Anchor: who scored against whom in its LLM faceoffs ties it to no Anchor match.'
  }
}

/** What a bound means, for the Rating cell's tooltip; null for an estimate or no Rating. */
export function boundText(rating: Estimate | null): string | null {
  if (rating === null || rating.estimate !== null) return null
  if (rating.high !== null)
    return 'An upper bound: it lost every game that places it, and results this bad had a 5% chance at this Rating.'
  if (rating.low !== null)
    return 'A lower bound: it won every game that places it, and results this good had a 5% chance at this Rating.'
  return null
}

export const REFERENCE_CONFIGURATION =
  'Thinking off, Free, Standard rules, 5 attempts with explained Retry feedback, fresh Turn memory, no Tools, the ' +
  'default Prompt template and the model’s own sampling.'
