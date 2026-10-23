import { queryOptions } from '@tanstack/react-query'
import { getProbes } from '@/api/client'
import type { GameState, LlmTurn } from '@/api/types'

/** GET /api/games/{game_id}/probes: the game's probes, in the order asked. Kept, as only Try adds to them. */
export const probesQuery = (gameId: string) =>
  queryOptions({
    queryKey: ['probes', gameId],
    queryFn: ({ signal }) => getProbes(gameId, signal),
    staleTime: Infinity,
  })

/** The probes asked of one turn, by the row's Try or the dock's, so their wait and their error stay with that turn. */
export const probeKey = (game: GameState, turn: LlmTurn) => ['probe', game.game_id, turn.ply, turn.color]
