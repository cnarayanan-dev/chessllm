// Leaderboard entries for tests, as GET /api/leaderboard returns them.
import type { LeaderboardEntry, PlayerConfiguration } from '@/analytics/leaderboard'

type Overrides = Omit<Partial<LeaderboardEntry>, 'configuration'> & { configuration?: Partial<PlayerConfiguration> }

/** A Free configuration of llama3:8b, rated 400, with the given changes. */
export function anEntry(id: string, overrides: Overrides = {}): LeaderboardEntry {
  const { configuration, ...rest } = overrides
  return {
    id,
    configuration: {
      model: 'llama3:8b',
      thinking: false,
      llm_constraints: 'free',
      rules: 'standard',
      retry_feedback: 'explained',
      sampling: {},
      prompt: 'system.txt',
      ...configuration,
    },
    games: 10,
    wins: 5,
    draws: 2,
    losses: 3,
    score: 0.6,
    forfeits: 1,
    legal_moves: 300,
    attempts: 320,
    average_legal_move_streak: 12.5,
    opponents: [],
    average_centipawn_loss: null,
    average_accuracy: null,
    rating: { estimate: 400, low: 250, high: 550, rated_games: 10 },
    move_quality: null,
    ...rest,
  }
}

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
