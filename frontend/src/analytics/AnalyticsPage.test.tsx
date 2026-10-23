import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'
import { AnalyticsPage } from '@/analytics/AnalyticsPage'
import type { RankingEntry } from '@/analytics/ranking'
import { fakeBackend, later } from '@/test/fakeBackend'
import { anEntry, moveQuality, rated, unrated, upperBound } from '@/test/ranking'

const ENTRIES = [
  anEntry('qwen3.5:9b', {
    rank: 1,
    rating: rated(410, 270, 550),
    games: 24,
    wins: 9,
    draws: 3,
    losses: 12,
    forfeits: 2,
    move_quality: moveQuality(520, { low: 420, high: 620, validated: false }),
  }),
  anEntry('llama3:8b', { rank: 2, rating: upperBound(70), games: 10, wins: 0, draws: 0, losses: 10, forfeits: 4 }),
  unrated('gemma3:12b', 'no_anchor_path', { games: 4, wins: 4, draws: 0, losses: 0, forfeits: 0 }),
  unrated('phi4:14b', 'no_reference_games', { games: 0, wins: 0, draws: 0, losses: 0, forfeits: 0 }),
]

const ranking = (models: RankingEntry[], modes = ['play_llm', 'llm_faceoff', 'anchor_match']) =>
  Response.json({ modes, models })

function showPage(entries: RankingEntry[] = ENTRIES) {
  const backend = fakeBackend().on('GET /api/ranking', ranking(entries))
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
const row = (model: string) => screen.getByText(model, { selector: 'td' }).closest('tr')!

test('lists every model in the order of the Ranking, unranked ones last without a rank', async () => {
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
    ['1', 'qwen3.5:9b', '410', '270 to 550', '520unvalidated', '24', '9 · 3 · 12', '2'],
    ['2', 'llama3:8b', '< 70', '—', '—', '10', '0 · 0 · 10', '4'],
    ['', 'gemma3:12b', '—', '—', '—', '4', '4 · 0 · 0', '0'],
    ['', 'phi4:14b', '—', '—', '—', '0', '0 · 0 · 0', '0'],
  ])
})

test('the old table is gone: no Player configurations, no "All columns" switch, no Score', async () => {
  showPage()
  await screen.findByText('qwen3.5:9b')

  expect(screen.queryByRole('switch', { name: 'All columns' })).toBeNull()
  expect(screen.queryByRole('columnheader', { name: 'Score' })).toBeNull()
  expect(screen.queryByRole('columnheader', { name: 'Player configuration' })).toBeNull()
})

test('a missing Rating says why on hover and to screen readers', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')

  const gemma = within(row('gemma3:12b')).getAllByText('—')[0]!
  expect(gemma).toHaveAttribute('aria-description', expect.stringMatching(/No path to an Anchor/))
  await user.hover(gemma)
  expect(await screen.findByText(/ties it to no Anchor match/)).toBeInTheDocument()

  const phi = within(row('phi4:14b')).getAllByText('—')[0]!
  expect(phi).toHaveAttribute('aria-description', expect.stringMatching(/No games under the Reference configuration/))
})

test('an upper bound explains itself, and so does the Reference configuration', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')

  await user.hover(within(row('llama3:8b')).getByText('< 70'))
  expect(await screen.findByText(/An upper bound: it lost every game/)).toBeInTheDocument()

  const [reference] = screen.getAllByText('Reference configuration')
  expect(reference).toHaveAttribute('aria-description', expect.stringMatching(/^Thinking off, Free, Standard rules/))
})

test('the unvalidated Move-quality estimate is marked, and the mark explains itself', async () => {
  const user = userEvent.setup()
  showPage()
  await screen.findByText('qwen3.5:9b')

  await user.hover(screen.getByText('unvalidated'))
  expect(await screen.findByText(/has not passed its validation/)).toBeInTheDocument()
})

test('the Mode filter starts with every Mode, and narrowing it asks for those Modes alone', async () => {
  const user = userEvent.setup()
  const backend = showPage()
  await screen.findByText('qwen3.5:9b')
  const filter = screen.getByRole('group', { name: 'Modes' })
  const mode = (name: string) => within(filter).getByRole('button', { name })
  for (const name of ['Anchor matches', 'LLM faceoffs', 'Play LLM']) {
    expect(mode(name)).toHaveAttribute('aria-pressed', 'true')
  }
  expect(mode('LLM faceoffs')).toHaveAttribute('aria-description', expect.stringMatching(/alone reach no Anchor/))

  backend.on('GET /api/ranking?mode=llm_faceoff&mode=play_llm', ranking(ENTRIES, ['llm_faceoff', 'play_llm']))
  backend.on(
    'GET /api/ranking?mode=llm_faceoff',
    ranking([unrated('qwen3.5:9b', 'no_anchor_path', { games: 6, wins: 3, draws: 0, losses: 3, forfeits: 0 })], [
      'llm_faceoff',
    ]),
  )
  await user.click(mode('Anchor matches'))
  await user.click(mode('Play LLM'))

  expect(mode('Anchor matches')).toHaveAttribute('aria-pressed', 'false')
  await waitFor(() => expect(rows()).toEqual([['', 'qwen3.5:9b', '—', '—', '—', '6', '3 · 0 · 3', '0']]))

  // The last Mode chosen stays.
  await user.click(mode('LLM faceoffs'))
  expect(mode('LLM faceoffs')).toHaveAttribute('aria-pressed', 'true')
  expect(backend.sentTo('GET /api/ranking')).toHaveLength(1)
})

test('while the Modes just chosen load, the last Ranking stays, marked stale, and explains itself as before', async () => {
  const user = userEvent.setup()
  const backend = showPage()
  await screen.findByText('qwen3.5:9b')
  const narrowed = later()
  backend.on('GET /api/ranking?mode=llm_faceoff&mode=play_llm', narrowed.promise)

  await user.click(screen.getByRole('button', { name: 'Anchor matches' }))

  const table = screen.getByRole('table')
  expect(table).toHaveAttribute('aria-busy', 'true')
  const phi = () => within(row('phi4:14b')).getAllByText('—')[0]!
  expect(phi()).toHaveAttribute('aria-description', expect.stringMatching(/yet, so not ranked/))

  narrowed.resolve(ranking(ENTRIES, ['llm_faceoff', 'play_llm']))
  await waitFor(() => expect(table).toHaveAttribute('aria-busy', 'false'))
  expect(phi()).toHaveAttribute('aria-description', expect.stringMatching(/in the Modes chosen/))
})

test('says so when there are no finished games yet', async () => {
  showPage([])

  expect(await screen.findByText(/No finished games yet/)).toBeInTheDocument()
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
