import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'

// GET /api/models, typed here until the generated API types (#38) replace it.
type LlmModel = {
  name: string
  thinking: boolean
  sampling: Record<string, number> | null
}

async function fetchModels(): Promise<LlmModel[]> {
  const response = await fetch('/api/models')
  if (!response.ok) throw new Error(`GET /api/models: ${response.status}`)
  return response.json() as Promise<LlmModel[]>
}

/** Placeholder proving the setup works, until the port of the old page (#29) replaces it. */
export default function App() {
  const models = useQuery({ queryKey: ['models'], queryFn: fetchModels })

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 p-8">
      <h1 className="text-2xl font-semibold">ChessLLM</h1>
      {models.isPending && <p className="text-muted-foreground">Loading models…</p>}
      {models.isError && <p className="text-destructive">Couldn't load the models: {models.error.message}</p>}
      {models.isSuccess && (
        <ul className="list-disc pl-6">
          {models.data.map((model) => (
            <li key={model.name}>{model.name}</li>
          ))}
        </ul>
      )}
      <Button className="self-start" onClick={() => void models.refetch()}>
        Reload models
      </Button>
    </main>
  )
}
