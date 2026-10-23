import { queryOptions } from '@tanstack/react-query'
import { rankingPath, type ModeKey } from '@/analytics/ranking'
import { getRanking } from '@/api/client'

/** GET /api/ranking: the models by their Rating under the Reference configuration, from the chosen Modes' games. */
export const rankingQuery = (modes: readonly ModeKey[]) =>
  queryOptions({ queryKey: ['ranking', ...modes], queryFn: ({ signal }) => getRanking(rankingPath(modes), signal) })
