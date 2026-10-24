import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query'
import { askProbe, getProbes } from '@/api/client'
import type { ProbeRequest } from '@/api/types'

/** GET /api/games/{game_id}/probes: the game's Probes, in the order they were asked, so a reopened game shows them. */
export const probesQuery = (gameId: string) =>
  queryOptions({
    queryKey: ['probes', gameId],
    queryFn: ({ signal }) => getProbes(gameId, signal),
  })

/** The mutation key of the game's Probes being asked, from the Turn panel or after a Pause. */
export const probeMutationKey = (gameId: string) => ['probe', gameId]

/** POST /api/games/current/probes: asks a Probe of the game, which joins its listed probes once answered. */
export function useAskProbe(gameId: string) {
  const queryClient = useQueryClient()
  const listed = probesQuery(gameId)
  return useMutation({
    mutationKey: probeMutationKey(gameId),
    mutationFn: (request: ProbeRequest) => askProbe(request),
    onSuccess: (probe) => queryClient.setQueryData(listed.queryKey, (before) => [...(before ?? []), probe]),
  })
}
