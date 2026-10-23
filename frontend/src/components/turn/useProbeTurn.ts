// Asking a Probe of a turn, from the Prompt tab's row or the dock: one place, so both share the turn's last probe
// (its wait and its error) and anything that must happen before a probe is asked.
import { useMutation, useMutationState, useQueryClient } from '@tanstack/react-query'
import { probeTurn } from '@/api/client'
import { probeKey, probesQuery } from '@/api/probes'
import type { GameState, LlmTurn, ProbeRequest } from '@/api/types'

/** Asks probes of the turn, each added to its game's probes once answered; `last` is the turn's last probe asked,
 * wherever it was asked from: its wait, or its error. */
export function useProbeTurn(game: GameState, turn: LlmTurn) {
  const queryClient = useQueryClient()
  const mutationKey = probeKey(game, turn)
  const asking = useMutation({
    mutationKey,
    mutationFn: (request: ProbeRequest) => probeTurn(request),
    // By the game the probe answered for, never the game shown when it lands.
    onSuccess: (probe) =>
      queryClient.setQueryData(probesQuery(probe.game_id).queryKey, (asked = []) => [...asked, probe]),
  })
  const last = useMutationState({
    filters: { mutationKey, exact: true },
    select: (mutation) => ({ status: mutation.state.status, error: mutation.state.error }),
  }).at(-1)
  return { ask: (request: ProbeRequest) => asking.mutate(request), last }
}
