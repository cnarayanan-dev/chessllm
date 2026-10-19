import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import App from '@/App'
import type { GameState } from '@/api/types'
import { playMoveSound } from '@/components/board/moveSound'
import { fakeBackend, later } from '@/test/fakeBackend'
import { theBoard } from '@/test/fakeChessboard'
import { aGame, aTurn, afterE4, afterE5 } from '@/test/games'

vi.mock('@/components/board/moveSound', () => ({ playMoveSound: vi.fn() }))

beforeEach(() => {
  vi.mocked(playMoveSound).mockClear()
})

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

const status = () => screen.getByTestId('status')

/** Plays a move on the board, once the board takes moves. */
async function drop(from: string, to: string) {
  const board = await waitFor(theBoard)
  await waitFor(() => expect(board.input).not.toBeNull())
  act(() => void board.drop(from, to))
}

const llmPlaysWhite = (overrides: Partial<GameState> = {}) =>
  aGame({
    human_legal_moves: [],
    settings: { ...aGame().settings, white: aGame().settings.black, black: { player: 'human' } },
    ...overrides,
  })

test('shows the current game: who plays whom, the status and the board', async () => {
  fakeBackend().on('GET /api/games/current', Response.json(aGame()))

  renderApp()

  expect(await screen.findByText('Your move (White)')).toBeInTheDocument()
  for (const chip of ['you play White', 'qwen3.5:9b', 'thinking off', 'free', 'explained feedback']) {
    expect(screen.getByText(chip)).toBeInTheDocument()
  }
  const board = theBoard()
  await waitFor(() => expect(board.input?.color).toBe('w'))
  expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
  expect(board.orientation).toBe('w')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('starts a game with the default settings when there is none', async () => {
  const backend = fakeBackend()
    .on('GET /api/games/current', Response.json({ detail: 'no game started' }, { status: 404 }))
    .on('POST /api/games', Response.json(aGame()))

  renderApp()

  expect(await screen.findByText('Your move (White)')).toBeInTheDocument()
  expect(backend.sentTo('POST /api/games')).toEqual([{ method: 'POST', path: '/api/games', body: undefined }])
})

test('says so when no game can be started', async () => {
  fakeBackend()
    .on('GET /api/games/current', Response.json({ detail: 'no game started' }, { status: 404 }))
    .on('POST /api/games', Response.json({ detail: 'Ollama is not running' }, { status: 400 }))

  renderApp()

  expect(await screen.findByText('Could not start a game')).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('Ollama is not running')
})

test("the human's move lands at once, then the LLM's turn runs and its move lands", async () => {
  const turn = later()
  const backend = fakeBackend()
    .on('GET /api/games/current', Response.json(aGame()))
    .on('POST /api/games/current/moves', Response.json(afterE4()))
    .on('POST /api/games/current/llm-turn', turn.promise)
  renderApp()

  await drop('e2', 'e4')

  expect(await screen.findByText('qwen3.5:9b is choosing a move… 0s')).toBeInTheDocument()
  expect(backend.sentTo('POST /api/games/current/moves')[0].body).toEqual({ uci: 'e2e4' })
  const board = theBoard()
  await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR'))
  expect(board.marked('last-move')).toEqual(['e2', 'e4'])
  expect(board.input).toBeNull()
  expect(playMoveSound).toHaveBeenCalledTimes(1)

  await act(async () => turn.resolve(Response.json(afterE5())))

  expect(await screen.findByText('Your move (White)')).toBeInTheDocument()
  await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR'))
  await waitFor(() => expect(board.input?.color).toBe('w'))
  expect(playMoveSound).toHaveBeenCalledTimes(2)
})

test("a thinking LLM's status says so, and its thinking can be shown once its move lands", async () => {
  const thinking = (game: GameState) => ({
    ...game,
    settings: { ...game.settings, black: { ...afterE4().settings.black, thinking: true } },
  })
  const turn = later()
  fakeBackend()
    .on('GET /api/games/current', Response.json(thinking(afterE4())))
    .on('POST /api/games/current/llm-turn', turn.promise)
  renderApp()

  expect(await screen.findByText('qwen3.5:9b is thinking… 0s')).toBeInTheDocument()
  expect(screen.getByText('Show thinking')).not.toBeVisible()

  const landed = aTurn('e5', { thinking: 'The king pawn, to fight for the centre.' })
  await act(async () => turn.resolve(Response.json(thinking(afterE5({ llm_turn: landed, llm_turns: [landed] })))))

  await userEvent.click(await screen.findByText('Show thinking'))
  expect(await screen.findByText('The king pawn, to fight for the centre.')).toBeVisible()
})

test('a rejected move shows the error and snaps the piece back', async () => {
  fakeBackend()
    .on('GET /api/games/current', Response.json(aGame()))
    .on('POST /api/games/current/moves', Response.json({ detail: 'illegal move: e2e4' }, { status: 400 }))
  renderApp()

  await drop('e2', 'e4')

  expect(await screen.findByRole('alert')).toHaveTextContent('illegal move: e2e4')
  const board = theBoard()
  await waitFor(() => expect(board.input?.color).toBe('w'))
  expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
  expect(status()).toHaveTextContent('Your move (White)')
  expect(playMoveSound).not.toHaveBeenCalled()
})

test('an LLM turn that fails shows the error, and the status says who is to move', async () => {
  fakeBackend()
    .on('GET /api/games/current', Response.json(afterE4()))
    .on('POST /api/games/current/llm-turn', new TypeError('Failed to fetch'))
  renderApp()

  expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch')
  expect(status()).toHaveTextContent('Waiting for Black…')
})

test('the end-of-game banner names the result and the reason, with a New game button', async () => {
  const over = afterE5({ status: 'over', result: '0-1', end_reason: 'checkmate', human_legal_moves: [] })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  const banner = await screen.findByTestId('banner')
  expect(within(banner).getByText('Black wins')).toBeInTheDocument()
  expect(within(banner).getByText('by checkmate')).toBeInTheDocument()
  expect(within(banner).getByRole('button', { name: 'New game' })).toBeInTheDocument()
  expect(status()).toHaveTextContent('Game over')
  await waitFor(() => expect(theBoard().position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR'))
  expect(theBoard().input).toBeNull()
})

test('a forfeit with no answer says why in the banner', async () => {
  const forfeit = aTurn('e5', {
    attempts: [{ ...aTurn('e5').attempts[0], move: null, san: null, result: 'timeout', error: 'no answer in 300 s' }],
  })
  const over = afterE4({ llm_turn: forfeit, llm_turns: [forfeit], status: 'over', result: '1-0', end_reason: 'forfeit' })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  expect(await screen.findByText('White wins')).toBeInTheDocument()
  expect(screen.getByText('by forfeit: no answer in 300 s')).toBeInTheDocument()
})

test('a draw at the Move cap names the cap in the banner', async () => {
  const over = afterE5({ status: 'over', result: '1/2-1/2', end_reason: 'move_cap', human_legal_moves: [] })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  const banner = await screen.findByTestId('banner')
  expect(within(banner).getByText('Draw')).toBeInTheDocument()
  expect(within(banner).getByText('at the move cap of 150 moves each')).toBeInTheDocument()
})

test('an end reason the page has no wording for is spelled out', async () => {
  const over = afterE4({ status: 'over', result: '1-0', end_reason: 'king_capture' })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  expect(await screen.findByText('by king capture')).toBeInTheDocument()
})

test('playing Black: the board turns, and the LLM opens', async () => {
  const turn = later()
  const backend = fakeBackend()
    .on('GET /api/games/current', Response.json(llmPlaysWhite()))
    .on('POST /api/games/current/llm-turn', turn.promise)

  renderApp()

  expect(await screen.findByText('qwen3.5:9b is choosing a move… 0s')).toBeInTheDocument()
  expect(screen.getByText('you play Black')).toBeInTheDocument()
  await waitFor(() => expect(theBoard().orientation).toBe('b'))
  expect(backend.sentTo('POST /api/games/current/llm-turn')).toHaveLength(1)
})

test("New game starts a game with the running game's settings and drops the abandoned game's LLM turn", async () => {
  const abandoned = later()
  const backend = fakeBackend()
    .on('GET /api/games/current', Response.json(afterE4()))
    .on('POST /api/games/current/llm-turn', abandoned.promise)
    .on('POST /api/games', Response.json(aGame({ game_id: 'game-2' })))
  renderApp()
  expect(await screen.findByText('qwen3.5:9b is choosing a move… 0s')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'New game' }))
  expect(await screen.findByText('Your move (White)')).toBeInTheDocument()
  await act(async () => abandoned.resolve(Response.json(afterE5())))

  expect(backend.sentTo('POST /api/games')[0].body).toEqual({
    mode: 'play_llm',
    white: { player: 'human' },
    black: { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
    rules: 'standard',
  })
  expect(status()).toHaveTextContent('Your move (White)')
  await waitFor(() => expect(theBoard().position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))
  expect(playMoveSound).not.toHaveBeenCalled()
})

test('New game in the banner starts the next game', async () => {
  const over = afterE5({ status: 'over', result: '1/2-1/2', end_reason: 'stalemate', human_legal_moves: [] })
  fakeBackend()
    .on('GET /api/games/current', Response.json(over))
    .on('POST /api/games', Response.json(aGame({ game_id: 'game-2' })))
  renderApp()

  const banner = await screen.findByTestId('banner')
  expect(within(banner).getByText('Draw')).toBeInTheDocument()
  expect(within(banner).getByText('by stalemate')).toBeInTheDocument()
  await userEvent.click(within(banner).getByRole('button', { name: 'New game' }))

  expect(await screen.findByText('Your move (White)')).toBeInTheDocument()
  expect(screen.queryByTestId('banner')).not.toBeInTheDocument()
})
