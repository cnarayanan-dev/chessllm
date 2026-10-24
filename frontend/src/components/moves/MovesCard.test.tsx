import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import type { Attempt, GameState } from '@/api/types'
import { MovesCard } from '@/components/moves/MovesCard'
import { aGame, aTurn, chaosAttempt, chaosGame, E4, E5, NF3, plies, STOCKFISH } from '@/test/games'

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

/** chaosGame(6) with Black's 3...e5 written in UCI: a notation slip. */
const chaosWithSlip = (): GameState => {
  const game = chaosGame(6)
  const slip = anAttempt('e7e5', 'legal', { san: 'e5', notation_slip: true })
  return { ...game, llm_turns: game.llm_turns.map((turn) => (turn.ply === 6 ? { ...turn, attempts: [slip] } : turn)) }
}

test('under Chaos rules notation slips are not shown in the move list, and the switch is "Show rule-breaking"', () => {
  render(<MovesCard game={chaosWithSlip()} />)

  expect(chips()).toEqual([])
  expect(within(moveList()).getByText('e5')).not.toHaveClass('slip')
  expect(screen.getByRole('switch', { name: 'Show rule-breaking' })).toBeChecked()
  expect(screen.queryByRole('switch', { name: 'Show LLM mistakes' })).not.toBeInTheDocument()
})

/** The LLM mistakes card's rows, cell by cell: White's number, the metric, Black's number, for the LLM sides. */
const mistakes = () =>
  [...screen.getByTestId('mistakes-card').querySelectorAll('tbody tr')].map((row) =>
    [...row.children].map((cell) => cell.textContent),
  )

test("the LLM mistakes card counts the LLM's illegal tries and notation slips", () => {
  const game = withMistakes()
  const stats = { ...game.stats.black!, illegal_moves: { invalid: 1, illegal: 1, ambiguous: 0 }, notation_slips: 1 }
  render(<MovesCard game={{ ...game, stats: { white: null, black: stats } }} />)

  expect(within(screen.getByTestId('mistakes-card')).getByText('LLM mistakes')).toBeInTheDocument()
  expect(mistakes()).toEqual([
    ['Illegal tries', '2'],
    ['Notation slips', '1'],
  ])
  expect(icons(screen.getByTestId('mistakes-card'))).toEqual(['lucide-x', 'lucide-pen-line'])
})

test('under Chaos rules the card is Rule-breaking: one Illegal moves row for illegal tries and chaos moves, then Spawns', () => {
  render(<MovesCard game={chaosWithSlip()} />)
  const card = screen.getByTestId('mistakes-card')

  expect(within(card).getByText('Rule-breaking')).toBeInTheDocument()
  expect(mistakes()).toEqual([
    ['Illegal moves', '2'],
    ['Spawns', '0'],
  ])
  expect(icons(card)).toEqual(['lucide-x', 'lucide-sparkles'])
  expect(within(card).getByText('Illegal moves')).toHaveAttribute(
    'aria-description',
    'Illegal moves, played anyway, or retried if they could not be read.',
  )
})

describe('the Chaos gain row', () => {
  const gain = (vs_counterpart: number | null) => ({
    best_evaluation: { pawns: 0, mate: null, unjudged: null },
    vs_counterpart,
    vs_best: 5,
  })
  /** A Legal counterpart that gave a move, or with `failed` one that gave none. */
  const counterpart = (failed = false) => ({
    move: failed ? null : 'e7e5',
    san: failed ? null : 'e5',
    fen_after: failed ? null : 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
    attempt: aTurn('e5').attempts[0],
  })
  /** chaosGame(8), Black's Chaos moves Bb4, Qg5 and the spawn Qd5 with the gains given, judged by Stockfish; the
  Legal counterparts at the indexes in `failed` gave no move. */
  const withGains = (gains: (number | null)[], switchOn = true, failed: number[] = []): GameState => {
    const game = chaosGame(8)
    const chaosPlies = [2, 4, 8]
    const turns = game.llm_turns.map((turn) => {
      const index = chaosPlies.indexOf(turn.ply)
      return index >= 0 && index < gains.length
        ? { ...turn, legal_counterpart: counterpart(failed.includes(index)), chaos_gain: gain(gains[index]) }
        : turn
    })
    return { ...game, llm_turns: turns, evaluator: STOCKFISH, settings: { ...game.settings, legal_counterpart: switchOn } }
  }
  const row = () => mistakes().find((cells) => cells.includes('Chaos gain'))

  test("sums each side's judged gains over the Legal counterpart, leaving those not judged out", async () => {
    render(<MovesCard game={withGains([6.6, null, -2.1])} />)

    expect(row()).toEqual(['Chaos gain', '+4.5'])
    const card = screen.getByTestId('mistakes-card')
    expect(icons(card).at(-1)).toBe('lucide-trending-up-down')
    const total = within(card).getByText('+4.5')
    expect(total).toHaveAttribute('aria-description', 'Adds up 3 Chaos moves; 1 not judged is left out.')
  })

  test('leaves out a Chaos move whose Legal counterpart gave no move: it has no gain', () => {
    render(<MovesCard game={withGains([6.6, null, -2.1], true, [1])} />)

    expect(row()).toEqual(['Chaos gain', '+4.5'])
    expect(within(screen.getByTestId('mistakes-card')).getByText('+4.5')).toHaveAttribute(
      'aria-description',
      'Adds up 2 Chaos moves.',
    )
  })

  test('is 0.0 before the first Chaos move', () => {
    render(<MovesCard game={withGains([])} />)

    expect(row()).toEqual(['Chaos gain', '0.0'])
    expect(within(screen.getByTestId('mistakes-card')).getByText('0.0')).toHaveAttribute(
      'aria-description',
      'Adds up 0 Chaos moves.',
    )
  })

  test('is not shown with the Legal counterpart switch off, under Standard rules, or without an evaluator', () => {
    const { unmount } = render(<MovesCard game={withGains([6.6], false)} />)
    expect(row()).toBeUndefined()
    unmount()

    render(<MovesCard game={{ ...withGains([6.6]), evaluator: undefined }} />)
    expect(row()).toBeUndefined()
  })
})

test('under Enforced decoding illegal tries are not applicable, unless one gets through anyway', () => {
  const enforced = aGame({ pgn: '1. e4 e5', llm_turns: [aTurn('e5')] })
  enforced.stats.black = { ...enforced.stats.black!, legal_move_streak: null, illegal_moves: null, recovered_turns: null }
  const { unmount } = render(<MovesCard game={enforced} />)

  expect(mistakes()[0]).toEqual(['Illegal tries', '–'])
  unmount()

  const turn = aTurn('e5', { attempts: [anAttempt('Ke7', 'illegal'), anAttempt('e5', 'legal')] })
  render(<MovesCard game={{ ...enforced, llm_turn: turn, llm_turns: [turn] }} />)

  expect(mistakes()[0]).toEqual(['Illegal tries', '1'])
})

test('in a faceoff the sides are head to head, White left and Black right, the side with more in red', () => {
  const llm = { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained', turn_memory: 'fresh' } as const
  const white = aTurn('e4', { ply: 1, color: 'white', attempts: [anAttempt('Ke2', 'illegal'), anAttempt('e4', 'legal')] })
  const game = aGame({
    pgn: '1. e4 e5',
    settings: { ...aGame().settings, mode: 'llm_faceoff', white: { ...llm, model: 'gemma3:4b' }, black: llm },
    llm_turns: [white, aTurn('e5')],
  })
  game.stats.white = game.stats.black
  render(<MovesCard game={game} />)

  const card = screen.getByTestId('mistakes-card')
  expect([...card.querySelectorAll('thead th')].map((head) => head.textContent)).toEqual(['White', '', 'Black'])
  expect(within(card).getByText('White')).toHaveAttribute('aria-description', 'gemma3:4b')
  expect(within(card).getByText('Black')).toHaveAttribute('aria-description', 'qwen3.5:9b')
  expect(mistakes()).toEqual([
    ['1', 'Illegal tries', '0'],
    ['0', 'Notation slips', '0'],
  ])
  expect([...card.querySelectorAll('[data-more]')].map((cell) => cell.textContent)).toEqual(['1'])
})

test("a metric's name and meaning show in its tooltip on hover, and in aria-description", async () => {
  render(<MovesCard game={withMistakes()} />)
  const slips = within(screen.getByTestId('mistakes-card')).getByText('Notation slips')

  expect(slips).toHaveAttribute('aria-description', 'Legal moves written in the wrong notation.')
  await userEvent.hover(slips)
  const tooltip = (await screen.findByText('Legal moves written in the wrong notation.')).closest(
    '[data-slot=tooltip-content]',
  )
  expect(tooltip).toHaveTextContent('Notation slips Legal moves written in the wrong notation.')
})

test('in a faceoff a tie is not in red', () => {
  const llm = { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained', turn_memory: 'fresh' } as const
  const white = aTurn('e4', { ply: 1, color: 'white', attempts: [anAttempt('Ke2', 'illegal'), anAttempt('e4', 'legal')] })
  const black = aTurn('e5', { attempts: [anAttempt('Ke7', 'illegal'), anAttempt('e5', 'legal')] })
  const game = aGame({
    pgn: '1. e4 e5',
    settings: { ...aGame().settings, mode: 'llm_faceoff', white: { ...llm, model: 'gemma3:4b' }, black: llm },
    llm_turns: [white, black],
  })
  game.stats.white = game.stats.black
  render(<MovesCard game={game} />)

  expect(mistakes()[0]).toEqual(['1', 'Illegal tries', '1'])
  expect(screen.getByTestId('mistakes-card').querySelector('[data-more]')).toBeNull()
})

test('"Show LLM mistakes" hides the mistakes and the LLM mistakes card, and is kept in the browser', async () => {
  localStorage.clear()
  const { unmount } = render(<MovesCard game={withMistakes()} />)
  const toggle = screen.getByRole('switch', { name: 'Show LLM mistakes' })
  expect(toggle).toBeChecked()

  await userEvent.click(toggle)

  expect(toggle).not.toBeChecked()
  expect(chips()).toEqual([])
  expect(within(moveList()).getByText('Nf6')).not.toHaveClass('slip')
  expect(screen.queryByTestId('mistakes-card')).not.toBeInTheDocument()
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
