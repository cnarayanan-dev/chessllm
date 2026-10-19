import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { modelsQuery } from '@/api/models'
import type { GameState } from '@/api/types'
import { Board } from '@/components/board/Board'
import { BoardFlashes } from '@/components/board/BoardFlashes'
import { MovesCard } from '@/components/moves/MovesCard'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { chaosShown, type ChaosShown } from '@/game/chaos'
import {
  boardInput,
  humanColor,
  phase,
  shownPosition,
  waitingForLlm,
  type History,
  type Shown,
} from '@/game/gameLoop'
import { useGameLoop } from '@/game/useGameLoop'
import { bannerText, faceoff, historyStatusText, llmName, settingsChips, statusText } from '@/game/wording'
import { isPending, newGameRequest, type Models } from '@/settings/next-game'
import { SettingsButton, SettingsModal } from '@/settings/SettingsModal'
import { PrototypeNewGameSheet, PrototypeSwitcher, prototypeVariant } from '@/settings/prototype-new-game-sheet' // PROTOTYPE

const PROTOTYPE = prototypeVariant() // PROTOTYPE: ?variant=A|B swaps the Settings modal for a New game sheet

const NO_MOVES: readonly string[] = []
const NO_ARROWS: readonly [string, string][] = []

type StatusProps = {
  game: GameState | null
  failed: boolean
  running: boolean
  /** The past position viewed in the move history, which the status names instead, with Back to live. */
  viewing: { shown: Shown; history: History; onLive: () => void } | null
}

/**
 * The status line. While an LLM turn runs, a timer ticks every second, to show the app has not frozen. While the
 * move history shows the past, it says so, with Back to live, marked once the game has moved on.
 */
function Status({ game, failed, running, viewing }: StatusProps) {
  const [started] = useState(() => Date.now())
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [running, started])
  return (
    <Card size="sm">
      <CardContent className="flex items-center gap-3 text-muted-foreground">
        <span data-testid="status">
          {viewing ? historyStatusText(viewing.shown) : statusText(game, failed, running ? seconds : null)}
        </span>
        {viewing && (
          <>
            <span className="flex-1" />
            <Button size="sm" variant={viewing.history.news ? 'default' : 'outline'} onClick={viewing.onLive}>
              {!viewing.history.news
                ? 'Back to live'
                : game?.status === 'over'
                  ? 'Back to live · game over'
                  : 'Back to live · new move'}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}

/** Whether a key press belongs to a field or a dialog rather than to the move history. */
const keyTakenElsewhere = (event: KeyboardEvent) =>
  event.defaultPrevented ||
  event.altKey ||
  event.ctrlKey ||
  event.metaKey ||
  event.shiftKey ||
  (event.target instanceof HTMLElement &&
    (event.target.isContentEditable || !!event.target.closest('input, textarea, select, [role="dialog"]')))

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

/** The caption under the board for the chaos move or spawn shown, live or in the move history. */
function ChaosCaption({ chaos }: { chaos: ChaosShown }) {
  return (
    <div data-testid="chaos-caption" className={`chaos-caption ${chaos.kind}`} key={chaos.caption}>
      {chaos.kind === 'spawn' ? '✦ ' : '↯ '}
      {chaos.caption}
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
  const { state, newGame, humanMove, changeNext, viewPly, step, backToLive } = useGameLoop()
  const { game, error, request, next, history } = state
  const shown = shownPosition(state)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // The models as the Settings modal last listed them, or null until it has: they decide whether thinking is on.
  const modelsList = useQuery({ ...modelsQuery, enabled: false })
  const models: Models = modelsList.isError ? null : (modelsList.data ?? null)
  const pending = game !== null && next !== null && isPending(next, models, game.settings)
  const running = waitingForLlm(state)
  const human = game && humanColor(game)
  // A new array with every state, so the same position given again snaps a rejected move's piece back.
  const legalMoves = useMemo(() => (game ? [...game.human_legal_moves] : NO_MOVES), [game])
  // The chaos move or spawn shown, from the ply's own resolution: the same live and in the history. Kept while
  // the ply is, so the board doesn't draw its arrows again at every render.
  const shownPly = shown?.move ?? null
  const chaos = useMemo(() => chaosShown(shownPly), [shownPly])
  // The next game, as set up in the Settings modal, or the default game if none could be loaded.
  const startNewGame = () => newGame(next ? newGameRequest(next, models) : null)

  // ← and → step through the move history, unless a field or the Settings modal has the keys.
  useEffect(() => {
    if (settingsOpen) return
    const onKey = (event: KeyboardEvent) => {
      const by = ({ ArrowLeft: -1, ArrowRight: 1 } as const)[event.key as 'ArrowLeft' | 'ArrowRight']
      if (!by || keyTakenElsewhere(event)) return
      event.preventDefault()
      step(by)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [settingsOpen, step])

  return (
    <div className="min-h-svh text-sm">
      <header className="flex items-center gap-3 border-b px-5 py-2.5">
        <span className="font-semibold">♞ ChessLLM</span>
        <div className="ml-2 flex flex-wrap gap-1.5">
          {game && settingsChips(game).map((chip) => <Badge variant="secondary" key={chip}>{chip}</Badge>)}
          {pending && <Badge className="bg-primary/10 text-primary">changes apply next game</Badge>}
        </div>
        <span className="flex-1" />
        <a href="/analytics" className={buttonVariants({ variant: 'ghost' })}>
          Analytics
        </a>
        <Button variant="ghost" onClick={PROTOTYPE ? () => setSettingsOpen(true) : startNewGame}>
          New game
        </Button>
        {!PROTOTYPE && <SettingsButton onClick={() => setSettingsOpen(true)} />}
      </header>
      {PROTOTYPE && next && (
        <>
          <PrototypeNewGameSheet
            variant={PROTOTYPE}
            open={settingsOpen}
            onOpenChange={setSettingsOpen}
            next={next}
            onNextChange={changeNext}
            onStart={newGame}
          />
          <PrototypeSwitcher current={PROTOTYPE} />
        </>
      )}
      {!PROTOTYPE && game && next && (
        <SettingsModal
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          running={game.settings}
          next={next}
          onNextChange={changeNext}
          onStartNext={newGame}
        />
      )}
      <main className="grid grid-cols-[minmax(320px,560px)_340px] justify-center gap-8 px-5 pt-7 pb-10 max-[960px]:grid-cols-[minmax(280px,560px)]">
        {game && shown ? (
          <div className="flex flex-col gap-2.5">
            <Board
              fen={shown.fen}
              orientation={human ?? 'white'}
              lastMove={shown.lastMove}
              animateFrom={shown.animateFrom}
              check={shown.check}
              // Unchanged while the human's move is sent: the board locks itself, and a change would redraw the
              // position the move left. Locked while the move history shows the past.
              input={boardInput(state)}
              legalMoves={legalMoves}
              arrows={chaos?.arrows ?? NO_ARROWS}
              spawn={chaos?.spawn ?? null}
              onMove={humanMove}
            >
              {/* The live turn's flashes, kept off a past position. */}
              {!history && <BoardFlashes flash={state.flash} />}
            </Board>
            {chaos && <ChaosCaption chaos={chaos} />}
          </div>
        ) : (
          <div className="aspect-square w-full" />
        )}
        <div className="flex flex-col gap-3.5">
          {game && phase(state) === 'over' && <Banner game={game} onNewGame={startNewGame} />}
          <Status
            key={running ? request!.id : 'idle'}
            game={game}
            failed={error !== null}
            running={running}
            viewing={history && shown ? { shown, history, onLive: backToLive } : null}
          />
          {error !== null && (
            <Alert variant="destructive">
              <AlertDescription className="text-destructive">{error}</AlertDescription>
            </Alert>
          )}
          {/* In Play LLM the thinking hides as the LLM's next turn starts. */}
          {game && <Thinking game={game} hidden={running && !faceoff(game)} />}
          {game && <MovesCard game={game} viewed={history?.ply ?? null} onView={viewPly} />}
        </div>
      </main>
      <footer className="px-5 pb-6 text-center text-xs text-muted-foreground">
        Pieces: Merida by Armando Hernandez Marroquin, GPLv2+ · Move sound: Kenney, CC0
      </footer>
    </div>
  )
}
