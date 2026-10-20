// The top bar of every page: the ChessLLM mark, then Analytics and New game, and Preferences at the end.
import { ChartNoAxesColumn, Plus } from 'lucide-react'
import { useEffect } from 'react'
import rook from '@/assets/chessllm-rook.svg'
import { Preferences } from '@/components/top-bar/Preferences'
import { thenHref } from '@/components/top-bar/then'
import { Button, buttonVariants } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/** A link styled as a button, its variant's classes merged over the base ones as Button does. */
const linkClass = (variant: 'ghost' | 'outline', className?: string) => cn(buttonVariants({ variant }), className)

type TopBarProps = {
  /**
   * Opens the New game sheet, as ⌘K (Ctrl+K) does. Without it, as on a page without the game, New game and ⌘K go to
   * the game page and open the sheet there.
   */
  onNewGame?: () => void
  /** The page shown, marked among the links. */
  current?: 'analytics'
}

export function TopBar({ onNewGame, current }: TopBarProps) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        if (onNewGame) onNewGame()
        else window.location.assign(thenHref('new-game'))
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onNewGame])

  return (
    <header className="flex flex-wrap items-center gap-1.5 px-6 py-3">
      <a href="/" className="mr-4 flex items-center gap-2.5 rounded-lg text-lg font-semibold tracking-tight">
        <img src={rook} width={28} height={28} alt="" className="rounded-md" />
        ChessLLM
      </a>
      <a
        href="/analytics"
        aria-current={current === 'analytics' ? 'page' : undefined}
        className={linkClass('ghost', 'aria-[current=page]:bg-muted')}
      >
        <ChartNoAxesColumn data-icon="inline-start" aria-hidden="true" />
        Analytics
      </a>
      <Tooltip>
        <TooltipTrigger
          render={
            onNewGame ? (
              <Button variant="outline" onClick={onNewGame} />
            ) : (
              <a href={thenHref('new-game')} className={linkClass('outline')} />
            )
          }
        >
          <Plus data-icon="inline-start" aria-hidden="true" />
          New game
        </TooltipTrigger>
        <TooltipContent side="bottom">
          New game <Kbd>⌘K</Kbd>
        </TooltipContent>
      </Tooltip>
      <div className="ml-auto">
        <Preferences />
      </div>
    </header>
  )
}
