import { useEffect, useMemo, useState } from 'react'
import type { GameState } from '@/api/types'
import { Board } from '@/components/board/Board'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { humanColor, phase, waitingForLlm } from '@/game/gameLoop'
import { useGameLoop } from '@/game/useGameLoop'
import { bannerText, faceoff, llmName, newGameFrom, settingsChips, statusText } from '@/game/wording'

const NO_MOVES: readonly string[] = []

/** The status line. While an LLM turn runs, a timer ticks every second, to show the app has not frozen. */
function Status({ game, failed, running }: { game: GameState | null; failed: boolean; running: boolean }) {
  const [started] = useState(() => Date.now())
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [running, started])
  return (
    <Card size="sm">
      <CardContent className="text-muted-foreground" data-testid="status">
        {statusText(game, failed, running ? seconds : null)}
      </CardContent>
    </Card>
  )
}

function Banner({ game, onNewGame }: { game: GameState; onNewGame: () => void }) {
  const { title, reason } = bannerText(game)
  return (
    <div data-testid="banner" className="flex items-center gap-3 rounded-lg border bg-muted px-4 py-3.5">
      <div>
        <div className="text-base font-semibold">{title}</div>
        <div className="text-muted-foreground">{reason}</div>
      </div>
      <span className="flex-1" />
      <Button variant="outline" onClick={onNewGame}>
        New game
      </Button>
    </div>
  )
}

/** The last LLM turn's thinking. In a faceoff it stays up, named by its side, as the next turn starts at once. */
function Thinking({ game, hidden }: { game: GameState; hidden: boolean }) {
  const thinking = game.llm_turn?.thinking
  const named = faceoff(game) && thinking && game.llm_turn
  return (
    <Collapsible hidden={hidden || !thinking}>
      <Card size="sm">
        <CardContent>
          <CollapsibleTrigger className="cursor-pointer text-muted-foreground">
            {named ? `Show thinking · ${llmName(game, game.llm_turn!.color)}` : 'Show thinking'}
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 max-h-80 overflow-y-auto text-sm whitespace-pre-wrap text-muted-foreground">
            {thinking}
          </CollapsibleContent>
        </CardContent>
      </Card>
    </Collapsible>
  )
}

export default function App() {
  const { state, newGame, humanMove } = useGameLoop()
  const { game, error, request } = state
  const running = waitingForLlm(state)
  const human = game && humanColor(game)
  // A new array with every state, so the same position given again snaps a rejected move's piece back.
  const legalMoves = useMemo(() => (game ? [...game.human_legal_moves] : NO_MOVES), [game])
  // Another game under the running game's settings, or the default game if none could be loaded.
  const startNewGame = () => newGame(game ? newGameFrom(game.settings) : null)

  return (
    <div className="min-h-svh text-sm">
      <header className="flex items-center gap-3 border-b px-5 py-2.5">
        <span className="font-semibold">♞ ChessLLM</span>
        <div className="ml-2 flex flex-wrap gap-1.5">
          {game && settingsChips(game).map((chip) => <Badge variant="secondary" key={chip}>{chip}</Badge>)}
        </div>
        <span className="flex-1" />
        <Button variant="ghost" onClick={startNewGame}>
          New game
        </Button>
      </header>
      <main className="grid grid-cols-[minmax(320px,560px)_340px] justify-center gap-8 px-5 pt-7 pb-10 max-[960px]:grid-cols-[minmax(280px,560px)]">
        {game ? (
          <Board
            fen={game.fen}
            orientation={human ?? 'white'}
            lastMove={game.last_move}
            check={game.check}
            // Unchanged while the human's move is sent: the board locks itself, and a change would redraw the
            // position the move left.
            input={phase(state) === 'human' ? human : null}
            legalMoves={legalMoves}
            onMove={humanMove}
          />
        ) : (
          <div className="aspect-square w-full" />
        )}
        <div className="flex flex-col gap-3.5">
          {game && phase(state) === 'over' && <Banner game={game} onNewGame={startNewGame} />}
          <Status key={running ? request!.id : 'idle'} game={game} failed={error !== null} running={running} />
          {error !== null && (
            <Alert variant="destructive">
              <AlertDescription className="text-destructive">{error}</AlertDescription>
            </Alert>
          )}
          {/* In Play LLM the thinking hides as the LLM's next turn starts. */}
          {game && <Thinking game={game} hidden={running && !faceoff(game)} />}
        </div>
      </main>
      <footer className="px-5 pb-6 text-center text-xs text-muted-foreground">
        Pieces: Merida by Armando Hernandez Marroquin, GPLv2+ · Move sound: Kenney, CC0
      </footer>
    </div>
  )
}
