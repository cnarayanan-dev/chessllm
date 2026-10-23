import { keepPreviousData, queryOptions } from '@tanstack/react-query'
import type { components } from '@/api/schema'

type Ranking = components['schemas']['Ranking']
type ModeKey = Ranking['modes'][number]

/** The request for the Ranking narrowed to these Modes: every Mode's games when none are given. */
export function rankingPath(modes: readonly ModeKey[]): string {
  const query = new URLSearchParams(modes.map((mode) => ['mode', mode]))
  return modes.length ? `/api/ranking?${query}` : '/api/ranking'
}

async function fetchRanking(modes: readonly ModeKey[]): Promise<Ranking> {
  const response = await fetch(rankingPath(modes))
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? response.statusText)
  }
  return response.json() as Promise<Ranking>
}

/** GET /api/ranking: every model by its Rating under the Reference configuration, from the given Modes' games (all
 * when none). The last Ranking stays shown while another Modes' loads. */
export const rankingQuery = (modes: readonly ModeKey[]) =>
  queryOptions({
    queryKey: ['ranking', ...modes],
    queryFn: () => fetchRanking(modes),
    placeholderData: keepPreviousData,
  })
