import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import type { GameState } from '@/api/types'
import { GameCard } from '@/components/game-card/GameCard'
import { aGame, chaosGame } from '@/test/games'

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
/** A line of settings as text: the shared one ("Settings") or a player's ("White's settings"). */
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

test('the Rules are the one setting shown as an icon, named beside it; the others are a line of text', () => {
  renderCard(aGame())

  expect(rules()).toBe('chess-knight: Standard rules')
  expect(line('Settings')).toEqual(['Board only (Free)', 'Explained feedback', 'Thinking off', 'Forfeit after 5 illegal moves'])
  expect(icons(within(gameCard()).getByRole('list', { name: 'Settings' }))).toEqual([])
})

test('the other values: Chaos rules as a zap', () => {
  renderCard(
    chaosGame(1, {
      settings: { ...chaosGame(1).settings, black: { ...llm, llm_constraints: 'listed', retry_feedback: 'hinted', thinking: true } },
    }),
  )

  expect(rules()).toBe('zap: Chaos rules')
  expect(line('Settings')).toEqual([
    'Board + legal moves (Listed)',
    'Hinted feedback',
    'Thinking on',
    'Forfeit after 5 illegal moves',
  ])
})

test('under an enforced constraint there is no Retry feedback and no forfeit limit', () => {
  renderCard(faceoffOf({ llm_constraints: 'blind_enforced' }, { llm_constraints: 'listed_enforced', retry_feedback: 'bare' }))

  expect(line('Settings')).toEqual(['Thinking off'])
  expect(line("White's settings")).toEqual(['Kept legal, not told (Blind enforced)'])
  expect(line("Black's settings")).toEqual(['Shown and kept legal (Listed enforced)'])
})

test("a setting's meaning shows in its tooltip on hover and keyboard focus, and in aria-description", async () => {
  renderCard(aGame())
  const standard = within(gameCard()).getByRole('img', { name: 'Standard rules' })
  expect(standard).toHaveAttribute('aria-description', 'Normal chess. Rated.')
  const free = within(gameCard()).getByText('Board only (Free)')

  expect(free).toHaveAttribute('aria-description', 'The LLM finds its own moves and can play an illegal one.')
  await userEvent.hover(free)
  const tooltip = (await screen.findByText('The LLM finds its own moves and can play an illegal one.')).closest(
    '[data-slot=tooltip-content]',
  )
  expect(tooltip).toHaveTextContent('Board only (Free)')
  await userEvent.unhover(free)

  await userEvent.tab()
  await userEvent.tab()
  expect(free).toHaveFocus()
  expect(await screen.findByText('The LLM finds its own moves and can play an illegal one.')).toBeInTheDocument()
})

test("in a faceoff a setting the LLMs share is in the line; one that differs is on each player's row", () => {
  renderCard(faceoffOf({ thinking: true }, { retry_feedback: 'bare' }))

  expect(line('Settings')).toEqual(['Board only (Free)', 'Forfeit after 5 illegal moves'])
  expect(line("White's settings")).toEqual(['Explained feedback', 'Thinking on'])
  expect(line("Black's settings")).toEqual(['Bare feedback', 'Thinking off'])
  expect(within(gameCard()).getByText('Thinking on')).toHaveAttribute('aria-description', 'The LLM reasons before each move.')
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

test('no Rematch while the game is playing', () => {
  renderCard(aGame())

  expect(within(gameCard()).queryByRole('button')).not.toBeInTheDocument()
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
