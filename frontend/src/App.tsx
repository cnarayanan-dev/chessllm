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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { chaosShown, type ChaosShown } from '@/game/chaos'
import { boardInput, orientation, shownPosition, waitingForLlm } from '@/game/gameLoop'
import { material } from '@/game/material'
import { rematchOf } from '@/game/rematch'
import { useGameLoop } from '@/game/useGameLoop'
import { NewGameSheet } from '@/settings/NewGameSheet'
import { newGameRequest, nextGameFrom, type Models, type NextGame } from '@/settings/next-game'

const NO_MOVES: readonly string[] = []
const NO_ARROWS: readonly [string, string][] = []

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
  const { state, newGame, humanMove, viewPly, step } = useGameLoop()
  const { game, error, request, history } = state
  const shown = shownPosition(state)
  const [sheetOpen, setSheetOpen] = useState(false)
  const openSheet = useCallback(() => setSheetOpen(true), [])
  // The models as the New game sheet last listed them, or null until it has: they decide whether thinking is on.
  const modelsList = useQuery({ ...modelsQuery, enabled: false })
  const models: Models = modelsList.isError ? null : (modelsList.data ?? null)
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
  /** Starts a game set up as `next`, replacing the running one at once: the New game sheet's start buttons. */
  const startGame = useCallback((next: NextGame) => newGame(newGameRequest(next, models)), [newGame, models])

  // New game chosen in the top bar of another page: the sheet opens once the game is shown.
  const then = useRef(thenFrom(window.location.search))
  useEffect(() => {
    if (!then.current || !game) return
    then.current = null
    window.history.replaceState(null, '', window.location.pathname)
    setSheetOpen(true)
  }, [game])

  // ← and → step through the move history, unless a field or the New game sheet has the keys.
  useEffect(() => {
    if (sheetOpen) return
    const onKey = (event: KeyboardEvent) => {
      const by = ({ ArrowLeft: -1, ArrowRight: 1 } as const)[event.key as 'ArrowLeft' | 'ArrowRight']
      if (!by || keyTakenElsewhere(event)) return
      event.preventDefault()
      step(by)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sheetOpen, step])

  return (
    <div className="min-h-svh text-sm">
      <TopBar onNewGame={openSheet} />
      {game && (
        // It opens with the last game's settings, each time.
        <NewGameSheet
          open={sheetOpen}
          onOpenChange={setSheetOpen}
          initial={nextGameFrom(game.settings)}
          onStart={startGame}
        />
      )}
      <GameLayout
        game={
          // The Reasoning panel follows the position on the board. "Show thinking" is hidden for now; the Thinking
          // stays in the API and the game log. (`shown` is set whenever `game` is.)
          game && shown ? (
            <>
              <GameCard game={game} error={error} onRematch={() => newGame(rematchOf(game.settings))} />
              <ReasoningPanel game={game} ply={shown.ply} live={!history} />
            </>
          ) : (
            error !== null && (
              <Alert variant="destructive">
                <AlertTitle>Could not start a game</AlertTitle>
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
        moves={game && <MovesCard game={game} viewed={history?.ply ?? null} onView={viewPly} />}
      />
      <footer className="px-5 pb-6 text-center text-xs text-muted-foreground">
        Pieces: Merida by Armando Hernandez Marroquin, GPLv2+ · Move sound: Kenney, CC0 · Model logos: LobeHub Icons, MIT
      </footer>
    </div>
  )
}
