import { queryOptions } from '@tanstack/react-query'
import { getPromptTemplates } from '@/api/client'

/** GET /api/prompt-templates: the Prompt library, the defaults first, each with the LLM constraints it fits. */
export const promptLibraryQuery = queryOptions({
  queryKey: ['prompt-templates'],
  queryFn: ({ signal }) => getPromptTemplates(signal),
})
