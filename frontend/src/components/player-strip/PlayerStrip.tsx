// A player strip, directly above or below the board: the side's icon and name, ringed while it is to move, what
// follows the name (its captures, from #55), and on the right the move timer during an LLM's move.
import { User } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Color, GameState } from '@/api/types'
import { modelIcon } from '@/components/player-strip/logos'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Item } from '@/components/ui/item'
import { cn } from '@/lib/utils'

type PlayerStripProps = {
  /** The live game: the ring follows it, also while the move history shows a past position. */
  game: GameState
  color: Color
  /** The move timer, in the strip of the LLM whose move is running, else nothing. */
  timer?: ReactNode
  /** What follows the name: the pieces the side has taken, its spawns and +N. */
  children?: ReactNode
}

/** The side's icon: the model's family logo or monogram, or a person for the human. */
function PlayerIcon({ game, color }: { game: GameState; color: Color }) {
  const side = game.settings[color]
  if (side.player !== 'llm') {
    return (
      <Avatar>
        <AvatarFallback data-testid="person">
          <User className="size-4" strokeWidth={2} aria-hidden="true" />
        </AvatarFallback>
      </Avatar>
    )
  }
  const icon = modelIcon(side.model)
  return (
    <Avatar>
      {'logo' in icon ? (
        <span className="grid size-full place-items-center rounded-full bg-card">
          <img src={icon.logo} alt={icon.family} className="size-[62%]" />
        </span>
      ) : (
        <AvatarFallback
          data-testid="monogram"
          aria-hidden="true"
          className="text-sm font-semibold text-white"
          style={{ background: icon.colour }}
        >
          {icon.monogram}
        </AvatarFallback>
      )}
    </Avatar>
  )
}

export function PlayerStrip({ game, color, timer, children }: PlayerStripProps) {
  const side = game.settings[color]
  const toMove = game.status === 'playing' && game.turn === color
  return (
    <Item
      data-testid={`strip-${color}`}
      data-to-move={toMove || undefined}
      className="min-h-12 flex-nowrap gap-2.5 p-0"
    >
      <span
        className={cn(
          'inline-flex h-11 min-w-0 items-center gap-2.5 rounded-full bg-card py-0 pr-4 pl-1.5 shadow-xs ring-1 ring-foreground/5',
          toMove && 'shadow-md ring-2 ring-turn',
        )}
      >
        <PlayerIcon game={game} color={color} />
        <span className="truncate text-base font-semibold">{side.player === 'llm' ? side.model : 'You'}</span>
        {toMove && <span className="sr-only">, to move</span>}
      </span>
      {children}
      {timer}
    </Item>
  )
}

/** The seconds since the LLM's move started, ticking every second so the page is seen not to have frozen. */
export function MoveTimer() {
  const [started] = useState(() => Date.now())
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [started])
  return (
    <span
      role="timer"
      className="ml-auto inline-flex h-10 min-w-19 flex-none items-center justify-end rounded-full bg-timer px-4 text-xl font-medium text-timer-foreground tabular-nums"
    >
      {seconds}s
    </span>
  )
}
