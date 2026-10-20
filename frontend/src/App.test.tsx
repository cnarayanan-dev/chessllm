import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import App from '@/App'
import type { GameState } from '@/api/types'
import { playMoveSound } from '@/components/board/moveSound'
import { fakeBackend, later } from '@/test/fakeBackend'
import { theBoard } from '@/test/fakeChessboard'
import { aGame, aTurn, afterE4, afterE5, chaosGame, E4, plies } from '@/test/games'

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

const strip = (color: 'white' | 'black') => screen.getByTestId(`strip-${color}`)
/** The strips above and below the board, top first, by their side. */
const strips = () =>
  within(screen.getByTestId('board-column'))
    .getAllByTestId(/^strip-/)
    .map((element) => element.dataset.testid!.replace('strip-', ''))
/** The sides whose strip has the turn ring. */
const ringed = () => (['white', 'black'] as const).filter((color) => screen.queryByTestId(`strip-${color}`)?.hasAttribute('data-to-move'))
const timer = () => screen.queryByRole('timer')
/** What a strip shows after the name: the pieces its side took, those it spawned, and +N, or null for none. */
const pieces = (color: 'white' | 'black', which: 'Took' | 'Spawned') =>
  within(strip(color))
    .queryByRole('img', { name: new RegExp(`^${which}: `) })
    ?.getAttribute('aria-label') ?? null
const ahead = (color: 'white' | 'black') => within(strip(color)).queryByTestId('ahead')?.textContent ?? null

/** Waits for the human's move: the ring on their strip, and no timer running. */
async function yourMove(color: 'white' | 'black' = 'white') {
  await waitFor(() => expect(ringed()).toEqual([color]))
  expect(timer()).not.toBeInTheDocument()
}

/** Waits for an LLM's move to run: the ring and the timer, from 0m 00s, in its strip. */
async function llmMoving(color: 'white' | 'black') {
  await waitFor(() => expect(within(strip(color)).getByRole('timer')).toHaveTextContent('0m 00s'))
  expect(ringed()).toEqual([color])
  expect(screen.getAllByRole('timer')).toHaveLength(1)
}
const topBar = () => screen.getByRole('banner')
const models = [{ name: 'qwen3.5:9b', thinking: true, sampling: {} }]
/** Opens the New game sheet from the top bar. */
async function openSheet() {
  await userEvent.click(within(topBar()).getByRole('button', { name: 'New game' }))
  return screen.findByRole('dialog', { name: 'New game' })
}
const gameCard = () => screen.getByRole('region', { name: 'Game' })
const reasoning = () => screen.getByRole('region', { name: 'Reasoning' })
/** The Game card's players, White first, each as its side and name. */
const players = () =>
  within(within(gameCard()).getByRole('list', { name: 'Players' }))
    .getAllByRole('listitem')
    .map((item) => item.textContent)
/** The Game card's settings, chip by chip, by their accessible names. */
const settingsItems = () =>
  within(within(gameCard()).getByRole('list', { name: 'Settings' }))
    .getAllByRole('img')
    .map((chip) => chip.getAttribute('aria-label'))

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

test('shows the current game: the Game card, the player strips and the board', async () => {
  fakeBackend().on('GET /api/games/current', Response.json(aGame()))

  renderApp()

  await yourMove()
  // The LLM above the board, you below, with no status line.
  expect(strips()).toEqual(['black', 'white'])
  expect(strip('black')).toHaveTextContent('qwen3.5:9b')
  expect(within(strip('black')).getByRole('img', { name: 'Qwen' })).toBeInTheDocument()
  expect(strip('white')).toHaveTextContent('You')
  expect(screen.queryByTestId('status')).not.toBeInTheDocument()
  expect(within(gameCard()).getByText('Play LLM')).toBeInTheDocument()
  expect(settingsItems()).toEqual([
    'Board only (Free)',
    'Standard rules',
    'Explained feedback',
    'Thinking off',
    'Forfeit after 5 illegal moves',
  ])
  expect(players()).toEqual(['White You', 'Black qwen3.5:9b'])
  expect(within(gameCard()).queryByText(/Elo/)).not.toBeInTheDocument()
  // The settings live in the Game card, not in the top bar.
  expect(within(topBar()).queryByText(/qwen3.5:9b|thinking|Free/)).not.toBeInTheDocument()
  const board = theBoard()
  await waitFor(() => expect(board.input?.color).toBe('w'))
  expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
  expect(board.orientation).toBe('w')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('each strip shows the pieces its side took and +N for the side ahead, of the position on the board', async () => {
  const AFTER_D5 = 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
  const AFTER_EXD5 = 'rnbqkbnr/ppp1pppp/8/3P4/8/8/PPPP1PPP/RNBQKBNR b KQkq - 0 2'
  fakeBackend().on(
    'GET /api/games/current',
    Response.json(
      afterE4({
        fen: AFTER_EXD5,
        pgn: '1. e4 d5 2. exd5',
        last_move: 'e4d5',
        plies: plies(E4, ['d7d5', 'd5', AFTER_D5], ['e4d5', 'exd5', AFTER_EXD5]),
      }),
    ),
  )
  renderApp()

  await waitFor(() => expect(pieces('white', 'Took')).toBe('Took: pawn'))
  expect(ahead('white')).toBe('+1')
  expect(pieces('black', 'Took')).toBeNull()
  expect(ahead('black')).toBeNull()

  // Stepping back through the move history shows the position on the board.
  await userEvent.keyboard('{ArrowLeft}')
  await waitFor(() => expect(pieces('white', 'Took')).toBeNull())
  expect(ahead('white')).toBeNull()
  expect(ahead('black')).toBeNull()

  await userEvent.keyboard('{ArrowRight}')
  await waitFor(() => expect(pieces('white', 'Took')).toBe('Took: pawn'))
  expect(ahead('white')).toBe('+1')
})

test('credits the Merida pieces, the move sound and the model logos', async () => {
  fakeBackend().on('GET /api/games/current', Response.json(aGame()))

  renderApp()

  expect(await screen.findByText(/Pieces: Merida by Armando Hernandez Marroquin, GPLv2\+/)).toBeVisible()
  expect(screen.getByText(/Move sound: Kenney, CC0/)).toBeVisible()
  expect(screen.getByText(/Model logos: LobeHub Icons, MIT/)).toBeVisible()
})

describe('with no current game', () => {
  const noGame = () => Response.json({ detail: 'no game started' }, { status: 404 })
  // The API's defaults for a new game, here with a model and limit the test can tell apart.
  const defaults = {
    mode: 'play_llm',
    white: { player: 'human' },
    black: { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'listed', retry_feedback: 'explained' },
    rules: 'standard',
    max_attempts: 7,
  }

  test('the page shows an empty board and the New game sheet with the default settings, and starts no game', async () => {
    const backend = fakeBackend()
      .on('GET /api/games/current', noGame())
      .on('GET /api/games/defaults', Response.json(defaults))
      .on('GET /api/models', Response.json(models))
    renderApp()

    const sheet = await screen.findByRole('dialog', { name: 'New game' })
    expect(within(sheet).getByRole('radio', { name: 'Play LLM' })).toHaveAttribute('aria-checked', 'true')
    expect(within(sheet).getByRole('combobox', { name: 'Opponent' })).toHaveTextContent('qwen3.5:9b')
    expect(within(sheet).getByRole('button', { name: 'Play as White' })).toBeInTheDocument()
    // The board with no pieces, taking no move, and no player strips or Game card.
    expect(theBoard().position).toBe('8/8/8/8/8/8/8/8')
    expect(theBoard().input).toBeNull()
    expect(screen.queryByTestId('strip-white')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Game' })).not.toBeInTheDocument()
    expect(backend.sentTo('POST /api/games')).toHaveLength(0)
  })

  test('starting from the sheet plays the default settings as set', async () => {
    const backend = fakeBackend()
      .on('GET /api/games/current', noGame())
      .on('GET /api/games/defaults', Response.json(defaults))
      .on('GET /api/models', Response.json(models))
      .on('POST /api/games', Response.json(aGame()))
    renderApp()

    const sheet = await screen.findByRole('dialog', { name: 'New game' })
    await userEvent.click(within(sheet).getByRole('button', { name: 'Play as White' }))

    await yourMove()
    expect(backend.sentTo('POST /api/games')[0].body).toEqual(defaults)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('closing the sheet leaves the empty board; New game and ⌘K open it again', async () => {
    const backend = fakeBackend()
      .on('GET /api/games/current', noGame())
      .on('GET /api/games/defaults', Response.json(defaults))
      .on('GET /api/models', Response.json(models), Response.json(models), Response.json(models))
    renderApp()

    await screen.findByRole('dialog', { name: 'New game' })
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.queryByTestId('strip-white')).not.toBeInTheDocument()

    expect(await openSheet()).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await userEvent.keyboard('{Meta>}k{/Meta}')
    expect(await screen.findByRole('dialog', { name: 'New game' })).toBeInTheDocument()
    expect(backend.sentTo('POST /api/games')).toHaveLength(0)
  })

  test('says so when the game started from the sheet cannot start', async () => {
    fakeBackend()
      .on('GET /api/games/current', noGame())
      .on('GET /api/games/defaults', Response.json(defaults))
      .on('GET /api/models', Response.json(models))
      .on('POST /api/games', Response.json({ detail: 'Ollama is not running' }, { status: 400 }))
    renderApp()

    const sheet = await screen.findByRole('dialog', { name: 'New game' })
    await userEvent.click(within(sheet).getByRole('button', { name: 'Play as White' }))

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Could not start a game')).toBeInTheDocument()
    expect(alert).toHaveTextContent('Ollama is not running')
    expect(screen.queryByTestId('strip-white')).not.toBeInTheDocument()
  })

  test("says so when the defaults can't be loaded", async () => {
    fakeBackend()
      .on('GET /api/games/current', noGame())
      .on('GET /api/games/defaults', Response.json({ detail: 'Internal Server Error' }, { status: 500 }))
    renderApp()

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Could not start a game')).toBeInTheDocument()
    expect(alert).toHaveTextContent('Internal Server Error')
  })

  test("says so when the current game can't be loaded, and opens no sheet", async () => {
    fakeBackend().on('GET /api/games/current', Response.json({ detail: 'Internal Server Error' }, { status: 500 }))
    renderApp()

    expect(await screen.findByRole('alert')).toHaveTextContent('Internal Server Error')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

test('a reload with a current game shows that game and opens no sheet', async () => {
  const backend = fakeBackend().on('GET /api/games/current', Response.json(aGame()))
  renderApp()

  await yourMove()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(backend.sentTo('GET /api/games/defaults')).toHaveLength(0)
  expect(backend.sentTo('POST /api/games')).toHaveLength(0)
})

test("the human's move lands at once, then the LLM's turn runs, timed in its strip, and its move lands", async () => {
  const turn = later()
  const backend = fakeBackend()
    .on('GET /api/games/current', Response.json(aGame()))
    .on('POST /api/games/current/moves', Response.json(afterE4()))
    .on('POST /api/games/current/llm-turn', turn.promise)
  renderApp()

  await drop('e2', 'e4')

  await llmMoving('black')
  expect(backend.sentTo('POST /api/games/current/moves')[0].body).toEqual({ uci: 'e2e4' })
  const board = theBoard()
  await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR'))
  expect(board.marked('last-move')).toEqual(['e2', 'e4'])
  expect(board.input).toBeNull()
  expect(playMoveSound).toHaveBeenCalledTimes(1)

  await act(async () => turn.resolve(Response.json(afterE5())))

  await yourMove()
  await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR'))
  await waitFor(() => expect(board.input?.color).toBe('w'))
  expect(playMoveSound).toHaveBeenCalledTimes(2)
})

test("a thinking LLM's move is timed too, and once its move lands its Thinking is not shown", async () => {
  const thinking = (game: GameState) => ({
    ...game,
    settings: { ...game.settings, black: { ...afterE4().settings.black, thinking: true } },
  })
  const turn = later()
  fakeBackend()
    .on('GET /api/games/current', Response.json(thinking(afterE4())))
    .on('POST /api/games/current/llm-turn', turn.promise)
  renderApp()

  await llmMoving('black')

  const landed = aTurn('e5', { thinking: 'The king pawn, to fight for the centre.' })
  await act(async () => turn.resolve(Response.json(thinking(afterE5({ llm_turn: landed, llm_turns: [landed] })))))

  // "Show thinking" is hidden for now; the Reasoning panel says a thinking LLM gives no Reasoning.
  expect(await within(reasoning()).findByText('qwen3.5:9b plays with thinking on, so it gives no Reasoning.')).toBeVisible()
  expect(screen.queryByText('Show thinking')).not.toBeInTheDocument()
  expect(screen.queryByText('The king pawn, to fight for the centre.')).not.toBeInTheDocument()
})

test('a rejected move shows the error and snaps the piece back', async () => {
  fakeBackend()
    .on('GET /api/games/current', Response.json(aGame()))
    .on('POST /api/games/current/moves', Response.json({ detail: 'illegal move: e2e4' }, { status: 400 }))
  renderApp()

  await drop('e2', 'e4')

  expect(await within(gameCard()).findByRole('alert')).toHaveTextContent('illegal move: e2e4')
  const board = theBoard()
  await waitFor(() => expect(board.input?.color).toBe('w'))
  expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
  await yourMove()
  expect(playMoveSound).not.toHaveBeenCalled()
})

test('an LLM turn that fails shows the error, and the ring stays on the LLM with no timer running', async () => {
  fakeBackend()
    .on('GET /api/games/current', Response.json(afterE4()))
    .on('POST /api/games/current/llm-turn', new TypeError('Failed to fetch'))
  renderApp()

  const card = await screen.findByRole('region', { name: 'Game' })
  expect(await within(card).findByRole('alert')).toHaveTextContent('Failed to fetch')
  expect(ringed()).toEqual(['black'])
  expect(timer()).not.toBeInTheDocument()
})

test('at the end of the game the Game card shows the result line and a Rematch button', async () => {
  const over = afterE5({ status: 'over', result: '0-1', end_reason: 'checkmate', human_legal_moves: [] })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  expect(await screen.findByTestId('result')).toHaveTextContent('Black wins by checkmate')
  expect(within(gameCard()).getByTestId('result')).toBeInTheDocument()
  expect(within(gameCard()).getByRole('button', { name: 'Rematch' })).toBeInTheDocument()
  expect(screen.queryByTestId('banner')).not.toBeInTheDocument()
  expect(ringed()).toEqual([])
  expect(timer()).not.toBeInTheDocument()
  await waitFor(() => expect(theBoard().position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR'))
  expect(theBoard().input).toBeNull()
})

test('a forfeit with no answer says why under the result line', async () => {
  const forfeit = aTurn('e5', {
    attempts: [{ ...aTurn('e5').attempts[0], move: null, san: null, result: 'timeout', error: 'no answer in 300 s' }],
  })
  const over = afterE4({ llm_turn: forfeit, llm_turns: [forfeit], status: 'over', result: '1-0', end_reason: 'forfeit' })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  expect(await screen.findByText('White wins by forfeit')).toBeInTheDocument()
  expect(within(screen.getByTestId('result')).getByText('no answer in 300 s')).toBeInTheDocument()
})

test('a draw at the Move cap names the cap in the result line', async () => {
  const over = afterE5({ status: 'over', result: '1/2-1/2', end_reason: 'move_cap', human_legal_moves: [] })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  expect(await screen.findByTestId('result')).toHaveTextContent('Draw at the move cap of 150 moves each')
})

test('an end reason the page has no wording for is spelled out', async () => {
  const over = afterE4({ status: 'over', result: '1-0', end_reason: 'variant_win' })
  fakeBackend().on('GET /api/games/current', Response.json(over))

  renderApp()

  expect(await screen.findByTestId('result')).toHaveTextContent('White wins by variant win')
})

test('playing Black: the board turns, with the human at the bottom, and the LLM opens', async () => {
  const turn = later()
  const backend = fakeBackend()
    .on('GET /api/games/current', Response.json(llmPlaysWhite()))
    .on('POST /api/games/current/llm-turn', turn.promise)

  renderApp()

  await llmMoving('white')
  expect(strips()).toEqual(['white', 'black'])
  expect(players()).toEqual(['White qwen3.5:9b', 'Black You'])
  await waitFor(() => expect(theBoard().orientation).toBe('b'))
  expect(backend.sentTo('POST /api/games/current/llm-turn')).toHaveLength(1)
})

test("New game opens the sheet with the running game's settings; starting replaces the game, dropping its LLM turn", async () => {
  const abandoned = later()
  const backend = fakeBackend()
    .on('GET /api/games/current', Response.json(afterE4()))
    .on('GET /api/models', Response.json(models))
    .on('POST /api/games/current/llm-turn', abandoned.promise)
    .on('POST /api/games', Response.json(aGame({ game_id: 'game-2' })))
  renderApp()
  await llmMoving('black')

  const sheet = await openSheet()
  expect(backend.sentTo('POST /api/games')).toHaveLength(0)
  await userEvent.click(within(sheet).getByRole('button', { name: 'Play as White' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  await yourMove()
  await act(async () => abandoned.resolve(Response.json(afterE5())))

  expect(backend.sentTo('POST /api/games')[0].body).toEqual({
    mode: 'play_llm',
    white: { player: 'human' },
    black: { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
    rules: 'standard',
    max_attempts: 5,
  })
  await yourMove()
  await waitFor(() => expect(theBoard().position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))
  expect(playMoveSound).not.toHaveBeenCalled()
})

describe('Rematch', () => {
  test('in Play LLM the human takes the other colour: the board turns and the LLM opens', async () => {
    const over = afterE5({ status: 'over', result: '1/2-1/2', end_reason: 'stalemate', human_legal_moves: [] })
    const backend = fakeBackend()
      .on('GET /api/games/current', Response.json(over))
      .on('POST /api/games', Response.json(llmPlaysWhite({ game_id: 'game-2' })))
      .on('POST /api/games/current/llm-turn', later().promise)
    renderApp()

    expect(await screen.findByTestId('result')).toHaveTextContent('Draw by stalemate')
    await userEvent.click(within(gameCard()).getByRole('button', { name: 'Rematch' }))

    await llmMoving('white')
    expect(backend.sentTo('POST /api/games')[0].body).toEqual({
      mode: 'play_llm',
      white: { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
      black: { player: 'human' },
      rules: 'standard',
      max_attempts: 5,
    })
    expect(players()).toEqual(['White qwen3.5:9b', 'Black You'])
    await waitFor(() => expect(theBoard().orientation).toBe('b'))
    expect(screen.queryByTestId('result')).not.toBeInTheDocument()
  })

  test('in an LLM faceoff the two LLMs change sides, each with its own settings', async () => {
    const llm = afterE4().settings.black
    const white = { ...llm, model: 'gemma3:4b', thinking: true, llm_constraints: 'listed' as const }
    const settings = { ...aGame().settings, mode: 'llm_faceoff' as const, white, black: llm }
    const over = afterE5({ status: 'over', result: '1-0', end_reason: 'checkmate', human_legal_moves: [], settings })
    const swapped = { ...settings, white: llm, black: white }
    const backend = fakeBackend()
      .on('GET /api/games/current', Response.json(over))
      .on('POST /api/games', Response.json(aGame({ game_id: 'game-2', human_legal_moves: [], settings: swapped })))
      .on('POST /api/games/current/llm-turn', later().promise)
      .on('GET /api/models', Response.json(models))
    renderApp()

    await userEvent.click(await within(await screen.findByRole('region', { name: 'Game' })).findByRole('button', { name: 'Rematch' }))

    await llmMoving('white')
    expect(backend.sentTo('POST /api/games')[0].body).toEqual({
      mode: 'llm_faceoff',
      white: llm,
      black: white,
      rules: 'standard',
      max_attempts: 5,
    })
    expect(players()).toEqual(['White qwen3.5:9b', 'Black gemma3:4b'])

    // The New game sheet then opens with the Rematch's settings: the last game's.
    const sheet = await openSheet()
    expect(within(sheet).getByRole('combobox', { name: 'White model' })).toHaveTextContent('qwen3.5:9b')
    expect(within(sheet).getByRole('combobox', { name: 'Black model' })).toHaveTextContent('gemma3:4b')
  })
})

describe('the New game sheet', () => {
  test('⌘K opens it; closing it leaves the running game as it is and forgets its changes, with no note', async () => {
    const backend = fakeBackend().on('GET /api/games/current', Response.json(aGame())).on('GET /api/models', Response.json(models), Response.json(models))
    renderApp()
    await yourMove()

    await userEvent.keyboard('{Meta>}k{/Meta}')
    const sheet = await screen.findByRole('dialog', { name: 'New game' })
    await userEvent.click(within(sheet).getByRole('radio', { name: 'LLM faceoff' }))
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    expect(within(gameCard()).queryByText(/next game/)).not.toBeInTheDocument()
    expect(players()).toEqual(['White You', 'Black qwen3.5:9b'])
    expect(backend.sentTo('POST /api/games')).toHaveLength(0)
    await userEvent.keyboard('{Control>}k{/Control}')
    expect(await screen.findByRole('radio', { name: 'Play LLM' })).toHaveAttribute('aria-checked', 'true')
    await yourMove()
  })

  test('Play as Black starts the game as set up in the sheet', async () => {
    const backend = fakeBackend()
      .on('GET /api/games/current', Response.json(aGame()))
      .on('GET /api/models', Response.json(models))
      .on('POST /api/games', Response.json(llmPlaysWhite({ game_id: 'game-2' })))
      .on('POST /api/games/current/llm-turn', later().promise)
    renderApp()
    await yourMove()

    const sheet = await openSheet()
    await userEvent.click(within(sheet).getByRole('button', { name: 'Play as Black' }))

    await waitFor(() => expect(players()).toEqual(['White qwen3.5:9b', 'Black You']))
    expect(backend.sentTo('POST /api/games')[0].body).toEqual({
      mode: 'play_llm',
      white: { player: 'llm', model: 'qwen3.5:9b', thinking: false, llm_constraints: 'free', retry_feedback: 'explained' },
      black: { player: 'human' },
      rules: 'standard',
      max_attempts: 5,
    })
  })

  describe('coming from another page', () => {
    afterEach(() => window.history.replaceState(null, '', '/'))

    test('its New game opens the sheet once the game is shown, and the address loses the request', async () => {
      const backend = fakeBackend().on('GET /api/games/current', Response.json(aGame())).on('GET /api/models', Response.json(models))
      window.history.replaceState(null, '', '/?then=new-game')
      renderApp()

      expect(await screen.findByRole('dialog', { name: 'New game' })).toBeInTheDocument()
      expect(window.location.search).toBe('')
      expect(backend.sentTo('POST /api/games')).toHaveLength(0)
      await yourMove()
    })

    test('with no current game, its New game opens the sheet with the defaults, and the address loses the request', async () => {
      const defaults = { mode: 'play_llm', white: { player: 'human' }, black: afterE4().settings.black, rules: 'standard', max_attempts: 5 }
      const backend = fakeBackend()
        .on('GET /api/games/current', Response.json({ detail: 'no game started' }, { status: 404 }))
        .on('GET /api/games/defaults', Response.json(defaults))
        .on('GET /api/models', Response.json(models))
      window.history.replaceState(null, '', '/?then=new-game')
      renderApp()

      const sheet = await screen.findByRole('dialog', { name: 'New game' })
      expect(within(sheet).getByRole('combobox', { name: 'Opponent' })).toHaveTextContent('qwen3.5:9b')
      expect(window.location.search).toBe('')
      expect(backend.sentTo('POST /api/games')).toHaveLength(0)
    })
  })

  test('an LLM faceoff started from the sheet plays itself to the end, White at the bottom and the board locked', async () => {
    const llm = afterE4().settings.black
    const settings = { ...aGame().settings, mode: 'llm_faceoff' as const, white: llm, black: llm }
    const faceoff = (overrides: Partial<GameState>) =>
      aGame({ game_id: 'game-2', human_legal_moves: [], settings, ...overrides })
    const white = aTurn('e4', { ply: 1, color: 'white' })
    const black = aTurn('e5', { ply: 2, color: 'black' })
    const second = later()
    const third = later()
    const backend = fakeBackend()
      .on('GET /api/games/current', Response.json(aGame()))
      .on('GET /api/models', Response.json(models))
      .on('POST /api/games', Response.json(faceoff({})))
      .on(
        'POST /api/games/current/llm-turn',
        Response.json(faceoff({ fen: afterE4().fen, turn: 'black', last_move: 'e2e4', llm_turn: white, llm_turns: [white] })),
        second.promise,
        third.promise,
      )
    renderApp()
    await yourMove()

    await userEvent.keyboard('{Meta>}k{/Meta}')
    await userEvent.click(await screen.findByRole('radio', { name: 'LLM faceoff' }))
    await userEvent.click(screen.getByRole('button', { name: 'Start faceoff' }))

    // Each turn is asked for as soon as the last one lands, its timer in the strip of the side to move.
    await waitFor(() => expect(backend.sentTo('POST /api/games/current/llm-turn')).toHaveLength(2))
    await llmMoving('black')
    await act(async () =>
      second.resolve(Response.json(faceoff({ fen: afterE5().fen, last_move: 'e7e5', llm_turn: black, llm_turns: [white, black] }))),
    )
    await waitFor(() => expect(backend.sentTo('POST /api/games/current/llm-turn')).toHaveLength(3))
    await llmMoving('white')
    expect(strips()).toEqual(['black', 'white'])
    expect(backend.sentTo('POST /api/games')[0].body).toMatchObject({ mode: 'llm_faceoff', white: llm, black: llm })
    expect(within(gameCard()).getByText('LLM faceoff')).toBeInTheDocument()
    expect(players()).toEqual(['White qwen3.5:9b', 'Black qwen3.5:9b'])
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

    const result = await within(gameCard()).findByTestId('result')
    expect(within(result).getByText('qwen3.5:9b (Black) wins by forfeit')).toBeInTheDocument()
    expect(within(result).getByText('qwen3.5:9b gave no legal move in 4 tries')).toBeInTheDocument()
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
    .on('GET /api/models', Response.json(models))
    .on('POST /api/games/current/llm-turn', Response.json(landed))
    .on('POST /api/games', starting.promise)
  renderApp()

  expect(await screen.findByText('✗ LLM move illegal')).toBeInTheDocument()
  expect(screen.getByText('illegal · try 1 of 5')).toBeInTheDocument()
  const moves = screen.getByTestId('moves')
  expect(within(moves).getByText('e4')).toBeInTheDocument()
  expect(within(moves).getByText('illegal · try 1', { exact: false })).toHaveClass('mistake', 'illegal')
  expect(screen.getByTestId('totals')).toHaveTextContent('1 illegal try · 0 notation slips')

  // The flashes go at the start, before the new game has arrived.
  const sheet = await openSheet()
  expect(screen.getByText('✗ LLM move illegal')).toBeInTheDocument()
  await userEvent.click(within(sheet).getByRole('button', { name: 'Play as White' }))
  expect(screen.queryByText('✗ LLM move illegal')).not.toBeInTheDocument()

  await act(async () => starting.resolve(Response.json(aGame({ game_id: 'game-2' }))))
  await yourMove()
  expect(within(screen.getByTestId('moves')).queryByText('e4')).not.toBeInTheDocument()
})

describe('the move history', () => {
  /** The move marked in the move list as the past position the board shows. */
  const viewedMove = () => within(screen.getByTestId('moves')).queryByRole('button', { current: 'step' })

  test('← and → step through the game with the board locked, → up to the latest move gives the move back', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    const board = await waitFor(theBoard)
    await waitFor(() => expect(board.input?.color).toBe('w'))
    expect(viewedMove()).not.toBeInTheDocument()

    await userEvent.keyboard('{ArrowLeft}')

    expect(viewedMove()).toHaveTextContent('e4')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR'))
    expect(board.marked('last-move')).toEqual(['e2', 'e4'])
    expect(board.input).toBeNull()

    await userEvent.keyboard('{ArrowLeft}')
    expect(viewedMove()).not.toBeInTheDocument()
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))
    expect(board.input).toBeNull()

    await userEvent.keyboard('{ArrowRight}{ArrowRight}')
    await yourMove()
    await waitFor(() => expect(board.input?.color).toBe('w'))
    expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR')
    expect(viewedMove()).not.toBeInTheDocument()
  })

  test('the Reasoning panel under the Game card follows the position stepped to', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    const board = await waitFor(theBoard)
    await waitFor(() => expect(board.input?.color).toBe('w'))
    expect(gameCard().nextElementSibling).toBe(reasoning())
    expect(within(reasoning()).getByText('Reasoning for e5.')).toBeVisible()

    await userEvent.keyboard('{ArrowLeft}')

    expect(within(reasoning()).getByText('The LLM has not moved yet.')).toBeVisible()

    await userEvent.keyboard('{ArrowRight}')

    expect(within(reasoning()).getByTestId('reasoning-move')).toHaveTextContent('qwen3.5:9b · 1… e5')
    expect(within(reasoning()).getByText('Reasoning for e5.')).toBeVisible()
  })

  test('there is no Back to live button, and no status line', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    await yourMove()

    await userEvent.keyboard('{ArrowLeft}')

    expect(viewedMove()).toHaveTextContent('e4')
    expect(screen.queryByRole('button', { name: /live/i })).not.toBeInTheDocument()
    expect(screen.queryByTestId('status')).not.toBeInTheDocument()
  })

  test('clicking a move views the position after it, and clicking the latest move returns to live', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    const board = await waitFor(theBoard)
    await yourMove()

    await userEvent.click(within(screen.getByTestId('moves')).getByRole('button', { name: 'e4' }))

    expect(viewedMove()).toHaveTextContent('e4')
    expect(viewedMove()).toHaveClass('viewed')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR'))
    expect(board.input).toBeNull()

    await userEvent.click(within(screen.getByTestId('moves')).getByRole('button', { name: 'e5' }))

    expect(viewedMove()).not.toBeInTheDocument()
    await waitFor(() => expect(board.input?.color).toBe('w'))
    expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR')
  })

  test("an LLM move landing while viewing the past doesn't pull the view, the latest move pulses, and the ring and timer follow the live game", async () => {
    const turn = later()
    fakeBackend()
      .on('GET /api/games/current', Response.json(afterE4()))
      .on('POST /api/games/current/llm-turn', turn.promise)
    renderApp()
    const board = await waitFor(theBoard)
    await llmMoving('black')

    await userEvent.keyboard('{ArrowLeft}')
    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))
    await llmMoving('black')

    await act(async () => turn.resolve(Response.json(afterE5())))

    expect(await within(screen.getByTestId('moves')).findByRole('button', { name: 'e5' })).toHaveClass('last', 'arrived')
    await yourMove()
    expect(board.position).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
    expect(board.input).toBeNull()

    await userEvent.keyboard('{ArrowRight}{ArrowRight}')

    await waitFor(() => expect(board.position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR'))
    await waitFor(() => expect(board.input?.color).toBe('w'))
  })

  test('the arrow keys leave the New game sheet alone', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5())).on('GET /api/models', Response.json([]))
    renderApp()
    await yourMove()

    await userEvent.keyboard('{Meta>}k{/Meta}')
    await screen.findByRole('dialog', { name: 'New game' })
    await userEvent.keyboard('{ArrowLeft}')

    expect(viewedMove()).not.toBeInTheDocument()
    expect(theBoard().position).toBe('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR')
  })
})

describe('Chaos rules', () => {
  const caption = () => screen.queryByTestId('chaos-caption')

  test('a Standard rules game says so in the Game card, with no caption or arrow', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(afterE5()))
    renderApp()
    const board = await waitFor(theBoard)
    await waitFor(() => expect(board.input?.color).toBe('w'))

    expect(settingsItems()).toContain('Standard rules')
    expect(settingsItems()).not.toContain('Chaos rules')
    expect(caption()).not.toBeInTheDocument()
    expect(board.arrows).toEqual([])
  })

  test('a chaos move lands with a red arrow and its caption, in red in the move list, with no illegal flash', async () => {
    const turn = later()
    fakeBackend()
      .on('GET /api/games/current', Response.json(chaosGame(1)))
      .on('POST /api/games/current/llm-turn', turn.promise)
    renderApp()
    const card = await screen.findByRole('region', { name: 'Game' })
    expect(await within(card).findByRole('img', { name: 'Chaos rules' })).toBeInTheDocument()
    const board = await waitFor(theBoard)

    await act(async () => turn.resolve(Response.json(chaosGame(2))))

    await waitFor(() => expect(caption()).toHaveTextContent('Bf8→b4: the bishop on f8 moves'))
    await waitFor(() => expect(board.arrows).toEqual([{ class: 'chaos-arrow', from: 'f8', to: 'b4' }]))
    expect(board.position).toBe('rnbqk1nr/pppppppp/8/8/1b2P3/8/PPPP1PPP/RNBQKBNR')
    expect(within(screen.getByTestId('moves')).getByRole('button', { name: 'Bb4' })).toHaveClass('chaos')
    expect(screen.queryByText(/LLM move illegal|LLM forfeits/)).not.toBeInTheDocument()
    expect(screen.getByTestId('moves').querySelector('.mistake')).toBeNull()
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
    expect(within(screen.getByTestId('moves')).getByRole('button', { name: 'Bb4' })).toHaveAttribute('aria-current', 'step')
    await waitFor(() => expect(caption()).toHaveTextContent('Bf8→b4: the bishop on f8 moves'))
    await waitFor(() => expect(board.arrows).toEqual([{ class: 'chaos-arrow', from: 'f8', to: 'b4' }]))
    expect(board.marked('spawn')).toEqual([])
    // Animated in from the position before it.
    expect(board.positionsSet.slice(-2)).toEqual([
      { position: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR', animated: false },
      { position: 'rnbqk1nr/pppppppp/8/8/1b2P3/8/PPPP1PPP/RNBQKBNR', animated: true },
    ])
  })

  test("a queen spawned after Black's queen was taken: White's strip keeps the queen, Black's shows the spawn", async () => {
    fakeBackend().on('GET /api/games/current', Response.json(chaosGame(8)))
    renderApp()

    await waitFor(() => expect(pieces('white', 'Took')).toBe('Took: queen'))
    expect(pieces('black', 'Spawned')).toBe('Spawned: queen')
    expect(pieces('black', 'Took')).toBeNull()
    expect(ahead('white')).toBeNull()
    expect(ahead('black')).toBeNull()

    await userEvent.keyboard('{ArrowLeft}') // 4. Bxg5, before the spawn
    await waitFor(() => expect(pieces('black', 'Spawned')).toBeNull())
    expect(pieces('white', 'Took')).toBe('Took: queen')
    expect(ahead('white')).toBe('+9')
  })

  test('the totals add the chaos moves and spawns', async () => {
    fakeBackend().on('GET /api/games/current', Response.json(chaosGame(8)))
    renderApp()

    expect(await screen.findByTestId('totals')).toHaveTextContent(
      '3 illegal tries · 0 notation slips · 3 chaos moves (1 spawn)',
    )
  })

  test('the result line names a King capture: the human took the king the LLM left hanging', async () => {
    fakeBackend().on(
      'GET /api/games/current',
      Response.json(chaosGame(13, { status: 'over', result: '1-0', end_reason: 'king_capture', human_legal_moves: [] })),
    )
    renderApp()

    const result = await screen.findByTestId('result')
    expect(within(result).getByText('White wins by King capture')).toBeInTheDocument()
    expect(within(result).getByText('qwen3.5:9b left its king hanging')).toBeInTheDocument()
  })
})
