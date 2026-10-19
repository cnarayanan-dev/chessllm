/*
  The moves card: the move history, one row per move number. It runs no chess logic (ADR 0001): the moves are the
  game's PGN as the backend wrote it.
*/
import { useState, type ReactNode } from 'react'
import type { GameState, LlmTurn } from '@/api/types'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { faceoff, ICON, llmColors } from '@/game/wording'
import './moves.css'

// A chip per failed attempt, in order, then an amber chip if the move it played was a notation slip.
function mistakeChips(turn: LlmTurn | undefined): ReactNode[] {
  return (turn?.attempts ?? []).flatMap((attempt, index) => {
    const key = `${turn!.ply}-${index}`
    if (attempt.notation_slip) return [<span key={key} className="mistake slip">{`⚑ written "${attempt.move}"`}</span>]
    if (attempt.result === 'legal') return []
    if (attempt.error) return [<span key={key} className="mistake error">{`⚠ ${attempt.error}`}</span>]
    return [
      <span key={key} className="mistake illegal">
        {'✗ '}
        <s>{attempt.move}</s>
        {` ${attempt.result} · try ${index + 1}`}
      </span>,
    ]
  })
}

// One row per move number, and under each LLM move its mistakes. A forfeited turn has no move, but its chips still
// show under the ply the LLM failed to play. With the switch off, only the moves.
// Each move is a button that views the position after it in the move history; the one viewed is marked.
function MoveList({ game, mistakes: shown, viewed, onView }: { game: GameState; mistakes: boolean } & Viewing) {
  const sans = game.pgn.split(' ').filter((token) => token && !token.endsWith('.')) // drop the move numbers
  const turns = new Map(game.llm_turns.map((turn) => [turn.ply, turn]))
  const plies = Math.max(sans.length, ...game.llm_turns.map((turn) => turn.ply))
  const rows = []
  for (let white = 1; white <= plies; white += 2) {
    const mistakes: ReactNode[] = []
    rows.push(<span key={`no${white}`} className="no">{`${(white + 1) / 2}.`}</span>)
    for (const ply of [white, white + 1]) {
      const slip = shown && turns.get(ply)?.attempts.at(-1)?.notation_slip
      const className =
        'ply' + (ply === sans.length ? ' last' : '') + (slip ? ' slip' : '') + (ply === viewed ? ' viewed' : '')
      const san = sans[ply - 1]
      rows.push(
        san ? (
          <button
            type="button"
            key={ply}
            className={className}
            aria-current={ply === viewed ? 'step' : undefined}
            onClick={() => onView?.(ply)}
          >
            {san}
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

// One total per LLM side, named by its model in a faceoff.
function totalsText(game: GameState): string {
  return llmColors(game)
    .map((color) => {
      // Counted from the attempts, since under Enforced decoding the illegal-move counts are null (ADR 0003).
      const attempts = game.llm_turns.filter((turn) => turn.color === color).flatMap((turn) => turn.attempts)
      const illegal = attempts.filter((attempt) => attempt.result !== 'legal' && !attempt.error).length
      const stats = game.stats[color]
      const slips = stats?.notation_slips ?? 0
      // Under Enforced decoding illegal tries are not applicable, unless one gets through anyway.
      const tries =
        stats?.illegal_moves === null && illegal === 0
          ? '✗ illegal tries n/a'
          : `✗ ${illegal} illegal ${illegal === 1 ? 'try' : 'tries'}`
      const total = `${tries} · ⚑ ${slips} notation ${slips === 1 ? 'slip' : 'slips'}`
      const side = game.settings[color]
      return faceoff(game) && side.player === 'llm' ? `${ICON[color]} ${side.model} ${total}` : total
    })
    .join('  ·  ')
}

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
  return (
    <Card size="sm" className="moves-card">
      <CardContent>
        <div className="mb-1.5 flex items-center">
          <span className="text-[11px] tracking-[.06em] text-muted-foreground uppercase">Moves</span>
          <span className="flex-1" />
          <label className="flex cursor-pointer items-center gap-[7px] text-xs text-muted-foreground select-none">
            <Switch size="sm" checked={show} onCheckedChange={toggle} />
            Show LLM mistakes
          </label>
        </div>
        <MoveList game={game} mistakes={show} viewed={viewed} onView={onView} />
        {show && (
          <div className="mt-2.5 border-t pt-2 text-xs text-muted-foreground" data-testid="totals">
            {totalsText(game)}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
