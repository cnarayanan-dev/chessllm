// The Game card, as a lichess game card without Elo: the Mode, the settings, the players, and the result and Rematch
// once over.
import { Bot, RotateCcw, Settings2, User } from 'lucide-react'
import type { GameState } from '@/api/types'
import { settingIcon } from '@/components/game-card/settingIcons'
import { SettingChip } from '@/components/setting-chip/SettingChip'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { rematchDescription } from '@/game/rematch'
import { COLORS, COLOR_NAMES, gameSettings, resultText } from '@/game/wording'
import { cn } from '@/lib/utils'

/** Each Mode as its players: you against an LLM, or an LLM against an LLM. */
const MODES = {
  play_llm: { name: 'Play LLM', players: 'You against an LLM', First: User },
  llm_faceoff: { name: 'LLM faceoff', players: 'An LLM against an LLM', First: Bot },
} as const

type GameCardProps = {
  game: GameState
  /** Whether the Settings modal holds changes, which apply to the next game. */
  pending: boolean
  /** The last request's error. */
  error: string | null
  /** Starts the Rematch, once the game is over. */
  onRematch: () => void
}

/** The game's settings, one chip each, the meaning in its tooltip; a setting the LLMs differ in, one chip per side. */
function Settings({ game }: { game: GameState }) {
  return (
    <ul aria-label="Settings" className="mt-1.5 flex flex-wrap gap-1.5">
      {gameSettings(game).map((setting) => (
        <li key={setting.name} className="flex">
          <SettingChip
            icon={settingIcon(setting)}
            name={setting.name}
            description={setting.description}
            side={setting.color}
          />
        </li>
      ))}
    </ul>
  )
}

export function GameCard({ game, pending, error, onRematch }: GameCardProps) {
  const mode = MODES[game.settings.mode]
  const over = game.status === 'over' ? resultText(game) : null
  const name = (color: 'white' | 'black') => {
    const side = game.settings[color]
    return side.player === 'llm' ? side.model : 'You'
  }
  return (
    <Card role="region" aria-label="Game" className="text-[15px]">
      <CardHeader className="flex items-start gap-3.5">
        <span
          role="img"
          aria-label={mode.players}
          className="flex h-10 w-16 flex-none items-center justify-center gap-1 rounded-full bg-muted"
        >
          <mode.First className="size-4" strokeWidth={1.75} aria-hidden="true" />
          <span aria-hidden="true" className="text-[11px] text-muted-foreground">
            vs
          </span>
          <Bot className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <CardTitle className="font-semibold">{mode.name}</CardTitle>
          <Settings game={game} />
        </div>
      </CardHeader>
      <CardContent>
        {/* Indented under the Mode and settings: the Mode icon's 64px and the header's 14px gap. */}
        <ul aria-label="Players" className="ml-[78px] flex flex-col gap-1">
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
          <SettingChip
            icon={RotateCcw}
            name="Rematch"
            description={rematchDescription(game.settings)}
            onClick={onRematch}
          />
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
