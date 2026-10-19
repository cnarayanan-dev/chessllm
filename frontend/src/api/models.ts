import { queryOptions } from '@tanstack/react-query'
import type { components } from '@/api/schema'

type ModelInfo = components['schemas']['ModelInfo']

async function fetchModels(): Promise<ModelInfo[]> {
  const response = await fetch('/api/models')
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? response.statusText)
  }
  return response.json() as Promise<ModelInfo[]>
}

/** GET /api/models: each model with whether it can think and the sampling it would play at. */
export const modelsQuery = queryOptions({ queryKey: ['models'], queryFn: fetchModels })
