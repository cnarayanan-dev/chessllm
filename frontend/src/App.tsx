import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { modelsQuery } from '@/api/models'
import type { Color, GameState } from '@/api/types'
import { Board } from '@/components/board/Board'
import { BoardFlashes } from '@/components/board/BoardFlashes'
import { GameCard } from '@/components/game-card/GameCard'
import { GameLayout } from '@/components/game-layout/GameLayout'
import { MovesCard } from '@/components/moves/MovesCard'
import { Captures } from '@/components/player-strip/Captures'
import { MoveTimer, PlayerStrip } from '@/components/player-strip/PlayerStrip'
import { ReasoningPanel } from '@/components/reasoning/ReasoningPanel'
import { thenFrom } from '@/components/top-bar/then'
import { TopBar } from '@/components/top-bar/TopBar'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { chaosShown, type ChaosShown } from '@/game/chaos'
import {
  boardInput,
  orientation,
  shownPosition,
  waitingForLlm,
  type History,
  type Shown,
} from '@/game/gameLoop'
import { material } from '@/game/material'
import { useGameLoop } from '@/game/useGameLoop'
import { historyStatusText } from '@/game/wording'
import { isPending, newGameRequest, type Models } from '@/settings/next-game'
import { SettingsModal } from '@/settings/SettingsModal'

const NO_MOVES: readonly string[] = []
const NO_ARROWS: readonly [string, string][] = []

type StatusProps = {
  game: GameState
  /** The past position viewed in the move history, which the status names, with Back to live. */
  viewing: { shown: Shown; history: History; onLive: () => void }
}

/**
 * The status line, only while the move history shows the past: it says so, with Back to live, marked once the game
 * has moved on. Whose move it is and the LLM's move timer are in the player strips.
 */
function Status({ game, viewing }: StatusProps) {
  return (
    <Card size="sm">
      <CardContent className="flex items-center gap-3 text-muted-foreground">
        <span data-testid="status">{historyStatusText(viewing.shown)}</span>
        <span className="flex-1" />
        <Button size="sm" variant={viewing.history.news ? 'default' : 'outline'} onClick={viewing.onLive}>
          {!viewing.history.news
            ? 'Back to live'
            : game.status === 'over'
              ? 'Back to live · game over'
              : 'Back to live · new move'}
        </Button>
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

/** The caption under the board for the chaos move or spawn shown, live or in the move history. */
function ChaosCaption({ chaos }: { chaos: ChaosShown }) {
  return (
    <div data-testid="chaos-caption" className={`chaos-caption ${chaos.kind}`} key={chaos.caption}>
      {chaos.kind === 'spawn' ? '✦ ' : '↯ '}
      {chaos.caption}
    </div>
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
  // A new array with every state, so the same position given again snaps a rejected move's piece back.
  const legalMoves = useMemo(() => (game ? [...game.human_legal_moves] : NO_MOVES), [game])
  // The chaos move or spawn shown, from the ply's own resolution: the same live and in the history. Kept while
  // the ply is, so the board doesn't draw its arrows again at every render.
  const shownPly = shown?.move ?? null
  const chaos = useMemo(() => chaosShown(shownPly), [shownPly])
  // The player strips, by the live game, with the captures, spawns and +N of the position shown; the LLM's move
  // timer, in the strip of the side to move, restarts each turn.
  const strip = (live: GameState, color: Color) => (
    <PlayerStrip
      game={live}
      color={color}
      timer={running && live.turn === color ? <MoveTimer key={request!.id} /> : null}
    >
      {shown && <Captures material={material(live.plies.slice(0, shown.ply), shown.fen, color)} color={color} />}
    </PlayerStrip>
  )
  // The next game, as set up in the Settings modal, or the default game if none could be loaded.
  const startNewGame = useCallback(() => newGame(next ? newGameRequest(next, models) : null), [newGame, next, models])

  // New game or Settings chosen in the top bar of another page, done once the game is shown. New game is then the
  // button's: the models are listed only by the Settings modal, so until it opens the button has none either.
  const then = useRef(thenFrom(window.location.search))
  useEffect(() => {
    if (!then.current || !game || !next) return
    const asked = then.current
    then.current = null
    window.history.replaceState(null, '', window.location.pathname)
    if (asked === 'settings') setSettingsOpen(true)
    else startNewGame()
  }, [game, next, startNewGame])

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
      <TopBar onNewGame={startNewGame} onSettings={() => setSettingsOpen(true)} />
      {game && next && (
        <SettingsModal
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          running={game.settings}
          next={next}
          onNextChange={changeNext}
          onStartNext={newGame}
        />
      )}
      <GameLayout
        game={
          // The Reasoning panel follows the position on the board. "Show thinking" is hidden for now; the Thinking
          // stays in the API and the game log. (`shown` is set whenever `game` is.)
          game && shown ? (
            <>
              <GameCard game={game} pending={pending} error={error} onNewGame={startNewGame} />
              <ReasoningPanel game={game} ply={shown.ply} live={!history} />
            </>
          ) : (
            error !== null && (
              <Alert variant="destructive">
                <AlertDescription className="text-destructive">{error}</AlertDescription>
              </Alert>
            )
          )
        }
        board={
          game && shown ? (
            <>
              {strip(game, orientation(game) === 'white' ? 'black' : 'white')}
              <Board
                fen={shown.fen}
                orientation={orientation(game)}
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
                {!history && <BoardFlashes flash={state.flash} maxAttempts={game.settings.max_attempts} />}
              </Board>
              {strip(game, orientation(game))}
              {chaos && <ChaosCaption chaos={chaos} />}
            </>
          ) : (
            <div className="aspect-square w-full" />
          )
        }
        moves={
          <>
            {game && history && shown && <Status game={game} viewing={{ shown, history, onLive: backToLive }} />}
            {game && <MovesCard game={game} viewed={history?.ply ?? null} onView={viewPly} />}
          </>
        }
      />
      <footer className="px-5 pb-6 text-center text-xs text-muted-foreground">
        Pieces: Merida by Armando Hernandez Marroquin, GPLv2+ · Move sound: Kenney, CC0 · Model logos: LobeHub Icons, MIT
      </footer>
    </div>
  )
}
