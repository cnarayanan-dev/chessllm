import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'
import { AnalyticsPage } from '@/analytics/AnalyticsPage'
import type { LeaderboardEntry } from '@/analytics/leaderboard'
import { fakeBackend } from '@/test/fakeBackend'
import { anEntry, moveQuality, rated, upperBound } from '@/test/leaderboard'

const ENTRIES = [
  anEntry('faceoff-only', {
    configuration: { model: 'mistral:7b', retry_feedback: 'bare' },
    rating: null,
    games: 6,
    wins: 3,
    draws: 0,
    losses: 3,
  }),
  anEntry('lost-all', { rating: upperBound(70), games: 10, wins: 0, draws: 0, losses: 10 }),
  anEntry('enforced', {
    configuration: { model: 'qwen3.5:9b', thinking: true, llm_constraints: 'listed_enforced' },
    rating: rated(410, 270, 550),
    games: 24,
    wins: 9,
    draws: 3,
    losses: 12,
    attempts: null,
    average_legal_move_streak: null,
    move_quality: moveQuality(520, { low: 420, high: 620, validated: false }),
  }),
]

function showPage(entries: LeaderboardEntry[] = ENTRIES) {
  const backend = fakeBackend().on('GET /api/leaderboard', Response.json({ configurations: entries }))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AnalyticsPage />
    </QueryClientProvider>,
  )
  return backend
}

const headers = () => screen.getAllByRole('columnheader').map((header) => header.textContent)
/** The table's rows below the header, each as its cells' text. */
const rows = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getAllByRole('cell').map((cell) => cell.textContent))
const models = () => rows().map((cells) => cells[1]!.split(' ')[0])

test('lists every configuration ranked by Rating, with the default columns', async () => {
  showPage()

  expect(await screen.findByText('qwen3.5:9b')).toBeInTheDocument()
  expect(headers()).toEqual(['#', 'Player configuration', 'Rating↓', 'Games', 'W · D · L'])
  expect(rows().map((cells) => [cells[0], cells[2], cells[3], cells[4]])).toEqual([
    ['1', '410', '24', '9 · 3 · 12'],
    ['2', '< 70', '10', '0 · 0 · 10'],
    ['3', '—', '6', '3 · 0 · 3'],
  ])
})

test('shows each configuration as its model and chips, with a legend of the colours', async () => {
  showPage()

  const qwen = (await screen.findByText('qwen3.5:9b')).closest('tr')!
  expect(within(qwen).getByText('Listed enforced')).toHaveAttribute('data-hue', 'listed_enforced')
  expect(within(qwen).getByText('thinking on')).toHaveAttribute('data-hue', 'thinking')
  expect(within(qwen).getByText('feedback explained')).not.toHaveAttribute('data-hue')
  const legend = screen.getByTestId('legend')
  for (const name of ['Free', 'Listed', 'Blind enforced', 'Listed enforced', 'thinking on']) {
    expect(within(legend).getByText(name)).toBeInTheDocument()
  }
})

test('sorts by a column, and turns the order round on a second click', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')

  await user.click(screen.getByRole('button', { name: 'Games' }))
  expect(models()).toEqual(['qwen3.5:9b', 'llama3:8b', 'mistral:7b'])
  expect(screen.getByRole('columnheader', { name: /Games/ })).toHaveAttribute('aria-sort', 'descending')

  await user.click(screen.getByRole('button', { name: /Games/ }))
  expect(models()).toEqual(['mistral:7b', 'llama3:8b', 'qwen3.5:9b'])
  expect(screen.getByRole('columnheader', { name: /Games/ })).toHaveAttribute('aria-sort', 'ascending')
  // The rank stays the Rating's.
  expect(rows().map((cells) => cells[0])).toEqual(['3', '2', '1'])
})

test('the Player configuration column does not sort', async () => {
  showPage()
  await screen.findByText('qwen3.5:9b')

  expect(screen.queryByRole('button', { name: 'Player configuration' })).toBeNull()
})

test('"All columns" adds the rest, with n/a under Enforced decoding and an unvalidated estimate marked', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')

  await user.click(screen.getByRole('switch', { name: 'All columns' }))

  expect(headers()).toEqual([
    '#',
    'Player configuration',
    'Rating↓',
    'Games',
    'W · D · L',
    'Rating 95%',
    'Move-quality estimate',
    'Score',
    'Forfeits',
    'Legal moves played',
    'Attempts legal',
    'Avg. Legal-move streak',
  ])
  const [qwen, llama] = rows()
  expect(qwen!.slice(5)).toEqual(['270 to 550', '520unvalidated', '60%', '1', '300', 'n/a', 'n/a'])
  expect(llama!.slice(5)).toEqual(['—', '—', '60%', '1', '300', '94%', '12.5'])

  await user.click(screen.getByRole('switch', { name: 'All columns' }))
  expect(headers()).toHaveLength(5)
})

test('says so when there are no finished games yet', async () => {
  showPage([])

  expect(await screen.findByText(/No finished games yet/)).toBeInTheDocument()
})

test('says so when the leaderboard cannot be loaded', async () => {
  fakeBackend().on('GET /api/leaderboard', Response.json({ detail: 'disk on fire' }, { status: 500 }))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AnalyticsPage />
    </QueryClientProvider>,
  )

  expect(await screen.findByText(/Could not load the leaderboard: disk on fire/)).toBeInTheDocument()
})

test('has the top bar: the ChessLLM mark links back to the game, and Analytics is marked as the page shown', () => {
  showPage()

  const topBar = screen.getByRole('banner')
  expect(within(topBar).getByRole('link', { name: 'ChessLLM' })).toHaveAttribute('href', '/')
  expect(within(topBar).getByRole('link', { name: 'Analytics' })).toHaveAttribute('aria-current', 'page')
  expect(within(topBar).getByRole('link', { name: 'New game' })).toBeInTheDocument()
  expect(within(topBar).getByRole('link', { name: 'Settings' })).toBeInTheDocument()
})
