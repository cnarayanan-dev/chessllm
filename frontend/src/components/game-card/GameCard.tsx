// The Game card, as a lichess game card without Elo: the Mode, the settings, the players, and the result and Rematch
// once over. With Prompt lab on, a game no human plays has Pause beside "Playing".
import { Bot, Pause, Play, RotateCcw, User } from 'lucide-react'
import type { Color, GameState } from '@/api/types'
import { settingIcon } from '@/components/game-card/settingIcons'
import { SettingChip } from '@/components/setting-chip/SettingChip'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { PauseState } from '@/game/gameLoop'
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
  /** Where Pause stands, with Prompt lab on in a game no human plays; else undefined, and there is no Pause. */
  pause?: PauseState | null
  /** Why the paused game can't be resumed now (a probe runs); undefined when it can. */
  resumeBlocked?: string
  /** Pauses the game, or resumes it: the Pause button's. */
  onPause?: () => void
  onResume?: () => void
}

// What the Pause button does, or why it can't now, in its tooltip and `aria-description` (the hover rule).
const PAUSE = "No new LLM turn starts until you resume; the turn running finishes first. Time used doesn't grow while paused."
const PAUSING = 'Pausing: the LLM turn running finishes first.'
const RESUME = "The next LLM turn starts. Time used doesn't grow while paused."
const PAUSE_STATUS = { playing: 'Playing', pausing: 'Pausing after this turn…', paused: 'Paused' } as const

type PauseButtonProps = { pause: PauseState; resumeBlocked?: string; onPause?: () => void; onResume?: () => void }

/**
 * A round icon button: Pause while playing, held (disabled) while the turn running finishes, and Resume once paused,
 * disabled while a probe runs; its name and meaning, or why it can't now, in a tooltip.
 */
function PauseButton({ pause, resumeBlocked, onPause, onResume }: PauseButtonProps) {
  const paused = pause === 'paused'
  const name = paused ? 'Resume' : 'Pause'
  const blocked = pause === 'pausing' ? PAUSING : paused ? resumeBlocked : undefined
  const description = blocked ?? (paused ? RESUME : PAUSE)
  const Icon = paused ? Play : Pause
  return (
    <Tooltip>
      {/* The tooltip hangs on a wrapper, as a disabled button takes no hover. */}
      <TooltipTrigger delay={150} render={<span className="inline-flex" />}>
        <button
          type="button"
          aria-label={name}
          aria-description={description}
          disabled={blocked !== undefined}
          onClick={paused ? onResume : onPause}
          className="inline-flex size-7 flex-none cursor-pointer items-center justify-center rounded-full bg-muted text-foreground outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
        >
          <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="block max-w-64">
        <span className="font-semibold">{name}</span> {description}
      </TooltipContent>
    </Tooltip>
  )
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

const RESULT = 'line-clamp-2 w-full text-[15px]/5 font-semibold tracking-tight'

/** The result, up to two lines; its detail, such as a forfeit's reason, in a tooltip on hover and keyboard focus and
 * in its `aria-description` (the hover rule). */
function ResultLine({ result, detail }: { result: string; detail: string | null }) {
  if (detail === null) {
    return (
      <div data-testid="result" className={RESULT}>
        {result}
      </div>
    )
  }
  return (
    <Tooltip>
      <TooltipTrigger
        delay={150}
        render={
          <div
            data-testid="result"
            tabIndex={0}
            aria-description={detail}
            className={cn(RESULT, 'cursor-help outline-none focus-visible:underline')}
          />
        }
      >
        {result}
      </TooltipTrigger>
      <TooltipContent className="block max-w-64">{detail}</TooltipContent>
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
        <li key={setting.name} className="min-w-0">
          {index > 0 && <span aria-hidden="true">&nbsp;·&nbsp;</span>}
          <SettingText setting={setting} name={onSideRow ? setting.plainName : setting.name} />
        </li>
      ))}
    </ul>
  )
}

export function GameCard({ game, error, onRematch, pause, resumeBlocked, onPause, onResume }: GameCardProps) {
  const mode = MODES[game.settings.mode]
  const over = game.status === 'over' ? resultText(game) : null
  // The Rules, whether the game is wild, is the one setting shown, as an icon; the settings the LLMs share are not
  // shown, to keep the card simple, and in a faceoff the ones they differ in are on each player's row.
  const settings = gameSettings(game)
  const rules = settings.find((setting) => setting.setting === 'rules')!
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
              <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                {name(color)}
                {sideOf(color).length > 0 && (
                  <SettingsLine settings={sideOf(color)} label={`${COLOR_NAMES[color]}'s settings`} onSideRow />
                )}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
      {/* The same height playing or over, so the card never grows when the game ends, and kept small to leave the
          Turn panel room: a result of up to two lines, the detail in its tooltip, and Rematch. While playing, the
          room is held under "Playing". */}
      <CardContent className="flex min-h-[89px] flex-col items-start gap-2.5">
        <Separator />
        {over ? (
          <>
            <ResultLine result={over.result} detail={over.detail} />
            <SettingChip
              icon={RotateCcw}
              name="Rematch"
              description={rematchDescription(game.settings)}
              onClick={onRematch}
            />
          </>
        ) : (
          <div className="flex items-center gap-2">
            <div className="text-[15px]/5 font-semibold tracking-tight text-muted-foreground">
              {PAUSE_STATUS[pause ?? 'playing']}
            </div>
            {pause && (
              <PauseButton pause={pause} resumeBlocked={resumeBlocked} onPause={onPause} onResume={onResume} />
            )}
          </div>
        )}
      </CardContent>
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
