// The leaderboard's logic, apart from the page: how its numbers read, its columns, and how its rows are ranked and
// sorted. The Rating and the Move-quality estimate are on the chess.com Rapid scale and never blended (ADR 0005).
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type LeaderboardEntry = Schemas['LeaderboardEntry']
export type PlayerConfiguration = Schemas['PlayerConfiguration']

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

export const scoreText = (entry: LeaderboardEntry) => `${Math.round(100 * entry.score)}%`

/** Not applicable under Enforced decoding (ADR 0003). */
export const NOT_APPLICABLE = 'n/a'

export function attemptsLegalText(entry: LeaderboardEntry): string {
  if (entry.attempts === null) return NOT_APPLICABLE
  const share = attemptsLegal(entry)
  return share === null ? '—' : `${Math.round(100 * share)}%`
}

export function streakText(entry: LeaderboardEntry): string {
  const streak = entry.average_legal_move_streak
  return streak === null ? NOT_APPLICABLE : streak.toFixed(1)
}

export type Hue = PlayerConfiguration['llm_constraints'] | 'thinking'
/** A chip: coloured by its hue (a dot and a tint, the text stays ink), or grey with none. */
export type Chip = { label: string; hue: Hue | null }

export const LLM_CONSTRAINTS_NAMES: Record<PlayerConfiguration['llm_constraints'], string> = {
  free: 'Free',
  listed: 'Listed',
  blind_enforced: 'Blind enforced',
  listed_enforced: 'Listed enforced',
}
const DEFAULT_PROMPT = 'system.txt'

/** The chips that tell configurations apart: the LLM constraints, thinking on, retry feedback, then what's unusual. */
export function chips(configuration: PlayerConfiguration): Chip[] {
  const sampling = Object.entries(configuration.sampling)
  return [
    { label: LLM_CONSTRAINTS_NAMES[configuration.llm_constraints], hue: configuration.llm_constraints },
    ...(configuration.thinking ? [{ label: 'thinking on', hue: 'thinking' as const }] : []),
    { label: `feedback ${configuration.retry_feedback}`, hue: null },
    ...(configuration.rules === 'chaos' ? [{ label: 'Chaos rules', hue: null }] : []),
    ...(sampling.length ? [{ label: sampling.map(([name, value]) => `${name} ${value}`).join(' · '), hue: null }] : []),
    ...(configuration.prompt !== DEFAULT_PROMPT ? [{ label: `prompt ${configuration.prompt}`, hue: null }] : []),
  ]
}

/** The legend: each LLM constraints' colour, and thinking on's. */
export const LEGEND: Chip[] = [
  ...(Object.entries(LLM_CONSTRAINTS_NAMES) as [Hue, string][]).map(([hue, label]) => ({ label, hue })),
  { label: 'thinking on', hue: 'thinking' },
]

// An upper bound sorts below every estimate: "< 300" may be far lower than an estimate of 120.
const UPPER_BOUND = -1_000_000

/** The number an estimate sorts by: the estimate, a lower bound's number, an upper bound below all of those. */
function estimateKey(value: Estimate | null): number | null {
  if (value === null) return null
  if (value.estimate !== null) return value.estimate
  if (value.low !== null) return value.low
  if (value.high !== null) return UPPER_BOUND + value.high
  return null
}

/** Highest first, null always last; ties in model then id order, so the order never depends on the response's. */
function byKey<T extends LeaderboardEntry>(key: (entry: T) => number | null, direction: 'asc' | 'desc') {
  return (a: T, b: T) => {
    const x = key(a)
    const y = key(b)
    if (x !== y) {
      if (x === null) return 1
      if (y === null) return -1
      return direction === 'asc' ? x - y : y - x
    }
    return a.configuration.model.localeCompare(b.configuration.model) || a.id.localeCompare(b.id)
  }
}

/** Every configuration, ranked by Rating. */
export function ranked(entries: readonly LeaderboardEntry[]): LeaderboardEntry[] {
  return [...entries].sort(byKey((entry) => estimateKey(entry.rating), 'desc'))
}

export type SortKey =
  | 'rank'
  | 'rating'
  | 'games'
  | 'wdl'
  | 'interval'
  | 'move_quality'
  | 'score'
  | 'forfeits'
  | 'legal_moves'
  | 'attempts_legal'
  | 'streak'
export type ColumnKey = SortKey | 'configuration'
export type Column = { key: ColumnKey; label: string; sortable: boolean; numeric: boolean }
export type Sort = { key: SortKey; direction: 'asc' | 'desc' }

/** Ranked by Rating, as the page opens. */
export const DEFAULT_SORT: Sort = { key: 'rating', direction: 'desc' }

const column = (key: ColumnKey, label: string): Column => ({
  key,
  label,
  sortable: key !== 'configuration',
  numeric: key !== 'configuration' && key !== 'rank',
})

const DEFAULT_COLUMNS = [
  column('rank', '#'),
  column('configuration', 'Player configuration'),
  column('rating', 'Rating'),
  column('games', 'Games'),
  column('wdl', 'W · D · L'),
]
const MORE_COLUMNS = [
  column('interval', 'Rating 95%'),
  column('move_quality', 'Move-quality estimate'),
  column('score', 'Score'),
  column('forfeits', 'Forfeits'),
  column('legal_moves', 'Legal moves played'),
  column('attempts_legal', 'Attempts legal'),
  column('streak', 'Avg. Legal-move streak'),
]

/** The default columns, or with `all` every column. */
export function columns(all: boolean): Column[] {
  return all ? [...DEFAULT_COLUMNS, ...MORE_COLUMNS] : DEFAULT_COLUMNS
}

/** The share of attempts that were legal moves; null under Enforced decoding (ADR 0003). */
export function attemptsLegal(entry: LeaderboardEntry): number | null {
  return entry.attempts ? entry.legal_moves / entry.attempts : null
}

const SORT_KEYS: Record<Exclude<SortKey, 'rank'>, (entry: LeaderboardEntry) => number | null> = {
  rating: (entry) => estimateKey(entry.rating),
  games: (entry) => entry.games,
  wdl: (entry) => entry.wins,
  // The interval's width: how sure the Rating is.
  interval: (entry) =>
    entry.rating?.estimate != null && entry.rating.low !== null && entry.rating.high !== null
      ? entry.rating.high - entry.rating.low
      : null,
  move_quality: (entry) => estimateKey(entry.move_quality),
  score: (entry) => entry.score,
  forfeits: (entry) => entry.forfeits,
  legal_moves: (entry) => entry.legal_moves,
  attempts_legal: attemptsLegal,
  streak: (entry) => entry.average_legal_move_streak,
}

/** The rows in the order of `sort`; values that are null (none, or not applicable) last either way. */
export function sortRows(entries: readonly LeaderboardEntry[], sort: Sort): LeaderboardEntry[] {
  if (sort.key === 'rank') {
    const byRank = ranked(entries)
    return sort.direction === 'asc' ? byRank : byRank.reverse()
  }
  return [...entries].sort(byKey(SORT_KEYS[sort.key], sort.direction))
}

/** The sort after a click on a column: the same column turns round, another sorts highest first (rank: first). */
export function nextSort(sort: Sort, key: SortKey): Sort {
  if (sort.key === key) return { key, direction: sort.direction === 'asc' ? 'desc' : 'asc' }
  return { key, direction: key === 'rank' ? 'asc' : 'desc' }
}
