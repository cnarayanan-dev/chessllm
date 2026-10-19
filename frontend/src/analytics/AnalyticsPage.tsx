// The analytics page: the leaderboard of every Player configuration, ranked by Rating (prototype variant A).
import { useQuery } from '@tanstack/react-query'
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
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import '@/analytics/analytics.css'

function ChipView({ chip }: { chip: Chip }) {
  return (
    <span
      className="chip inline-flex items-center gap-1.5 rounded px-1.5 text-[11px] whitespace-nowrap text-muted-foreground not-data-hue:bg-muted"
      data-hue={chip.hue ?? undefined}
    >
      {chip.label}
    </span>
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
            render={<span />}
            className="ml-1.5 rounded border border-dashed px-1 text-[11px] text-muted-foreground"
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

  return (
    <>
      <div className="flex items-start justify-between gap-5">
        <div>
          <h1 className="text-xl font-semibold">Leaderboard</h1>
          <p className="mt-1 text-muted-foreground">
            Every Player configuration, ranked by Rating on the chess.com Rapid scale. Click a column to sort.
          </p>
        </div>
        <label className="mt-2 flex cursor-pointer items-center gap-2 text-muted-foreground">
          <Switch checked={all} onCheckedChange={setAll} />
          All columns
        </label>
      </div>
      <div data-testid="legend" className="mt-4 mb-2.5 flex flex-wrap gap-1.5">
        {LEGEND.map((chip) => (
          <ChipView chip={chip} key={chip.label} />
        ))}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            {shown.map((column) => {
              const sorted = sort.key === column.key
              return (
                <TableHead
                  key={column.key}
                  className={cn('text-xs text-muted-foreground', column.numeric && 'text-right')}
                  aria-sort={sorted ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {column.sortable ? (
                    <button
                      type="button"
                      className="cursor-pointer hover:text-foreground"
                      onClick={() => setSort(nextSort(sort, column.key as Sort['key']))}
                    >
                      {column.label}
                      {sorted && <span aria-hidden="true" className="ml-0.5">{sort.direction === 'asc' ? '↑' : '↓'}</span>}
                    </button>
                  ) : (
                    column.label
                  )}
                </TableHead>
              )
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((entry) => (
            <TableRow key={entry.id}>
              {shown.map((column) => {
                if (column.key === 'rank')
                  return (
                    <TableCell key="rank" className="w-8 text-muted-foreground">
                      {ranks.get(entry.id)}
                    </TableCell>
                  )
                if (column.key === 'configuration')
                  return (
                    <TableCell key="configuration" className="min-w-72 whitespace-normal">
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
      <p className="mt-4 text-xs text-muted-foreground">
        The Rating comes only from wins, draws and losses against Anchors and in LLM faceoffs; “&lt; X” is an upper bound
        when every anchored game was lost, “—” no path to an Anchor. The Move-quality estimate comes from the moves
        alone, and is never blended with it. n/a: not applicable under Enforced decoding.
      </p>
    </>
  )
}

export function AnalyticsPage() {
  const leaderboard = useQuery(leaderboardQuery)
  const entries = leaderboard.data?.configurations

  return (
    <TooltipProvider>
      <div className="min-h-svh text-sm">
        <TopBar current="analytics" />
        <main className="mx-auto max-w-[1400px] px-5 pt-6 pb-10">
          {leaderboard.isError ? (
            <p className="text-destructive">Could not load the leaderboard: {leaderboard.error.message}</p>
          ) : entries === undefined ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : entries.length === 0 ? (
            <p className="text-muted-foreground">
              No finished games yet. Play a game or run an Anchor match batch, and its Player configuration shows up
              here.
            </p>
          ) : (
            <Leaderboard entries={entries} />
          )}
        </main>
      </div>
    </TooltipProvider>
  )
}
