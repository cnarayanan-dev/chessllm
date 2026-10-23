// The analytics page: the Ranking of models, each by its Rating under the Reference configuration (ADR 0011),
// narrowed by Mode, in a Luma card on the Stone page. Layout from the prototype's Ranking view (variant E).
import { useQuery } from '@tanstack/react-query'
import { Anchor, Bot, User, type LucideIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  ALL_MODES,
  MODES,
  REFERENCE_CONFIGURATION,
  boundText,
  estimateText,
  intervalText,
  noRatingText,
  toggleMode,
  type ModeKey,
  type RankingEntry,
} from '@/analytics/ranking'
import { rankingQuery } from '@/api/ranking'
import { TopBar } from '@/components/top-bar/TopBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

const MODE_ICONS: Record<ModeKey, LucideIcon> = { anchor_match: Anchor, llm_faceoff: Bot, play_llm: User }

const COLUMNS = ['#', 'Model', 'Rating', '95% interval', 'Move-quality estimate', 'Games', 'W · D · L', 'Forfeits']

/** A word or number that explains itself on hover and on keyboard focus, the same text read to screen readers. */
function Explained({ children, explanation, className }: { children: ReactNode; explanation: string; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span tabIndex={0} aria-description={explanation} />}
        className={cn('cursor-help rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50', className)}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent className="max-w-80">{explanation}</TooltipContent>
    </Tooltip>
  )
}

function RatingCell({ entry, narrowed }: { entry: RankingEntry; narrowed: boolean }) {
  const text = estimateText(entry.rating)
  const explanation =
    entry.no_rating !== null ? noRatingText(entry.no_rating, narrowed) : boundText(entry.rating)
  if (explanation === null) return <span className="font-semibold">{text}</span>
  return (
    <Explained explanation={explanation} className={cn(entry.rating !== null && 'font-semibold')}>
      {text}
    </Explained>
  )
}

function MoveQualityCell({ entry }: { entry: RankingEntry }) {
  const quality = entry.move_quality
  return (
    <>
      {estimateText(quality)}
      {quality && !quality.validated && (
        <Tooltip>
          <TooltipTrigger
            render={<Badge variant="outline" />}
            className="ml-1.5 border-dashed font-normal text-muted-foreground"
          >
            unvalidated
          </TooltipTrigger>
          <TooltipContent>
            The estimator has not passed its validation against human games of known rating, so take this number with
            caution.
          </TooltipContent>
        </Tooltip>
      )}
    </>
  )
}

/** The Modes whose games count: each a toggle, its name and icon, what its games give in its tooltip. */
function ModeFilter({ modes, onChange }: { modes: ModeKey[]; onChange: (modes: ModeKey[]) => void }) {
  return (
    <div role="group" aria-label="Modes" className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-muted-foreground">Modes</span>
      {MODES.map(({ key, name, explanation }) => {
        const Icon = MODE_ICONS[key]
        const on = modes.includes(key)
        return (
          <Tooltip key={key}>
            <TooltipTrigger
              render={
                <Button
                  variant={on ? 'secondary' : 'ghost'}
                  size="sm"
                  aria-pressed={on}
                  aria-description={explanation}
                  onClick={() => onChange(toggleMode(modes, key))}
                />
              }
              className={cn(!on && 'text-muted-foreground')}
            >
              <Icon aria-hidden="true" />
              {name}
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-80">
              {explanation}
            </TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}

/** The table; `stale` while the Modes just chosen load, the last Ranking shown faded and marked busy until then. */
function RankingTable({ entries, narrowed, stale }: { entries: RankingEntry[]; narrowed: boolean; stale: boolean }) {
  return (
    <Table
      className={cn('border-separate border-spacing-0 transition-opacity', stale && 'opacity-50')}
      aria-busy={stale}
      data-stale={stale || undefined}
    >
      <TableHeader className="[&_tr]:border-0">
        <TableRow className="hover:bg-transparent">
          {COLUMNS.map((column, index) => (
            <TableHead
              key={column}
              className={cn(
                'h-10 bg-muted text-xs text-muted-foreground first:rounded-l-2xl last:rounded-r-2xl',
                index > 1 && 'text-right',
              )}
            >
              {column}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody className="[&_tr:last-child_td]:border-0">
        {entries.map((entry) => (
          <TableRow key={entry.model} className="border-0 [&>td]:border-b [&>td]:border-border/70">
            <TableCell className="w-8 text-muted-foreground">{entry.rank ?? ''}</TableCell>
            <TableCell className="font-semibold">{entry.model}</TableCell>
            <TableCell className="text-right tabular-nums">
              <RatingCell entry={entry} narrowed={narrowed} />
            </TableCell>
            <TableCell className="text-right text-muted-foreground tabular-nums">{intervalText(entry.rating)}</TableCell>
            <TableCell className="text-right tabular-nums">
              <MoveQualityCell entry={entry} />
            </TableCell>
            <TableCell className="text-right tabular-nums">{entry.games}</TableCell>
            <TableCell className="text-right whitespace-nowrap tabular-nums">
              <b>{entry.wins}</b> · {entry.draws} · {entry.losses}
            </TableCell>
            <TableCell className="text-right tabular-nums">{entry.forfeits}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** What the page says in the table's place: loading, no games yet, or an error. */
function Notice({ className, children }: { className?: string; children: ReactNode }) {
  return <p className={cn('px-3 text-muted-foreground', className)}>{children}</p>
}

export function AnalyticsPage() {
  const [modes, setModes] = useState<ModeKey[]>(ALL_MODES)
  const ranking = useQuery(rankingQuery(modes.length < ALL_MODES.length ? modes : []))
  const entries = ranking.data?.models
  // The Ranking shown, which stays while another Modes' loads: its own Modes say what its numbers come from.
  const narrowed = (ranking.data?.modes.length ?? ALL_MODES.length) < ALL_MODES.length
  const stale = ranking.isPlaceholderData
  const reference = <Explained explanation={REFERENCE_CONFIGURATION}>Reference configuration</Explained>

  return (
    <TooltipProvider>
      <div className="min-h-svh text-sm">
        <TopBar current="analytics" />
        <main className="mx-auto max-w-[1400px] px-6 pt-4 pb-10">
          <h1 className="text-2xl font-semibold tracking-tight">Ranking</h1>
          <p className="mt-1 mb-5 text-muted-foreground">
            Every model, ranked by its Rating under the {reference}, on the chess.com Rapid scale.
          </p>
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
                  No finished games yet. Run an Anchor match batch, and its model shows up here.
                </Notice>
              ) : (
                <RankingTable entries={entries} narrowed={narrowed} stale={stale} />
              )}
            </CardContent>
            <CardFooter>
              <p className="text-xs text-muted-foreground">
                Only games under the {reference} count, in the Modes chosen. The Rating comes only from wins, draws
                and losses against Anchors and in LLM faceoffs; “&lt; X” is an upper bound, “—” no Rating, why on
                hover. The Move-quality estimate comes from the moves alone, and is never blended with it. No score:
                models face different Anchors on the ladder.
              </p>
            </CardFooter>
          </Card>
        </main>
      </div>
    </TooltipProvider>
  )
}
