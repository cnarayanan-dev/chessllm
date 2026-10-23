import { act, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { GameState } from '@/api/types'
import { PlayerStrip, TimeUsed } from '@/components/player-strip/PlayerStrip'
import { gameLoop, initialGameLoop, type GameLoop } from '@/game/gameLoop'
import { aGame, afterE4, afterE5 } from '@/test/games'

afterEach(() => vi.useRealTimers())

const strip = (color: 'white' | 'black') => screen.getByTestId(`strip-${color}`)
const llm = aGame().settings.black as Extract<GameState['settings']['black'], { player: 'llm' }>
const faceoff = (white: string, black: string, overrides: Partial<GameState> = {}) =>
  aGame({
    settings: { ...aGame().settings, mode: 'llm_faceoff', white: { ...llm, model: white }, black: { ...llm, model: black } },
    ...overrides,
  })

test("the LLM's strip shows its family logo and the model; the human's a person icon and You", () => {
  render(
    <>
      <PlayerStrip game={aGame()} color="black" />
      <PlayerStrip game={aGame()} color="white" />
    </>,
  )

  expect(within(strip('black')).getByRole('img', { name: 'Qwen' })).toBeInTheDocument()
  expect(strip('black')).toHaveTextContent('qwen3.5:9b')
  expect(within(strip('white')).queryByRole('img')).not.toBeInTheDocument()
  expect(within(strip('white')).getByTestId('person')).toBeInTheDocument()
  expect(strip('white')).toHaveTextContent('You')
})

test('a model of a family without a logo shows a monogram', () => {
  render(<PlayerStrip game={faceoff('phi4-mini:3.8b', 'gemma3:4b')} color="white" />)

  expect(within(strip('white')).queryByRole('img')).not.toBeInTheDocument()
  expect(within(strip('white')).getByTestId('monogram')).toHaveTextContent('P')
  expect(strip('white')).toHaveTextContent('phi4-mini:3.8b')
})

test('the side to move has the turn ring; the other side and a game that is over have none', () => {
  const { rerender } = render(
    <>
      <PlayerStrip game={afterE4()} color="black" />
      <PlayerStrip game={afterE4()} color="white" />
    </>,
  )

  expect(strip('black')).toHaveAttribute('data-to-move')
  expect(strip('black')).toHaveTextContent('to move')
  expect(strip('white')).not.toHaveAttribute('data-to-move')

  const over = afterE4({ status: 'over', result: '1-0', end_reason: 'forfeit' })
  rerender(
    <>
      <PlayerStrip game={over} color="black" />
      <PlayerStrip game={over} color="white" />
    </>,
  )
  expect(strip('black')).not.toHaveAttribute('data-to-move')
  expect(strip('white')).not.toHaveAttribute('data-to-move')
})

test('what follows the name and the timer go in the strip', () => {
  render(
    <PlayerStrip game={afterE4()} color="black" timer={<span role="timer">0m 00s</span>}>
      <span>captures</span>
    </PlayerStrip>,
  )

  expect(within(strip('black')).getByText('captures')).toBeInTheDocument()
  expect(within(strip('black')).getByRole('timer')).toHaveTextContent('0m 00s')
})

/** The game loop once `game` has arrived (now), its LLM turn asked for if an LLM is to move. */
const arrived = (game: GameState) => gameLoop(initialGameLoop, { type: 'received', requestId: 1, game, at: Date.now() })

/** Both strips as the page shows them, each with its side's Time used from the live game. */
function Strips({ state }: { state: GameLoop }) {
  const clock = state.clock!
  return (
    <>
      {(['black', 'white'] as const).map((color) => (
        <PlayerStrip key={color} game={state.game!} color={color} timer={<TimeUsed clock={clock} color={color} />} />
      ))}
    </>
  )
}

const timeUsed = (color: 'white' | 'black') => within(strip(color)).getByRole('timer')

describe('Time used', () => {
  beforeEach(() => vi.useFakeTimers())

  test("in Play LLM both strips show it; only the LLM's ticks while its turn runs, once a second", () => {
    render(<Strips state={arrived(afterE4({ time_used: { white: 4.2, black: 0 }, running_s: null }))} />)

    expect(timeUsed('white')).toHaveTextContent('0m 04s')
    expect(timeUsed('black')).toHaveTextContent('0m 00s')
    act(() => vi.advanceTimersByTime(999))
    expect(timeUsed('black')).toHaveTextContent('0m 00s')
    act(() => vi.advanceTimersByTime(1))
    expect(timeUsed('black')).toHaveTextContent('0m 01s')
    act(() => vi.advanceTimersByTime(12_000))
    expect(timeUsed('black')).toHaveTextContent('0m 13s')
    expect(timeUsed('white')).toHaveTextContent('0m 04s')
  })

  test("on the human's move theirs ticks on from the time the backend sent, on the whole second", () => {
    render(<Strips state={arrived(afterE5({ time_used: { white: 4.2, black: 1.2 }, running_s: 0.6 }))} />)

    expect(timeUsed('white')).toHaveTextContent('0m 04s')
    act(() => vi.advanceTimersByTime(200))
    expect(timeUsed('white')).toHaveTextContent('0m 05s')
    act(() => vi.advanceTimersByTime(60_000))
    expect(timeUsed('white')).toHaveTextContent('1m 05s')
    expect(timeUsed('black')).toHaveTextContent('0m 01s')
  })

  test('in an LLM faceoff both strips show it and only the side to move ticks', () => {
    const game = faceoff('gemma3:4b', 'qwen3.5:9b', { time_used: { white: 3599.5, black: 75 }, running_s: null })
    render(<Strips state={arrived(game)} />)

    expect(timeUsed('white')).toHaveTextContent('59m 59s')
    expect(timeUsed('black')).toHaveTextContent('1m 15s')
    act(() => vi.advanceTimersByTime(500))
    expect(timeUsed('white')).toHaveTextContent('1h 00m 00s')
    expect(timeUsed('black')).toHaveTextContent('1m 15s')
  })

  test('once the game is over both stop at their totals', () => {
    const over = afterE5({
      status: 'over',
      result: '0-1',
      end_reason: 'checkmate',
      time_used: { white: 9, black: 7 },
      running_s: null,
    })
    render(<Strips state={arrived(over)} />)

    act(() => vi.advanceTimersByTime(10_000))
    expect(timeUsed('white')).toHaveTextContent('0m 09s')
    expect(timeUsed('black')).toHaveTextContent('0m 07s')
  })

  test('stepping back through the move history, they show the live game, still ticking', () => {
    const live = arrived(afterE5({ time_used: { white: 4, black: 1.2 }, running_s: 0 }))
    render(<Strips state={gameLoop(live, { type: 'view', ply: 0 })} />)

    act(() => vi.advanceTimersByTime(3000))
    expect(timeUsed('white')).toHaveTextContent('0m 07s')
    expect(timeUsed('black')).toHaveTextContent('0m 01s')
  })

  test('its name and meaning are in its aria-description, for the tooltip', () => {
    render(<Strips state={arrived(afterE4())} />)

    expect(timeUsed('black')).toHaveAttribute('aria-description', expect.stringMatching(/^Time used/))
  })
})
