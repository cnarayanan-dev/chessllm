import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import type { GameSettings, ModelInfo, NewGame, SideValues } from '@/settings/next-game'
import { nextGameFrom } from '@/settings/next-game'
import { SettingsButton, SettingsModal } from '@/settings/SettingsModal'

const qwen: ModelInfo = { name: 'qwen3.5:9b', thinking: true, sampling: { temperature: 0.6, top_k: 40 } }
const gemma: ModelInfo = { name: 'gemma3:4b', thinking: false, sampling: {} }
const llama: ModelInfo = { name: 'llama3:8b', thinking: false, sampling: null }

const llm = (model: string, more: Partial<SideValues> = {}) => ({
  player: 'llm' as const,
  model,
  thinking: false,
  llm_constraints: 'free' as const,
  retry_feedback: 'explained' as const,
  ...more,
})

const playLlm: GameSettings = {
  mode: 'play_llm',
  white: { player: 'human' },
  black: llm('qwen3.5:9b', { thinking: true }),
  sampling: {},
  rules: 'standard',
}

const faceoff: GameSettings = {
  mode: 'llm_faceoff',
  white: llm('qwen3.5:9b'),
  black: llm('qwen3.5:9b'),
  sampling: {},
  rules: 'standard',
}

/** The modal as the page holds it: the next game and whether the modal is open, with the running game's settings. */
function Page({ running, onStartNext }: { running: GameSettings; onStartNext: (request: NewGame) => void }) {
  const [open, setOpen] = useState(false)
  const [next, setNext] = useState(() => nextGameFrom(running))
  return (
    <>
      <SettingsButton onClick={() => setOpen(true)} />
      <SettingsModal
        open={open}
        onOpenChange={setOpen}
        running={running}
        next={next}
        onNextChange={setNext}
        onStartNext={onStartNext}
      />
    </>
  )
}

function stubModels(response: () => Response) {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(response()))
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function renderPage(running = playLlm) {
  const onStartNext = vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <Page running={running} onStartNext={onStartNext} />
    </QueryClientProvider>,
  )
  return { onStartNext, user: userEvent.setup() }
}

async function openSettings(running = playLlm) {
  const page = renderPage(running)
  await page.user.keyboard('{Meta>}k{/Meta}')
  const dialog = await screen.findByRole('dialog', { name: 'Settings' })
  return { ...page, dialog }
}

const radio = (name: string | RegExp) => screen.getByRole('radio', { name })
const radiosIn = (group: string) => within(screen.getByRole('radiogroup', { name: group })).getAllByRole('radio')

beforeEach(() => {
  localStorage.clear()
  stubModels(() => Response.json([qwen, gemma, llama]))
})

describe('opening and closing', () => {
  test('⌘K opens the modal and closes it again', async () => {
    const { user } = renderPage()

    await user.keyboard('{Meta>}k{/Meta}')
    expect(await screen.findByRole('dialog', { name: 'Settings' })).toBeInTheDocument()

    await user.keyboard('{Meta>}k{/Meta}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('Ctrl+K opens it too, and Escape closes it', async () => {
    const { user } = renderPage()

    await user.keyboard('{Control>}k{/Control}')
    expect(await screen.findByRole('dialog', { name: 'Settings' })).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('the settings button opens it', async () => {
    const { user } = renderPage()

    await user.click(screen.getByRole('button', { name: /Settings/ }))

    expect(await screen.findByRole('dialog', { name: 'Settings' })).toBeInTheDocument()
  })

  test('the models are listed afresh each time it opens', async () => {
    const fetch = stubModels(() => Response.json([qwen]))
    const { user } = renderPage()

    await user.keyboard('{Meta>}k{/Meta}')
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    await user.keyboard('{Meta>}k{/Meta}')
    await user.keyboard('{Meta>}k{/Meta}')

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch).toHaveBeenCalledWith('/api/models')
  })
})

describe('changes apply to the next game', () => {
  test('none pending: only the note', async () => {
    await openSettings()

    expect(screen.getByText('Changes apply when you start a new game.')).toBeInTheDocument()
    expect(screen.queryByText('changes apply next game')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start new game' })).not.toBeInTheDocument()
  })

  test('a change is pending, and "Start new game" starts the next game with it and closes the modal', async () => {
    const { user, onStartNext } = await openSettings()

    await user.click(radio(/^Black/))
    expect(screen.getByText('changes apply next game')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start new game' }))

    expect(onStartNext).toHaveBeenCalledWith({
      mode: 'play_llm',
      rules: 'standard',
      white: llm('qwen3.5:9b', { thinking: true }),
      black: { player: 'human' },
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('changes are kept when the modal closes and opens again', async () => {
    const { user } = await openSettings()

    await user.click(radio(/^Hinted/))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await user.keyboard('{Meta>}k{/Meta}')

    expect(await screen.findByRole('radio', { name: /^Hinted/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('changes apply next game')).toBeInTheDocument()
  })
})

describe('Game section', () => {
  test('offers the Modes, Play LLM the default, and in Play LLM the human picks a colour', async () => {
    await openSettings()

    expect(radiosIn('Mode').map((card) => card.textContent)).toEqual([
      expect.stringMatching(/^Play LLMdefault/),
      expect.stringMatching(/^LLM faceoff/),
    ])
    expect(radio(/^Play LLM/)).toHaveAttribute('aria-checked', 'true')
    expect(radio(/^White/)).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('The LLM plays the other colour. White moves first.')).toBeInTheDocument()
    expect(screen.queryByText('Players')).not.toBeInTheDocument()
    expect(screen.queryByRole('switch', { name: 'Customize per LLM' })).not.toBeInTheDocument()
  })

  test('an LLM faceoff offers a model per side, swapped with ⇄, and Customize per LLM', async () => {
    const { user, onStartNext } = await openSettings({
      ...faceoff,
      white: llm('qwen3.5:9b'),
      black: llm('gemma3:4b'),
    })

    expect(screen.queryByText('Your colour')).not.toBeInTheDocument()
    expect(screen.getByText('A model for each side. The same model can play itself.')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'White model' })).toHaveTextContent('qwen3.5:9b')
    expect(screen.getByRole('combobox', { name: 'Black model' })).toHaveTextContent('gemma3:4b')

    await user.click(screen.getByRole('button', { name: 'Swap colours' }))
    expect(screen.getByRole('combobox', { name: 'White model' })).toHaveTextContent('gemma3:4b')

    expect(screen.getByRole('switch', { name: 'Customize per LLM' })).toHaveAttribute('aria-checked', 'false')
    await user.click(screen.getByRole('button', { name: 'Start new game' }))
    expect(onStartNext).toHaveBeenCalledWith({
      mode: 'llm_faceoff',
      rules: 'standard',
      white: llm('gemma3:4b'),
      black: llm('qwen3.5:9b'),
    })
  })

  test('picking a model for a side', async () => {
    const { user, onStartNext } = await openSettings(faceoff)

    await user.click(screen.getByRole('combobox', { name: 'Black model' }))
    await user.click(await screen.findByRole('option', { name: 'llama3:8b' }))
    await user.click(screen.getByRole('button', { name: 'Start new game' }))

    expect(onStartNext).toHaveBeenCalledWith({
      mode: 'llm_faceoff',
      rules: 'standard',
      white: llm('qwen3.5:9b'),
      black: llm('llama3:8b'),
    })
  })

  test('the LLM constraints and Retry feedback, each with its default', async () => {
    await openSettings()

    expect(radiosIn('LLM constraints').map((card) => card.textContent)).toEqual([
      expect.stringMatching(/^Freedefault/),
      expect.stringMatching(/^Listed/),
      expect.stringMatching(/^Blind enforced/),
      expect.stringMatching(/^Listed enforced/),
    ])
    expect(radiosIn('Retry feedback').map((card) => card.textContent)).toEqual([
      expect.stringMatching(/^Explaineddefault/),
      expect.stringMatching(/^Bare/),
      expect.stringMatching(/^Hinted/),
    ])
    expect(screen.getByText('What the LLM is told after an illegal move. It gets 3 retries, then forfeits.'))
      .toBeInTheDocument()
  })

  test.each(['Blind enforced', 'Listed enforced'])('%s greys out Retry feedback', async (constraints) => {
    const { user } = await openSettings()

    await user.click(radio(new RegExp(`^${constraints}`)))

    for (const card of radiosIn('Retry feedback')) expect(card).toHaveAttribute('data-disabled')
    expect(screen.getByText("No effect: under Enforced decoding the LLM can't play an illegal move."))
      .toBeInTheDocument()
  })

  test('customized, an enforced side greys out its own Retry feedback only', async () => {
    await openSettings({ ...faceoff, black: llm('qwen3.5:9b', { llm_constraints: 'listed_enforced' }) })

    expect(screen.getAllByText(/^♔ White · qwen3.5:9b|^♚ Black · qwen3.5:9b/)).toHaveLength(4)
    const [white, black] = screen.getAllByRole('radiogroup', { name: 'Retry feedback' })
    for (const card of within(white).getAllByRole('radio')) expect(card).not.toHaveAttribute('data-disabled')
    for (const card of within(black).getAllByRole('radio')) expect(card).toHaveAttribute('data-disabled')
    expect(screen.getByText(/No effect for Black: under Enforced decoding it can't play an illegal move\./))
      .toBeInTheDocument()
  })

  test('Customize per LLM on splits the settings into White and Black, off gives both White\'s again', async () => {
    const { user, onStartNext } = await openSettings(faceoff)

    await user.click(screen.getByRole('switch', { name: 'Customize per LLM' }))
    expect(screen.getAllByRole('radiogroup', { name: 'LLM constraints' })).toHaveLength(2)
    const [, black] = screen.getAllByRole('radiogroup', { name: 'LLM constraints' })
    await user.click(within(black).getByRole('radio', { name: /^Listed$|^Listed[^ ]/ }))
    await user.click(screen.getByRole('button', { name: 'Start new game' }))
    expect(onStartNext).toHaveBeenLastCalledWith({
      mode: 'llm_faceoff',
      rules: 'standard',
      white: llm('qwen3.5:9b'),
      black: llm('qwen3.5:9b', { llm_constraints: 'listed' }),
    })

    await user.keyboard('{Meta>}k{/Meta}')
    await user.click(await screen.findByRole('switch', { name: 'Customize per LLM' }))
    expect(screen.getAllByRole('radiogroup', { name: 'LLM constraints' })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Start new game' })).not.toBeInTheDocument()
  })

  test('the Chaos rules switch, off by default, starts the next game under Chaos rules', async () => {
    const { user, onStartNext } = await openSettings()
    const chaos = screen.getByRole('switch', { name: 'Chaos rules' })

    expect(chaos).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText(/The LLM's illegal moves are played on the board/)).toBeInTheDocument()
    await user.click(chaos)
    expect(chaos).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('changes apply next game')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start new game' }))

    expect(onStartNext).toHaveBeenCalledWith(expect.objectContaining({ mode: 'play_llm', rules: 'chaos' }))
  })

  test('a running Chaos rules game shows the switch on', async () => {
    await openSettings({ ...playLlm, rules: 'chaos' })

    expect(screen.getByRole('switch', { name: 'Chaos rules' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByText('changes apply next game')).not.toBeInTheDocument()
  })

  test.each(['Blind enforced', 'Listed enforced'])('%s disables Chaos rules, with a hint why', async (constraints) => {
    const { user } = await openSettings({ ...playLlm, rules: 'chaos' })

    await user.click(radio(new RegExp(`^${constraints}`)))

    const chaos = screen.getByRole('switch', { name: 'Chaos rules' })
    expect(chaos).toHaveAttribute('aria-checked', 'false')
    expect(chaos).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText(/Only under Free or Listed: under Enforced decoding the LLM can't play an illegal move\./))
      .toBeInTheDocument()
  })

  test('customized, one enforced LLM disables Chaos rules, naming its side', async () => {
    const { user, onStartNext } = await openSettings({
      ...faceoff,
      black: llm('qwen3.5:9b', { llm_constraints: 'listed_enforced' }),
    })

    const chaos = screen.getByRole('switch', { name: 'Chaos rules' })
    expect(chaos).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText(/Only when every LLM plays under Free or Listed: Black plays under Listed enforced\./))
      .toBeInTheDocument()

    const [, black] = screen.getAllByRole('radiogroup', { name: 'LLM constraints' })
    await user.click(within(black).getByRole('radio', { name: /^Free/ }))
    await user.click(chaos)
    await user.click(screen.getByRole('button', { name: 'Start new game' }))

    expect(onStartNext).toHaveBeenCalledWith(expect.objectContaining({ mode: 'llm_faceoff', rules: 'chaos' }))
  })

  test('the Move sound switch is kept in this browser', async () => {
    const { user } = await openSettings()
    const sound = screen.getByRole('switch', { name: 'Move sound' })

    expect(sound).toHaveAttribute('aria-checked', 'true')
    await user.click(sound)

    expect(sound).toHaveAttribute('aria-checked', 'false')
    expect(localStorage.getItem('chessllm.moveSound')).toBe('off')
    expect(screen.queryByText('changes apply next game')).not.toBeInTheDocument()
  })
})

describe('Model section', () => {
  async function openModel(running = playLlm) {
    const page = await openSettings(running)
    await page.user.click(screen.getByRole('button', { name: /Model/ }))
    return page
  }

  test('the model select lists the models, with the hint', async () => {
    const { user } = await openModel()

    expect(await screen.findByText('The models in chessllm/models.py')).toBeInTheDocument()
    await user.click(screen.getByRole('combobox', { name: 'Model' }))
    expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toEqual([
      'qwen3.5:9b',
      'gemma3:4b',
      'llama3:8b',
    ])
  })

  test('says why when the models cannot be listed, and keeps the chosen model', async () => {
    stubModels(() => Response.json({ detail: 'Ollama is not running' }, { status: 503 }))
    await openModel()

    expect(await screen.findByText('Could not list the models: Ollama is not running')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Model' })).toHaveTextContent('qwen3.5:9b')
  })

  test('the thinking switch, with its hint, when the model can think', async () => {
    await openModel()
    await screen.findByText('The models in chessllm/models.py')

    expect(screen.getByRole('switch', { name: 'Thinking' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('switch', { name: 'Thinking' })).not.toHaveAttribute('data-disabled')
    expect(screen.getByText(
      'The model reasons before answering. Slower, likely stronger play. The thinking text is saved to the game log.',
    )).toBeInTheDocument()
  })

  test("a model that can't think: the switch is off and disabled, with the hint", async () => {
    const { user, onStartNext } = await openModel()
    await screen.findByText('The models in chessllm/models.py')

    await user.click(screen.getByRole('combobox', { name: 'Model' }))
    await user.click(await screen.findByRole('option', { name: 'gemma3:4b' }))

    expect(screen.getByRole('switch', { name: 'Thinking' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('switch', { name: 'Thinking' })).toHaveAttribute('data-disabled')
    expect(screen.getByText("gemma3:4b can't think: it reasons in its answer instead, before the move."))
      .toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start new game' }))
    expect(onStartNext).toHaveBeenCalledWith({
      mode: 'play_llm',
      rules: 'standard',
      white: { player: 'human' },
      black: llm('gemma3:4b'),
    })
  })

  test('shared thinking in a faceoff only when both models can think, with a hint to customize otherwise', async () => {
    await openModel({ ...faceoff, black: llm('gemma3:4b') })
    await screen.findByText(/Shared by both LLMs/)

    expect(screen.queryByRole('combobox', { name: 'Model' })).not.toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Thinking' })).toHaveAttribute('data-disabled')
    expect(screen.getByText(
      "Shared by both LLMs, so only on when both can think: gemma3:4b can't. It reasons in its answer instead, before the move.",
    )).toBeInTheDocument()
  })

  test('customized, thinking per side', async () => {
    const { user, onStartNext } = await openModel({
      ...faceoff,
      black: llm('gemma3:4b', { retry_feedback: 'bare' }),
    })
    await screen.findByText('gemma3:4b can\'t think: it reasons in its answer instead, before the move.')

    expect(screen.queryByRole('switch', { name: 'Thinking' })).not.toBeInTheDocument()
    expect(screen.getByText('qwen3.5:9b reasons before answering. Slower, likely stronger play.')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Black thinking' })).toHaveAttribute('data-disabled')
    await user.click(screen.getByRole('switch', { name: 'White thinking' }))
    await user.click(screen.getByRole('button', { name: 'Start new game' }))

    expect(onStartNext).toHaveBeenCalledWith({
      mode: 'llm_faceoff',
      rules: 'standard',
      white: llm('qwen3.5:9b', { thinking: true }),
      black: llm('gemma3:4b', { retry_feedback: 'bare' }),
    })
  })
})

describe('Advanced section: the sampling, read-only', () => {
  async function openAdvanced(running = playLlm) {
    const page = await openSettings(running)
    await page.user.click(screen.getByRole('button', { name: /Advanced/ }))
    return page
  }

  test("the LLM's sampling, from /api/models", async () => {
    await openAdvanced()

    expect(await screen.findByText(
      'Sampling for qwen3.5:9b: the model\'s defaults, overridden by chessllm/sampling.toml. Change them in that file.',
    )).toBeInTheDocument()
    const rows = screen.getAllByRole('row').map((row) => row.textContent)
    expect(rows).toEqual(['temperature0.6', 'top_k40'])
  })

  test('each model named in a faceoff, and a model with no parameters set says so', async () => {
    await openAdvanced({ ...faceoff, black: llm('gemma3:4b') })

    await screen.findByText(/^Sampling for qwen3.5:9b and gemma3:4b/)
    expect(screen.getAllByRole('row').map((row) => row.textContent)).toEqual([
      'qwen3.5:9b',
      'temperature0.6',
      'top_k40',
      'gemma3:4b',
      "No sampling parameters set: Ollama's built-in defaults",
    ])
  })

  test('Ollama could not show the model', async () => {
    await openAdvanced({ ...playLlm, black: llm('llama3:8b') })

    expect(await screen.findByText('Ollama could not show llama3:8b. Is it installed, and is Ollama running?'))
      .toBeInTheDocument()
  })
})
