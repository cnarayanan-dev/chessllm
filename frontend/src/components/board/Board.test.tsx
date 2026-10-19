import { render, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { Board } from '@/components/board/Board'
import { theBoard } from '@/test/fakeChessboard'

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

test('draws the position with Merida pieces on the brown board', async () => {
  render(<Board fen={START} orientation="white" />)

  const board = theBoard()
  await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))
  expect(board.orientation).toBe('w')
  expect(board.props.style).toMatchObject({ cssClass: 'lichess', pieces: { file: '/static/pieces/merida.svg' } })
})

const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

test('a new position or orientation reaches the same board', async () => {
  const { rerender } = render(<Board fen={START} orientation="white" />)
  const board = theBoard()

  rerender(<Board fen={AFTER_E4} orientation="black" />)

  await waitFor(() => expect(board.orientation).toBe('b'))
  expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR')
  expect(theBoard()).toBe(board)
})

// 1. e4 f5 2. Qh5+
const BLACK_IN_CHECK = 'rnbqkbnr/ppppp1pp/8/5p1Q/4P3/8/PPPP1PPP/RNB1KBNR b KQkq - 1 2'

test('tints the last move and the king in check, on the same board', async () => {
  const { rerender } = render(<Board fen={AFTER_E4} orientation="white" lastMove="e2e4" />)
  const board = theBoard()
  await waitFor(() => expect(board.marked('last-move')).toEqual(['e2', 'e4']))
  expect(board.marked('check')).toEqual([])

  rerender(<Board fen={BLACK_IN_CHECK} orientation="white" lastMove="d1h5" check />)

  await waitFor(() => expect(board.marked('check')).toEqual(['e8']))
  expect(board.marked('last-move')).toEqual(['d1', 'h5'])
  expect(theBoard()).toBe(board)
})

const AFTER_E5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
const AFTER_NF3 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2'

test('a move replayed from the history animates in from the position before it', async () => {
  const { rerender } = render(<Board fen={AFTER_NF3} orientation="white" lastMove="g1f3" />)
  const board = theBoard()
  await waitFor(() => expect(board.positionsSet).toHaveLength(1))

  // Back to 1… e5: the board jumps to the position after 1. e4, then plays e7e5.
  rerender(<Board fen={AFTER_E5} orientation="white" lastMove="e7e5" animateFrom={AFTER_E4} />)

  await waitFor(() => expect(board.positionsSet).toHaveLength(3))
  expect(board.positionsSet.slice(1)).toEqual([
    { position: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR', animated: false },
    { position: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR', animated: true },
  ])
  expect(board.marked('last-move')).toEqual(['e5', 'e7'])
})

test('a replayed move is not replayed again when only other props change', async () => {
  const { rerender } = render(<Board fen={AFTER_E5} orientation="white" lastMove="e7e5" animateFrom={AFTER_E4} />)
  const board = theBoard()
  await waitFor(() => expect(board.positionsSet).toHaveLength(2))

  // A state lands while the history is viewed: the board gets new legal moves, but shows the same position.
  rerender(<Board fen={AFTER_E5} orientation="white" lastMove="e7e5" animateFrom={AFTER_E4} legalMoves={[]} />)

  await waitFor(() => expect(board.positionsSet).toHaveLength(3))
  expect(board.positionsSet.at(-1)).toEqual({ position: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR', animated: true })
})

test('stepping quickly through the history skips the positions already left behind', async () => {
  const { rerender } = render(<Board fen={START} orientation="white" />)
  const board = theBoard()

  rerender(<Board fen={AFTER_E4} orientation="white" lastMove="e2e4" animateFrom={START} />)
  rerender(<Board fen={AFTER_E5} orientation="white" lastMove="e7e5" animateFrom={AFTER_E4} />)

  await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR'))
  // Only the last step is drawn: e5 played from the position before it.
  expect(board.positionsSet).toEqual([
    { position: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR', animated: false },
    { position: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR', animated: true },
  ])
  expect(board.marked('last-move')).toEqual(['e5', 'e7'])
})

test("a spawn's drop tints only the square it appeared on", async () => {
  render(<Board fen={AFTER_E5} orientation="white" lastMove="Q@d5" />)
  const board = theBoard()

  await waitFor(() => expect(board.marked('last-move')).toEqual(['d5']))
})

// 1. e4 d5, White to move. Only some of White's legal moves: the board takes the list as given (ADR 0001).
const SCANDINAVIAN = 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
const SOME_LEGAL_MOVES = ['e4e5', 'e4d5', 'g1f3', 'g1h3']

test('a picked-up piece shows its square, a dot where it can go and a ring where it captures', async () => {
  render(<Board fen={SCANDINAVIAN} orientation="white" input="white" legalMoves={SOME_LEGAL_MOVES} onMove={vi.fn()} />)
  const board = theBoard()
  await waitFor(() => expect(board.input?.color).toBe('w'))

  expect(board.pickUp('e4')).toBe(true)
  expect(board.marked('selected')).toEqual(['e4'])
  expect(board.marked('target-dot')).toEqual(['e5'])
  expect(board.marked('target-ring')).toEqual(['d5'])

  expect(board.pickUp('d2')).toBe(false) // no legal move from d2 in the list
})

test('a legal drop reports the move as UCI and locks the board until the next position', async () => {
  const onMove = vi.fn()
  render(<Board fen={SCANDINAVIAN} orientation="white" input="white" legalMoves={SOME_LEGAL_MOVES} onMove={onMove} />)
  const board = theBoard()
  await waitFor(() => expect(board.input).not.toBeNull())

  board.pickUp('g1')
  expect(board.drop('g1', 'f3')).toBe(true)

  expect(onMove).toHaveBeenCalledExactlyOnceWith('g1f3')
  expect(board.input).toBeNull()
  expect(board.marked('target-dot')).toEqual([])
})

test('an illegal drop snaps back and reports nothing', async () => {
  const onMove = vi.fn()
  render(<Board fen={SCANDINAVIAN} orientation="white" input="white" legalMoves={SOME_LEGAL_MOVES} onMove={onMove} />)
  const board = theBoard()
  await waitFor(() => expect(board.input).not.toBeNull())

  board.pickUp('e4')
  expect(board.drop('e4', 'e6')).toBe(false)

  expect(onMove).not.toHaveBeenCalled()
  expect(board.input).not.toBeNull()
})

test('giving the same position again after a move unlocks the board', async () => {
  const { rerender } = render(<Board fen={SCANDINAVIAN} orientation="white" input="white" legalMoves={SOME_LEGAL_MOVES} />)
  const board = theBoard()
  await waitFor(() => expect(board.input).not.toBeNull())
  board.drop('g1', 'f3')

  // The backend refused the move: the same position comes back with the legal moves.
  rerender(<Board fen={SCANDINAVIAN} orientation="white" input="white" legalMoves={[...SOME_LEGAL_MOVES]} />)

  await waitFor(() => expect(board.input).not.toBeNull())
  expect(board.position).toBe('rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR')
})

// Black's pawn on b2 can promote on b1, or on a1 by capturing the rook.
const BLACK_PROMOTES = '4k3/8/8/8/8/8/1p6/R3K3 b - - 0 1'
const PROMOTIONS = ['b2b1q', 'b2b1r', 'b2b1b', 'b2b1n', 'b2a1q', 'b2a1r', 'b2a1b', 'b2a1n', 'e8d7']

test('a drop onto the last rank asks for the promotion piece and reports it', async () => {
  const onMove = vi.fn()
  render(<Board fen={BLACK_PROMOTES} orientation="black" input="black" legalMoves={PROMOTIONS} onMove={onMove} />)
  const board = theBoard()
  await waitFor(() => expect(board.input).not.toBeNull())

  board.pickUp('b2')
  expect(board.marked('target-dot')).toEqual(['b1'])
  expect(board.marked('target-ring')).toEqual(['a1'])
  expect(board.drop('b2', 'a1')).toBe(true)
  expect(board.promotion).toMatchObject({ square: 'a1', color: 'b' })
  expect(onMove).not.toHaveBeenCalled()

  board.choosePromotion('n')

  expect(onMove).toHaveBeenCalledExactlyOnceWith('b2a1n')
})

test('closing the promotion dialog puts the pawn back and reports nothing', async () => {
  const onMove = vi.fn()
  render(<Board fen={BLACK_PROMOTES} orientation="black" input="black" legalMoves={PROMOTIONS} onMove={onMove} />)
  const board = theBoard()
  await waitFor(() => expect(board.input).not.toBeNull())
  board.drop('b2', 'b1')
  board.position = '4k3/8/8/8/8/8/8/Rp2K3' // where cm-chessboard leaves the dropped pawn

  board.choosePromotion(null)

  await waitFor(() => expect(board.position).toBe('4k3/8/8/8/8/8/1p6/R3K3'))
  expect(board.input).not.toBeNull()
  expect(onMove).not.toHaveBeenCalled()
})

test('the board takes no moves when there is no side to input, or no legal move', async () => {
  const { rerender } = render(<Board fen={SCANDINAVIAN} orientation="white" input="white" legalMoves={SOME_LEGAL_MOVES} />)
  const board = theBoard()
  await waitFor(() => expect(board.input).not.toBeNull())

  rerender(<Board fen={SCANDINAVIAN} orientation="white" input={null} legalMoves={SOME_LEGAL_MOVES} />)
  await waitFor(() => expect(board.input).toBeNull())

  rerender(<Board fen={SCANDINAVIAN} orientation="white" input="white" legalMoves={[]} />)
  await new Promise((resolve) => setTimeout(resolve))
  expect(board.input).toBeNull()
})

test('the board is destroyed when it leaves the page', () => {
  const { unmount } = render(<Board fen={START} orientation="white" />)

  unmount()

  expect(theBoard().destroyed).toBe(true)
})

const AFTER_CHAOS_BB4 = 'rnbqk1nr/pppppppp/8/8/1b2P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2'

test("a chaos move's arrows and a spawn's marker are drawn on the position, and cleared with the next one", async () => {
  const { rerender } = render(
    <Board fen={AFTER_CHAOS_BB4} orientation="white" lastMove="f8b4" arrows={[['f8', 'b4']]} />,
  )
  const board = theBoard()
  await waitFor(() => expect(board.arrows).toEqual([{ class: 'chaos-arrow', from: 'f8', to: 'b4' }]))
  expect(board.marked('spawn')).toEqual([])

  rerender(<Board fen={AFTER_E4} orientation="white" lastMove="Q@d5" spawn="d5" />)

  await waitFor(() => expect(board.marked('spawn')).toEqual(['d5']))
  expect(board.arrows).toEqual([])
  expect(board.marked('last-move')).toEqual(['d5'])

  rerender(<Board fen={AFTER_E4} orientation="white" lastMove="e2e4" />)

  await waitFor(() => expect(board.marked('spawn')).toEqual([]))
})
