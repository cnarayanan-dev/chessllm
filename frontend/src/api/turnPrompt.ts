import { queryOptions } from '@tanstack/react-query'
import { getTurnPrompt } from '@/api/client'

/**
 * GET /api/games/current/llm-turns/{ply}/attempts/{attempt}/prompt: an attempt's whole Prompt, rebuilt from the
 * records. A recorded attempt never changes, so it is asked for once per game.
 */
export const turnPromptQuery = (gameId: string, ply: number, attempt: number) =>
  queryOptions({
    queryKey: ['turn-prompt', gameId, ply, attempt],
    queryFn: ({ signal }) => getTurnPrompt(ply, attempt, signal),
    staleTime: Infinity,
  })
