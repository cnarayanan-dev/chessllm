// Asking a Probe of a turn, from the Prompt tab's row or the dock: one place, so both share the turn's last probe
// (its wait and its error) and anything that must happen before a probe is asked: in a running game no human plays,
// pausing it (Pause), so a probe never runs alongside a real turn.
import { useMutation, useMutationState, useQueryClient } from '@tanstack/react-query'
import { probeTurn } from '@/api/client'
import { probeKey, probesQuery } from '@/api/probes'
import type { GameState, LlmTurn, ProbeRequest } from '@/api/types'

/**
 * Asks probes of the turn, each added to its game's probes once answered; `last` is the turn's last probe asked,
 * wherever it was asked from: its wait, or its error, and `waiting` what its wait is, while it lasts. Given
 * `pauseFirst` (a running game no human plays), a probe is asked once it has resolved: once the game has paused.
 */
export function useProbeTurn(game: GameState, turn: LlmTurn, pauseFirst?: () => Promise<void>) {
  const queryClient = useQueryClient()
  const mutationKey = probeKey(game, turn)
  const asking = useMutation({
    mutationKey,
    mutationFn: async (request: ProbeRequest) => {
      await pauseFirst?.()
      return probeTurn(request)
    },
    // By the game the probe answered for, never the game shown when it lands.
    onSuccess: (probe) =>
      queryClient.setQueryData(probesQuery(probe.game_id).queryKey, (asked = []) => [...asked, probe]),
  })
  const last = useMutationState({
    filters: { mutationKey, exact: true },
    select: (mutation) => ({ status: mutation.state.status, error: mutation.state.error }),
  }).at(-1)
  // While the game still plays, a pending probe waits for the pause; once paused, it is being asked.
  const waiting =
    last?.status !== 'pending'
      ? undefined
      : pauseFirst
        ? 'Waiting for the LLM turn running to finish, then asking…'
        : 'Asking the LLM…'
  return { ask: (request: ProbeRequest) => asking.mutate(request), last, waiting }
}
