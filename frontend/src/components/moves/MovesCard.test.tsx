import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import type { Attempt, GameState } from '@/api/types'
import { MovesCard } from '@/components/moves/MovesCard'
import { aGame, aTurn, chaosAttempt, chaosGame, E4, E5, NF3, plies } from '@/test/games'

const NF6: [string, string, string] = ['g8f6', 'Nf6', 'rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2']

const moveList = () => screen.getByTestId('moves')
/** The move list's text, one row per move number: its number, White's and Black's move. */
const rows = () => {
  const cells = [...moveList().children]
  const result: string[][] = []
  for (const cell of cells) {
    if (cell.classList.contains('no')) result.push([cell.textContent!])
    else if (cell.classList.contains('ply')) result.at(-1)!.push(cell.textContent!)
  }
  return result
}

test('lists the moves, one row per move number, the last move marked', () => {
  render(<MovesCard game={aGame({ plies: plies(E4, E5, NF3), llm_turns: [aTurn('e5')] })} />)

  expect(rows()).toEqual([
    ['1.', 'e4', 'e5'],
    ['2.', 'Nf3', ''],
  ])
  expect(within(moveList()).getByText('Nf3')).toHaveClass('last')
  expect(within(moveList()).getByText('e5')).not.toHaveClass('last')
})

test('clicking a move views the position after it', async () => {
  const onView = vi.fn()
  render(<MovesCard game={aGame({ plies: plies(E4, E5, NF3), llm_turns: [aTurn('e5')] })} viewed={null} onView={onView} />)

  await userEvent.click(within(moveList()).getByRole('button', { name: 'e5' }))
  await userEvent.click(within(moveList()).getByRole('button', { name: 'Nf3' }))

  expect(onView.mock.calls).toEqual([[2], [3]])
})

test('the move viewed in the history is marked, and the last move still is', () => {
  render(<MovesCard game={aGame({ plies: plies(E4, E5, NF3), llm_turns: [aTurn('e5')] })} viewed={2} onView={vi.fn()} />)

  expect(within(moveList()).getByText('e5')).toHaveClass('viewed')
  expect(within(moveList()).getByText('e5')).toHaveAttribute('aria-current', 'step')
  expect(within(moveList()).getByText('Nf3')).toHaveClass('last')
  expect(within(moveList()).getByText('Nf3')).not.toHaveClass('viewed')
})

test('a new move arriving while a past position is viewed makes the latest move pulse', () => {
  const before = aGame({ plies: plies(E4, E5), llm_turns: [aTurn('e5')] })
  const { rerender } = render(<MovesCard game={before} viewed={1} onView={vi.fn()} />)
  expect(moveList().querySelector('.arrived')).toBeNull()

  rerender(<MovesCard game={aGame({ plies: plies(E4, E5, NF3), llm_turns: [aTurn('e5')] })} viewed={1} onView={vi.fn()} />)

  expect(within(moveList()).getByText('Nf3')).toHaveClass('last', 'arrived')
  expect(within(moveList()).getByText('e4')).toHaveClass('viewed')
})

test('a new move arriving at the live position does not pulse, nor does stepping back', () => {
  const before = aGame({ plies: plies(E4, E5), llm_turns: [aTurn('e5')] })
  const after = aGame({ plies: plies(E4, E5, NF3), llm_turns: [aTurn('e5')] })
  const { rerender } = render(<MovesCard game={before} viewed={null} onView={vi.fn()} />)

  rerender(<MovesCard game={after} viewed={null} onView={vi.fn()} />)
  rerender(<MovesCard game={after} viewed={2} onView={vi.fn()} />)

  expect(moveList().querySelector('.arrived')).toBeNull()
})

test('the pulse is brief: it ends after a moment, or as soon as the view returns to live', () => {
  vi.useFakeTimers()
  try {
    const before = aGame({ plies: plies(E4, E5), llm_turns: [aTurn('e5')] })
    const after = aGame({ plies: plies(E4, E5, NF3), llm_turns: [aTurn('e5')] })
    const { rerender } = render(<MovesCard game={before} viewed={1} onView={vi.fn()} />)
    rerender(<MovesCard game={after} viewed={1} onView={vi.fn()} />)
    expect(within(moveList()).getByText('Nf3')).toHaveClass('arrived')

    act(() => vi.advanceTimersByTime(2000))
    expect(within(moveList()).getByText('Nf3')).not.toHaveClass('arrived')

    rerender(<MovesCard game={before} viewed={1} onView={vi.fn()} />)
    rerender(<MovesCard game={after} viewed={1} onView={vi.fn()} />)
    expect(within(moveList()).getByText('Nf3')).toHaveClass('arrived')
    rerender(<MovesCard game={after} viewed={null} onView={vi.fn()} />)
    expect(within(moveList()).getByText('Nf3')).not.toHaveClass('arrived')
  } finally {
    vi.useRealTimers()
  }
})

/** The list's scroll position, which jsdom doesn't lay out: the list is 1000px high, and scrolls to its bottom. */
function scrollable() {
  const viewport = document.querySelector<HTMLElement>('[data-slot=scroll-area-viewport]')!
  let top = 0
  Object.defineProperty(viewport, 'scrollHeight', { configurable: true, value: 1000 })
  Object.defineProperty(viewport, 'scrollTop', { configurable: true, get: () => top, set: (value: number) => (top = value) })
  return viewport
}

test('a new move scrolls the live list to it, but a game state with no new move leaves where the user scrolled', () => {
  const game = aGame({ plies: plies(E4, E5), llm_turns: [aTurn('e5')] })
  const { rerender } = render(<MovesCard game={game} />)
  const list = scrollable()
  list.scrollTop = 100 // the user scrolled up to read

  rerender(<MovesCard game={{ ...game }} />)
  expect(list.scrollTop).toBe(100)

  rerender(<MovesCard game={aGame({ plies: plies(E4, E5, NF3), llm_turns: [aTurn('e5')] })} />)
  expect(list.scrollTop).toBe(1000)
})

test("a further try in the latest LLM turn scrolls the live list to its chip", () => {
  const turn = aTurn('', { attempts: [anAttempt('Nf9', 'invalid')] })
  const game = aGame({ plies: plies(E4), llm_turn: turn, llm_turns: [turn] })
  const { rerender } = render(<MovesCard game={game} />)
  const list = scrollable()
  list.scrollTop = 100

  const further = { ...turn, attempts: [...turn.attempts, anAttempt('Ke7', 'illegal')] }
  rerender(<MovesCard game={{ ...game, llm_turn: further, llm_turns: [further] }} />)

  expect(list.scrollTop).toBe(1000)
})

function anAttempt(move: string | null, result: Attempt['result'], overrides: Partial<Attempt> = {}): Attempt {
  return { ...aTurn(move ?? '').attempts[0], move, san: result === 'legal' ? move : null, result, ...overrides }
}

/** 1. e4 Nf6, the LLM's Nf6 after an invalid and an illegal try, written in UCI: a notation slip. */
const withMistakes = (): GameState => {
  const turn = aTurn('Nf6', {
    attempts: [
      anAttempt('Nf9', 'invalid'),
      anAttempt('Ke7', 'illegal'),
      anAttempt('g8f6', 'legal', { san: 'Nf6', notation_slip: true }),
    ],
  })
  return aGame({ plies: plies(E4, NF6), llm_turn: turn, llm_turns: [turn] })
}

const chips = () => [...moveList().querySelectorAll('.mistake')].map((chip) => chip.textContent)
/** The Lucide icons in an element, by name: the text carries no glyphs. */
const icons = (element: Element) =>
  [...element.querySelectorAll('svg.lucide')].map((icon) => [...icon.classList].find((name) => name.startsWith('lucide-'))!)

test("lists each LLM turn's illegal tries by kind and its notation slip under its move", () => {
  render(<MovesCard game={withMistakes()} />)

  expect(chips()).toEqual(['Nf9 invalid · try 1', 'Ke7 illegal · try 2', 'written "g8f6"'])
  expect([...moveList().querySelectorAll('.mistake')].map(icons)).toEqual([['lucide-x'], ['lucide-x'], ['lucide-pen-line']])
  // The illegal move struck through; the slip shown as a slip, not as an illegal move.
  expect(within(moveList()).getByText('Nf9').tagName).toBe('S')
  expect(within(moveList()).getByText('written "g8f6"')).toHaveClass('mistake', 'slip')
  expect(within(moveList()).getByText('written "g8f6"')).not.toHaveClass('illegal')
  // The move it played, in standard SAN, outlined in amber.
  expect(within(moveList()).getByText('Nf6')).toHaveClass('ply', 'slip')
})

test('a forfeited turn has no move, but its illegal tries show under the ply the LLM failed to play', () => {
  const turn = aTurn('', {
    attempts: [
      anAttempt('Nf9', 'invalid'),
      anAttempt('Ke7', 'illegal'),
      anAttempt('Nc6', 'illegal'),
      anAttempt('Bb4', 'ambiguous'),
    ],
  })
  render(<MovesCard game={aGame({ plies: plies(E4), llm_turn: turn, llm_turns: [turn], status: 'over' })} />)

  expect(rows()).toEqual([['1.', 'e4', '']])
  expect(chips()).toEqual([
    'Nf9 invalid · try 1',
    'Ke7 illegal · try 2',
    'Nc6 illegal · try 3',
    'Bb4 ambiguous · try 4',
  ])
})

test('a forfeit with no answer shows why', () => {
  const turn = aTurn('', { attempts: [anAttempt(null, 'timeout', { error: 'no answer within 300s' })] })
  render(<MovesCard game={aGame({ plies: plies(E4), llm_turn: turn, llm_turns: [turn], status: 'over' })} />)

  expect(chips()).toEqual(['no answer within 300s'])
  expect(within(moveList()).getByText('no answer within 300s')).toHaveClass('mistake', 'error')
  expect(icons(within(moveList()).getByText('no answer within 300s'))).toEqual(['lucide-triangle-alert'])
})

test("under Chaos rules a chaos move is listed as the LLM wrote it, in red, a spawn in purple, with no chip", () => {
  render(<MovesCard game={chaosGame(8)} />)

  expect(rows()).toEqual([
    ['1.', 'e4', 'Bb4'],
    ['2.', 'c3', 'Qg5'],
    ['3.', 'd4', 'e5'],
    ['4.', 'Bxg5', 'Qd5'],
  ])
  expect(within(moveList()).getByText('Bb4')).toHaveClass('chaos')
  expect(within(moveList()).getByText('Qg5')).toHaveClass('chaos')
  expect(within(moveList()).getByText('Qd5')).toHaveClass('spawn')
  expect(within(moveList()).getByText('Qd5')).not.toHaveClass('chaos')
  expect(within(moveList()).getByText('e5')).not.toHaveClass('chaos')
  expect(chips()).toEqual([])
})

test('an invalid try before a chaos move stays struck through under it', () => {
  const turn = aTurn('Bb4', { attempts: [anAttempt('Bb9', 'invalid'), chaosAttempt('Bb4', { kind: 'chaos', from: 'f8', to: 'b4', piece: 'b', rook: null, reason: 'the bishop on f8 moves' } as const)] })
  render(<MovesCard game={chaosGame(2, { llm_turn: turn, llm_turns: [turn] })} />)

  expect(chips()).toEqual(['Bb9 invalid · try 1'])
  expect(within(moveList()).getByText('Bb4')).toHaveClass('chaos')
})

/** The totals, a line per LLM side. */
const totals = () => [...screen.getByTestId('totals').children].map((line) => line.textContent)

test("the totals line counts the LLM's illegal tries and notation slips", () => {
  const game = withMistakes()
  const stats = { ...game.stats.black!, illegal_moves: { invalid: 1, illegal: 1, ambiguous: 0 }, notation_slips: 1 }
  render(<MovesCard game={{ ...game, stats: { white: null, black: stats } }} />)

  expect(totals()).toEqual(['2 illegal tries · 1 notation slip'])
  expect(icons(screen.getByTestId('totals'))).toEqual(['lucide-x', 'lucide-pen-line'])
})

test('the totals say one illegal try, and no notation slips', () => {
  const turn = aTurn('e5', { attempts: [anAttempt('Ke7', 'illegal'), anAttempt('e5', 'legal')] })
  render(<MovesCard game={aGame({ pgn: '1. e4 e5', llm_turn: turn, llm_turns: [turn] })} />)

  expect(totals()).toEqual(['1 illegal try · 0 notation slips'])
})

test('under Enforced decoding illegal tries are not applicable, unless one gets through anyway', () => {
  const enforced = aGame({ pgn: '1. e4 e5', llm_turns: [aTurn('e5')] })
  enforced.stats.black = { ...enforced.stats.black!, legal_move_streak: null, illegal_moves: null, recovered_turns: null }
  const { unmount } = render(<MovesCard game={enforced} />)

  expect(totals()).toEqual(['illegal tries n/a · 0 notation slips'])
  unmount()

  const turn = aTurn('e5', { attempts: [anAttempt('Ke7', 'illegal'), anAttempt('e5', 'legal')] })
  render(<MovesCard game={{ ...enforced, llm_turn: turn, llm_turns: [turn] }} />)

  expect(totals()).toEqual(['1 illegal try · 0 notation slips'])
})

test('in a faceoff there is a total per LLM side, named by its model', () => {
  const llm = { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' } as const
  const white = aTurn('e4', { ply: 1, color: 'white', attempts: [anAttempt('Ke2', 'illegal'), anAttempt('e4', 'legal')] })
  const game = aGame({
    pgn: '1. e4 e5',
    settings: { ...aGame().settings, mode: 'llm_faceoff', white: { ...llm, model: 'gemma3:4b' }, black: llm },
    llm_turns: [white, aTurn('e5')],
  })
  game.stats.white = game.stats.black
  render(<MovesCard game={game} />)

  expect(totals()).toEqual([
    'White · gemma3:4b 1 illegal try · 0 notation slips',
    'Black · qwen3.5:9b 0 illegal tries · 0 notation slips',
  ])
})

test('"Show LLM mistakes" hides the mistakes and the totals, and is kept in the browser', async () => {
  localStorage.clear()
  const { unmount } = render(<MovesCard game={withMistakes()} />)
  const toggle = screen.getByRole('switch', { name: 'Show LLM mistakes' })
  expect(toggle).toBeChecked()

  await userEvent.click(toggle)

  expect(toggle).not.toBeChecked()
  expect(chips()).toEqual([])
  expect(within(moveList()).getByText('Nf6')).not.toHaveClass('slip')
  expect(screen.queryByTestId('totals')).not.toBeInTheDocument()
  expect(rows()).toEqual([['1.', 'e4', 'Nf6']])
  expect(localStorage.getItem('chessllm.showMistakes')).toBe('off')

  unmount()
  render(<MovesCard game={withMistakes()} />)

  expect(screen.getByRole('switch', { name: 'Show LLM mistakes' })).not.toBeChecked()
  expect(chips()).toEqual([])

  await userEvent.click(screen.getByRole('switch', { name: 'Show LLM mistakes' }))

  expect(chips()).toHaveLength(3)
  expect(localStorage.getItem('chessllm.showMistakes')).toBe('on')
})
