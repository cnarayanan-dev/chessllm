import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import type { Attempt, Probe, PromptTemplateInfo } from '@/api/types'
import { TurnPanel } from '@/components/turn/TurnPanel'
import { setPromptLabOn } from '@/settings/promptLab'
import { fakeBackend } from '@/test/fakeBackend'
import { AFTER_E4, aTurn, afterE5 } from '@/test/games'
import { defaultsOf, FREE, POSITION } from '@/test/promptLibrary'

beforeEach(() => {
  localStorage.clear()
  setPromptLabOn(true)
})

const DEFAULT: PromptTemplateInfo = {
  id: 'default@1',
  name: 'Default',
  system_prompt: 'You play $color.',
  turn_template: 'PGN: $moves\nFEN: $fen',
  fits: FREE,
  turn_memories: POSITION,
  default_for: defaultsOf(FREE, POSITION),
  saved: false,
  hidden: false,
}
const DESCRIBED: PromptTemplateInfo = {
  ...DEFAULT,
  id: 'described@1',
  name: 'Described',
  turn_template: 'PGN: $moves\nFEN: $fen\n$description',
  default_for: [],
}

/** A probe of 1… e5 asked with the template text given, answered with the move and result given. */
function aProbe(template: Probe['template'], move: string, result: Attempt['result'], reasoning = `Probed ${move}.`): Probe {
  return {
    game_id: 'game-1',
    game_log: 'game.jsonl',
    ply: 2,
    color: 'black',
    pgn: '1. e4',
    fen: AFTER_E4,
    side: afterE5().settings.black as Probe['side'],
    sampling: {},
    template,
    attempt: { ...aTurn(move).attempts[0], san: result === 'legal' ? move : null, result, reasoning, prompt: [] },
    probed_at: '2026-01-01T10:00:00+00:00',
  }
}

const panel = () => screen.getByRole('region', { name: 'Turn' })
const dock = () => screen.getByRole('region', { name: 'Prompt editor' })
const box = () => within(dock()).getByRole('textbox', { name: /System prompt|Turn template/ })
const save = () => within(dock()).getByRole('button', { name: 'Save as new version' })

function renderPanel(probes: Probe[] = []) {
  const backend = fakeBackend()
    .on('GET /api/prompt-templates', Response.json([DEFAULT, DESCRIBED]))
    .on('GET /api/games/game-1/probes', Response.json(probes))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onDock = vi.fn()
  render(
    <QueryClientProvider client={queryClient}>
      <TurnPanel game={afterE5()} ply={2} live onDock={onDock} />
    </QueryClientProvider>,
  )
  return { backend, onDock }
}

/** Opens the dock from the Prompt tab's row, on the template the row names. */
async function openDock(user: ReturnType<typeof userEvent.setup>, name = 'Default') {
  await user.click(within(panel()).getByRole('tab', { name: 'Prompt' }))
  const nameButton = await within(panel()).findByRole('button', { name })
  await waitFor(() => expect(nameButton).toBeEnabled())
  await user.click(nameButton)
  return dock()
}

test("the prompt's name opens the dock on its text, the System prompt / Turn template pill switching the box", async () => {
  const { onDock } = renderPanel()
  const user = userEvent.setup()

  await openDock(user)

  expect(onDock).toHaveBeenLastCalledWith(true)
  expect(within(dock()).getByText('based on Default')).toBeVisible()
  expect(box()).toHaveFocus()
  expect(box()).toHaveAccessibleName('System prompt')
  expect(box()).toHaveValue('You play $color.')
  await user.click(within(dock()).getByRole('button', { name: 'Turn template' }))
  expect(box()).toHaveAccessibleName('Turn template')
  expect(box()).toHaveValue('PGN: $moves\nFEN: $fen')
  expect(within(dock()).getByRole('button', { name: 'Turn template' })).toHaveAttribute('aria-pressed', 'true')
})

test("the dock shows the game's answer and this version's last one, a line each, the Reasoning on hover", async () => {
  renderPanel([aProbe({ ...DEFAULT, id: 'default@1' }, 'Qh4', 'illegal', 'The queen attacks f2.')])
  const user = userEvent.setup()
  await openDock(user)

  const inGame = within(dock()).getByTestId('in-the-game')
  const thisVersion = within(dock()).getByTestId('this-version')
  expect(inGame).toHaveTextContent('In the game: e5 Legal')
  expect(inGame).toHaveAttribute('aria-description', aTurn('e5').reasoning)
  await waitFor(() => expect(thisVersion).toHaveTextContent('This version: Qh4 Illegal'))
  expect(thisVersion).toHaveAttribute('aria-description', 'The queen attacks f2.')

  await user.type(box(), ' Think.')

  expect(within(dock()).getByTestId('this-version')).toHaveTextContent('This version: not tried yet')
})

test('Try in the dock probes the turn with the text as it is, saved or not', async () => {
  const { backend } = renderPanel()
  const user = userEvent.setup()
  await openDock(user)
  const unsaved = { id: null, name: null, system_prompt: 'You play $color. Think.', turn_template: DEFAULT.turn_template }
  backend
    .on('POST /api/games/current/probes', Response.json(aProbe({ ...DEFAULT }, 'd5', 'legal')))
    .on('POST /api/games/current/probes', Response.json(aProbe(unsaved, 'Nf6', 'legal', 'Develop.')))

  await user.click(within(dock()).getByRole('button', { name: 'Try' }))
  await waitFor(() => expect(within(dock()).getByTestId('this-version')).toHaveTextContent('This version: d5 Legal'))
  await user.type(box(), ' Think.')
  await user.click(within(dock()).getByRole('button', { name: 'Try' }))

  await waitFor(() => expect(within(dock()).getByTestId('this-version')).toHaveTextContent('This version: Nf6 Legal'))
  expect(backend.sentTo('POST /api/games/current/probes').map((request) => request.body)).toEqual([
    { ply: 2, color: 'black', prompt_template_id: null }, // the game's own template, unchanged
    { ply: 2, color: 'black', system_prompt: 'You play $color. Think.', turn_template: 'PGN: $moves\nFEN: $fen' },
  ])
})

test('Save as new version is disabled until something changed, and adds a library entry the row then names', async () => {
  const { backend } = renderPanel()
  const user = userEvent.setup()
  await openDock(user)
  expect(save()).toBeDisabled()
  await user.click(within(dock()).getByRole('button', { name: 'Turn template' }))
  await user.type(box(), '\n$description')
  const saved = { ...DESCRIBED, id: 'terse@2', name: 'Terse', turn_template: 'PGN: $moves\nFEN: $fen\n$description' }
  backend
    .on('POST /api/prompt-templates', Response.json(saved))
    .on('GET /api/prompt-templates', Response.json([DEFAULT, DESCRIBED, saved]))

  await user.type(within(dock()).getByRole('textbox', { name: 'Name' }), 'Terse')
  await user.click(save())

  await waitFor(() => expect(within(dock()).getByText('based on Terse')).toBeVisible())
  expect(backend.sentTo('POST /api/prompt-templates')[0].body).toEqual({
    name: 'Terse',
    system_prompt: 'You play $color.',
    turn_template: 'PGN: $moves\nFEN: $fen\n$description',
    llm_constraints: 'free',
  })
  expect(save()).toBeDisabled()
  expect(within(panel()).getByRole('combobox', { name: 'Prompt to try', hidden: true })).toHaveTextContent('Terse')
})

test('a refused save shows the reason, and the text stays to be fixed', async () => {
  const { backend } = renderPanel()
  const user = userEvent.setup()
  await openDock(user)
  await user.type(box(), ' $colour')
  const reason = 'the System prompt has an unknown placeholder: $colour'
  backend.on('POST /api/prompt-templates', Response.json({ detail: reason, code: 'invalid_prompt_template' }, { status: 400 }))

  await user.click(save())

  expect(await within(dock()).findByText(reason)).toBeVisible()
  expect(box()).toHaveValue('You play $color. $colour')
  expect(within(dock()).getByText('based on Default')).toBeVisible()

  await user.type(box(), 's')

  expect(within(dock()).queryByText(reason)).not.toBeInTheDocument() // the reason was about the text before
})

test('closing the dock gives the page back its layout', async () => {
  const { onDock } = renderPanel()
  const user = userEvent.setup()
  await openDock(user)

  await user.click(within(dock()).getByRole('button', { name: 'Close the editor' }))

  expect(screen.queryByRole('region', { name: 'Prompt editor' })).not.toBeInTheDocument()
  expect(onDock).toHaveBeenLastCalledWith(false)
})

test('Esc closes the dock from anywhere in it, and the focus goes back to the name it was opened from', async () => {
  const { onDock } = renderPanel()
  const user = userEvent.setup()
  await openDock(user)
  await user.click(within(dock()).getByRole('button', { name: 'Turn template' }))

  await user.keyboard('{Escape}')

  expect(screen.queryByRole('region', { name: 'Prompt editor' })).not.toBeInTheDocument()
  expect(onDock).toHaveBeenLastCalledWith(false)
  expect(within(panel()).getByRole('button', { name: 'Default' })).toHaveFocus()
})

test('a saved template can be hidden from the dock, its meaning on hover; a default one has no Hide', async () => {
  const terse = { ...DEFAULT, id: 'terse@1', name: 'Terse', default_for: [], saved: true }
  const backend = fakeBackend()
    .on('GET /api/prompt-templates', Response.json([DEFAULT, DESCRIBED, terse]))
    .on('GET /api/games/game-1/probes', Response.json([]))
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TurnPanel game={afterE5()} ply={2} live />
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await openDock(user)
  expect(within(dock()).queryByRole('button', { name: 'Hide' })).not.toBeInTheDocument()
  await user.keyboard('{Escape}')
  await user.click(within(panel()).getByRole('combobox', { name: 'Prompt to try' }))
  await user.click(await screen.findByRole('option', { name: 'Terse' }))
  await openDock(user, 'Terse')
  const hide = within(dock()).getByRole('button', { name: 'Hide' })
  expect(hide).toHaveAttribute('aria-description', expect.stringContaining('Leave Terse out of the Prompt pickers'))
  backend
    .on('POST /api/prompt-templates/terse%401/hide', Response.json({ ...terse, hidden: true }))
    .on('GET /api/prompt-templates', Response.json([DEFAULT, DESCRIBED]))

  await user.click(hide)

  expect(await within(dock()).findByText('based on Terse (hidden)')).toBeVisible()
  expect(within(dock()).queryByRole('button', { name: 'Hide' })).not.toBeInTheDocument()
  expect(backend.sentTo('POST /api/prompt-templates/terse%401/hide')).toHaveLength(1)
})

test('the name of a template the library no longer lists opens the dock on that template, fetched by its ID', async () => {
  const user = userEvent.setup()
  const old = { ...DEFAULT, id: 'default@0', system_prompt: 'You played $color.' }
  fakeBackend()
    .on('GET /api/prompt-templates', Response.json([DEFAULT, DESCRIBED]))
    .on('GET /api/games/game-1/probes', Response.json([]))
    .on('GET /api/prompt-templates/default%400', Response.json(old))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TurnPanel game={afterE5({ prompt_template_ids: { black: 'default@0' } })} ply={2} live />
    </QueryClientProvider>,
  )

  await openDock(user, 'default@0')

  expect(await within(dock()).findByText('based on Default')).toBeVisible()
  expect(box()).toHaveValue('You played $color.')
})
