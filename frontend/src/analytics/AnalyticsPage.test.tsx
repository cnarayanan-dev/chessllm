import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'
import { AnalyticsPage } from '@/analytics/AnalyticsPage'
import type { RankingEntry } from '@/analytics/ranking'
import { fakeBackend } from '@/test/fakeBackend'
import { anEntry, moveQuality, rated, unranked, upperBound } from '@/test/ranking'

const ALL = ['play_llm', 'llm_faceoff', 'anchor_match']

const ENTRIES = [
  anEntry('qwen3.5:9b', {
    rating: rated(410, 270, 550),
    games: 24,
    wins: 9,
    draws: 3,
    losses: 12,
    forfeits: 0,
    move_quality: moveQuality(520, { low: 420, high: 620, validated: false }),
  }),
  anEntry('llama3:8b', { rank: 2, rating: upperBound(70), games: 10, wins: 0, draws: 0, losses: 10, forfeits: 4 }),
  unranked('gemma3:12b', 'no_path_to_anchor', { games: 6, wins: 3, draws: 0, losses: 3, forfeits: 0 }),
  unranked('phi4:14b', 'no_reference_games', { games: 0, wins: 0, draws: 0, losses: 0, forfeits: 0 }),
]

function showPage(entries: RankingEntry[] = ENTRIES) {
  const backend = fakeBackend().on('GET /api/ranking', Response.json({ modes: ALL, models: entries }))
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

test('ranks the models by their Rating, the unranked ones last, with a row of numbers each', async () => {
  showPage()

  expect(await screen.findByText('qwen3.5:9b')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Ranking' })).toBeInTheDocument()
  expect(headers()).toEqual([
    '#',
    'Model',
    'Rating',
    '95% interval',
    'Move-quality estimate',
    'Games',
    'W · D · L',
    'Forfeits',
  ])
  expect(rows()).toEqual([
    ['1', 'qwen3.5:9b', '410', '270 to 550', '520unvalidated', '24', '9 · 3 · 12', '0'],
    ['2', 'llama3:8b', '< 70', '—', '—', '10', '0 · 0 · 10', '4'],
    ['', 'gemma3:12b', '—', '—', '—', '6', '3 · 0 · 3', '0'],
    ['', 'phi4:14b', '—', '—', '—', '0', '0 · 0 · 0', '0'],
  ])
})

test('the old leaderboard is gone: no All columns switch, no Player configurations, no Score', async () => {
  showPage()
  await screen.findByText('qwen3.5:9b')

  expect(screen.queryByRole('switch', { name: 'All columns' })).toBeNull()
  expect(screen.queryByRole('columnheader', { name: 'Player configuration' })).toBeNull()
  expect(screen.queryByRole('columnheader', { name: 'Score' })).toBeNull()
})

test('a missing Rating gives its reason on hover', async () => {
  const user = userEvent.setup()
  showPage()

  const gemma = (await screen.findByText('gemma3:12b')).closest('tr')!
  await user.hover(within(gemma).getAllByText('—')[0]!)
  expect(await screen.findByText(/^No path to an Anchor/)).toBeInTheDocument()

  const phi = screen.getByText('phi4:14b').closest('tr')!
  await user.hover(within(phi).getAllByText('—')[0]!)
  expect(await screen.findByText('No games under the Reference configuration yet.')).toBeInTheDocument()
})

test('an upper bound says so on hover', async () => {
  const user = userEvent.setup()
  showPage()

  await user.hover(await screen.findByText('< 70'))
  expect(await screen.findByText(/^An upper bound/)).toBeInTheDocument()
})

test('the unvalidated mark explains itself in a tooltip', async () => {
  const user = userEvent.setup()
  showPage()

  await user.hover(await screen.findByText('unvalidated'))
  expect(await screen.findByText(/has not passed its validation/)).toBeInTheDocument()
})

test('what the Ranking is, and the Reference configuration, are on hover, not on the page', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')
  expect(screen.queryByText(/^Every model/)).toBeNull()
  expect(screen.queryByText(/^The Rating comes only/)).toBeNull()

  await user.hover(screen.getByRole('button', { name: 'About the Ranking' }))
  expect(await screen.findByText(/Thinking off, Free, Standard rules, 5 attempts/)).toBeInTheDocument()
})

test('each column but # and Model explains itself on hover', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')

  await user.hover(within(screen.getByRole('columnheader', { name: 'W · D · L' })).getByText('W · D · L'))
  expect(await screen.findByText(/only the Rating compares them/)).toBeInTheDocument()
})

test('the Mode filter: every Mode by default; narrowed, the Ranking is asked for again from those Modes', async () => {
  const user = userEvent.setup()
  const backend = showPage()
  await screen.findByText('qwen3.5:9b')
  const modes = within(screen.getByRole('group', { name: 'Modes' }))
  const pressed = () =>
    modes.getAllByRole('button').map((button) => [button.textContent, button.getAttribute('aria-pressed')])
  expect(pressed()).toEqual([
    ['Play LLM', 'true'],
    ['LLM faceoffs', 'true'],
    ['Anchor matches', 'true'],
  ])

  const faceoffsOnly = [unranked('qwen3.5:9b', 'no_path_to_anchor', { games: 4 })]
  backend.on(
    'GET /api/ranking?modes=llm_faceoff&modes=anchor_match',
    Response.json({ modes: ['llm_faceoff', 'anchor_match'], models: ENTRIES }),
  )
  backend.on('GET /api/ranking?modes=llm_faceoff', Response.json({ modes: ['llm_faceoff'], models: faceoffsOnly }))
  await user.click(modes.getByRole('button', { name: 'Play LLM' }))
  await user.click(modes.getByRole('button', { name: 'Anchor matches' }))

  await waitFor(() => expect(rows()).toEqual([['', 'qwen3.5:9b', '—', '—', '—', '4', '5 · 2 · 3', '1']]))
  expect(pressed()).toEqual([
    ['Play LLM', 'false'],
    ['LLM faceoffs', 'true'],
    ['Anchor matches', 'false'],
  ])
  // The last Mode left can't be turned off.
  expect(modes.getByRole('button', { name: 'LLM faceoffs' })).toHaveAttribute('aria-disabled', 'true')
  expect(backend.sentTo('GET /api/ranking?modes=llm_faceoff')).toHaveLength(1)
})

test('each Mode explains on hover what its games give', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')

  await user.hover(screen.getByRole('button', { name: 'Play LLM' }))
  expect(await screen.findByText(/never the Rating/)).toBeInTheDocument()
})

test('says so when there are no finished games yet', async () => {
  showPage([])

  expect((await screen.findByText(/No finished games yet/)).closest('[data-slot=card]')).not.toBeNull()
})

test('says so when the Ranking cannot be loaded', async () => {
  fakeBackend().on('GET /api/ranking', Response.json({ detail: 'disk on fire' }, { status: 500 }))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AnalyticsPage />
    </QueryClientProvider>,
  )

  expect(await screen.findByText(/Could not load the Ranking: disk on fire/)).toBeInTheDocument()
})

test('has the top bar: the ChessLLM mark links back to the game, and Analytics is marked as the page shown', () => {
  showPage()

  const topBar = screen.getByRole('banner')
  expect(within(topBar).getByRole('link', { name: 'ChessLLM' })).toHaveAttribute('href', '/')
  expect(within(topBar).getByRole('link', { name: 'Analytics' })).toHaveAttribute('aria-current', 'page')
  expect(within(topBar).getByRole('link', { name: 'New game' })).toHaveAttribute('href', '/?then=new-game')
  expect(within(topBar).queryByRole('link', { name: 'Settings' })).not.toBeInTheDocument()
})
