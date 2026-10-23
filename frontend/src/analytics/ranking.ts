// The Ranking's logic, apart from the page: how its numbers read, why one is missing, and the Mode filter. The Rating
// and the Move-quality estimate are on the chess.com Rapid scale and never blended (ADR 0005); every number comes from
// the models' games under the Reference configuration in the chosen Modes (ADR 0011).
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

export const REFERENCE_CONFIGURATION =
  'Thinking off, Free, Standard rules, 5 attempts per turn with explained Retry feedback, fresh Turn memory, no ' +
  'Tools, the default Prompt template and the model’s own sampling. Games under any other settings are left out.'

/** What the page shows, in the tooltip of the info button beside its heading. */
export const ABOUT_RANKING =
  'Every model, ranked by its Rating on the chess.com Rapid scale, from its games under the Reference ' +
  `configuration in the chosen Modes alone. The Reference configuration: ${REFERENCE_CONFIGURATION}`

/** The table's columns, each with what it means for its header's tooltip; null for none. */
export const COLUMNS: { label: string; description: string | null }[] = [
  { label: '#', description: null },
  { label: 'Model', description: null },
  {
    label: 'Rating',
    description:
      'From wins, draws and losses alone, a Forfeit a loss: games against Anchors set the chess.com scale, LLM ' +
      'faceoffs place models relative to each other. Never blended with the Move-quality estimate.',
  },
  { label: '95% interval', description: 'Where the Rating lies, with 95% confidence.' },
  {
    label: 'Move-quality estimate',
    description:
      'The human rating whose players would most likely have made the same moves, from the moves alone, whoever ' +
      'won. Play LLM games count towards it.',
  },
  { label: 'Games', description: 'Its games under the Reference configuration in the chosen Modes.' },
  {
    label: 'W · D · L',
    description:
      'Wins, draws and losses in those games. Not comparable across models: under the adaptive ladder each faces ' +
      'its own Anchors, so only the Rating compares them.',
  },
  { label: 'Forfeits', description: 'Games lost by Forfeit, among the losses.' },
]

/** Why a model has no Rating, for the "—" in its row. */
export function noRatingReason(reason: NoRating, modes: readonly ModeKey[]): string {
  const narrowed = modes.length < ALL_MODES.length
  switch (reason) {
    case 'no_reference_games':
      return `No games under the Reference configuration ${narrowed ? 'in these Modes' : 'yet'}.`
    case 'no_rated_games':
      return 'Only Play LLM games, which never give a Rating: the human’s strength is unknown.'
    case 'no_path_to_anchor':
      return (
        'No path to an Anchor: no chain of wins or draws runs from it to an Anchor, or from an Anchor to it, so ' +
        'nothing sets its place on the scale.' +
        (modes.includes('anchor_match') ? '' : ' LLM faceoffs alone reach no Anchor.')
      )
  }
}

/** What a Rating that is only a bound means; null for an estimate or none. */
export function boundReason(rating: Estimate | null): string | null {
  if (rating === null || rating.estimate !== null) return null
  if (rating.high !== null) return 'An upper bound: it lost every game that leads to an Anchor.'
  if (rating.low !== null) return 'A lower bound: it won every game that leads to an Anchor.'
  return null
}

export const NO_INTERVAL = 'No interval without an estimate: only a bound, or no Rating.'
export const NO_MOVE_QUALITY = 'No analysed moves among these games.'
export const UNVALIDATED =
  'The estimator has not passed its validation against human games of known rating, so take this number with caution.'

/** The Modes in the API's order, each with its name in the filter and what its games give the Ranking. */
export const MODES: { key: ModeKey; name: string; description: string }[] = [
  {
    key: 'play_llm',
    name: 'Play LLM',
    description: 'A human against an LLM: counts towards the record and the Move-quality estimate, never the Rating.',
  },
  {
    key: 'llm_faceoff',
    name: 'LLM faceoffs',
    description: 'LLM against LLM: places models relative to each other, but alone reaches no Anchor.',
  },
  {
    key: 'anchor_match',
    name: 'Anchor matches',
    description: 'An LLM against an Anchor: what puts the Rating on the chess.com scale.',
  },
]
export const ALL_MODES: readonly ModeKey[] = MODES.map((mode) => mode.key)

/** GET /api/ranking, narrowed to the Modes unless they are all of them. */
export function rankingPath(modes: readonly ModeKey[]): string {
  if (modes.length === ALL_MODES.length) return '/api/ranking'
  return `/api/ranking?${modes.map((mode) => `modes=${mode}`).join('&')}`
}

/** The Modes with mode turned on or off, in the Modes' order; the last one left stays on. */
export function toggleMode(modes: readonly ModeKey[], mode: ModeKey): ModeKey[] {
  const on = modes.includes(mode) ? modes.filter((other) => other !== mode) : [...modes, mode]
  return on.length === 0 ? [...modes] : ALL_MODES.filter((key) => on.includes(key))
}
