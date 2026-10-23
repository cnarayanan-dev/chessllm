import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test } from 'vitest'
import type { Attempt, GameState, Probe, PromptTemplateInfo } from '@/api/types'
import { TurnPanel } from '@/components/turn/TurnPanel'
import { setPromptLabOn } from '@/settings/promptLab'
import { fakeBackend, later } from '@/test/fakeBackend'
import { AFTER_E4, aTurn, afterE5, E4, E5, NC6, NF3, plies } from '@/test/games'
import { defaultsOf, FREE, LISTED, POSITION } from '@/test/promptLibrary'

beforeEach(() => localStorage.clear())

const template = (
  id: string,
  name: string | null,
  fits: PromptTemplateInfo['fits'],
  isDefault = false,
  turn_memories = POSITION,
) => ({
  id,
  name,
  system_prompt: 'You play $color.',
  turn_template: fits === LISTED ? '$moves $legal_moves' : '$moves',
  fits,
  turn_memories,
  default_for: isDefault ? defaultsOf(fits, turn_memories) : [],
  saved: false,
  hidden: false,
})
const library: PromptTemplateInfo[] = [
  template('default@1', 'Default', FREE, true),
  template('described@1', 'Described', FREE),
  template('moves@1', 'Moves', FREE, true, ['chat_moves']),
  template('default-listed@1', 'Default listed', LISTED, true),
]

const PROMPT = [
  { role: 'system', content: 'You play Black.' },
  { role: 'user', content: 'PGN: 1. e4' },
] as const

/** A probe of 1… e5 with the template given, answered with the move and result given. */
function aProbe(templateId: string, move: string, result: Attempt['result'], reasoning = `Probed ${move}.`): Probe {
  const [name] = library.filter((entry) => entry.id === templateId).map((entry) => entry.name)
  return {
    game_id: 'game-1',
    game_log: 'game.jsonl',
    ply: 2,
    color: 'black',
    pgn: '1. e4',
    fen: AFTER_E4,
    side: afterE5().settings.black as Probe['side'],
    sampling: {},
    template: { id: templateId, name, system_prompt: 'You play $color.', turn_template: '$moves' },
    attempt: {
      ...aTurn(move).attempts[0],
      san: result === 'legal' ? move : null,
      result,
      reasoning,
      latency_s: 2.5,
      prompt: [...PROMPT],
    },
    probed_at: '2026-01-01T10:00:00+00:00',
  }
}

const panel = () => screen.getByRole('region', { name: 'Turn' })
const tab = (name: string) => within(panel()).getByRole('tab', { name })
const tryButton = () => within(panel()).getByRole('button', { name: 'Try' })
const picker = () => within(panel()).getByRole('combobox', { name: 'Prompt to try' })
const probeList = () => within(panel()).getByRole('list', { name: 'Probes' })

type Given = { game?: GameState; ply?: number; listed?: Response }

function renderPanel(tryBlocked?: string, probes: Probe[] = [], { game = afterE5(), ply = 2, listed }: Given = {}) {
  const backend = fakeBackend()
    .on('GET /api/prompt-templates', listed ?? Response.json(library))
    .on(`GET /api/games/${game.game_id}/probes`, Response.json(probes))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const panelOf = (shown: GameState, at: number) => (
    <QueryClientProvider client={queryClient}>
      <TurnPanel game={shown} ply={at} live tryBlocked={tryBlocked} />
    </QueryClientProvider>
  )
  const { rerender } = render(panelOf(game, ply))
  return { backend, queryClient, show: (shown: GameState, at: number) => rerender(panelOf(shown, at)) }
}

/** 1. e4 e5 2. Nf3 Nc6, the LLM's e5 and Nc6. */
const twoMovesIn = () =>
  afterE5({ plies: plies(E4, E5, NF3, NC6), llm_turns: [aTurn('e5'), aTurn('Nc6', { ply: 4 })] })

test('with Prompt lab off, the Prompt tab is as before: no Prompt row, no Try', async () => {
  const { backend } = renderPanel()

  await userEvent.click(tab('Prompt'))

  expect(within(panel()).queryByRole('button', { name: 'Try' })).not.toBeInTheDocument()
  expect(within(panel()).queryByRole('combobox')).not.toBeInTheDocument()
  expect(backend.sent).toEqual([])
})

describe('with Prompt lab on', () => {
  beforeEach(() => setPromptLabOn(true))

  test("the Prompt tab's row names the game's own template, the library listing the templates that fit", async () => {
    renderPanel()
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    await user.click(picker())
    const options = (await screen.findAllByRole('option')).map((option) => option.textContent)
    expect(options).toEqual(['Default (in the game)', 'Described'])
  })

  test('a Probe is a fresh prompt: for a side under chat with moves, its Moves template is not offered', async () => {
    const game = afterE5()
    const side = { ...(game.settings.black as Probe['side']), turn_memory: 'chat_moves' as const }
    const chatting = { ...game, settings: { ...game.settings, black: side }, prompt_template_ids: { black: 'moves@1' } }
    const { backend } = renderPanel(undefined, [], { game: chatting })
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    await user.click(picker())
    expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toEqual(['Default', 'Described'])
    await user.keyboard('{Escape}')
    backend.on('POST /api/games/current/probes', Response.json(aProbe('default@1', 'e5', 'legal')))
    await user.click(tryButton())
    // By no ID, as the game's own: the backend asks with the fresh Default, the one picked.
    expect(backend.sentTo('POST /api/games/current/probes')).toMatchObject([
      { body: { ply: 2, color: 'black', prompt_template_id: null } },
    ])
  })

  test("Try probes the turn shown with the template picked, and shows the probe's result under the row", async () => {
    const { backend } = renderPanel()
    const user = userEvent.setup()
    await user.click(tab('Prompt'))
    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    await user.click(picker())
    await user.click(await screen.findByRole('option', { name: 'Described' }))
    const answer = later()
    backend.on('POST /api/games/current/probes', answer.promise)

    await user.click(tryButton())

    expect(backend.sentTo('POST /api/games/current/probes')).toEqual([
      { method: 'POST', path: '/api/games/current/probes', body: { ply: 2, color: 'black', prompt_template_id: 'described@1' } },
    ])
    await waitFor(() => expect(tryButton()).toBeDisabled())
    answer.resolve(Response.json(aProbe('described@1', 'Qh4', 'illegal')))

    const probe = within(await within(panel()).findByRole('list', { name: 'Probes' })).getByRole('listitem')
    expect(probe).toHaveTextContent('Qh4')
    expect(probe).toHaveTextContent('Illegal')
    expect(probe).toHaveTextContent('Described')
    expect(probe).toHaveTextContent('2.5 s')
    expect(within(panel()).getByTestId('probe-tally')).toHaveTextContent('Described: 0 of 1 legal')
    expect(tryButton()).toBeEnabled()
  })

  test("a reopened turn lists its probes again, a tally per template, each opening on its Reasoning and Prompt", async () => {
    const probes = [
      aProbe('default@1', 'e5', 'legal'),
      aProbe('described@1', 'Qh4', 'illegal', 'The queen attacks f2.'),
      aProbe('described@1', 'd5', 'legal'),
      { ...aProbe('default@1', 'Nf3', 'legal'), ply: 4 }, // another turn's
    ]
    renderPanel(undefined, probes)
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    await waitFor(() => expect(within(probeList()).getAllByRole('listitem')).toHaveLength(3))
    expect(within(panel()).getByTestId('probe-tally')).toHaveTextContent('Default: 1 of 1 legal')
    expect(within(panel()).getByTestId('probe-tally')).toHaveTextContent('Described: 1 of 2 legal')
    expect(within(panel()).queryByText('The queen attacks f2.')).not.toBeInTheDocument()

    await user.click(within(probeList()).getByRole('button', { name: /Qh4/ }))

    expect(within(panel()).getByText('The queen attacks f2.')).toBeVisible()
    expect(within(probeList()).getByText('PGN: 1. e4')).toBeVisible()
  })

  test('Try is disabled while an LLM turn runs, the reason on hover', async () => {
    renderPanel('An LLM turn is running. Try once it has ended.')
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    expect(tryButton()).toBeDisabled()
    expect(tryButton()).toHaveAttribute('aria-description', 'An LLM turn is running. Try once it has ended.')
  })

  test('a refused probe says why', async () => {
    const { backend } = renderPanel()
    const user = userEvent.setup()
    await user.click(tab('Prompt'))
    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    backend.on(
      'POST /api/games/current/probes',
      Response.json({ detail: 'an LLM turn is running', code: 'llm_turn_running' }, { status: 409 }),
    )

    await user.click(tryButton())

    expect(await within(panel()).findByText('an LLM turn is running')).toBeVisible()
  })

  test("Try with the game's own template asks for it by no ID: the backend uses the text the game recorded", async () => {
    const { backend } = renderPanel()
    const user = userEvent.setup()
    await user.click(tab('Prompt'))
    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    backend.on('POST /api/games/current/probes', Response.json(aProbe('default@1', 'd5', 'legal')))

    await user.click(tryButton())

    expect(backend.sentTo('POST /api/games/current/probes')[0].body).toEqual({ ply: 2, color: 'black', prompt_template_id: null })
  })

  test("a version the library no longer has is still the game's, marked by its ID, and can be tried", async () => {
    const game = afterE5({ prompt_template_ids: { black: 'default@0' } })
    const { backend } = renderPanel(undefined, [], { game })
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    await waitFor(() => expect(picker()).toHaveTextContent('default@0'))
    await user.click(picker())
    const options = (await screen.findAllByRole('option')).map((option) => option.textContent)
    expect(options).toEqual(['default@0 (in the game)', 'Default', 'Described'])
    await user.keyboard('{Escape}')
    backend.on('POST /api/games/current/probes', Response.json(aProbe('default@1', 'd5', 'legal')))
    await user.click(tryButton())
    expect(backend.sentTo('POST /api/games/current/probes')[0].body).toMatchObject({ prompt_template_id: null })
  })

  test("when the library can't be loaded it says so, and Try still asks with the game's own template", async () => {
    const listed = Response.json({ detail: 'the library is broken', code: 'error' }, { status: 500 })
    renderPanel(undefined, [], { listed })
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    expect(await within(panel()).findByText(/the library is broken/)).toBeVisible()
    expect(picker()).toHaveTextContent('default@1')
    expect(tryButton()).toBeEnabled()
  })

  test("when the library can't be loaded, a side under chat with moves is still probed, with the fresh Default", async () => {
    const game = afterE5()
    const side = { ...(game.settings.black as Probe['side']), turn_memory: 'chat_moves' as const }
    const chatting = { ...game, settings: { ...game.settings, black: side }, prompt_template_ids: { black: 'moves@1' } }
    const listed = Response.json({ detail: 'the library is broken', code: 'error' }, { status: 500 })
    const { backend } = renderPanel(undefined, [], { game: chatting, listed })
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    expect(await within(panel()).findByText(/the library is broken/)).toBeVisible()
    expect(picker()).toHaveTextContent('Default')
    expect(picker()).not.toHaveTextContent('moves@1')
    backend.on('POST /api/games/current/probes', Response.json(aProbe('default@1', 'e5', 'legal')))
    await user.click(tryButton())
    // No ID: the backend asks with the fresh Default of the side's LLM constraints.
    expect(backend.sentTo('POST /api/games/current/probes')).toMatchObject([
      { body: { ply: 2, color: 'black', prompt_template_id: null } },
    ])
  })

  test("a probe's error and its wait belong to the turn asked, not to the turn stepped to", async () => {
    const game = twoMovesIn()
    const { backend, show } = renderPanel(undefined, [], { game, ply: 4 })
    const user = userEvent.setup()
    await user.click(tab('Prompt'))
    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    const answer = later()
    backend.on('POST /api/games/current/probes', answer.promise)
    await user.click(tryButton())
    await waitFor(() => expect(tryButton()).toBeDisabled())

    show(game, 2)
    await waitFor(() => expect(tryButton()).toBeEnabled())
    answer.resolve(Response.json({ detail: 'the LLM is gone', code: 'error' }, { status: 409 }))
    show(game, 4)
    expect(await within(panel()).findByText('the LLM is gone')).toBeVisible()
    show(game, 2)

    expect(within(panel()).queryByText('the LLM is gone')).not.toBeInTheDocument()
  })

  test('a probe lands in the game it was asked in, even if another game is shown when it answers', async () => {
    const { backend, queryClient, show } = renderPanel()
    const user = userEvent.setup()
    await user.click(tab('Prompt'))
    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    const answer = later()
    backend.on('POST /api/games/current/probes', answer.promise).on('GET /api/games/game-2/probes', Response.json([]))
    await user.click(tryButton())

    show(afterE5({ game_id: 'game-2' }), 2)
    await act(async () => answer.resolve(Response.json(aProbe('default@1', 'd5', 'legal'))))

    await waitFor(() => expect(queryClient.getQueryData(['probes', 'game-1'])).toHaveLength(1))
    expect(queryClient.getQueryData(['probes', 'game-2'])).toEqual([])
  })

  test('a probe answered with a Notation slip is shown as one, and the tally counts it apart', async () => {
    const slip = { ...aProbe('default@1', 'e7e5', 'legal'), attempt: { ...aProbe('default@1', 'e7e5', 'legal').attempt, san: 'e5', notation_slip: true } }
    renderPanel(undefined, [slip, aProbe('default@1', 'd5', 'legal')])
    const user = userEvent.setup()
    await user.click(tab('Prompt'))

    await waitFor(() => expect(within(probeList()).getAllByRole('listitem')).toHaveLength(2))
    expect(within(probeList()).getAllByRole('listitem')[0]).toHaveTextContent('written "e7e5"')
    expect(within(panel()).getByTestId('probe-tally')).toHaveTextContent('Default: 2 of 2 legal (1 slip)')
  })
})
