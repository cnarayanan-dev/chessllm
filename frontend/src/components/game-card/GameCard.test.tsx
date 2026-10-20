import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'
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

const renderCard = (game: GameState) =>
  render(<GameCard game={game} pending={false} error={null} onNewGame={() => {}} />)

const gameCard = () => screen.getByRole('region', { name: 'Game' })
/** The Lucide icons in an element, by name ("user", "bot", …). */
const icons = (element: Element) =>
  [...element.querySelectorAll('svg.lucide')].map((svg) =>
    [...svg.classList].find((name) => name.startsWith('lucide-'))!.replace('lucide-', ''),
  )
const chips = () => within(within(gameCard()).getByRole('list', { name: 'Settings' })).getAllByRole('listitem')
/** The setting chips, each as its icon and its accessible name. */
const settingIcons = () => chips().map((item) => `${icons(item).join(' ')}: ${within(item).getByRole('img').getAttribute('aria-label')}`)

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

test('each setting is one icon, named for screen readers, with no settings text line', () => {
  renderCard(aGame())

  expect(settingIcons()).toEqual([
    'eye: Board only (Free)',
    'chess-knight: Standard rules',
    'message-square-text: Explained feedback',
    'brain-off: Thinking off',
    'flag: Forfeit after 5 illegal moves',
  ])
  expect(gameCard()).not.toHaveTextContent(/Board only|Standard rules|feedback|Thinking|Forfeit/)
})

test('the icons of the other values', () => {
  renderCard(
    chaosGame(1, {
      settings: { ...chaosGame(1).settings, black: { ...llm, llm_constraints: 'listed', retry_feedback: 'hinted', thinking: true } },
    }),
  )

  expect(settingIcons()).toEqual([
    'list-checks: Board + legal moves (Listed)',
    'zap: Chaos rules',
    'lightbulb: Hinted feedback',
    'brain: Thinking on',
    'flag: Forfeit after 5 illegal moves',
  ])
})

test('under an enforced constraint there is no Retry feedback and no forfeit limit', () => {
  renderCard(faceoffOf({ llm_constraints: 'blind_enforced' }, { llm_constraints: 'listed_enforced', retry_feedback: 'bare' }))

  expect(settingIcons()).toEqual([
    'lock: White: Kept legal, not told (Blind enforced)',
    'shield-check: Black: Shown and kept legal (Listed enforced)',
    'chess-knight: Standard rules',
    'brain-off: Thinking off',
  ])
})

test("a setting's meaning shows in its tooltip on hover and keyboard focus, and in aria-description", async () => {
  renderCard(aGame())
  const free = within(chips()[0]).getByRole('img')

  expect(free).toHaveAttribute('aria-description', 'The LLM finds its own moves and can play an illegal one.')
  await userEvent.hover(free)
  const tooltip = (await screen.findByText('The LLM finds its own moves and can play an illegal one.')).closest(
    '[data-slot=tooltip-content]',
  )
  expect(tooltip).toHaveTextContent('Board only (Free)')
  await userEvent.unhover(free)

  await userEvent.tab()
  expect(free).toHaveFocus()
  expect(await screen.findByText('The LLM finds its own moves and can play an illegal one.')).toBeInTheDocument()
})

test('in a faceoff a setting the LLMs share is one icon; one that differs is one per side, with a colour dot', () => {
  renderCard(faceoffOf({ thinking: true }, { retry_feedback: 'bare' }))

  expect(settingIcons()).toEqual([
    'eye: Board only (Free)',
    'chess-knight: Standard rules',
    'message-square-text: White: Explained feedback',
    'message-square: Black: Bare feedback',
    'brain: White: Thinking on',
    'brain-off: Black: Thinking off',
    'flag: Forfeit after 5 illegal moves',
  ])
  const dots = chips().map((item) => item.querySelector('[data-side]')?.getAttribute('data-side') ?? null)
  expect(dots).toEqual([null, null, 'white', 'black', 'white', 'black', null])
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
