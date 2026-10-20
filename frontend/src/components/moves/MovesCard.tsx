/*
  The moves card: the move history, one row per move number. It runs no chess logic (ADR 0001): the moves are the
  game's plies as the backend wrote them, a chaos move in the LLM's own spelling, in red, and a spawn in purple.
  The list has a set height, about 8 rows, and scrolls: to the latest move, or while a past position is viewed, just
  enough to keep the move viewed in view. With "Show LLM mistakes" on, the LLM mistakes card follows it.
*/
import { PenLine, TriangleAlert, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { GameState, LlmTurn } from '@/api/types'
import { MistakesCard } from '@/components/moves/MistakesCard'
import { Card, CardContent, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Switch } from '@/components/ui/switch'
import { chaosResolution, played } from '@/game/chaos'
import './moves.css'

// A chip per failed attempt, in order, then an amber chip if the move it played was a notation slip. A chaos move
// is the move itself, so it has no chip.
function mistakeChips(turn: LlmTurn | undefined): ReactNode[] {
  return (turn?.attempts ?? []).flatMap((attempt, index) => {
    const key = `${turn!.ply}-${index}`
    if (attempt.notation_slip) {
      return [
        <span key={key} className="mistake slip">
          <PenLine aria-hidden="true" />
          {`written "${attempt.move}"`}
        </span>,
      ]
    }
    if (played(attempt)) return []
    if (attempt.error) {
      return [
        <span key={key} className="mistake error">
          <TriangleAlert aria-hidden="true" />
          {attempt.error}
        </span>,
      ]
    }
    return [
      <span key={key} className="mistake illegal">
        <X aria-hidden="true" />
        <s>{attempt.move}</s>
        {` ${attempt.result} · try ${index + 1}`}
      </span>,
    ]
  })
}

// One row per move number, and under each LLM move its mistakes. A forfeited turn has no move, but its chips still
// show under the ply the LLM failed to play. With the switch off, only the moves.
// Each move is a button that views the position after it in the move history; the one viewed is marked, and the
// ply that `arrived` while a past position was viewed pulses.
function MoveList({
  game,
  mistakes: shown,
  viewed,
  onView,
  arrived,
}: { game: GameState; mistakes: boolean; arrived: number | null } & Viewing) {
  const turns = new Map(game.llm_turns.map((turn) => [turn.ply, turn]))
  const plies = Math.max(game.plies.length, ...game.llm_turns.map((turn) => turn.ply))
  const rows = []
  for (let white = 1; white <= plies; white += 2) {
    const mistakes: ReactNode[] = []
    rows.push(<span key={`no${white}`} className="no">{`${(white + 1) / 2}.`}</span>)
    for (const ply of [white, white + 1]) {
      const slip = shown && turns.get(ply)?.attempts.at(-1)?.notation_slip
      const move = game.plies[ply - 1]
      const chaos = chaosResolution(move)?.kind
      const className =
        'ply' +
        (ply === game.plies.length ? ' last' : '') +
        (slip ? ' slip' : '') +
        (chaos ? ` ${chaos}` : '') +
        (ply === viewed ? ' viewed' : '') +
        (ply === arrived ? ' arrived' : '')
      rows.push(
        move ? (
          <button
            type="button"
            key={ply}
            className={className}
            aria-current={ply === viewed ? 'step' : undefined}
            title={chaos === 'spawn' ? 'Spawn' : chaos ? 'Chaos move' : undefined}
            onClick={() => onView?.(ply)}
          >
            {move.written}
          </button>
        ) : (
          <span key={ply} className={className} />
        ),
      )
      if (shown) mistakes.push(...mistakeChips(turns.get(ply)))
    }
    if (mistakes.length) {
      rows.push(
        <div key={`mistakes${white}`} className="mistakes">
          {mistakes}
        </div>,
      )
    }
  }
  return (
    <div className="moves" data-testid="moves">
      {rows}
    </div>
  )
}

// How long a move that arrives while a past position is viewed pulses: the animation's two beats (moves.css).
const PULSE_MS = 1600

// The switch is a page setting, kept in the browser across games and reloads.
const MISTAKES_KEY = 'chessllm.showMistakes'

type Viewing = {
  /** The ply viewed in the move history (0: the start position), or null when live. */
  viewed?: number | null
  /** Views the position after a ply. */
  onView?: (ply: number) => void
}

export function MovesCard({ game, viewed = null, onView }: { game: GameState } & Viewing) {
  const [show, setShow] = useState(() => localStorage.getItem(MISTAKES_KEY) !== 'off')
  const toggle = (on: boolean) => {
    setShow(on)
    localStorage.setItem(MISTAKES_KEY, on ? 'on' : 'off')
  }
  // A move that arrives while a past position is viewed pulses, since the view stays where it is: briefly, and not
  // once the view is back at live.
  const [plies, setPlies] = useState(game.plies.length)
  const [arrived, setArrived] = useState<number | null>(null)
  if (plies !== game.plies.length) {
    setPlies(game.plies.length)
    setArrived(viewed !== null && game.plies.length > plies ? game.plies.length : null)
  } else if (arrived !== null && viewed === null) {
    setArrived(null)
  }
  useEffect(() => {
    if (arrived === null) return
    const timer = setTimeout(() => setArrived(null), PULSE_MS)
    return () => clearTimeout(timer)
  }, [arrived])
  // The list scrolls when a move or a try lands, or the view or the switch changes; not at every state the game
  // sends, so it leaves alone a user who scrolled up to read.
  const latest = game.llm_turns.at(-1)
  const landed = `${game.game_id} ${game.plies.length} ${game.llm_turns.length} ${latest?.attempts.length ?? 0}`
  const list = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const viewport = list.current?.querySelector<HTMLElement>('[data-slot=scroll-area-viewport]')
    if (!viewport) return
    if (viewed === null) {
      viewport.scrollTop = viewport.scrollHeight
      return
    }
    // The start position has no move: the list's top.
    const move = viewport.querySelector<HTMLElement>('[aria-current=step]')
    if (!move) {
      viewport.scrollTop = 0
      return
    }
    const shown = viewport.getBoundingClientRect()
    const row = move.getBoundingClientRect()
    if (row.top < shown.top) viewport.scrollTop -= shown.top - row.top
    else if (row.bottom > shown.bottom) viewport.scrollTop += row.bottom - shown.bottom
  }, [landed, viewed, show])
  return (
    <>
      <Card size="sm" className="moves-card">
        <CardContent>
          <div className="mb-2.5 flex items-center">
            <CardTitle className="font-semibold text-card-foreground">Moves</CardTitle>
            <span className="flex-1" />
            <label className="flex cursor-pointer items-center gap-[7px] text-xs text-muted-foreground select-none">
              <Switch size="sm" checked={show} onCheckedChange={toggle} />
              Show LLM mistakes
            </label>
          </div>
          <ScrollArea ref={list} className="move-scroll">
            <MoveList game={game} mistakes={show} viewed={viewed} onView={onView} arrived={arrived} />
          </ScrollArea>
        </CardContent>
      </Card>
      {show && <MistakesCard game={game} />}
    </>
  )
}
