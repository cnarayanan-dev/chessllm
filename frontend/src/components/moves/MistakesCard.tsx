/*
  The LLM mistakes card, under the Moves card: the LLM sides' totals head to head, White's number | the metric |
  Black's number. A row per metric: illegal tries and notation slips; under Chaos rules, where an illegal move is
  played anyway and a slip is no mistake, illegal moves and spawns, and with Legal counterparts asked for each side's
  Chaos gain score.
  In a faceoff the side with more of a mistake is in red. The metric's meaning is in its tooltip (the hover rule).
*/
import { PenLine, Sparkles, TrendingUpDown, X, type LucideIcon } from 'lucide-react'
import type { Color, GameState } from '@/api/types'
import { Card, CardContent, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { illegalMove } from '@/game/chaos'
import { gainScore, gainText, showsChaosGains } from '@/game/chaosGain'
import { COLOR_NAMES, llmColors } from '@/game/wording'
import { cn } from '@/lib/utils'

type Metric = 'illegal' | 'slips' | 'spawns'

const METRICS: Record<Metric, { icon: LucideIcon; name: string; description: string }> = {
  illegal: { icon: X, name: 'Illegal tries', description: 'Moves tried that were not legal, or could not be read.' },
  slips: { icon: PenLine, name: 'Notation slips', description: 'Legal moves written in the wrong notation.' },
  spawns: { icon: Sparkles, name: 'Spawns', description: 'Chaos moves that put a new piece on the board.' },
}
const CHAOS_GAIN = {
  icon: TrendingUpDown,
  name: 'Chaos gain',
  description:
    "Each Chaos move's gain over its Legal counterpart, added up: the Evaluation after it minus the one after the counterpart, in pawns from the side's point of view.",
}
// Under Chaos rules an illegal move is played anyway (or retried, if it could not be read): one count for both.
const CHAOS_ILLEGAL = { icon: X, name: 'Illegal moves', description: 'Illegal moves, played anyway, or retried if they could not be read.' }

/** A side's counts; null where a metric does not apply to it. */
type Counts = Record<Metric, number | null>

function counts(game: GameState, color: Color): Counts {
  // Counted from the attempts, since under Enforced decoding the illegal-move counts are null (ADR 0003).
  const attempts = game.llm_turns.filter((turn) => turn.color === color).flatMap((turn) => turn.attempts)
  const illegal = attempts.filter(illegalMove).length
  const stats = game.stats[color]
  const chaos = stats?.chaos_moves ?? null
  return {
    // Under Enforced decoding illegal tries are not applicable, unless one gets through anyway.
    illegal: stats?.illegal_moves === null && illegal === 0 ? null : illegal,
    slips: stats?.notation_slips ?? 0,
    spawns: chaos === null ? null : (stats?.spawns ?? 0),
  }
}

/** A side's column head: its colour and dot, the model in the tooltip. */
function SideHead({ color, model }: { color: Color; model: string }) {
  const dot = (
    <span
      aria-hidden="true"
      className={cn(
        'size-2.5 flex-none rounded-full border-[1.5px] border-foreground',
        color === 'white' ? 'bg-card' : 'bg-foreground',
      )}
    />
  )
  return (
    <TableHead className={color === 'black' ? 'text-right' : undefined}>
      <Tooltip>
        <TooltipTrigger
          delay={150}
          render={
            <span tabIndex={0} aria-description={model} className="inline-flex cursor-help items-center gap-1.5" />
          }
        >
          {color === 'white' && dot}
          {COLOR_NAMES[color]}
          {color === 'black' && dot}
        </TooltipTrigger>
        <TooltipContent>{model}</TooltipContent>
      </Tooltip>
    </TableHead>
  )
}

function MetricName({ metric, chaosRules }: { metric: Metric; chaosRules: boolean }) {
  return <RowName {...(chaosRules && metric === 'illegal' ? CHAOS_ILLEGAL : METRICS[metric])} />
}

function RowName({ icon: Icon, name, description }: { icon: LucideIcon; name: string; description: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        delay={150}
        render={
          <span tabIndex={0} aria-description={description} className="inline-flex cursor-help items-center gap-1.5" />
        }
      >
        <Icon className="size-3.5" aria-hidden="true" />
        {name}
      </TooltipTrigger>
      <TooltipContent className="block max-w-64">
        <span className="font-semibold">{name}</span> {description}
      </TooltipContent>
    </Tooltip>
  )
}

/** What a side's Chaos gain score adds up, for its tooltip. */
function scoreCovers(moves: number, unjudged: number): string {
  const covers = `Adds up ${moves} Chaos ${moves === 1 ? 'move' : 'moves'}`
  return unjudged === 0 ? `${covers}.` : `${covers}; ${unjudged} not judged ${unjudged === 1 ? 'is' : 'are'} left out.`
}

/** A side's Chaos gain score, what it adds up in its tooltip. Never in red: a gain is no mistake. */
function GainCell({ game, color }: { game: GameState; color: Color }) {
  const { total, moves, unjudged } = gainScore(game, color)
  const covers = scoreCovers(moves, unjudged)
  return (
    <TableCell
      className={cn('text-base tabular-nums', color === 'black' && 'text-right', moves === 0 && 'text-muted-foreground')}
    >
      <Tooltip>
        <TooltipTrigger delay={150} render={<span tabIndex={0} aria-description={covers} className="cursor-help" />}>
          {gainText(total)}
        </TooltipTrigger>
        <TooltipContent>{covers}</TooltipContent>
      </Tooltip>
    </TableCell>
  )
}

export function MistakesCard({ game }: { game: GameState }) {
  const sides = new Map(llmColors(game).map((color) => [color, counts(game, color)]))
  const chaosRules = game.settings.rules === 'chaos'
  const metrics: Metric[] = chaosRules ? ['illegal', 'spawns'] : ['illegal', 'slips']
  // Gains need an evaluator: without one there are none to add up.
  const gains = showsChaosGains(game) && game.evaluator != null
  const model = (color: Color) => {
    const side = game.settings[color]
    return side.player === 'llm' ? side.model : ''
  }
  const countCell = (color: Color, metric: Metric) => {
    const mine = sides.get(color)![metric]
    const other = sides.get(color === 'white' ? 'black' : 'white')?.[metric]
    const more = mine !== null && other != null && mine > other
    return (
      <TableCell
        data-more={more || undefined}
        className={cn(
          'text-base tabular-nums',
          color === 'black' && 'text-right',
          more ? 'font-semibold text-destructive' : !mine && 'text-muted-foreground',
        )}
      >
        {mine === null ? '–' : mine}
      </TableCell>
    )
  }
  return (
    <Card size="sm" data-testid="mistakes-card">
      <CardContent>
        <CardTitle className="mb-2 font-semibold text-card-foreground">{chaosRules ? 'Rule-breaking' : 'LLM mistakes'}</CardTitle>
        <Table className="text-xs [&_td]:px-1.5 [&_th]:px-1.5">
          <TableHeader>
            <TableRow>
              {sides.has('white') && <SideHead color="white" model={model('white')} />}
              <TableHead />
              {sides.has('black') && <SideHead color="black" model={model('black')} />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {metrics.map((metric) => (
              <TableRow key={metric}>
                {sides.has('white') && countCell('white', metric)}
                <TableCell className="text-center text-muted-foreground">
                  <MetricName metric={metric} chaosRules={chaosRules} />
                </TableCell>
                {sides.has('black') && countCell('black', metric)}
              </TableRow>
            ))}
            {gains && (
              <TableRow>
                {sides.has('white') && <GainCell game={game} color="white" />}
                <TableCell className="text-center text-muted-foreground">
                  <RowName {...CHAOS_GAIN} />
                </TableCell>
                {sides.has('black') && <GainCell game={game} color="black" />}
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
