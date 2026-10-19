import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Board } from '@/components/board/Board'
import { playMoveSound } from '@/components/board/moveSound'
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

// A fixed position to check the board by eye against the old page: Black's rook has just checked White's king, which
// can step aside or promote the b-pawn to block or capture. Its legal moves are python-chess's.
const SAMPLE = {
  fen: 'r6K/1P6/8/8/8/8/5k2/8 w - - 0 1',
  lastMove: 'a1a8',
  legalMoves: ['b7a8b', 'b7a8n', 'b7a8q', 'b7a8r', 'b7b8b', 'b7b8n', 'b7b8q', 'b7b8r', 'h8g7', 'h8h7'],
}

/** Placeholder proving the setup works, until the port of the old page (#29) replaces it. */
export default function App() {
  const models = useQuery({ queryKey: ['models'], queryFn: fetchModels })
  // No backend takes the sample's moves: each plays the move sound, then the piece goes back.
  const [legalMoves, setLegalMoves] = useState(SAMPLE.legalMoves)

  return (
    <main className="grid grid-cols-[minmax(320px,560px)_340px] justify-center gap-8 px-5 pt-7 pb-10 max-[960px]:grid-cols-[minmax(280px,560px)]">
      <Board
        fen={SAMPLE.fen}
        orientation="white"
        lastMove={SAMPLE.lastMove}
        check
        input="white"
        legalMoves={legalMoves}
        onMove={() => {
          playMoveSound()
          setLegalMoves([...SAMPLE.legalMoves])
        }}
      />
      <div className="flex flex-col gap-4">
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
      </div>
    </main>
  )
}
