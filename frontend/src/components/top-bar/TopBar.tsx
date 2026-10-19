// The top bar of every page: the ChessLLM mark, then Analytics, New game and Settings.
import { ChartNoAxesColumn, Plus, Settings2 } from 'lucide-react'
import { useEffect } from 'react'
import rook from '@/assets/chessllm-rook.svg'
import { thenHref } from '@/components/top-bar/then'
import { Button, buttonVariants } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/** A link styled as a button, its variant's classes merged over the base ones as Button does. */
const linkClass = (variant: 'ghost' | 'outline', className?: string) => cn(buttonVariants({ variant }), className)

type TopBarProps = {
  /** Starts a new game. Without it, as on a page without the game, New game is a link to the game page that does it. */
  onNewGame?: () => void
  /** Opens the Settings modal. Without it, Settings (and ⌘K) go to the game page and open it there. */
  onSettings?: () => void
  /** The page shown, marked among the links. */
  current?: 'analytics'
}

export function TopBar({ onNewGame, onSettings, current }: TopBarProps) {
  // On the game page the Settings modal itself listens for ⌘K (Ctrl+K).
  useEffect(() => {
    if (onSettings) return
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        window.location.assign(thenHref('settings'))
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onSettings])

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
      {onNewGame ? (
        <Button variant="outline" onClick={onNewGame}>
          <Plus data-icon="inline-start" aria-hidden="true" />
          New game
        </Button>
      ) : (
        <a href={thenHref('new-game')} className={linkClass('outline')}>
          <Plus data-icon="inline-start" aria-hidden="true" />
          New game
        </a>
      )}
      <Tooltip>
        <TooltipTrigger
          render={
            onSettings ? (
              <Button variant="ghost" onClick={onSettings} />
            ) : (
              <a href={thenHref('settings')} className={linkClass('ghost')} />
            )
          }
        >
          <Settings2 data-icon="inline-start" aria-hidden="true" />
          Settings
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Settings <Kbd>⌘K</Kbd>
        </TooltipContent>
      </Tooltip>
    </header>
  )
}
