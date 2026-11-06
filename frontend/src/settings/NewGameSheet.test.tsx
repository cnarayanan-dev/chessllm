import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import type { PromptTemplateInfo } from '@/api/types'
import type { GameSettings, ModelInfo, NextGame, SideValues } from '@/settings/next-game'
import { newGameRequest, nextGameFrom } from '@/settings/next-game'
import { NewGameSheet } from '@/settings/NewGameSheet'
import { setPromptLabOn } from '@/settings/promptLab'

const qwen: ModelInfo = { name: 'qwen3.5:9b', thinking: true, sampling: { temperature: 0.6, top_k: 40 } }
const gemma: ModelInfo = { name: 'gemma3:4b', thinking: false, sampling: {} }
const llama: ModelInfo = { name: 'llama3:8b', thinking: false, sampling: null }
const models = [qwen, gemma, llama]

const llm = (model: string, more: Partial<SideValues> = {}) => ({
  player: 'llm' as const,
  model,
  thinking: false,
  llm_constraints: 'free' as const,
  retry_feedback: 'explained' as const,
  turn_memory: 'fresh' as const,
  ...more,
})

const playLlm: GameSettings = {
  mode: 'play_llm',
  white: { player: 'human' },
  black: llm('qwen3.5:9b', { thinking: true }),
  sampling: {},
  rules: 'standard',
  max_attempts: 5,
}

const faceoff: GameSettings = {
  mode: 'llm_faceoff',
  white: llm('qwen3.5:9b'),
  black: llm('qwen3.5:9b'),
  sampling: {},
  rules: 'standard',
  max_attempts: 5,
}

/** The sheet as the page holds it: a New game button opens it, with the last game's settings each time. */
function Page({ last, onStart }: { last: GameSettings; onStart: (next: NextGame) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        New game
      </button>
      <NewGameSheet open={open} onOpenChange={setOpen} initial={nextGameFrom(last)} onStart={onStart} />
    </>
  )
}

const FREE: PromptTemplateInfo['fits'] = ['free', 'blind_enforced']
const LISTED: PromptTemplateInfo['fits'] = ['listed', 'listed_enforced']
const SHOWN: PromptTemplateInfo['turn_memories'] = ['fresh', 'chat_position']
const template = (
  id: string,
  name: string | null,
  fits: PromptTemplateInfo['fits'],
  isDefault = false,
  turn_memories: PromptTemplateInfo['turn_memories'] = SHOWN,
) => ({
  id,
  name,
  system_prompt: 'You play $color.',
  turn_template: fits === LISTED ? '$moves $legal_moves' : '$moves',
  fits,
  turn_memories,
  default_for: isDefault ? fits : [],
  saved: !id.includes('default') && !id.includes('described'),
})
/**
 * The Prompt library as GET /api/prompt-templates lists it: the defaults, Moves for Chat with moves alone, then a
 * saved template without a name, which fits every Turn memory.
 */
const library: PromptTemplateInfo[] = [
  template('default@1', 'Default', FREE, true),
  template('described@1', 'Described', FREE),
  template('moves@1', 'Moves', FREE, true, ['chat_moves']),
  template('default-listed@1', 'Default listed', LISTED, true),
  template('described-listed@1', 'Described listed', LISTED),
  template('moves-listed@1', 'Moves listed', LISTED, true, ['chat_moves']),
  template('terse@1', null, FREE, false, ['fresh', 'chat_position', 'chat_moves']),
]

/** The Prompt templates a System 1 model can play with, as GET /api/system1/options lists them. */
const system1Templates = [
  { id: 'system1@a1', name: 'System 1', system_prompt: 'Which move should $color play?', turn_template: '$moves' },
  { id: 'system1-position-only@b2', name: 'Position only', system_prompt: 'Which move?', turn_template: '$fen' },
]

/** Stubs the models' response; the Prompt library answers with `library`. */
function stubModels(response: () => Response) {
  const fetch = vi.fn().mockImplementation((path: string) => {
    if (path === '/api/prompt-templates') return Promise.resolve(Response.json(library))
    if (path === '/api/system1/options')
      return Promise.resolve(Response.json({ default_url: 'http://localhost:11434', models: [], templates: system1Templates }))
    return Promise.resolve(response())
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

async function openSheet(last = playLlm) {
  const onStart = vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <Page last={last} onStart={onStart} />
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'New game' }))
  const sheet = await screen.findByRole('dialog', { name: 'New game' })
  /** The game the sheet started, as the request the page sends. */
  const started = () => {
    expect(onStart).toHaveBeenCalledOnce()
    return newGameRequest(onStart.mock.calls[0][0], models)
  }
  return { user, sheet, onStart, started }
}

const radio = (name: string | RegExp) => screen.getByRole('radio', { name })
const radiosIn = (group: string) =>
  within(screen.getByRole('radiogroup', { name: group }))
    .getAllByRole('radio')
    .map((card) => card.textContent)
/** The open Tooltip, once it shows. */
const tooltip = () =>
  waitFor(() => {
    const content = document.querySelector('[data-slot=tooltip-content]')
    expect(content).toBeInTheDocument()
    return content
  })
async function openAdvanced(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Advanced settings' }))
  await screen.findByRole('radiogroup', { name: 'What the LLM is given' })
}

beforeEach(() => {
  localStorage.clear()
  stubModels(() => Response.json(models))
})

describe('opening and closing', () => {
  test("opens with the last game's settings, Advanced settings closed", async () => {
    await openSheet()

    expect(radio('Play LLM')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('combobox', { name: 'Opponent' })).toHaveTextContent('qwen3.5:9b')
    expect(screen.getByRole('switch', { name: 'Thinking' })).toHaveAttribute('aria-checked', 'true')
    expect(radio('Standard')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: 'Advanced settings' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('radiogroup', { name: 'What the LLM is given' })).not.toBeInTheDocument()
  })

  test('Esc closes it without starting, and its changes are forgotten: it opens again with the last game', async () => {
    const { user, onStart } = await openSheet()

    await user.click(radio('LLM faceoff'))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'New game' }))

    expect(await screen.findByRole('radio', { name: 'Play LLM' })).toHaveAttribute('aria-checked', 'true')
    expect(onStart).not.toHaveBeenCalled()
  })

  test('opens with the focus on the sheet itself, so no tooltip shows until asked for', async () => {
    const { sheet } = await openSheet()

    await waitFor(() => expect(sheet).toHaveFocus())
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(document.querySelector('[data-slot=tooltip-content]')).not.toBeInTheDocument()
  })

  test('✕ closes it too', async () => {
    const { user, onStart } = await openSheet()

    await user.click(screen.getByRole('button', { name: 'Close' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(onStart).not.toHaveBeenCalled()
  })

  test('the models are listed afresh each time it opens', async () => {
    const fetch = stubModels(() => Response.json([qwen]))
    const { user } = await openSheet()
    const listings = () => fetch.mock.calls.filter(([path]) => path === '/api/models').length
    await waitFor(() => expect(listings()).toBe(1))

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'New game' }))

    await waitFor(() => expect(listings()).toBe(2))
  })
})

describe('starting', () => {
  test('Play as White starts the game set up in the sheet, the human White, and closes the sheet', async () => {
    const { user, started } = await openSheet({ ...playLlm, white: playLlm.black, black: { player: 'human' } })

    await user.click(screen.getByRole('button', { name: 'Play as White' }))

    expect(started()).toEqual({
      mode: 'play_llm',
      rules: 'standard',
      max_attempts: 5,
      white: { player: 'human' },
      black: llm('qwen3.5:9b', { thinking: true }),
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('Play as Black: the human Black, the LLM keeping its model', async () => {
    const { user, started } = await openSheet()

    await user.click(screen.getByRole('button', { name: 'Play as Black' }))

    expect(started()).toEqual({
      mode: 'play_llm',
      rules: 'standard',
      max_attempts: 5,
      white: llm('qwen3.5:9b', { thinking: true }),
      black: { player: 'human' },
    })
  })

  test('there is no separate colour control', async () => {
    await openSheet()

    expect(screen.queryByRole('radiogroup', { name: /colour/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start faceoff' })).not.toBeInTheDocument()
  })

  test('an LLM faceoff has one Start faceoff button', async () => {
    const { user, started } = await openSheet()

    await user.click(radio('LLM faceoff'))
    expect(screen.queryByRole('button', { name: /^Play as/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start faceoff' }))

    expect(started()).toEqual({
      mode: 'llm_faceoff',
      rules: 'standard',
      max_attempts: 5,
      white: llm('qwen3.5:9b', { thinking: true }),
      black: llm('qwen3.5:9b', { thinking: true }),
    })
  })
})

describe('Mode', () => {
  test('two cards, each its players as icons above its name, the description a tooltip and aria-description', async () => {
    const { user, sheet } = await openSheet()

    expect(within(screen.getByRole('radiogroup', { name: 'Mode' })).getAllByRole('radio')).toEqual([
      radio('Play LLM'),
      radio('LLM faceoff'),
    ])
    const icons = (name: string) => [...radio(name).querySelectorAll('svg')].map((svg) => svg.classList[1])
    expect(icons('Play LLM')).toEqual(['lucide-user', 'lucide-bot'])
    expect(icons('LLM faceoff')).toEqual(['lucide-bot', 'lucide-bot'])
    expect(radio('Play LLM')).toHaveAttribute('aria-description', 'You play one side, a model the other')
    expect(radio('LLM faceoff')).toHaveAttribute('aria-description', 'A model on each side, to compare them')
    expect(sheet).not.toHaveTextContent('You play one side')

    await user.hover(radio('LLM faceoff'))
    expect(await tooltip()).toHaveTextContent(/^A model on each side, to compare them$/)
  })
})

describe('Opponent', () => {
  test('Play LLM: one model select listing the models', async () => {
    const { user, started } = await openSheet()

    await user.click(screen.getByRole('combobox', { name: 'Opponent' }))
    expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toEqual([
      'qwen3.5:9b',
      'gemma3:4b',
      'llama3:8b',
    ])
    await user.click(screen.getByRole('option', { name: 'llama3:8b' }))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))

    expect(started()).toMatchObject({ black: { model: 'llama3:8b' } })
  })

  test('says why when the models cannot be listed, and keeps the chosen model', async () => {
    stubModels(() => Response.json({ detail: 'Ollama is not running' }, { status: 503 }))
    await openSheet()

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not list the models: Ollama is not running')
    expect(screen.getByRole('combobox', { name: 'Opponent' })).toHaveTextContent('qwen3.5:9b')
  })

  test('LLM faceoff: White model, the swap button and Black model, the sides marked by dots', async () => {
    const { user, sheet, started } = await openSheet({ ...faceoff, black: llm('gemma3:4b') })

    expect(screen.queryByRole('combobox', { name: 'Opponent' })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'White model' })).toHaveTextContent('qwen3.5:9b')
    expect(screen.getByRole('combobox', { name: 'Black model' })).toHaveTextContent('gemma3:4b')
    expect(sheet.querySelectorAll('[data-side-dot]')).toHaveLength(2)
    const swap = screen.getByRole('button', { name: 'Swap colours' })
    expect(swap.querySelector('svg')).toHaveClass('lucide-arrow-left-right')

    await user.click(swap)
    await user.click(screen.getByRole('combobox', { name: 'Black model' }))
    await user.click(await screen.findByRole('option', { name: 'llama3:8b' }))
    await user.click(screen.getByRole('button', { name: 'Start faceoff' }))

    expect(started()).toMatchObject({ white: { model: 'gemma3:4b' }, black: { model: 'llama3:8b' } })
  })
})

describe('Thinking', () => {
  const explanation = 'Reasons before each move. Slower, likely stronger.'

  test('a switch, its explanation a tooltip and aria-description', async () => {
    const { user, sheet, started } = await openSheet()
    const thinking = screen.getByRole('switch', { name: 'Thinking' })

    expect(thinking).toHaveAttribute('aria-description', explanation)
    expect(sheet).not.toHaveTextContent(explanation)
    await user.hover(within(sheet).getByText('Thinking'))
    expect(await tooltip()).toHaveTextContent(explanation)

    await user.click(thinking)
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started()).toMatchObject({ black: { thinking: false } })
  })

  test("disabled when the model can't think, the tooltip naming the model", async () => {
    const { user, sheet } = await openSheet({ ...playLlm, black: llm('llama3:8b') })
    const thinking = screen.getByRole('switch', { name: 'Thinking' })

    await waitFor(() => expect(thinking).toHaveAttribute('aria-description', "llama3:8b can't think."))
    expect(thinking).toHaveAttribute('aria-checked', 'false')
    expect(thinking).toHaveAttribute('data-disabled')
    await user.hover(within(sheet).getByText('Thinking'))
    expect(await tooltip()).toHaveTextContent(/^llama3:8b can't think\.$/)
  })

  test("in a faceoff, shared, and disabled naming each model that can't think", async () => {
    await openSheet({ ...faceoff, white: llm('gemma3:4b'), black: llm('llama3:8b') })

    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Thinking' })).toHaveAttribute(
        'aria-description',
        "gemma3:4b and llama3:8b can't think.",
      ),
    )
  })
})

describe('Rules', () => {
  test('Standard and Chaos as icon cards, the descriptions in tooltips; Chaos starts a Chaos game', async () => {
    const { user, sheet, started } = await openSheet()

    expect(radiosIn('Rules')).toEqual(['Standard', 'Chaos'])
    expect(radio('Standard').querySelector('svg')).toHaveClass('lucide-chess-knight')
    expect(radio('Chaos').querySelector('svg')).toHaveClass('lucide-zap')
    expect(radio('Standard')).toHaveAttribute('aria-description', 'Normal chess. Rated.')
    expect(radio('Chaos')).toHaveAttribute('aria-description', "The LLM's illegal moves are played anyway. Unrated.")
    expect(sheet).not.toHaveTextContent('Rated.')

    await user.click(radio('Chaos'))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started()).toMatchObject({ rules: 'chaos' })
  })

  test('under an enforced constraint Chaos is disabled, the reason in its tooltip', async () => {
    const { user } = await openSheet({ ...playLlm, rules: 'chaos', black: llm('qwen3.5:9b', { llm_constraints: 'blind_enforced' }) })
    const reason = 'Needs an LLM that can play an illegal move: pick Board only or Board + legal moves in Advanced settings.'

    expect(radio('Chaos')).toHaveAttribute('aria-disabled', 'true')
    expect(radio('Chaos')).toHaveAttribute('aria-checked', 'false')
    expect(radio('Standard')).toHaveAttribute('aria-checked', 'true')
    expect(radio('Chaos')).toHaveAttribute('aria-description', reason)
    await user.hover(radio('Chaos'))
    expect(await tooltip()).toHaveTextContent(reason)
  })

  test('the Legal counterpart switch shows only under Chaos rules, on by default, its meaning in a tooltip', async () => {
    const { user, sheet, started } = await openSheet()
    const counterpart = () => screen.queryByRole('switch', { name: 'Legal counterpart' })

    expect(counterpart()).not.toBeInTheDocument()
    await user.click(radio('Chaos'))
    expect(counterpart()).toHaveAttribute('aria-checked', 'true')
    const meaning = 'After a Chaos move, the LLM is asked once more for a legal move: recorded, never played. One more call per Chaos move.'
    expect(counterpart()).toHaveAttribute('aria-description', meaning)
    expect(sheet).not.toHaveTextContent('never played')
    await user.hover(counterpart()!)
    expect(await tooltip()).toHaveTextContent(meaning)
    await user.click(radio('Standard'))
    expect(counterpart()).not.toBeInTheDocument()

    await user.click(radio('Chaos'))
    await user.click(counterpart()!)
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started()).toMatchObject({ rules: 'chaos', legal_counterpart: false })
  })

  test("the sheet keeps the last game's Legal counterpart switch", async () => {
    await openSheet({ ...playLlm, rules: 'chaos', legal_counterpart: false })

    expect(screen.getByRole('switch', { name: 'Legal counterpart' })).toHaveAttribute('aria-checked', 'false')
  })

  test('customized, one enforced LLM disables Chaos, the reason naming its side', async () => {
    await openSheet({ ...faceoff, black: llm('qwen3.5:9b', { llm_constraints: 'listed_enforced' }) })

    expect(radio('Chaos')).toHaveAttribute('aria-disabled', 'true')
    expect(radio('Chaos')).toHaveAttribute(
      'aria-description',
      'Needs every LLM able to play an illegal move: pick Board only or Board + legal moves for Black in Advanced settings.',
    )
  })
})

describe('Advanced settings', () => {
  test('its summary is a tooltip and the trigger\'s aria-description', async () => {
    const { user, sheet } = await openSheet()
    const advanced = screen.getByRole('button', { name: 'Advanced settings' })

    expect(advanced).toHaveAttribute('aria-description', 'What the LLM sees and remembers, retries, forfeit')
    expect(advanced.querySelector('svg')).toHaveClass('lucide-chevron-down')
    expect(sheet).not.toHaveTextContent('What the LLM sees')
    await user.hover(advanced)
    expect(await tooltip()).toHaveTextContent(/^What the LLM sees and remembers, retries, forfeit$/)
  })

  test('What the LLM is given: the four LLM constraints, the plain name over the glossary term', async () => {
    const { user, started } = await openSheet()
    await openAdvanced(user)

    expect(radiosIn('What the LLM is given')).toEqual([
      'Board onlyFree',
      'Board + legal movesListed',
      'Kept legal, not toldBlind enforced',
      'Shown and kept legalListed enforced',
    ])
    expect(radio(/^Board only/)).toHaveAttribute('aria-checked', 'true')
    for (const card of within(screen.getByRole('radiogroup', { name: 'What the LLM is given' })).getAllByRole('radio'))
      expect(card).toHaveAttribute('aria-description')

    await user.hover(radio(/^Board \+ legal moves/))
    expect(await tooltip()).toHaveTextContent('The LLM is shown the legal moves, but can still play an illegal one.')
    await user.click(radio(/^Board \+ legal moves/))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started()).toMatchObject({ black: { llm_constraints: 'listed' } })
  })

  test('After an illegal move, tell the LLM: Explained, Bare, Hinted or Repeat', async () => {
    const { user, started } = await openSheet()
    await openAdvanced(user)

    expect(radiosIn('After an illegal move, tell the LLM')).toEqual(['Explained', 'Bare', 'Hinted', 'Repeat'])
    expect(radio('Explained')).toHaveAttribute('aria-checked', 'true')
    expect(radio('Bare')).toHaveAttribute('aria-description', 'After an illegal move the LLM is told only that it was illegal.')
    await user.click(radio('Hinted'))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started()).toMatchObject({ black: { retry_feedback: 'hinted', turn_memory: 'fresh' } })
  })

  test('Repeat asks the LLM again with the same prompt, its description in the tooltip', async () => {
    const { user, started } = await openSheet()
    await openAdvanced(user)

    await user.hover(radio('Repeat'))
    expect(await tooltip()).toHaveTextContent(
      'After an illegal move the LLM is sent the same prompt again, never told its move was illegal.',
    )
    await user.click(radio('Repeat'))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started()).toMatchObject({ black: { retry_feedback: 'repeat', turn_memory: 'fresh' } })
  })

  test('What the LLM remembers: Fresh by default, Chat with position or Chat with moves, sent when not fresh', async () => {
    const { user, started } = await openSheet()
    await openAdvanced(user)

    expect(radiosIn('What the LLM remembers')).toEqual(['Fresh', 'Chat with position', 'Chat with moves'])
    expect(radio('Fresh')).toHaveAttribute('aria-checked', 'true')
    expect(radio('Chat with moves')).toHaveAttribute(
      'aria-description',
      "One conversation for the whole game, each turn adding only the opponent's last move: the LLM keeps track of the board.",
    )
    await user.hover(radio('Chat with position'))
    expect(await tooltip()).toHaveTextContent(
      'One conversation for the whole game, each turn adding the position as a fresh turn shows it.',
    )
    await user.click(radio('Chat with position'))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started()).toMatchObject({ black: { turn_memory: 'chat_position' } })
  })

  test('back on Fresh, a new game is sent as fresh; the sheet opens with the last game\'s Turn memory', async () => {
    const { user, started } = await openSheet({ ...playLlm, black: { ...llm('qwen3.5:9b'), turn_memory: 'chat_moves' } })
    await openAdvanced(user)

    expect(radio('Chat with moves')).toHaveAttribute('aria-checked', 'true')
    await user.click(radio('Fresh'))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started().black).toEqual(llm('qwen3.5:9b'))
  })

  test('Illegal moves before forfeit: 5 by default, any of 1 to 25', async () => {
    const { user, started } = await openSheet()
    await openAdvanced(user)
    const limit = screen.getByRole('combobox', { name: 'Illegal moves before forfeit' })

    expect(limit).toHaveTextContent('5')
    expect(limit).toHaveAttribute('aria-description', 'The LLM forfeits at its 5th illegal move in a turn: 4 retries. Default 5.')
    await user.click(limit)
    expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toEqual(
      Array.from({ length: 25 }, (_, index) => String(index + 1)),
    )
    await user.click(screen.getByRole('option', { name: '12' }))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))

    expect(started()).toMatchObject({ max_attempts: 12 })
  })

  test.each([/^Kept legal, not told/, /^Shown and kept legal/])(
    'under %s Retry feedback and the forfeit limit are hidden',
    async (constraint) => {
      const { user } = await openSheet()
      await openAdvanced(user)

      await user.click(radio(constraint))

      expect(screen.queryByRole('radiogroup', { name: 'After an illegal move, tell the LLM' })).not.toBeInTheDocument()
      expect(screen.queryByRole('combobox', { name: 'Illegal moves before forfeit' })).not.toBeInTheDocument()
      expect(screen.getByRole('radiogroup', { name: 'What the LLM remembers' })).toBeInTheDocument()
    },
  )

  test('Customize per LLM is a faceoff\'s only', async () => {
    const { user } = await openSheet()
    await openAdvanced(user)

    expect(screen.queryByRole('switch', { name: 'Customize per LLM' })).not.toBeInTheDocument()
    await user.click(radio('LLM faceoff'))
    expect(screen.getByRole('switch', { name: 'Customize per LLM' })).toHaveAttribute('aria-checked', 'false')
  })

  test('Customize per LLM on: Thinking, the constraint and Retry feedback per side, an enforced side without feedback', async () => {
    const { user, started } = await openSheet({ ...faceoff, black: llm('gemma3:4b') })
    await openAdvanced(user)

    await user.click(screen.getByRole('switch', { name: 'Customize per LLM' }))

    expect(screen.queryByRole('switch', { name: 'Thinking' })).not.toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Black thinking' })).toHaveAttribute('data-disabled')
    expect(screen.getByRole('switch', { name: 'Black thinking' })).toHaveAttribute('aria-description', "gemma3:4b can't think.")
    expect(screen.getAllByRole('radiogroup', { name: /what the LLM is given/i })).toHaveLength(2)
    await user.click(screen.getByRole('switch', { name: 'White thinking' }))
    const black = screen.getByRole('radiogroup', { name: 'Black: what the LLM is given' })
    await user.click(within(black).getByRole('radio', { name: /^Shown and kept legal/ }))
    expect(screen.getAllByRole('radiogroup', { name: /after an illegal move, tell the LLM/i })).toHaveLength(1)
    await user.click(
      within(screen.getByRole('radiogroup', { name: 'White: after an illegal move, tell the LLM' })).getByRole('radio', {
        name: 'Bare',
      }),
    )
    await user.click(
      within(screen.getByRole('radiogroup', { name: 'Black: what the LLM remembers' })).getByRole('radio', {
        name: 'Chat with moves',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Start faceoff' }))

    expect(started()).toEqual({
      mode: 'llm_faceoff',
      rules: 'standard',
      max_attempts: 5,
      white: llm('qwen3.5:9b', { thinking: true, retry_feedback: 'bare', turn_memory: 'fresh' }),
      black: { ...llm('gemma3:4b', { llm_constraints: 'listed_enforced' }), turn_memory: 'chat_moves' },
    })
  })
})

describe('Prompt lab', () => {
  const described = { ...playLlm, black: { ...llm('qwen3.5:9b', { thinking: true }), prompt_template_id: 'described@1' } }
  const picker = (name = 'Prompt') => screen.getByRole('combobox', { name })
  const options = async () => (await screen.findAllByRole('option')).map((option) => option.textContent)

  test('off: no Prompt picker, and a new game plays the defaults, even after a game with another template', async () => {
    const fetch = stubModels(() => Response.json(models))
    const { user, started } = await openSheet(described)
    await openAdvanced(user)

    expect(screen.queryByRole('combobox', { name: /prompt/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started().black).toEqual(llm('qwen3.5:9b', { thinking: true }))
    expect(fetch).not.toHaveBeenCalledWith('/api/prompt-templates')
  })

  test("on: a Prompt picker listing the templates that fit what the LLM is given, Default selected", async () => {
    setPromptLabOn(true)
    const { user, started } = await openSheet()
    await openAdvanced(user)

    await waitFor(() => expect(picker()).toHaveTextContent('Default'))
    expect(picker()).toHaveAttribute('aria-description', expect.stringMatching(/plays the whole game with/))
    await user.click(picker())
    expect(await options()).toEqual(['Default', 'Described', 'terse@1'])
    await user.click(screen.getByRole('option', { name: 'Described' }))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))

    expect(started().black).toEqual({ ...llm('qwen3.5:9b', { thinking: true }), prompt_template_id: 'described@1' })
  })

  test("its meaning is the row's tooltip", async () => {
    setPromptLabOn(true)
    const { user } = await openSheet()
    await openAdvanced(user)

    await user.hover(screen.getByText('Prompt', { selector: 'div' }))
    expect(await tooltip()).toHaveTextContent(picker().getAttribute('aria-description')!)
  })

  test('changing what the LLM is given moves a template that no longer fits back to the fitting default', async () => {
    setPromptLabOn(true)
    const { user, started } = await openSheet(described)
    await openAdvanced(user)
    await waitFor(() => expect(picker()).toHaveTextContent('Described'))

    await user.click(radio(/^Board \+ legal moves/))

    expect(picker()).toHaveTextContent('Default listed')
    await user.click(picker())
    expect(await options()).toEqual(['Default listed', 'Described listed'])
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started().black).toEqual(llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }))
  })

  test('a template that still fits stays chosen when what the LLM is given changes', async () => {
    setPromptLabOn(true)
    const { user, started } = await openSheet(described)
    await openAdvanced(user)
    await waitFor(() => expect(picker()).toHaveTextContent('Described'))

    await user.click(radio(/^Kept legal, not told/))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))

    expect(started().black).toMatchObject({ llm_constraints: 'blind_enforced', prompt_template_id: 'described@1' })
  })

  test('under Chat with moves the picker offers Moves, its Default, and the saved templates; the rest go back', async () => {
    setPromptLabOn(true)
    const { user, started } = await openSheet(described)
    await openAdvanced(user)
    await waitFor(() => expect(picker()).toHaveTextContent('Described'))

    await user.click(radio('Chat with moves'))

    expect(picker()).toHaveTextContent('Moves')
    await user.click(picker())
    expect(await options()).toEqual(['Moves', 'terse@1'])
    await user.keyboard('{Escape}')
    await user.click(radio(/^Board \+ legal moves/))
    expect(picker()).toHaveTextContent('Moves listed')
    await user.click(screen.getByRole('button', { name: 'Play as White' }))
    expect(started().black).toEqual({
      ...llm('qwen3.5:9b', { thinking: true, llm_constraints: 'listed' }),
      turn_memory: 'chat_moves',
    })
  })

  test('Customize per LLM: a Prompt picker per side', async () => {
    setPromptLabOn(true)
    const { user, started } = await openSheet(faceoff)
    await openAdvanced(user)
    expect(screen.getAllByRole('combobox', { name: /prompt/i })).toHaveLength(1)

    await user.click(screen.getByRole('switch', { name: 'Customize per LLM' }))
    expect(picker('White: prompt')).toHaveTextContent('Default')
    await user.click(picker('Black: prompt'))
    await user.click(await screen.findByRole('option', { name: 'Described' }))
    await user.click(screen.getByRole('button', { name: 'Start faceoff' }))

    expect(started()).toMatchObject({
      white: llm('qwen3.5:9b'),
      black: { ...llm('qwen3.5:9b'), prompt_template_id: 'described@1' },
    })
    expect(started().white).not.toHaveProperty('prompt_template_id')
  })
})

test('no Move sound, no sampling table, no text glyphs, and no description lines', async () => {
  const { user, sheet } = await openSheet({ ...faceoff, black: llm('gemma3:4b') })
  await openAdvanced(user)
  await user.click(screen.getByRole('switch', { name: 'Customize per LLM' }))

  expect(screen.queryByRole('switch', { name: 'Move sound' })).not.toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(sheet).not.toHaveTextContent(/temperature|sampling/i)
  expect(sheet).not.toHaveTextContent(/[♔♚⇄▸]/)
  expect(sheet).not.toHaveTextContent(/default|Default/)
})

describe('System 1 models', () => {
  const system1 = (more: Record<string, unknown> = {}) => ({
    player: 'system1' as const,
    model: 'd3:2b',
    base_url: 'http://localhost:11434',
    choice_temperature: 1,
    ...more,
  })
  const kind = (group: string) => within(screen.getByRole('radiogroup', { name: group }))
  const openSystem1Settings = async (user: ReturnType<typeof userEvent.setup>) =>
    user.click(screen.getByRole('button', { name: 'Advanced settings' }))

  test('each Model player is an LLM or a System 1 model, an LLM by default', async () => {
    await openSheet()

    expect(radiosIn('Opponent kind')).toEqual(['LLM', 'System 1'])
    expect(kind('Opponent kind').getByRole('radio', { name: 'LLM' })).toBeChecked()
  })

  test('Play LLM: a System 1 opponent is named in a field, with the server and Choice temperature in Advanced settings', async () => {
    const { user, started } = await openSheet()

    await user.click(kind('Opponent kind').getByRole('radio', { name: 'System 1' }))
    expect(screen.queryByRole('combobox', { name: 'Opponent' })).not.toBeInTheDocument()
    const model = screen.getByRole('textbox', { name: 'Opponent' })
    expect(model).toHaveValue('d3:2b')
    await user.clear(model)
    await user.type(model, 'd1:2b')
    await openSystem1Settings(user)
    const url = screen.getByRole('textbox', { name: 'Server URL' })
    expect(url).toHaveValue('http://localhost:11434')
    await user.clear(url)
    await user.type(url, 'http://localhost:9000')
    const temperature = screen.getByRole('spinbutton', { name: 'Choice temperature' })
    expect(temperature).toHaveValue(1)
    await user.clear(temperature)
    await user.type(temperature, '0.5')
    await user.click(screen.getByRole('button', { name: 'Play as Black' }))

    expect(started()).toEqual({
      mode: 'play_llm',
      white: system1({ model: 'd1:2b', base_url: 'http://localhost:9000', choice_temperature: 0.5 }),
      black: { player: 'human' },
      rules: 'standard',
      max_attempts: 5,
    })
  })

  test("a System 1 side's server starts as the one the API names", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) =>
        Promise.resolve(
          path === '/api/system1/options'
            ? Response.json({ default_url: 'http://api-says:1234', models: [], templates: system1Templates })
            : path === '/api/prompt-templates'
              ? Response.json(library)
              : Response.json(models),
        ),
      ),
    )
    const { user } = await openSheet()

    await user.click(kind('Opponent kind').getByRole('radio', { name: 'System 1' }))
    await openSystem1Settings(user)

    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Server URL' })).toHaveValue('http://api-says:1234'))
  })

  describe('with System 1 models listed', () => {
    /** Answers GET /api/system1/options with these models, as Ollama has them. */
    const listed = (...names: string[]) =>
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation((path: string) =>
          Promise.resolve(
            path === '/api/system1/options'
              ? Response.json({ default_url: 'http://localhost:11434', models: names, templates: system1Templates })
              : path === '/api/prompt-templates'
                ? Response.json(library)
                : Response.json(models),
          ),
        ),
      )
    const options = () => screen.findAllByRole('option').then((all) => all.map((option) => option.textContent))

    test('a System 1 opponent is picked from the listed models', async () => {
      listed('d3:9b', 'd3:2b', 'd1:2b')
      const { user, started } = await openSheet()

      await user.click(kind('Opponent kind').getByRole('radio', { name: 'System 1' }))
      const picker = await screen.findByRole('combobox', { name: 'Opponent' })
      expect(screen.queryByRole('textbox', { name: 'Opponent' })).not.toBeInTheDocument()
      expect(picker).toHaveTextContent('d3:2b') // the side's model, since it is listed
      await user.click(picker)
      expect(await options()).toEqual(['d3:9b', 'd3:2b', 'd1:2b'])
      await user.click(screen.getByRole('option', { name: 'd1:2b' }))
      await user.click(screen.getByRole('button', { name: 'Play as White' }))

      expect(started()).toMatchObject({ black: system1({ model: 'd1:2b' }) })
    })

    test('a side that becomes a System 1 model takes the first listed when its model is not listed', async () => {
      listed('d3:9b', 'd1:2b')
      const { user, started } = await openSheet()

      await user.click(kind('Opponent kind').getByRole('radio', { name: 'System 1' }))
      await waitFor(() => expect(screen.getByRole('combobox', { name: 'Opponent' })).toHaveTextContent('d3:9b'))
      await user.click(screen.getByRole('button', { name: 'Play as White' }))

      expect(started()).toMatchObject({ black: system1({ model: 'd3:9b' }) })
    })

    test("the sheet opens with the last game's model, listed or not, and starts it again", async () => {
      listed('d3:9b', 'd1:2b')
      const last = { ...faceoff, white: llm('gemma3:4b'), black: system1({ model: 'old:1b' }) }
      const { user, started } = await openSheet(last)

      const picker = await screen.findByRole('combobox', { name: 'Black model' })
      expect(picker).toHaveTextContent('old:1b')
      await user.click(picker)
      expect(await options()).toEqual(['old:1b', 'd3:9b', 'd1:2b'])
      await user.keyboard('{Escape}')
      await user.click(screen.getByRole('button', { name: 'Start faceoff' }))

      expect(started()).toMatchObject({ black: system1({ model: 'old:1b' }) })
    })

    test('a server other than the default is not Ollama, so its model is typed', async () => {
      listed('d3:9b', 'd1:2b')
      const { user, started } = await openSheet({ ...playLlm, black: system1({ model: 'd3:9b' }) })
      await screen.findByRole('combobox', { name: 'Opponent' })
      await openSystem1Settings(user)

      const url = screen.getByRole('textbox', { name: 'Server URL' })
      await user.clear(url)
      await user.type(url, 'http://localhost:8080')
      const model = screen.getByRole('textbox', { name: 'Opponent' })
      expect(screen.queryByRole('combobox', { name: 'Opponent' })).not.toBeInTheDocument()
      await user.clear(model)
      await user.type(model, 'served-here')
      await user.click(screen.getByRole('button', { name: 'Play as White' }))

      expect(started()).toMatchObject({ black: system1({ model: 'served-here', base_url: 'http://localhost:8080' }) })
    })

    test('its tooltip says where the models come from and how to name another', async () => {
      listed('d3:9b')
      const { user } = await openSheet({ ...playLlm, black: system1({ model: 'd3:9b' }) })

      await user.hover(await screen.findByRole('combobox', { name: 'Opponent' }))

      expect(await tooltip()).toHaveTextContent(/installed in Ollama.*Server URL/)
    })
  })

  test('with no System 1 model listed, e.g. Ollama not answering, the model is typed in a field', async () => {
    const { user } = await openSheet({ ...playLlm, black: system1() })

    const field = await screen.findByRole('textbox', { name: 'Opponent' })
    expect(field).toHaveValue('d3:2b')
    await user.hover(field)
    expect(await tooltip()).toHaveTextContent(/Ollama has no System 1 models, or didn't answer/)
    expect(screen.queryByRole('combobox', { name: 'Opponent' })).not.toBeInTheDocument()
  })

  test('its Prompt template is picked from the System 1 templates the API lists, the first being the default', async () => {
    const { user, started } = await openSheet({ ...playLlm, black: system1() })
    await openSystem1Settings(user)

    const picker = await screen.findByRole('combobox', { name: 'Prompt template' })
    await waitFor(() => expect(picker).toHaveTextContent('System 1'))
    await user.click(picker)
    expect((await screen.findAllByRole('option')).map((option) => option.textContent)).toEqual([
      'System 1',
      'Position only',
    ])
    await user.click(screen.getByRole('option', { name: 'Position only' }))
    await user.click(screen.getByRole('button', { name: 'Play as White' }))

    expect(started()).toMatchObject({ black: system1({ prompt_template_id: 'system1-position-only@b2' }) })
  })

  test('the sheet opens with the last game\'s System 1 side and its settings', async () => {
    const last = { ...faceoff, white: llm('gemma3:4b'), black: system1({ model: 'd1:2b', choice_temperature: 0.25 }) }
    const { user, started } = await openSheet(last)

    expect(screen.getByRole('textbox', { name: 'Black model' })).toHaveValue('d1:2b')
    expect(screen.getByRole('combobox', { name: 'White model' })).toHaveTextContent('gemma3:4b')
    await user.click(screen.getByRole('button', { name: 'Start faceoff' }))

    expect(started()).toMatchObject({ white: llm('gemma3:4b'), black: system1({ model: 'd1:2b', choice_temperature: 0.25 }) })
  })

  test('LLM faceoff: either side can be a System 1 model, against an LLM or another', async () => {
    const { user, started } = await openSheet(faceoff)

    await user.click(kind('White kind').getByRole('radio', { name: 'System 1' }))
    await user.click(kind('Black kind').getByRole('radio', { name: 'System 1' }))
    await user.type(screen.getByRole('textbox', { name: 'Black model' }), '-x')
    await user.click(screen.getByRole('button', { name: 'Start faceoff' }))

    expect(started()).toMatchObject({ white: system1(), black: system1({ model: 'd3:2b-x' }) })
  })

  test('with no LLM in the game, the settings that are an LLM\'s are not offered', async () => {
    const { user } = await openSheet({ ...playLlm, black: system1() })

    expect(screen.queryByRole('switch', { name: 'Thinking' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Advanced settings' }))
    expect(screen.queryByRole('radiogroup', { name: 'What the LLM is given' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Illegal moves before forfeit' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Server URL' })).toBeVisible()
  })

  test('Chaos rules cannot be chosen against a System 1 model, the reason in the tooltip', async () => {
    const { user } = await openSheet({ ...playLlm, black: system1() })

    const chaos = radio(/Chaos/)
    expect(chaos).toHaveAttribute('aria-disabled', 'true')
    await user.hover(chaos)
    expect(await tooltip()).toHaveTextContent('A System 1 model plays only legal moves')
  })

  test('a game does not start with no model or a Choice temperature below 0, the reason in the tooltip', async () => {
    const { user, onStart } = await openSheet({ ...playLlm, black: system1() })
    await user.click(screen.getByRole('button', { name: 'Advanced settings' }))
    const temperature = screen.getByRole('spinbutton', { name: 'Choice temperature' })
    await user.clear(temperature)
    await user.type(temperature, '-1')

    const start = screen.getByRole('button', { name: 'Play as White' })
    expect(start).toBeDisabled()
    await user.hover(start.parentElement!)
    expect(await tooltip()).toHaveTextContent('Choice temperature must be a number, 0 or more.')
    await user.click(start)
    expect(onStart).not.toHaveBeenCalled()
  })
})
