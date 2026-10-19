import { queryOptions } from '@tanstack/react-query'
import type { components } from '@/api/schema'

type Leaderboard = components['schemas']['Leaderboard']

async function fetchLeaderboard(): Promise<Leaderboard> {
  const response = await fetch('/api/leaderboard')
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? response.statusText)
  }
  return response.json() as Promise<Leaderboard>
}

/** GET /api/leaderboard: every Player configuration with its results, Rating and Move-quality estimate. */
export const leaderboardQuery = queryOptions({ queryKey: ['leaderboard'], queryFn: fetchLeaderboard })
