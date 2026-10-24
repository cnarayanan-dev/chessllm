import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test } from 'vitest'
import type { GameState, Probe, PromptTemplateInfo } from '@/api/types'
import { GameLayout } from '@/components/game-layout/GameLayout'
import { TurnPanel } from '@/components/turn/TurnPanel'
import { fakeBackend, later } from '@/test/fakeBackend'
import { AFTER_NC6, AFTER_NF3, aTurn, afterE5, E4, E5, NC6, NF3, plies } from '@/test/games'
import { setPromptLabOn } from '@/settings/promptLab'

beforeEach(() => localStorage.clear())

const FREE: PromptTemplateInfo['fits'] = ['free', 'blind_enforced']
const template = (id: string, name: string | null, fits = FREE, isDefault = false): PromptTemplateInfo => ({
  id,
  name,
  system_prompt: `The System prompt of ${id}.`,
  turn_template: 'PGN: $moves\nFEN: $fen',
  fits,
  turn_memories: id.startsWith('moves') ? ['chat_moves'] : ['fresh', 'chat_position'],
  default_for: isDefault ? fits : [],
  saved: !['default', 'described'].includes(id.split(/[-@]/)[0]),
})

/** The Prompt library as GET /api/prompt-templates lists it; Moves, for Chat with moves alone, is never probed with. */
const LIBRARY = [
  template('default@1', 'Default', FREE, true),
  template('described@1', 'Described'),
  template('moves@1', 'Moves', FREE, true),
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
  const panel = (running: boolean, shown = game, ply = 4) => (
    <QueryClientProvider client={queryClient}>
      <GameLayout
        game={<TurnPanel game={shown} ply={ply} live llmTurnRunning={running} />}
        board={<div data-testid="board" />}
        moves={<div />}
      />
    </QueryClientProvider>
  )
  const { rerender } = render(panel(llmTurnRunning))
  /** Renders the panel again: an LLM turn starting or landing, or the game going on (another game, or ply). */
  return { rerender: (running: boolean, shown?: GameState, ply?: number) => rerender(panel(running, shown, ply)) }
}

const panel = () => screen.getByRole('region', { name: 'Turn' })
const openPromptTab = () => userEvent.click(within(panel()).getByRole('tab', { name: 'Prompt' }))
const picker = () => within(panel()).getByRole('combobox', { name: 'Prompt to probe with' })
const promptName = () => within(panel()).getByRole('button', { name: /^Prompt:/ })
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

  await waitFor(() => expect(promptName()).toHaveTextContent('Prompt: Default'))
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

  await waitFor(() => expect(promptName()).toHaveTextContent(`Prompt: ${first}`))
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
  await waitFor(() => expect(promptName()).toHaveTextContent('Prompt: Default'))
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
  await waitFor(() => expect(promptName()).toHaveTextContent('Prompt: Default'))

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
  await waitFor(() => expect(promptName()).toHaveTextContent('Prompt: Default'))

  await userEvent.click(tryButton())

  expect(await within(panel()).findByRole('alert')).toHaveTextContent(refused.detail)
  expect(probes()).not.toBeInTheDocument()
})

// The dock (Prompt lab): the template in a text box over the lower half of the page, the board in view above.
const dock = () => screen.getByRole('region', { name: 'Dock' })
const line = (label: string) => within(dock()).getByText(label).parentElement!
const openDock = async () => {
  await openPromptTab()
  await waitFor(() => expect(promptName()).toHaveTextContent('Prompt: Default'))
  await userEvent.click(promptName())
  return dock()
}
const withLibrary = () =>
  fakeBackend().on('GET /api/prompt-templates', Response.json(LIBRARY)).on('GET /api/games/game-1/probes', Response.json([]))

test("the prompt's name opens the dock on its template, the side columns inert; closing it restores the page", async () => {
  setPromptLabOn(true)
  withLibrary()
  renderPanel(twoMovesIn())

  const opened = await openDock()

  expect(within(opened).getByText('based on Default')).toBeVisible()
  expect(within(opened).getByRole('textbox', { name: 'System prompt' })).toHaveValue('The System prompt of default@1.')
  await userEvent.click(within(opened).getByRole('tab', { name: 'Turn template' }))
  expect(within(opened).getByRole('textbox', { name: 'Turn template' })).toHaveValue('PGN: $moves\nFEN: $fen')
  expect(line('In the game')).toHaveTextContent('Nc6 · Legal')
  expect(line('This version')).toHaveTextContent('Not tried yet')
  expect(screen.getByTestId('game-column')).toHaveAttribute('inert')
  expect(screen.getByTestId('moves-column')).toHaveAttribute('inert')
  expect(screen.getByTestId('board-column')).not.toHaveAttribute('inert')
  expect(document.body).toHaveClass('prompt-dock-open')

  await userEvent.click(within(opened).getByRole('button', { name: 'Close' }))

  expect(screen.queryByRole('region', { name: 'Dock' })).not.toBeInTheDocument()
  expect(screen.getByTestId('game-column')).not.toHaveAttribute('inert')
  expect(screen.getByTestId('moves-column')).not.toHaveAttribute('inert')
  expect(document.body).not.toHaveClass('prompt-dock-open')
})

test("Try in the dock probes with the text as it is: the template's ID until it is changed, then the unsaved text", async () => {
  setPromptLabOn(true)
  const backend = withLibrary()
  const edited = 'The System prompt of default@1. Be brief.'
  const unsavedProbe = aProbe('Nf6', true, 'default@1')
  unsavedProbe.prompt_template = { id: 'unsaved', name: null, system_prompt: edited, turn_template: 'PGN: $moves\nFEN: $fen' }
  backend.on('POST /api/games/current/probes', Response.json(aProbe('d6', true, 'default@1')), Response.json(unsavedProbe))
  renderPanel(twoMovesIn())
  const opened = await openDock()

  await userEvent.click(within(opened).getByRole('button', { name: 'Try' }))
  await waitFor(() => expect(line('This version')).toHaveTextContent('d6 · Legal'))
  await userEvent.type(within(opened).getByRole('textbox', { name: 'System prompt' }), ' Be brief.')
  expect(line('This version')).toHaveTextContent('Not tried yet')
  await userEvent.click(within(opened).getByRole('button', { name: 'Try' }))

  expect(backend.sentTo('POST /api/games/current/probes').map((request) => request.body)).toEqual([
    { ply: 4, color: 'black', prompt_template_id: 'default@1' },
    { ply: 4, color: 'black', system_prompt: edited, turn_template: 'PGN: $moves\nFEN: $fen' },
  ])
  await waitFor(() => expect(line('This version')).toHaveTextContent('Nf6 · Legal'))
  expect(within(panel()).getByText('unsaved: 1 of 1 legal')).toBeInTheDocument()
})

test('Save as new version adds a library entry, with its name if given, and the dock goes on from it', async () => {
  setPromptLabOn(true)
  const brief = { ...template('brief@abcd1234', 'Brief'), system_prompt: 'The System prompt of default@1. Be brief.' }
  const backend = withLibrary().on('POST /api/prompt-templates', Response.json(brief))
  renderPanel(twoMovesIn())
  const opened = await openDock()
  const save = () => within(opened).getByRole('button', { name: 'Save as new version' })
  expect(save()).toBeDisabled()

  await userEvent.type(within(opened).getByRole('textbox', { name: 'System prompt' }), ' Be brief.')
  await userEvent.type(within(opened).getByRole('textbox', { name: 'Name' }), 'Brief')
  await userEvent.click(save())

  expect(backend.sentTo('POST /api/prompt-templates').map((request) => request.body)).toEqual([
    {
      name: 'Brief',
      system_prompt: 'The System prompt of default@1. Be brief.',
      turn_template: 'PGN: $moves\nFEN: $fen',
      llm_constraints: 'free',
    },
  ])
  await waitFor(() => expect(within(opened).getByText('based on Brief')).toBeVisible())
  expect(save()).toBeDisabled()
  await userEvent.click(within(opened).getByRole('button', { name: 'Close' }))
  expect(promptName()).toHaveTextContent('Prompt: Brief')
  await userEvent.click(picker())
  expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toContain('Brief')
})

test('a refused save says why, and the text stays for fixing', async () => {
  setPromptLabOn(true)
  const refused = { detail: 'the System prompt has an unknown placeholder: $colour', code: 'invalid_prompt_template' }
  withLibrary().on('POST /api/prompt-templates', Response.json(refused, { status: 400 }))
  renderPanel(twoMovesIn())
  const opened = await openDock()

  await userEvent.type(within(opened).getByRole('textbox', { name: 'System prompt' }), ' You are $colour.')
  await userEvent.click(within(opened).getByRole('button', { name: 'Save as new version' }))

  expect(await within(opened).findByRole('alert')).toHaveTextContent(refused.detail)
  expect(within(opened).getByText('based on Default')).toBeVisible()
  expect(within(opened).getByRole('textbox', { name: 'System prompt' })).toHaveValue(
    'The System prompt of default@1. You are $colour.',
  )
})

test("the dock's text outlives the panel's tabs: the board stepping back, or the game's next turn landing", async () => {
  setPromptLabOn(true)
  withLibrary()
  const game = twoMovesIn()
  const { rerender } = renderPanel(game)
  const opened = await openDock()
  await userEvent.type(within(opened).getByRole('textbox', { name: 'System prompt' }), ' Be brief.')

  rerender(false, game, 2)
  const more = plies(E4, E5, NF3, NC6, ['f1c4', 'Bc4', AFTER_NC6], ['g8f6', 'Nf6', AFTER_NC6])
  const next = { ...game, plies: more, llm_turns: [...game.llm_turns, aTurn('Nf6', { ply: 6 })] }
  rerender(false, next, 6)

  expect(within(dock()).getByRole('textbox', { name: 'System prompt' })).toHaveValue('The System prompt of default@1. Be brief.')
  expect(line('In the game')).toHaveTextContent('Nc6 · Legal')
  expect(within(panel()).getByTestId('turn-move')).toHaveTextContent('Nc6')
  await userEvent.click(within(dock()).getByRole('button', { name: 'Close' }))
  expect(within(panel()).getByTestId('turn-move')).toHaveTextContent('Nf6')
})

test("closed and opened again on the same template and turn, the dock has its text as it was", async () => {
  setPromptLabOn(true)
  withLibrary()
  renderPanel(twoMovesIn())
  const opened = await openDock()
  await userEvent.type(within(opened).getByRole('textbox', { name: 'System prompt' }), ' Be brief.')
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('region', { name: 'Dock' })).not.toBeInTheDocument()

  await userEvent.click(promptName())

  expect(within(dock()).getByRole('textbox', { name: 'System prompt' })).toHaveValue('The System prompt of default@1. Be brief.')
})

test("the dock's Try is disabled while an LLM turn runs, why on hover", async () => {
  setPromptLabOn(true)
  withLibrary()
  const { rerender } = renderPanel(twoMovesIn())
  const opened = await openDock()

  rerender(true)

  const asking = within(opened).getByRole('button', { name: 'Try' })
  expect(asking).toBeDisabled()
  expect(asking).toHaveAttribute('aria-description', expect.stringMatching(/An LLM turn is running/))
  rerender(false)
  expect(asking).toBeEnabled()
})

test('a saved Prompt template can be hidden from the dock, leaving it out of the list; a default one cannot', async () => {
  setPromptLabOn(true)
  const backend = withLibrary().on(
    'POST /api/prompt-templates/terse%401/hide',
    Response.json(LIBRARY.filter((each) => each.id !== 'terse@1')),
  )
  renderPanel(twoMovesIn())
  expect(within(await openDock()).queryByRole('button', { name: 'Hide' })).not.toBeInTheDocument()
  await userEvent.click(within(dock()).getByRole('button', { name: 'Close' }))
  await userEvent.click(picker())
  await userEvent.click(await screen.findByRole('option', { name: 'terse@1' }))
  await userEvent.click(promptName())

  await userEvent.click(within(dock()).getByRole('button', { name: 'Hide' }))

  expect(backend.sentTo('POST /api/prompt-templates/terse%401/hide')).toHaveLength(1)
  await waitFor(() => expect(within(dock()).getByRole('button', { name: 'Hidden' })).toBeDisabled())
  await userEvent.click(within(dock()).getByRole('button', { name: 'Close' }))
  await userEvent.click(picker())
  expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toEqual([
    'Default · in the game',
    'Described',
  ])
})

test("a closed dock's text stays with its game: another game's dock on the same turn and template opens afresh", async () => {
  setPromptLabOn(true)
  withLibrary().on('GET /api/games/game-2/probes', Response.json([]))
  const { rerender } = renderPanel(twoMovesIn())
  const opened = await openDock()
  await userEvent.type(within(opened).getByRole('textbox', { name: 'System prompt' }), ' Be brief.')
  await userEvent.keyboard('{Escape}')

  rerender(false, twoMovesIn({ game_id: 'game-2' }))
  await userEvent.click(promptName())

  expect(within(dock()).getByRole('textbox', { name: 'System prompt' })).toHaveValue('The System prompt of default@1.')
})
