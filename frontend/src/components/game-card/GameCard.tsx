// The Game card, as a lichess game card without Elo: the Mode, the settings, the players, and the result and Rematch
// once over.
import { Bot, RotateCcw, User } from 'lucide-react'
import type { Color, GameState } from '@/api/types'
import { settingIcon } from '@/components/game-card/settingIcons'
import { SettingChip } from '@/components/setting-chip/SettingChip'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { rematchDescription } from '@/game/rematch'
import { COLORS, COLOR_NAMES, gameSettings, resultText, type GameSetting } from '@/game/wording'
import { cn } from '@/lib/utils'

/** Each Mode as its players: you against an LLM, or an LLM against an LLM. */
const MODES = {
  play_llm: { name: 'Play LLM', players: 'You against an LLM', First: User },
  llm_faceoff: { name: 'LLM faceoff', players: 'An LLM against an LLM', First: Bot },
} as const

type GameCardProps = {
  game: GameState
  /** The last request's error. */
  error: string | null
  /** Starts the Rematch, once the game is over. */
  onRematch: () => void
}

/** A setting as muted text, its meaning in a tooltip and its `aria-description` (DESIGN.md: the hover rule). */
function SettingText({ setting, name }: { setting: GameSetting; name: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        delay={150}
        render={
          <span
            tabIndex={0}
            aria-description={setting.description}
            className="cursor-help outline-none focus-visible:underline"
          />
        }
      >
        {name}
      </TooltipTrigger>
      <TooltipContent className="block max-w-64">
        <span className="font-semibold">{setting.name}</span> {setting.description}
      </TooltipContent>
    </Tooltip>
  )
}

/** Settings as a line of muted text, " · " between them; on a player's row, without the side, which the row shows. */
function SettingsLine({
  settings,
  label,
  onSideRow = false,
}: {
  settings: GameSetting[]
  label: string
  onSideRow?: boolean
}) {
  return (
    <ul aria-label={label} className="flex flex-wrap text-[13px] text-muted-foreground">
      {settings.map((setting, index) => (
        <li key={setting.name} className="whitespace-nowrap">
          {index > 0 && <span aria-hidden="true">&nbsp;·&nbsp;</span>}
          <SettingText setting={setting} name={onSideRow ? setting.plainName : setting.name} />
        </li>
      ))}
    </ul>
  )
}

export function GameCard({ game, error, onRematch }: GameCardProps) {
  const mode = MODES[game.settings.mode]
  const over = game.status === 'over' ? resultText(game) : null
  // The Rules, whether the game is wild, is the one setting shown as an icon; the rest are text: the ones the LLMs
  // share under it, and in a faceoff the ones they differ in on each player's row.
  const settings = gameSettings(game)
  const rules = settings.find((setting) => setting.setting === 'rules')!
  const shared = settings.filter((setting) => setting.setting !== 'rules' && setting.color === null)
  const sideOf = (color: Color) => settings.filter((setting) => setting.color === color)
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
          <div className="mt-1.5 flex">
            <SettingChip icon={settingIcon(rules)} name={rules.name} description={rules.description} labelled />
          </div>
          {shared.length > 0 && (
            <div className="mt-1.5">
              <SettingsLine settings={shared} label="Settings" />
            </div>
          )}
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
              <span className="flex flex-wrap items-baseline gap-x-2">
                {name(color)}
                {sideOf(color).length > 0 && (
                  <SettingsLine settings={sideOf(color)} label={`${COLOR_NAMES[color]}'s settings`} onSideRow />
                )}
              </span>
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
      {error !== null && (
        <CardContent>
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        </CardContent>
      )}
    </Card>
  )
}
