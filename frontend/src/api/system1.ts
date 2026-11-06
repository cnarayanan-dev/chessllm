import { queryOptions } from '@tanstack/react-query'
import { getSystem1Options } from '@/api/client'

/** GET /api/system1/options: the server a System 1 side starts at, and the Prompt templates it can play with, the default first. */
export const system1OptionsQuery = queryOptions({
  queryKey: ['system1-options'],
  queryFn: ({ signal }) => getSystem1Options(signal),
})
