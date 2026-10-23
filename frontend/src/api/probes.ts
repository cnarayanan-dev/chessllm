import { queryOptions } from '@tanstack/react-query'
import { getProbes } from '@/api/client'

/** GET /api/games/{game_id}/probes: the game's Probes, in the order they were asked, so a reopened game shows them. */
export const probesQuery = (gameId: string) =>
  queryOptions({
    queryKey: ['probes', gameId],
    queryFn: ({ signal }) => getProbes(gameId, signal),
  })
