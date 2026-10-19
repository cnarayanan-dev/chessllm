import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import App from '@/App'
import type { GameState } from '@/api/types'
import { playMoveSound } from '@/components/board/moveSound'
import { fakeBackend, later } from '@/test/fakeBackend'
import { theBoard } from '@/test/fakeChessboard'
import { aGame, aTurn, afterE4, afterE5, chaosGame } from '@/test/games'

vi.mock('@/components/board/moveSound', () => ({ playMoveSound: vi.fn(), isMoveSoundOn: () => true, setMoveSoundOn: vi.fn() }))

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

test('credits the Merida pieces and the move sound', async () => {
  fakeBackend().on('GET /api/games/current', Response.json(aGame()))

  renderApp()

  expect(await screen.findByText(/Pieces: Merida by Armando Hernandez Marroquin, GPLv2\+/)).toBeVisible()
  expect(screen.getByText(/Move sound: Kenney, CC0/)).toBeVisible()
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
  const over = afterE4({ status: 'over', result: '1-0', end_reason: 'variant_win' })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  expect(await screen.findByText('by variant win')).toBeInTheDocument()
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
    max_attempts: 5,
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

describe('settings', () => {
  const models = [{ name: 'qwen3.5:9b', thinking: true, sampling: {} }]
  const topBar = () => screen.getByRole('banner')

  test('the settings button opens the modal; a change is pending in the top bar, and the running game keeps its settings', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(aGame())).on('GET /api/models', Response.json(models))
    renderApp()
    await screen.findByText('Your move (White)')
    expect(within(topBar()).queryByText('changes apply next game')).not.toBeInTheDocument()

    await userEvent.click(within(topBar()).getByRole('button', { name: /Settings/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Settings' })
    await userEvent.click(within(dialog).getByRole('radio', { name: /^Black/ }))
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    expect(within(topBar()).getByText('changes apply next game')).toBeInTheDocument()
    expect(within(topBar()).getByText('you play White')).toBeInTheDocument()
    expect(status()).toHaveTextContent('Your move (White)')
  })

  test('New game starts the next game, after which no change is pending', async () => {
    const backend = fakeBackend()
      .on('GET /api/games/current', Response.json(aGame()))
      .on('GET /api/models', Response.json(models))
      .on('POST /api/games', Response.json(llmPlaysWhite({ game_id: 'game-2' })))
      .on('POST /api/games/current/llm-turn', later().promise)
    renderApp()
    await screen.findByText('Your move (White)')

    await userEvent.keyboard('{Meta>}k{/Meta}')
    await userEvent.click(await screen.findByRole('radio', { name: /^Black/ }))
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await userEvent.click(within(topBar()).getByRole('button', { name: 'New game' }))

    expect(await within(topBar()).findByText('you play Black')).toBeInTheDocument()
    expect(backend.sentTo('POST /api/games')[0].body).toEqual({
      mode: 'play_llm',
      white: { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
      black: { player: 'human' },
      rules: 'standard',
      max_attempts: 5,
    })
    expect(within(topBar()).queryByText('changes apply next game')).not.toBeInTheDocument()
  })

  test('an LLM faceoff started from the modal plays itself to the end, White at the bottom and the board locked', async () => {
    const llm = afterE4().settings.black
    const settings = { ...aGame().settings, mode: 'llm_faceoff' as const, white: llm, black: llm }
    const faceoff = (overrides: Partial<GameState>) =>
      aGame({ game_id: 'game-2', human_legal_moves: [], settings, ...overrides })
    const white = aTurn('e4', { ply: 1, color: 'white' })
    const black = aTurn('e5', { ply: 2, color: 'black' })
    const third = later()
    const backend = fakeBackend()
      .on('GET /api/games/current', Response.json(aGame()))
      .on('GET /api/models', Response.json(models))
      .on('POST /api/games', Response.json(faceoff({})))
      .on(
        'POST /api/games/current/llm-turn',
        Response.json(faceoff({ fen: afterE4().fen, turn: 'black', last_move: 'e2e4', llm_turn: white, llm_turns: [white] })),
        Response.json(faceoff({ fen: afterE5().fen, last_move: 'e7e5', llm_turn: black, llm_turns: [white, black] })),
        third.promise,
      )
    renderApp()
    await screen.findByText('Your move (White)')

    await userEvent.keyboard('{Meta>}k{/Meta}')
    await userEvent.click(await screen.findByRole('radio', { name: /^LLM faceoff/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Start new game' }))

    // Each turn is asked for as soon as the last one lands: the third runs.
    await waitFor(() => expect(backend.sentTo('POST /api/games/current/llm-turn')).toHaveLength(3))
    expect(status()).toHaveTextContent('♔ White · qwen3.5:9b is choosing a move… 0s')
    expect(backend.sentTo('POST /api/games')[0].body).toMatchObject({ mode: 'llm_faceoff', white: llm, black: llm })
    expect(within(topBar()).getByText('qwen3.5:9b vs qwen3.5:9b')).toBeInTheDocument()
    expect(theBoard().orientation).toBe('w')
    expect(theBoard().input).toBeNull()
    expect(playMoveSound).toHaveBeenCalledTimes(2)

    const forfeit = aTurn('Ke2', {
      ply: 3,
      color: 'white',
      attempts: Array.from({ length: 4 }, () => ({ ...aTurn('Ke2').attempts[0], result: 'illegal' as const })),
    })
    const over = faceoff({
      fen: afterE5().fen,
      llm_turn: forfeit,
      llm_turns: [white, black, forfeit],
      status: 'over',
      result: '0-1',
      end_reason: 'forfeit',
    })
    await act(async () => third.resolve(Response.json(over)))

    const banner = await screen.findByTestId('banner')
    expect(within(banner).getByText('qwen3.5:9b (Black) wins')).toBeInTheDocument()
    expect(within(banner).getByText('by forfeit: qwen3.5:9b gave no legal move in 4 tries')).toBeInTheDocument()
    expect(backend.sentTo('POST /api/games/current/llm-turn')).toHaveLength(3)
    expect(theBoard().input).toBeNull()
  })
})

test("an LLM turn's mistakes land in the moves card and flash on the board until New game", async () => {
  const turn = aTurn('e5', {
    attempts: [{ ...aTurn('Ke7').attempts[0], san: null, result: 'illegal' }, aTurn('e5').attempts[0]],
  })
  const landed = afterE5({ llm_turn: turn, llm_turns: [turn] })
  const starting = later()
  fakeBackend()
    .on('GET /api/games/current', Response.json(afterE4()))
    .on('POST /api/games/current/llm-turn', Response.json(landed))
    .on('POST /api/games', starting.promise)
  renderApp()

  expect(await screen.findByText('✗ LLM move illegal')).toBeInTheDocument()
  expect(screen.getByText('illegal · try 1 of 5')).toBeInTheDocument()
  const moves = screen.getByTestId('moves')
  expect(within(moves).getByText('e4')).toBeInTheDocument()
  expect(within(moves).getByText('illegal · try 1', { exact: false })).toHaveClass('mistake', 'illegal')
  expect(screen.getByTestId('totals')).toHaveTextContent('✗ 1 illegal try · ⚑ 0 notation slips')

  // The flashes go at the click, before the new game has arrived.
  await userEvent.click(screen.getByRole('button', { name: 'New game' }))
  expect(screen.queryByText('✗ LLM move illegal')).not.toBeInTheDocument()

  await act(async () => starting.resolve(Response.json(aGame({ game_id: 'game-2' }))))
  expect(await screen.findByText('Your move (White)')).toBeInTheDocument()
  expect(within(screen.getByTestId('moves')).queryByText('e4')).not.toBeInTheDocument()
})

describe('the move history', () => {
  const backToLive = () => screen.queryByRole('button', { name: /Back to live/ })

  test('← and → step through the game with the board locked, and Back to live gives the move back', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    const board = await waitFor(theBoard)
    await waitFor(() => expect(board.input?.color).toBe('w'))
    expect(backToLive()).not.toBeInTheDocument()

    await userEvent.keyboard('{ArrowLeft}')

    expect(status()).toHaveTextContent('Viewing 1. e4 · → or Back to live')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR'))
    expect(board.marked('last-move')).toEqual(['e2', 'e4'])
    expect(board.input).toBeNull()

    await userEvent.keyboard('{ArrowLeft}')
    expect(status()).toHaveTextContent('Viewing the start position · → or Back to live')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))

    await userEvent.keyboard('{ArrowRight}{ArrowRight}')
    expect(status()).toHaveTextContent('Your move (White)')
    await waitFor(() => expect(board.input?.color).toBe('w'))
    expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR')

    await userEvent.keyboard('{ArrowLeft}')
    await userEvent.click(backToLive()!)
    expect(status()).toHaveTextContent('Your move (White)')
    expect(backToLive()).not.toBeInTheDocument()
    await waitFor(() => expect(board.input?.color).toBe('w'))
  })

  test('clicking a move in the move list views the position after it', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    const board = await waitFor(theBoard)

    await userEvent.click(within(await screen.findByTestId('moves')).getByRole('button', { name: 'e4' }))

    expect(status()).toHaveTextContent('Viewing 1. e4')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR'))
    expect(within(screen.getByTestId('moves')).getByRole('button', { name: 'e4' })).toHaveClass('viewed')
  })

  test("an LLM move landing while viewing the past doesn't pull the view; Back to live says so and shows it", async () => {
    const turn = later()
    fakeBackend()
      .on('GET /api/games/current', Response.json(afterE4()))
      .on('POST /api/games/current/llm-turn', turn.promise)
    renderApp()
    const board = await waitFor(theBoard)
    await screen.findByText(/is choosing a move/)

    await userEvent.keyboard('{ArrowLeft}')
    expect(status()).toHaveTextContent('Viewing the start position')
    expect(backToLive()).toHaveAccessibleName('Back to live')

    await act(async () => turn.resolve(Response.json(afterE5())))

    expect(await screen.findByRole('button', { name: 'Back to live · new move' })).toBeInTheDocument()
    expect(status()).toHaveTextContent('Viewing the start position')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))
    expect(board.input).toBeNull()

    await userEvent.click(backToLive()!)

    expect(status()).toHaveTextContent('Your move (White)')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR'))
    await waitFor(() => expect(board.input?.color).toBe('w'))
  })

  test('the arrow keys leave the settings modal alone', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5())).on('GET /api/models', Response.json([]))
    renderApp()
    await screen.findByText('Your move (White)')

    await userEvent.keyboard('{Meta>}k{/Meta}')
    await screen.findByRole('dialog', { name: 'Settings' })
    await userEvent.keyboard('{ArrowLeft}')

    expect(status()).toHaveTextContent('Your move (White)')
  })
})

describe('Chaos rules', () => {
  const caption = () => screen.queryByTestId('chaos-caption')

  test('a Standard rules game has no chip, caption or arrow', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    const board = await waitFor(theBoard)
    await waitFor(() => expect(board.input?.color).toBe('w'))

    expect(screen.queryByText('Chaos rules')).not.toBeInTheDocument()
    expect(caption()).not.toBeInTheDocument()
    expect(board.arrows).toEqual([])
  })

  test('a chaos move lands with a red arrow and its caption, in red in the move list, with no illegal flash', async () => {
    const turn = later()
    fakeBackend()
      .on('GET /api/games/current', Response.json(chaosGame(1)))
      .on('POST /api/games/current/llm-turn', turn.promise)
    renderApp()
    expect(await screen.findByText('Chaos rules')).toBeInTheDocument()
    const board = await waitFor(theBoard)

    await act(async () => turn.resolve(Response.json(chaosGame(2))))

    await waitFor(() => expect(caption()).toHaveTextContent('Bf8→b4: the bishop on f8 moves'))
    await waitFor(() => expect(board.arrows).toEqual([{ class: 'chaos-arrow', from: 'f8', to: 'b4' }]))
    expect(board.position).toBe('rnbqk1nr/pppppppp/8/8/1b2P3/8/PPPP1PPP/RNBQKBNR')
    expect(within(screen.getByTestId('moves')).getByRole('button', { name: 'Bb4' })).toHaveClass('chaos')
    expect(screen.queryByText(/LLM move illegal|LLM forfeits/)).not.toBeInTheDocument()
    expect(within(screen.getByTestId('moves')).queryByText(/✗/)).not.toBeInTheDocument()
    expect(playMoveSound).toHaveBeenCalledTimes(1)
  })

  test("the caption and arrow go once the human's move lands", async () => {
    fakeBackend()
      .on('GET /api/games/current', Response.json(chaosGame(2)))
      .on('POST /api/games/current/moves', Response.json(chaosGame(3)))
      .on('POST /api/games/current/llm-turn', later().promise)
    renderApp()
    await waitFor(() => expect(caption()).toBeInTheDocument())

    await drop('c2', 'c3')

    await waitFor(() => expect(caption()).not.toBeInTheDocument())
    await waitFor(() => expect(theBoard().arrows).toEqual([]))
  })

  test('a spawn pops in with a purple marker and its caption, in purple in the move list', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(chaosGame(8)))
    renderApp()
    const board = await waitFor(theBoard)

    await waitFor(() => expect(caption()).toHaveTextContent('Qd5: no queen on the board; one appears on d5'))
    expect(caption()).toHaveClass('spawn')
    await waitFor(() => expect(board.marked('spawn')).toEqual(['d5']))
    expect(board.arrows).toEqual([])
    expect(within(screen.getByTestId('moves')).getByRole('button', { name: 'Qd5' })).toHaveClass('spawn')
  })

  test("an illegal castle moves the rook too, the arrow on the king's move", async () => {
    fakeBackend().on('GET /api/games/current', Response.json(chaosGame(10)))
    renderApp()
    const board = await waitFor(theBoard)

    await waitFor(() => expect(caption()).toHaveTextContent('O-O: illegal O-O: king e8→g8, rook h8→f8'))
    await waitFor(() => expect(board.arrows).toEqual([{ class: 'chaos-arrow', from: 'e8', to: 'g8' }]))
    expect(board.position).toBe('rnb2rk1/pppp1ppp/8/3qp1B1/1b1PP3/2P2N2/PP3PPP/RN1QKB1R')
    expect(within(screen.getByTestId('moves')).getByRole('button', { name: 'O-O' })).toHaveClass('chaos')
  })

  test('stepping onto a chaos move or spawn in the history replays it, with its arrow or marker and caption', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(chaosGame(10)))
    renderApp()
    const board = await waitFor(theBoard)
    await waitFor(() => expect(caption()).toBeInTheDocument())

    await userEvent.keyboard('{ArrowLeft}') // 5. Nf3
    await waitFor(() => expect(caption()).not.toBeInTheDocument())
    await waitFor(() => expect(board.arrows).toEqual([]))

    await userEvent.keyboard('{ArrowLeft}') // 4… Qd5, the spawn
    await waitFor(() => expect(caption()).toHaveTextContent('Qd5: no queen on the board; one appears on d5'))
    await waitFor(() => expect(board.marked('spawn')).toEqual(['d5']))

    await userEvent.click(within(screen.getByTestId('moves')).getByRole('button', { name: 'Bb4' }))
    expect(status()).toHaveTextContent('Viewing 1… Bb4')
    await waitFor(() => expect(caption()).toHaveTextContent('Bf8→b4: the bishop on f8 moves'))
    await waitFor(() => expect(board.arrows).toEqual([{ class: 'chaos-arrow', from: 'f8', to: 'b4' }]))
    expect(board.marked('spawn')).toEqual([])
    // Animated in from the position before it.
    expect(board.positionsSet.slice(-2)).toEqual([
      { position: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR', animated: false },
      { position: 'rnbqk1nr/pppppppp/8/8/1b2P3/8/PPPP1PPP/RNBQKBNR', animated: true },
    ])
  })

  test('the totals add the chaos moves and spawns', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(chaosGame(8)))
    renderApp()

    expect(await screen.findByTestId('totals')).toHaveTextContent(
      '✗ 3 illegal tries · ⚑ 0 notation slips · ↯ 3 chaos moves (1 spawn)',
    )
  })

  test('the banner names a King capture: the human took the king the LLM left hanging', async () => {
    fakeBackend().on(
      'GET /api/games/current',
      Response.json(chaosGame(13, { status: 'over', result: '1-0', end_reason: 'king_capture', human_legal_moves: [] })),
    )
    renderApp()

    const banner = await screen.findByTestId('banner')
    expect(within(banner).getByText('White wins')).toBeInTheDocument()
    expect(within(banner).getByText('by King capture: qwen3.5:9b left its king hanging')).toBeInTheDocument()
  })
})
