import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import type { GameState } from '@/api/types'
import { GameCard } from '@/components/game-card/GameCard'
import { aGame, aTurn, chaosGame } from '@/test/games'

const llm = aGame().settings.black as Extract<GameState['settings']['black'], { player: 'llm' }>
const faceoffOf = (white: Partial<typeof llm>, black: Partial<typeof llm>) =>
  aGame({
    settings: {
      ...aGame().settings,
      mode: 'llm_faceoff',
      white: { ...llm, model: 'gemma3:4b', ...white },
      black: { ...llm, ...black },
    },
  })

const renderCard = (game: GameState, onRematch = () => {}) =>
  render(<GameCard game={game} error={null} onRematch={onRematch} />)

const gameCard = () => screen.getByRole('region', { name: 'Game' })
/** The Lucide icons in an element, by name ("user", "bot", …). */
const icons = (element: Element) =>
  [...element.querySelectorAll('svg.lucide')].map((svg) =>
    [...svg.classList].find((name) => name.startsWith('lucide-'))!.replace('lucide-', ''),
  )
/** The Rules chip, the one setting shown as an icon: its icon and its name beside it. */
const rules = () => {
  const chip = within(gameCard()).getByRole('img', { name: /rules$/ })
  return `${icons(chip).join(' ')}: ${chip.textContent}`
}
/** A player's line of settings as text ("White's settings"). */
const line = (name: string) =>
  within(within(gameCard()).getByRole('list', { name })).getAllByRole('listitem').map((item) => item.textContent!.replace(/^\u00a0·\u00a0/, ''))

test("the Mode icon shows the players beside the Mode's name: you against an LLM, or an LLM against an LLM", () => {
  const { unmount } = renderCard(aGame())

  const mode = within(gameCard()).getByRole('img', { name: 'You against an LLM' })
  expect(icons(mode)).toEqual(['user', 'bot'])
  expect(within(gameCard()).getByText('Play LLM')).toBeInTheDocument()
  unmount()

  renderCard(faceoffOf({}, {}))
  expect(icons(within(gameCard()).getByRole('img', { name: 'An LLM against an LLM' }))).toEqual(['bot', 'bot'])
  expect(within(gameCard()).getByText('LLM faceoff')).toBeInTheDocument()
})

test('the Rules are the one setting shown, as an icon named beside it; the settings the LLMs share are not shown', () => {
  renderCard(aGame())

  expect(rules()).toBe('chess-knight: Standard rules')
  expect(within(gameCard()).queryByRole('list', { name: 'Settings' })).not.toBeInTheDocument()
  expect(within(gameCard()).queryByText('Board only (Free)')).not.toBeInTheDocument()
})

test('the other values: Chaos rules as a zap', () => {
  renderCard(
    chaosGame(1, {
      settings: { ...chaosGame(1).settings, black: { ...llm, llm_constraints: 'listed', retry_feedback: 'hinted', thinking: true } },
    }),
  )

  expect(rules()).toBe('zap: Chaos rules')
})

test('under an enforced constraint there is no Retry feedback and no forfeit limit', () => {
  renderCard(faceoffOf({ llm_constraints: 'blind_enforced' }, { llm_constraints: 'listed_enforced', retry_feedback: 'bare' }))

  expect(line("White's settings")).toEqual(['Kept legal, not told (Blind enforced)'])
  expect(line("Black's settings")).toEqual(['Shown and kept legal (Listed enforced)'])
})

test("a setting's meaning shows in its tooltip on hover and keyboard focus, and in aria-description", async () => {
  renderCard(faceoffOf({ thinking: true }, {}))
  const standard = within(gameCard()).getByRole('img', { name: 'Standard rules' })
  expect(standard).toHaveAttribute('aria-description', 'Normal chess. Rated.')
  const on = within(gameCard()).getByText('Thinking on')

  expect(on).toHaveAttribute('aria-description', 'The LLM reasons before each move.')
  await userEvent.hover(on)
  const tooltip = (await screen.findByText('The LLM reasons before each move.')).closest('[data-slot=tooltip-content]')
  expect(tooltip).toHaveTextContent('Thinking on')
  await userEvent.unhover(on)

  await userEvent.tab()
  await userEvent.tab()
  expect(on).toHaveFocus()
  expect(await screen.findByText('The LLM reasons before each move.')).toBeInTheDocument()
})

test("in a faceoff a setting the LLMs share is not shown; one that differs is on each player's row", () => {
  renderCard(faceoffOf({ thinking: true }, { retry_feedback: 'bare' }))

  expect(within(gameCard()).queryByText('Board only (Free)')).not.toBeInTheDocument()
  expect(line("White's settings")).toEqual(['Explained feedback', 'Thinking on'])
  expect(line("Black's settings")).toEqual(['Bare feedback', 'Thinking off'])
  expect(within(gameCard()).getByText('Thinking on')).toHaveAttribute('aria-description', 'The LLM reasons before each move.')
})

test("Repeat feedback is on the player's row of the LLM that plays under it, its meaning in aria-description", () => {
  renderCard(faceoffOf({}, { retry_feedback: 'repeat' }))

  expect(line("White's settings")).toEqual(['Explained feedback'])
  expect(line("Black's settings")).toEqual(['Repeat feedback'])
  expect(within(gameCard()).getByText('Repeat feedback')).toHaveAttribute(
    'aria-description',
    'After an illegal move the LLM is sent the same prompt again, never told its move was illegal.',
  )
})

test('the players are shown by name with their colour, without a model logo', () => {
  renderCard(faceoffOf({}, {}))
  const players = within(gameCard()).getByRole('list', { name: 'Players' })

  expect(within(players).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
    'White gemma3:4b',
    'Black qwen3.5:9b',
  ])
  expect(within(players).queryByRole('img')).not.toBeInTheDocument()
  expect(players.querySelector('img, svg')).toBeNull()
})

const over = (game: GameState): GameState => ({ ...game, status: 'over', result: '1-0', end_reason: 'checkmate' })

test("once the game is over, Rematch sits under the result line in the setting chips' style, instead of New game", async () => {
  const onRematch = vi.fn()
  renderCard(over(aGame()), onRematch)

  const rematch = within(gameCard()).getByRole('button', { name: 'Rematch' })
  expect(icons(rematch)).toEqual(['rotate-ccw'])
  expect(rematch).toHaveClass('rounded-full', 'bg-muted')
  expect(within(gameCard()).queryByRole('button', { name: 'New game' })).not.toBeInTheDocument()
  await userEvent.click(rematch)
  expect(onRematch).toHaveBeenCalledOnce()
})

test("the result's detail shows in its tooltip on hover and keyboard focus, and in aria-description", async () => {
  const turn = aTurn('e5', {
    attempts: [{ ...aTurn('e5').attempts[0], move: null, san: null, result: 'timeout', error: 'no answer in 300 s' }],
  })
  renderCard({ ...aGame({ llm_turn: turn }), status: 'over', result: '1-0', end_reason: 'forfeit' })
  const result = within(gameCard()).getByTestId('result')

  expect(result).toHaveTextContent('White wins by forfeit')
  expect(result).not.toHaveTextContent('no answer in 300 s')
  expect(result).toHaveAttribute('aria-description', 'no answer in 300 s')
  await userEvent.hover(result)
  expect((await screen.findByText('no answer in 300 s')).closest('[data-slot=tooltip-content]')).not.toBeNull()
  await userEvent.unhover(result)

  await userEvent.tab()
  await userEvent.tab()
  expect(result).toHaveFocus()
  expect(await screen.findByText('no answer in 300 s')).toBeInTheDocument()
})

test('a result with no detail has no tooltip and takes no focus', () => {
  renderCard(over(aGame()))

  expect(within(gameCard()).getByTestId('result')).not.toHaveAttribute('tabindex')
  expect(within(gameCard()).getByTestId('result')).not.toHaveAttribute('aria-description')
})

test('no Rematch while the game is playing; the result\'s room is held under "Playing"', () => {
  renderCard(aGame())

  expect(within(gameCard()).queryByRole('button')).not.toBeInTheDocument()
  expect(within(gameCard()).getByText('Playing')).toBeInTheDocument()
  expect(within(gameCard()).queryByTestId('result')).not.toBeInTheDocument()
})

test("Rematch's tooltip and aria-description say which colour you will play, or that the LLMs swap", async () => {
  const { unmount } = renderCard(over(aGame()))
  const rematch = within(gameCard()).getByRole('button', { name: 'Rematch' })

  expect(rematch).toHaveAttribute('aria-description', 'Same settings, you play Black')
  await userEvent.hover(rematch)
  const tooltip = (await screen.findByText('Same settings, you play Black')).closest('[data-slot=tooltip-content]')
  expect(tooltip).toHaveTextContent(/^Same settings, you play Black$/)
  unmount()

  renderCard(over(faceoffOf({}, {})))
  expect(within(gameCard()).getByRole('button', { name: 'Rematch' })).toHaveAttribute(
    'aria-description',
    'Same settings, the LLMs swap colours',
  )
})

test("a Turn memory but fresh is on its LLM's row, even when the LLMs share it, its meaning in aria-description", () => {
  renderCard(faceoffOf({ turn_memory: 'chat_moves' }, { turn_memory: 'chat_moves', retry_feedback: 'bare' }))

  expect(line("White's settings")).toEqual(['Explained feedback', 'Chat with moves'])
  expect(line("Black's settings")).toEqual(['Bare feedback', 'Chat with moves'])
  expect(within(gameCard()).getAllByText('Chat with moves')[0]).toHaveAttribute(
    'aria-description',
    expect.stringMatching(/only the opponent's last move/),
  )
})

test("in Play LLM the LLM's row shows its Turn memory; fresh is not shown", () => {
  const playing = (more: Partial<typeof llm>) => aGame({ settings: { ...aGame().settings, black: { ...llm, ...more } } })

  const { unmount } = renderCard(playing({ turn_memory: 'chat_position' }))
  expect(line("Black's settings")).toEqual(['Chat with position'])

  unmount()
  renderCard(playing({ turn_memory: 'fresh' }))
  expect(within(gameCard()).queryByRole('list', { name: "Black's settings" })).not.toBeInTheDocument()
})
