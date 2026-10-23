// The analytics page: the Ranking of models by their Rating under the Reference configuration (prototype
// model-ranking, variant E's Ranking view), narrowed by a Mode filter, in a Luma card on the Stone page.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Anchor, Bot, Info, User, type LucideIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  ABOUT_RANKING,
  ALL_MODES,
  COLUMNS,
  MODES,
  NO_INTERVAL,
  NO_MOVE_QUALITY,
  UNVALIDATED,
  boundReason,
  estimateText,
  intervalText,
  noRatingReason,
  toggleMode,
  type ModeKey,
  type RankingEntry,
} from '@/analytics/ranking'
import { rankingQuery } from '@/api/ranking'
import { TopBar } from '@/components/top-bar/TopBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

const MODE_ICONS: Record<ModeKey, LucideIcon> = { play_llm: User, llm_faceoff: Bot, anchor_match: Anchor }

/** Text with its explanation in a tooltip; just the text without one. */
function Explained({ tip, children }: { tip: string | null; children: ReactNode }) {
  if (tip === null) return <>{children}</>
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} />} aria-description={tip} className="cursor-help">
        {children}
      </TooltipTrigger>
      <TooltipContent className="max-w-80">{tip}</TooltipContent>
    </Tooltip>
  )
}

function ModeFilter({ modes, onChange }: { modes: ModeKey[]; onChange: (modes: ModeKey[]) => void }) {
  return (
    <div role="group" aria-label="Modes" className="flex flex-wrap gap-1.5">
      {MODES.map((mode) => {
        const Icon = MODE_ICONS[mode.key]
        const on = modes.includes(mode.key)
        const last = on && modes.length === 1
        const description = last ? `${mode.description} At least one Mode stays on.` : mode.description
        return (
          <Tooltip key={mode.key}>
            <TooltipTrigger
              render={
                <Button
                  variant={on ? 'secondary' : 'ghost'}
                  size="sm"
                  aria-pressed={on}
                  aria-description={description}
                  disabled={last}
                  focusableWhenDisabled
                  className={cn(!on && 'text-muted-foreground', last && 'opacity-100')}
                  onClick={() => onChange(toggleMode(modes, mode.key))}
                />
              }
            >
              <Icon aria-hidden="true" />
              {mode.name}
            </TooltipTrigger>
            <TooltipContent className="max-w-72">{description}</TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}

function MoveQualityCell({ entry }: { entry: RankingEntry }) {
  const quality = entry.move_quality
  if (quality === null) return <Explained tip={NO_MOVE_QUALITY}>—</Explained>
  return (
    <>
      {estimateText(quality)}
      {!quality.validated && (
        <Tooltip>
          <TooltipTrigger
            render={<Badge variant="outline" />}
            className="ml-1.5 border-dashed font-normal text-muted-foreground"
          >
            unvalidated
          </TooltipTrigger>
          <TooltipContent className="max-w-80">{UNVALIDATED}</TooltipContent>
        </Tooltip>
      )}
    </>
  )
}

function RankingTable({ entries, modes }: { entries: RankingEntry[]; modes: ModeKey[] }) {
  return (
    <Table className="border-separate border-spacing-0">
      <TableHeader className="[&_tr]:border-0">
        <TableRow className="hover:bg-transparent">
          {COLUMNS.map(({ label, description }) => (
            <TableHead
              key={label}
              className={cn(
                'h-10 bg-muted text-xs text-muted-foreground first:rounded-l-2xl last:rounded-r-2xl',
                label !== '#' && label !== 'Model' && 'text-right',
              )}
            >
              <Explained tip={description}>{label}</Explained>
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody className="[&_tr:last-child_td]:border-0">
        {entries.map((entry) => {
          const ratingTip = entry.no_rating ? noRatingReason(entry.no_rating, modes) : boundReason(entry.rating)
          return (
            <TableRow key={entry.model} className="border-0 [&>td]:border-b [&>td]:border-border/70">
              <TableCell className="w-8 text-muted-foreground">{entry.rank ?? ''}</TableCell>
              <TableCell className="font-semibold">{entry.model}</TableCell>
              <TableCell className="text-right font-semibold tabular-nums">
                <Explained tip={ratingTip}>{estimateText(entry.rating)}</Explained>
              </TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">
                <Explained tip={entry.rating?.estimate == null ? NO_INTERVAL : null}>
                  {intervalText(entry.rating)}
                </Explained>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                <MoveQualityCell entry={entry} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{entry.games}</TableCell>
              <TableCell className="text-right whitespace-nowrap tabular-nums">
                <b>{entry.wins}</b> · {entry.draws} · {entry.losses}
              </TableCell>
              <TableCell className="text-right tabular-nums">{entry.forfeits}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

/** What the page says in the Ranking's place: loading, no games yet, or an error. */
function Notice({ className, children }: { className?: string; children: ReactNode }) {
  return <p className={cn('px-3 py-2 text-muted-foreground', className)}>{children}</p>
}

export function AnalyticsPage() {
  const [modes, setModes] = useState<ModeKey[]>([...ALL_MODES])
  const ranking = useQuery({ ...rankingQuery(modes), placeholderData: keepPreviousData })
  const entries = ranking.data?.models

  return (
    <TooltipProvider>
      <div className="min-h-svh text-sm">
        <TopBar current="analytics" />
        <main className="mx-auto max-w-[1400px] px-6 pt-4 pb-10">
          <div className="mb-5 flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Ranking</h1>
            <Tooltip>
              <TooltipTrigger
                render={<Button variant="ghost" size="icon-sm" aria-label="About the Ranking" />}
                aria-description={ABOUT_RANKING}
                className="text-muted-foreground"
              >
                <Info aria-hidden="true" />
              </TooltipTrigger>
              <TooltipContent className="block max-w-96">{ABOUT_RANKING}</TooltipContent>
            </Tooltip>
          </div>
          <Card>
            <CardHeader>
              <ModeFilter modes={modes} onChange={setModes} />
            </CardHeader>
            <CardContent className="px-3">
              {ranking.isError ? (
                <Notice className="text-destructive">Could not load the Ranking: {ranking.error.message}</Notice>
              ) : entries === undefined ? (
                <Notice>Loading…</Notice>
              ) : entries.length === 0 ? (
                <Notice>
                  No finished games yet. Run an Anchor match batch with the default settings, and its model shows up
                  here.
                </Notice>
              ) : (
                <RankingTable entries={entries} modes={modes} />
              )}
            </CardContent>
          </Card>
        </main>
      </div>
    </TooltipProvider>
  )
}
