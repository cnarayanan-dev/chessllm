import { act, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { Attempt, LlmTurn } from '@/api/types'
import { Board } from '@/components/board/Board'
import { BoardFlashes } from '@/components/board/BoardFlashes'
import type { Flash } from '@/game/gameLoop'
import { aTurn, chaosAttempt } from '@/test/games'

afterEach(() => {
  vi.useRealTimers()
})

function anAttempt(move: string | null, result: Attempt['result'], overrides: Partial<Attempt> = {}): Attempt {
  return { ...aTurn(move ?? '').attempts[0], move, san: result === 'legal' ? move : null, result, ...overrides }
}

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

const withFlash = (flash: Flash | null) => (
  <Board fen={START} orientation="white">
    <BoardFlashes flash={flash} maxAttempts={5} />
  </Board>
)

/** The board, then a turn landing on it. */
function renderFlash(turn: LlmTurn, landedOn: string | null = 'f6', id = 1) {
  const view = render(withFlash(null))
  view.rerender(withFlash({ id, turn, landedOn }))
  return view
}

/** The card in the middle of the board: its head, then a line per illegal try. */
const card = () => {
  const element = document.querySelector('.center-flash')
  if (!element) return null
  return [...element.children].map((child) => child.textContent)
}

test("an LLM turn's illegal tries are listed in the middle of the board, by kind, out of the game's tries", () => {
  renderFlash(aTurn('Nf6', { attempts: [anAttempt('Nf9', 'invalid'), anAttempt('Ke7', 'illegal'), anAttempt('Nf6', 'legal')] }))

  expect(card()).toEqual(['✗ LLM move illegal ×2', 'Nf9 invalid · try 1 of 5', 'Ke7 illegal · try 2 of 5'])
  expect(screen.getByText('Nf9').tagName).toBe('S')
})

test('under Chaos rules, the chaos move played is not an illegal try: only the badly formed one before it is', () => {
  renderFlash(aTurn('Bb4', { attempts: [anAttempt('Bb9', 'invalid'), chaosAttempt('Bb4', { kind: 'chaos', from: 'f8', to: 'b4', piece: 'b', rook: null, reason: 'the bishop on f8 moves' } as const)] }))

  expect(card()).toEqual(['✗ LLM move illegal', 'Bb9 invalid · try 1 of 5'])
})

test('a chaos move at the first try flashes nothing in the middle of the board', () => {
  renderFlash(aTurn('Bb4', { attempts: [chaosAttempt('Bb4', { kind: 'chaos', from: 'f8', to: 'b4', piece: 'b', rook: null, reason: 'the bishop on f8 moves' } as const)] }))

  expect(card()).toBeNull()
})

test('one illegal try has no count', () => {
  renderFlash(aTurn('Nf6', { attempts: [anAttempt('Bb4', 'ambiguous'), anAttempt('Nf6', 'legal')] }))

  expect(card()).toEqual(['✗ LLM move illegal', 'Bb4 ambiguous · try 1 of 5'])
})

test('a forfeit after four illegal moves', () => {
  const tries = ['Nf9', 'Ke7', 'Nc6', 'Qh4'].map((move) => anAttempt(move, 'illegal'))
  renderFlash(aTurn('', { attempts: tries }))

  expect(card()).toEqual([
    '✗ LLM forfeits: 4 illegal moves',
    'Nf9 illegal · try 1 of 5',
    'Ke7 illegal · try 2 of 5',
    'Nc6 illegal · try 3 of 5',
    'Qh4 illegal · try 4 of 5',
  ])
})

test('a forfeit with no answer says why', () => {
  renderFlash(aTurn('', { attempts: [anAttempt(null, 'timeout', { error: 'no answer within 300s' })] }))

  expect(card()).toEqual(['✗ LLM forfeits: no answer', '⚠ no answer within 300s'])
})

test('a notation slip rings the square the move landed on, with what the LLM wrote, and is not an illegal move', () => {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    if (this.classList.contains('board-wrap')) return DOMRect.fromRect({ x: 100, y: 50, width: 480, height: 480 })
    if (this.getAttribute('data-square') === 'f6') return DOMRect.fromRect({ x: 400, y: 170, width: 60, height: 60 })
    return DOMRect.fromRect({ x: 0, y: 0, width: 0, height: 0 })
  })
  renderFlash(aTurn('Nf6', { attempts: [anAttempt('g8f6', 'legal', { san: 'Nf6', notation_slip: true })] }))

  expect(card()).toBeNull()
  const ring = document.querySelector<HTMLElement>('.square-ring')!
  expect([ring.style.left, ring.style.top, ring.style.width, ring.style.height]).toEqual(['300px', '120px', '60px', '60px'])
  const bubble = document.querySelector<HTMLElement>('.bubble')!
  expect(bubble.textContent).toBe('⚑ written "g8f6" → Nf6')
  expect([bubble.style.left, bubble.style.top]).toEqual(['330px', '120px'])
  vi.mocked(Element.prototype.getBoundingClientRect).mockRestore()
})

test('a clean turn flashes nothing', () => {
  renderFlash(aTurn('e5'))

  expect(document.querySelector('.flash')).toBeNull()
})

test('the flashes clear after 7 seconds, once faded out', () => {
  vi.useFakeTimers()
  renderFlash(aTurn('Nf6', { attempts: [anAttempt('Ke7', 'illegal'), anAttempt('g8f6', 'legal', { san: 'Nf6', notation_slip: true })] }))
  expect(document.querySelectorAll('.flash')).toHaveLength(3)

  act(() => void vi.advanceTimersByTime(7000))
  expect(document.querySelectorAll('.flash')).toHaveLength(3) // fading out

  act(() => void vi.advanceTimersByTime(400))
  expect(document.querySelectorAll('.flash')).toHaveLength(0)
})

test("the next turn's flashes replace the last one's, for another 7 seconds", () => {
  vi.useFakeTimers()
  const first = aTurn('Nf6', { attempts: [anAttempt('Ke7', 'illegal'), anAttempt('Nf6', 'legal')] })
  const { rerender } = renderFlash(first)
  act(() => void vi.advanceTimersByTime(5000))

  const second = aTurn('Nc6', { attempts: [anAttempt('Nc9', 'invalid'), anAttempt('Nc6', 'legal')] })
  rerender(withFlash({ id: 2, turn: second, landedOn: 'c6' }))
  expect(card()).toEqual(['✗ LLM move illegal', 'Nc9 invalid · try 1 of 5'])

  act(() => void vi.advanceTimersByTime(5000))
  expect(card()).not.toBeNull()
})

test('no flash, nothing laid over the board', () => {
  render(withFlash(null))

  expect(document.querySelector('.flash')).toBeNull()
})
