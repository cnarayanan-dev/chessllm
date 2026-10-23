import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test } from 'vitest'
import type { GameState, Probe, PromptTemplateInfo } from '@/api/types'
import { TurnPanel } from '@/components/turn/TurnPanel'
import { fakeBackend, later } from '@/test/fakeBackend'
import { AFTER_NF3, aTurn, afterE5, E4, E5, NC6, NF3, plies } from '@/test/games'
import { setPromptLabOn } from '@/settings/promptLab'

beforeEach(() => localStorage.clear())

const FREE: PromptTemplateInfo['fits'] = ['free', 'blind_enforced']
const template = (id: string, name: string | null, fits = FREE, isDefault = false): PromptTemplateInfo => ({
  id,
  name,
  system_prompt: `The System prompt of ${id}.`,
  turn_template: 'PGN: $moves\nFEN: $fen',
  fits,
  default_for: isDefault ? fits : [],
})

/** The Prompt library as GET /api/prompt-templates lists it. */
const LIBRARY = [
  template('default@1', 'Default', FREE, true),
  template('described@1', 'Described'),
  template('default-listed@1', 'Default listed', ['listed', 'listed_enforced'], true),
  template('terse@1', null),
]

/** 1. e4 e5 2. Nf3 Nc6, the LLM playing Black on the Default. */
const twoMovesIn = (overrides: Partial<GameState> = {}) =>
  afterE5({
    plies: plies(E4, E5, NF3, NC6),
    llm_turns: [aTurn('e5'), aTurn('Nc6', { ply: 4 })],
    prompt_templates: { black: { id: 'default@1', name: 'Default' } },
    ...overrides,
  })

/** A Probe of the LLM's Nc6 turn, as the API answers it. */
function aProbe(move: string, legal: boolean, templateId = 'described@1', ply = 4): Probe {
  const chosen = LIBRARY.find((each) => each.id === templateId)!
  return {
    game_id: 'game-1',
    ply,
    color: 'black',
    model: 'qwen3.5:9b',
    thinking: false,
    llm_constraints: 'free',
    sampling: {},
    prompt_template: { id: chosen.id, name: chosen.name, system_prompt: chosen.system_prompt, turn_template: chosen.turn_template },
    attempt: {
      move,
      san: legal ? move : null,
      notation_slip: false,
      result: legal ? 'legal' : 'illegal',
      feedback_sent: null,
      raw_reply: JSON.stringify({ reasoning: `Probed ${move}.`, move }),
      thinking: null,
      reasoning: `Probed ${move}.`,
      error: null,
      latency_s: 2.5,
      prompt: [
        { role: 'system', content: chosen.system_prompt },
        { role: 'user', content: `PGN: 1. e4 e5 2. Nf3\nFEN: ${AFTER_NF3}` },
      ],
    },
    asked_at: '2026-10-23T12:00:00+02:00',
  }
}

function renderPanel(game: GameState, llmTurnRunning = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const panel = (running: boolean) => (
    <QueryClientProvider client={queryClient}>
      <TurnPanel game={game} ply={4} live llmTurnRunning={running} />
    </QueryClientProvider>
  )
  const { rerender } = render(panel(llmTurnRunning))
  return { rerender: (running: boolean) => rerender(panel(running)) }
}

const panel = () => screen.getByRole('region', { name: 'Turn' })
const openPromptTab = () => userEvent.click(within(panel()).getByRole('tab', { name: 'Prompt' }))
const picker = () => within(panel()).getByRole('combobox', { name: 'Prompt to probe with' })
const tryButton = () => within(panel()).getByRole('button', { name: 'Try' })
const probes = () => within(panel()).queryByRole('list', { name: 'Probes' })

test('with Prompt lab off the Prompt tab is as before: no prompt to try, nothing asked of the API', async () => {
  const backend = fakeBackend()
  renderPanel(twoMovesIn())

  await openPromptTab()

  expect(within(panel()).queryByRole('button', { name: 'Try' })).not.toBeInTheDocument()
  expect(within(panel()).getByText('The Prompt was not recorded for this turn.')).toBeVisible()
  expect(backend.sent).toEqual([])
})

test("on, the row names the game's own template, and its list the templates that fit, that one marked", async () => {
  setPromptLabOn(true)
  fakeBackend().on('GET /api/prompt-templates', Response.json(LIBRARY)).on('GET /api/games/game-1/probes', Response.json([]))
  renderPanel(twoMovesIn())
  await openPromptTab()

  await waitFor(() => expect(picker()).toHaveTextContent('Prompt: Default'))
  await userEvent.click(picker())

  const options = (await screen.findAllByRole('option')).map((option) => option.textContent)
  expect(options).toEqual(['Default · in the game', 'Described', 'terse@1'])
})

test.each([
  ['saved and played', { id: 'terse@1', name: null }, 'terse@1', ['Default', 'Described', 'terse@1 · in the game']],
  ['since hidden, or never listed', { id: 'moves@1', name: 'Moves' }, 'Default', ['Default', 'Described', 'terse@1']],
])('the template the game played, %s, is marked by its ID', async (_, played, first, listed) => {
  setPromptLabOn(true)
  fakeBackend().on('GET /api/prompt-templates', Response.json(LIBRARY)).on('GET /api/games/game-1/probes', Response.json([]))
  renderPanel(twoMovesIn({ prompt_templates: { black: played } }))
  await openPromptTab()

  await waitFor(() => expect(picker()).toHaveTextContent(`Prompt: ${first}`))
  await userEvent.click(picker())

  expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toEqual(listed)
  const note = screen.queryByRole('note')
  expect(note?.textContent ?? null).toBe(played.id === 'moves@1' ? 'In the game: Moves, not in this list.' : null)
})

test('a Notation slip is marked in its row as the move list marks it, the move named in its standard SAN', async () => {
  setPromptLabOn(true)
  const slipped = aProbe('Nc6', true)
  slipped.attempt = { ...slipped.attempt, move: 'b8c6', notation_slip: true }
  fakeBackend()
    .on('GET /api/prompt-templates', Response.json(LIBRARY))
    .on('GET /api/games/game-1/probes', Response.json([slipped, aProbe('Nf6', true)]))
  renderPanel(twoMovesIn())
  await openPromptTab()

  const [clean, slip] = await within(await waitFor(() => probes()!)).findAllByRole('button', { name: /·/ })

  expect(slip).toHaveTextContent('Nc6 · Legal')
  expect(slip).toHaveTextContent('written "b8c6"')
  expect(clean).not.toHaveTextContent('written')
})

test('Try asks about the turn shown with the template picked, and shows the probe and the tally under the row', async () => {
  setPromptLabOn(true)
  const answer = later()
  const backend = fakeBackend()
    .on('GET /api/prompt-templates', Response.json(LIBRARY))
    .on('GET /api/games/game-1/probes', Response.json([]))
    .on('POST /api/games/current/probes', answer.promise)
  renderPanel(twoMovesIn())
  await openPromptTab()
  await waitFor(() => expect(picker()).toHaveTextContent('Prompt: Default'))
  await userEvent.click(picker())
  await userEvent.click(await screen.findByRole('option', { name: 'Described' }))

  await userEvent.click(tryButton())

  expect(backend.sentTo('POST /api/games/current/probes')).toEqual([
    { method: 'POST', path: '/api/games/current/probes', body: { ply: 4, color: 'black', prompt_template_id: 'described@1' } },
  ])
  expect(within(probes()!).getByText('asking…')).toBeVisible()
  answer.resolve(Response.json(aProbe('Bb4', false)))
  const row = await within(probes()!).findByRole('button', { name: /Bb4 · Illegal/ })
  expect(row).toHaveTextContent('Described')
  expect(row).toHaveTextContent('2.5 s')
  expect(within(panel()).getByText('Described: 0 of 1 legal')).toBeVisible()
})

test("a reopened game shows the turn's probes, each opening on its Reasoning and Prompt, tallied per template", async () => {
  setPromptLabOn(true)
  const listed = [aProbe('Nf6', true), aProbe('Bb4', false), aProbe('d6', true, 'default@1'), aProbe('Nc6', true, 'described@1', 2)]
  fakeBackend().on('GET /api/prompt-templates', Response.json(LIBRARY)).on('GET /api/games/game-1/probes', Response.json(listed))
  renderPanel(twoMovesIn())
  await openPromptTab()

  const rows = await within(await waitFor(() => probes()!)).findAllByRole('button', { name: /·/ })
  expect(rows.map((row) => row.textContent)).toEqual([
    expect.stringContaining('d6 · Legal'),
    expect.stringContaining('Bb4 · Illegal'),
    expect.stringContaining('Nf6 · Legal'),
  ])
  expect(within(panel()).getByText('Described: 1 of 2 legal')).toBeVisible()
  expect(within(panel()).getByText('Default: 1 of 1 legal')).toBeVisible()

  await userEvent.click(rows[1])

  expect(within(panel()).getByText('Probed Bb4.')).toBeVisible()
  expect(within(panel()).getByText(`PGN: 1. e4 e5 2. Nf3\nFEN: ${AFTER_NF3}`, { normalizer: (text) => text })).toBeVisible()
})

test('Try is disabled while an LLM turn runs, why on hover', async () => {
  setPromptLabOn(true)
  fakeBackend().on('GET /api/prompt-templates', Response.json(LIBRARY)).on('GET /api/games/game-1/probes', Response.json([]))
  const { rerender } = renderPanel(twoMovesIn(), true)
  await openPromptTab()
  await waitFor(() => expect(picker()).toHaveTextContent('Prompt: Default'))

  expect(tryButton()).toBeDisabled()
  expect(tryButton()).toHaveAttribute('aria-description', expect.stringMatching(/An LLM turn is running/))
  await userEvent.hover(tryButton().parentElement!)
  expect((await screen.findAllByText(/An LLM turn is running/)).some((text) => text.closest('[data-slot=tooltip-content]'))).toBe(true)

  rerender(false)

  expect(tryButton()).toBeEnabled()
})

test('a refused probe says why under the row', async () => {
  setPromptLabOn(true)
  const refused = { detail: 'an LLM turn is running: a Probe never runs alongside one', code: 'llm_turn_running' }
  fakeBackend()
    .on('GET /api/prompt-templates', Response.json(LIBRARY))
    .on('GET /api/games/game-1/probes', Response.json([]))
    .on('POST /api/games/current/probes', Response.json(refused, { status: 409 }))
  renderPanel(twoMovesIn())
  await openPromptTab()
  await waitFor(() => expect(picker()).toHaveTextContent('Prompt: Default'))

  await userEvent.click(tryButton())

  expect(await within(panel()).findByRole('alert')).toHaveTextContent(refused.detail)
  expect(probes()).not.toBeInTheDocument()
})
