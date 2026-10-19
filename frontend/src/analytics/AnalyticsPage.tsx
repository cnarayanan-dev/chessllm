// The analytics page: the leaderboard of every Player configuration, ranked by Rating (prototype variant A), in a
// Luma card on the Stone page.
import { useQuery } from '@tanstack/react-query'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import {
  DEFAULT_SORT,
  LEGEND,
  attemptsLegalText,
  chips,
  columns,
  estimateText,
  intervalText,
  nextSort,
  ranked,
  scoreText,
  sortRows,
  streakText,
  type Chip,
  type ColumnKey,
  type LeaderboardEntry,
  type Sort,
} from '@/analytics/leaderboard'
import { leaderboardQuery } from '@/api/leaderboard'
import { TopBar } from '@/components/top-bar/TopBar'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import '@/analytics/analytics.css'

function ChipView({ chip }: { chip: Chip }) {
  return (
    <Badge
      variant="secondary"
      className="chip gap-1.5 font-normal text-muted-foreground"
      data-hue={chip.hue ?? undefined}
    >
      {chip.label}
    </Badge>
  )
}

function MoveQualityCell({ entry }: { entry: LeaderboardEntry }) {
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

/** The cell of each column but the rank and Player configuration. */
const CELLS: Record<Exclude<ColumnKey, 'rank' | 'configuration'>, (entry: LeaderboardEntry) => ReactNode> = {
  rating: (entry) => <span className="font-semibold">{estimateText(entry.rating)}</span>,
  games: (entry) => entry.games,
  wdl: (entry) => (
    <span className="whitespace-nowrap tabular-nums">
      <b>{entry.wins}</b> · {entry.draws} · {entry.losses}
    </span>
  ),
  interval: (entry) => <span className="text-muted-foreground">{intervalText(entry.rating)}</span>,
  move_quality: (entry) => <MoveQualityCell entry={entry} />,
  score: scoreText,
  forfeits: (entry) => entry.forfeits,
  legal_moves: (entry) => entry.legal_moves,
  attempts_legal: attemptsLegalText,
  streak: streakText,
}

function Leaderboard({ entries }: { entries: LeaderboardEntry[] }) {
  const [all, setAll] = useState(false)
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT)
  const ranks = useMemo(() => new Map(ranked(entries).map((entry, index) => [entry.id, index + 1])), [entries])
  const rows = useMemo(() => sortRows(entries, sort), [entries, sort])
  const shown = columns(all)
  const SortIcon = sort.direction === 'asc' ? ArrowUp : ArrowDown

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-3">
        <div data-testid="legend" className="flex flex-wrap gap-1.5">
          {LEGEND.map((chip) => (
            <ChipView chip={chip} key={chip.label} />
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-muted-foreground">
          <Switch checked={all} onCheckedChange={setAll} />
          All columns
        </label>
      </CardHeader>
      <CardContent className="px-3">
        <Table className="border-separate border-spacing-0">
          <TableHeader className="[&_tr]:border-0">
            <TableRow className="hover:bg-transparent">
              {shown.map((column) => {
                const sorted = sort.key === column.key
                return (
                  <TableHead
                    key={column.key}
                    className={cn(
                      'h-10 bg-muted text-xs text-muted-foreground first:rounded-l-2xl last:rounded-r-2xl',
                      column.numeric && 'text-right',
                      sorted && 'text-foreground',
                    )}
                    aria-sort={sorted ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    {column.sortable ? (
                      <button
                        type="button"
                        className="inline-flex cursor-pointer items-center gap-1 rounded-full outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-3.5"
                        onClick={() => setSort(nextSort(sort, column.key as Sort['key']))}
                      >
                        {column.label}
                        {sorted && <SortIcon aria-hidden="true" />}
                      </button>
                    ) : (
                      column.label
                    )}
                  </TableHead>
                )
              })}
            </TableRow>
          </TableHeader>
          <TableBody className="[&_tr:last-child_td]:border-0">
            {rows.map((entry) => (
              <TableRow key={entry.id} className="border-0 [&>td]:border-b [&>td]:border-border/70">
                {shown.map((column) => {
                  if (column.key === 'rank')
                    return (
                      <TableCell key="rank" className="w-8 text-muted-foreground">
                        {ranks.get(entry.id)}
                      </TableCell>
                    )
                  if (column.key === 'configuration')
                    return (
                      <TableCell key="configuration" className="min-w-80 whitespace-normal">
                        <div className="flex flex-wrap items-center gap-1">
                          <span className="mr-1 font-semibold">{entry.configuration.model}</span>{' '}
                          {chips(entry.configuration).map((chip) => (
                            <ChipView chip={chip} key={chip.label} />
                          ))}
                        </div>
                      </TableCell>
                    )
                  return (
                    <TableCell key={column.key} className="text-right tabular-nums">
                      {CELLS[column.key](entry)}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          The Rating comes only from wins, draws and losses against Anchors and in LLM faceoffs; “&lt; X” is an upper
          bound when every anchored game was lost, “—” no path to an Anchor. The Move-quality estimate comes from the
          moves alone, and is never blended with it. n/a: not applicable under Enforced decoding.
        </p>
      </CardFooter>
    </Card>
  )
}

/** What the page says in the leaderboard's place: loading, no games yet, or an error. */
function Notice({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <Card>
      <CardContent>
        <p className={cn('text-muted-foreground', className)}>{children}</p>
      </CardContent>
    </Card>
  )
}

export function AnalyticsPage() {
  const leaderboard = useQuery(leaderboardQuery)
  const entries = leaderboard.data?.configurations

  return (
    <TooltipProvider>
      <div className="min-h-svh text-sm">
        <TopBar current="analytics" />
        <main className="mx-auto max-w-[1400px] px-6 pt-4 pb-10">
          <h1 className="text-2xl font-semibold tracking-tight">Leaderboard</h1>
          <p className="mt-1 mb-5 text-muted-foreground">
            Every Player configuration, ranked by Rating on the chess.com Rapid scale. Click a column to sort.
          </p>
          {leaderboard.isError ? (
            <Notice className="text-destructive">Could not load the leaderboard: {leaderboard.error.message}</Notice>
          ) : entries === undefined ? (
            <Notice>Loading…</Notice>
          ) : entries.length === 0 ? (
            <Notice>
              No finished games yet. Play a game or run an Anchor match batch, and its Player configuration shows up
              here.
            </Notice>
          ) : (
            <Leaderboard entries={entries} />
          )}
        </main>
      </div>
    </TooltipProvider>
  )
}
