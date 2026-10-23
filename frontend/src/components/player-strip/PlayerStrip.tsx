// A player strip, directly above or below the board: the side's icon and name, ringed while it is to move, what
// follows the name (its captures, from #55), and on the right its Time used, ticking while it is to move.
import { Timer, User } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Color, GameState } from '@/api/types'
import { modelIcon } from '@/components/player-strip/logos'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Item } from '@/components/ui/item'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatTimeUsed, liveTotal, type Clock } from '@/game/timeUsed'
import { cn } from '@/lib/utils'

type PlayerStripProps = {
  /** The live game: the ring follows it, also while the move history shows a past position. */
  game: GameState
  color: Color
  /** The side's Time used (`TimeUsed`), on the right. */
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

const TIME_USED = 'The total time this side has spent on its moves in this game, ticking while it is to move.'

/**
 * The side's Time used, in whole seconds. The side to move's ticks on each whole second from the clock's totals, so
 * the page is seen not to have frozen; the other side's stays still, and both once the game is over.
 */
export function TimeUsed({ clock, color }: { clock: Clock; color: Color }) {
  const ticking = clock.ticking === color
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!ticking) return
    let timer: ReturnType<typeof setTimeout>
    // Each tick is set for when the total next turns a whole second.
    const schedule = () => {
      const ms = Math.round(liveTotal(clock, color, Date.now()) * 1000)
      timer = setTimeout(() => {
        setNow(Date.now())
        schedule()
      }, 1000 - (ms % 1000))
    }
    schedule()
    return () => clearTimeout(timer)
  }, [clock, color, ticking])
  return (
    <Tooltip>
      <TooltipTrigger
        delay={150}
        render={
          <span
            role="timer"
            tabIndex={0}
            aria-description={`Time used: ${TIME_USED}`}
            data-ticking={ticking || undefined}
            className={cn(
              'ml-auto inline-flex h-10 min-w-28 flex-none cursor-help items-center justify-end gap-1.5 rounded-full px-4 text-xl font-medium whitespace-nowrap tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring',
              ticking
                ? 'bg-timer text-timer-foreground'
                : 'bg-card text-foreground shadow-xs ring-1 ring-foreground/5',
            )}
          />
        }
      >
        <Timer className="size-4 flex-none opacity-70" strokeWidth={2} aria-hidden="true" />
        {formatTimeUsed(liveTotal(clock, color, now))}
      </TooltipTrigger>
      <TooltipContent className="block max-w-64">
        <span className="font-semibold">Time used</span> {TIME_USED}
      </TooltipContent>
    </Tooltip>
  )
}
