import { queryOptions, type QueryClient } from '@tanstack/react-query'
import { getPromptTemplate, getPromptTemplates } from '@/api/client'

/** GET /api/prompt-templates: the Prompt library, the defaults first, each with the LLM constraints and Turn memories it fits. */
export const promptLibraryQuery = queryOptions({
  queryKey: ['prompt-templates'],
  queryFn: ({ signal }) => getPromptTemplates(signal),
})

/** GET /api/prompt-templates/{id}: one template, hidden or not, from the library's list when it holds it. Kept, as an
 * ID always means one text; hiding it updates it here. */
export const promptTemplateQuery = (queryClient: QueryClient, id: string) =>
  queryOptions({
    queryKey: ['prompt-template', id],
    queryFn: ({ signal }) => getPromptTemplate(id, signal),
    initialData: () => queryClient.getQueryData(promptLibraryQuery.queryKey)?.find((entry) => entry.id === id),
    staleTime: Infinity,
  })
