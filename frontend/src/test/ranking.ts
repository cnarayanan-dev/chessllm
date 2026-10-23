// Ranking entries for tests, as GET /api/ranking returns them.
import type { RankingEntry } from '@/analytics/ranking'

/** The model ranked first at 400, with the given changes. */
export function anEntry(model: string, overrides: Partial<RankingEntry> = {}): RankingEntry {
  return {
    rank: 1,
    model,
    rating: rated(400, 250, 550),
    no_rating: null,
    move_quality: null,
    games: 10,
    wins: 5,
    draws: 2,
    losses: 3,
    forfeits: 1,
    ...overrides,
  }
}

/** A model without a Rating, for the reason given, so unranked. */
export const unranked = (
  model: string,
  noRating: NonNullable<RankingEntry['no_rating']>,
  overrides: Partial<RankingEntry> = {},
) => anEntry(model, { rank: null, rating: null, no_rating: noRating, ...overrides })

export const rated = (estimate: number, low = estimate - 150, high = estimate + 150) => ({
  estimate,
  low,
  high,
  rated_games: 10,
})
export const upperBound = (high: number) => ({ estimate: null, low: null, high, rated_games: 10 })
export const lowerBound = (low: number) => ({ estimate: null, low, high: null, rated_games: 10 })

export const moveQuality = (
  estimate: number | null,
  { low = null, high = null, validated = false }: { low?: number | null; high?: number | null; validated?: boolean } = {},
) => ({
  estimate,
  low,
  high,
  extrapolated: false,
  validated,
  games: 3,
  moves: 90,
  move_model: 'maia2 rapid',
  lichess_rapid: { estimate: 1100, interval: [1000, 1200] as [number, number], ratings: [1000, 1100, 1200] },
})
