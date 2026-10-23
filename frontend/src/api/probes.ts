import { queryOptions } from '@tanstack/react-query'
import { getProbes } from '@/api/client'

/** GET /api/games/{game_id}/probes: the game's probes, in the order asked. Kept, as only Try adds to them. */
export const probesQuery = (gameId: string) =>
  queryOptions({
    queryKey: ['probes', gameId],
    queryFn: ({ signal }) => getProbes(gameId, signal),
    staleTime: Infinity,
  })
