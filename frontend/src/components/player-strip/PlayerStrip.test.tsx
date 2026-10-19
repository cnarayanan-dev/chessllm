import { act, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { GameState } from '@/api/types'
import { MoveTimer, PlayerStrip } from '@/components/player-strip/PlayerStrip'
import { aGame, afterE4 } from '@/test/games'

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
    <PlayerStrip game={afterE4()} color="black" timer={<MoveTimer />}>
      <span>captures</span>
    </PlayerStrip>,
  )

  expect(within(strip('black')).getByText('captures')).toBeInTheDocument()
  expect(within(strip('black')).getByRole('timer')).toHaveTextContent('0s')
})

test('the move timer counts the seconds since it started', () => {
  vi.useFakeTimers()
  render(<MoveTimer />)

  expect(screen.getByRole('timer')).toHaveTextContent('0s')
  act(() => vi.advanceTimersByTime(12_000))
  expect(screen.getByRole('timer')).toHaveTextContent('12s')
})
