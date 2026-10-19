// The Game card, as a lichess game card without Elo: the Mode, the settings, the players, and the result once over.
import { ArrowRight, Bot, Settings2, Swords } from 'lucide-react'
import type { GameState } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { COLORS, COLOR_NAMES, resultText, settingsLine } from '@/game/wording'
import { cn } from '@/lib/utils'

const MODES = {
  play_llm: { name: 'Play LLM', Icon: Swords },
  llm_faceoff: { name: 'LLM faceoff', Icon: Bot },
} as const

type GameCardProps = {
  game: GameState
  /** Whether the Settings modal holds changes, which apply to the next game. */
  pending: boolean
  /** The last request's error. */
  error: string | null
  onNewGame: () => void
}

/**
 * The settings, separated by "|". The line wraps between items: a flex line takes each item at its full width, so an
 * item breaks within itself only when it is wider than the card on its own. The "|" sits in each item's left padding
 * (17px), and the list is shifted left by the same 17px, so the clip hides the "|" of the item that starts a line.
 */
function SettingsLine({ items }: { items: string[] }) {
  return (
    <div className="overflow-hidden">
      <ul className="-ml-[17px] flex flex-wrap">
        {items.map((item) => (
          <li
            key={item}
            data-testid="setting"
            className="relative pl-[17px] before:absolute before:left-1.5 before:opacity-55 before:content-['|']"
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function GameCard({ game, pending, error, onNewGame }: GameCardProps) {
  const mode = MODES[game.settings.mode]
  const over = game.status === 'over' ? resultText(game) : null
  const name = (color: 'white' | 'black') => {
    const side = game.settings[color]
    return side.player === 'llm' ? side.model : 'You'
  }
  return (
    <Card role="region" aria-label="Game" className="text-[15px]">
      <CardHeader className="flex items-start gap-3.5">
        <span className="grid size-10 flex-none place-items-center rounded-full bg-muted">
          <mode.Icon className="size-5" strokeWidth={1.75} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1 text-sm/normal text-muted-foreground">
          <CardTitle className="mb-0.5 font-semibold text-card-foreground">{mode.name}</CardTitle>
          <SettingsLine items={settingsLine(game)} />
        </div>
      </CardHeader>
      <CardContent>
        {/* Indented under the Mode and settings: the Mode icon's 40px and the header's 14px gap. */}
        <ul aria-label="Players" className="ml-[54px] flex flex-col gap-1">
          {COLORS.map((color) => (
            <li key={color} className="flex items-center gap-2.5">
              <span
                aria-hidden="true"
                className={cn(
                  'size-2.5 flex-none rounded-full border-[1.5px] border-foreground',
                  color === 'black' && 'bg-foreground',
                )}
              />
              <span className="sr-only">{COLOR_NAMES[color]} </span>
              {name(color)}
            </li>
          ))}
        </ul>
      </CardContent>
      {over && (
        <CardContent className="flex flex-col items-start gap-3.5">
          <Separator />
          <div data-testid="result">
            <div className="text-xl/snug font-semibold tracking-tight">{over.result}</div>
            {over.detail && <div className="mt-1 text-sm text-muted-foreground">{over.detail}</div>}
          </div>
          <Button size="lg" onClick={onNewGame}>
            New game
            <ArrowRight data-icon="inline-end" aria-hidden="true" />
          </Button>
        </CardContent>
      )}
      {(pending || error !== null) && (
        <CardContent className="flex flex-col items-start gap-2">
          {pending && (
            <Badge variant="secondary" className="h-auto px-2.5 py-1 whitespace-normal">
              <Settings2 aria-hidden="true" />
              Your changes apply to the next game
            </Badge>
          )}
          {error !== null && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </CardContent>
      )}
    </Card>
  )
}
