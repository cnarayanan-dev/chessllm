// The journeys through the page: the built app at / against FastAPI with scripted LLM players
// (tests/e2e/server.py). Each sets the LLMs' replies, as SAN, before its game starts.
import { expect, test, type Page } from '@playwright/test'

/** Waits for the human's move as White, live: the turn ring on their strip, no move timer, no past position viewed. */
async function yourMove(page: Page) {
  await expect(page.getByTestId('strip-white')).toHaveAttribute('data-to-move')
  await expect(page.getByTestId('strip-white')).toContainText('You')
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(viewedMove(page)).toHaveCount(0)
}

/** Expects the game over at the live position: no side has the turn ring, and no move timer runs. */
async function expectOver(page: Page) {
  await expect(page.locator('[data-to-move]')).toHaveCount(0)
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(viewedMove(page)).toHaveCount(0)
}

type Script = { white?: string[]; black?: string[] }

/** Scripts the LLMs, then opens the page on a new Play LLM game in which the human plays White. */
async function playLlm(page: Page, script: Script) {
  await page.request.post('/e2e/script', { data: script })
  const started = await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } },
  })
  expect(started.ok()).toBe(true)
  await page.goto('/')
  await yourMove(page)
}

const square = (page: Page, name: string) => page.locator(`.chessboard rect.square[data-square="${name}"]`)
/** Expects the board to show `piece` (wq: a white queen) on `name`, and no other, once its moves are drawn. */
async function expectPiece(page: Page, name: string, piece: string) {
  const pieces = page.locator(`.chessboard g[data-piece][data-square="${name}"]`)
  await expect(pieces).toHaveCount(1)
  await expect(pieces).toHaveAttribute('data-piece', piece)
}

const lastMove = (page: Page) => page.locator('[data-testid="moves"] .ply.last')
/** The move viewed in the move history. */
const viewedMove = (page: Page) => page.locator('[data-testid="moves"] [aria-current=step]')
const boardTakesMoves = (page: Page) => page.locator('.chessboard .board.input-enabled')

/**
 * The human's move, as UCI (e2e4), by clicking its two squares. Waits until the move list ends with `then`, in SAN:
 * the LLM's reply, or the human's move if it ends the game.
 */
async function move(page: Page, uci: string, then: string) {
  await clickMove(page, uci)
  await expect(lastMove(page)).toHaveText(then)
}

/** Clicks the two squares of a move, as UCI (e2e4), once it is the human's move and the board takes input. */
async function clickMove(page: Page, uci: string) {
  await yourMove(page)
  // The board takes input once the LLM's move has been drawn.
  await expect(boardTakesMoves(page)).toBeAttached()
  await square(page, uci.slice(0, 2)).click()
  await square(page, uci.slice(2, 4)).click()
}

test('a first visit: an empty board and the New game sheet with the defaults; closed, New game and ⌘K open it again; a reload keeps the game started', async ({ page }) => {
  await page.request.post('/e2e/restart')
  await page.request.post('/e2e/script', { data: { black: ['e5'] } })
  await page.goto('/')

  const sheet = page.getByRole('dialog', { name: 'New game' })
  await expect(sheet).toBeVisible()
  await expect(sheet.getByRole('radio', { name: 'Play LLM' })).toBeChecked()
  await expect(sheet.getByRole('combobox', { name: 'Opponent' })).toContainText('llama3:8b')
  await expect(page.locator('.chessboard rect.square')).toHaveCount(64)
  await expect(page.locator('.chessboard g[data-piece]')).toHaveCount(0)
  expect((await page.request.get('/api/games/current')).status()).toBe(404)

  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()
  await expect(page.locator('.chessboard g[data-piece]')).toHaveCount(0)
  await page.getByRole('banner').getByRole('button', { name: 'New game' }).click()
  await expect(sheet).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()
  await page.keyboard.press('ControlOrMeta+k')
  await expect(sheet).toBeVisible()
  expect((await page.request.get('/api/games/current')).status()).toBe(404)

  await sheet.getByRole('button', { name: 'Play as White' }).click()
  await expect(sheet).toBeHidden()
  await move(page, 'e2e4', 'e5')
  await expect(page.getByTestId('strip-black')).toContainText('llama3:8b')

  await page.reload()
  await expect(lastMove(page)).toHaveText('e5')
  await expect(sheet).toBeHidden()
})

test('a Play LLM game to checkmate', async ({ page }) => {
  await playLlm(page, { black: ['e5', 'Nc6', 'Nf6'] })

  await move(page, 'e2e4', 'e5')
  await move(page, 'f1c4', 'Nc6')
  await move(page, 'd1h5', 'Nf6')
  await move(page, 'h5f7', 'Qxf7#')

  const result = page.getByTestId('result')
  await expect(result).toContainText('White wins')
  await expect(result).toContainText('by checkmate')
  await expectOver(page)
  await expect(page.getByTestId('moves')).toContainText('Qxf7#')
  await expectPiece(page, 'f7', 'wq')
})

test('an illegal LLM try flashes on the board, then its legal retry is played', async ({ page }) => {
  // Qh4 is blocked by Black's own pawn on e7.
  await playLlm(page, { black: ['Qh4', 'e5'] })

  await move(page, 'e2e4', 'e5')

  const flash = page.locator('.center-flash')
  await expect(flash).toContainText('✗ LLM move illegal')
  await expect(flash).toContainText('Qh4')
  await expect(flash).toContainText('illegal · try 1 of 5')
  await expect(page.getByTestId('moves').locator('.mistake.illegal')).toHaveText('Qh4 illegal · try 1')
  await expectPiece(page, 'e5', 'bp')
  await yourMove(page)
})

test('the LLM forfeits after its retries', async ({ page }) => {
  await playLlm(page, { black: ['Qh4', 'Qh4', 'Ke7', 'Ke7', 'Bb4'] })

  await clickMove(page, 'e2e4')

  const result = page.getByTestId('result')
  await expect(result).toContainText('White wins')
  await expect(result).toContainText('by forfeit')
  await expect(page.locator('.center-flash')).toContainText('✗ LLM forfeits: 5 illegal moves')
  await expectOver(page)
  await expect(page.getByTestId('moves').locator('.mistake.illegal').last()).toHaveText('Bb4 illegal · try 5')
  await expect(boardTakesMoves(page)).toHaveCount(0)
})

test('the human promotes a pawn through the promotion dialog', async ({ page }) => {
  await playLlm(page, { black: ['h5', 'h4', 'h3', 'hxg2', 'gxh1=Q'] })
  await move(page, 'a2a4', 'h5')
  await move(page, 'a4a5', 'h4')
  await move(page, 'a5a6', 'h3')
  await move(page, 'a6b7', 'hxg2')

  await clickMove(page, 'b7a8')
  const knight = page.locator('.promotion-dialog-button[data-piece="wn"]')
  await expect(knight).toBeVisible()
  await knight.click()

  await expect(lastMove(page)).toHaveText('gxh1=Q')
  await expect(page.getByTestId('moves')).toContainText('bxa8=N')
  await expectPiece(page, 'a8', 'wn')
  await expectPiece(page, 'h1', 'bq')
})

test('an LLM faceoff started from the New game sheet plays to its end', async ({ page }) => {
  await playLlm(page, { white: ['f3', 'g4'], black: ['e5', 'Qh4#'] })

  await page.getByRole('banner').getByRole('button', { name: 'New game' }).click()
  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('radio', { name: 'LLM faceoff' }).click()
  await sheet.getByRole('button', { name: 'Start faceoff' }).click()
  await expect(sheet).toBeHidden()

  const result = page.getByTestId('result')
  await expect(result).toContainText(/\(Black\) wins/)
  await expect(result).toContainText('by checkmate')
  await expect(page.getByTestId('moves')).toContainText(/1\.\s*f3\s*e5\s*2\.\s*g4\s*Qh4#/)
  await expectOver(page)
  await expectPiece(page, 'h4', 'bq')
})

test('Rematch after a Play LLM game: the human plays Black, the board turns and the LLM opens', async ({ page }) => {
  await playLlm(page, { white: ['e4'], black: ['Qh4', 'Qh4', 'Ke7', 'Ke7', 'Bb4'] })
  await clickMove(page, 'e2e4')
  await expect(page.getByTestId('result')).toContainText('by forfeit')
  await expect(page.getByRole('button', { name: 'New game' })).toHaveCount(1) // the top bar's alone

  const rematch = page.getByRole('region', { name: 'Game' }).getByRole('button', { name: 'Rematch' })
  await expect(rematch).toHaveAttribute('aria-description', 'Same settings, you play Black')
  await rematch.hover()
  await expect(page.locator('[data-slot=tooltip-content]')).toHaveText('Same settings, you play Black')
  await rematch.click()

  await expect(lastMove(page)).toHaveText('e4')
  await expect(page.getByTestId('result')).toHaveCount(0)
  await expect(page.getByTestId('strip-black')).toHaveAttribute('data-to-move')
  await expect(page.getByTestId('strip-black')).toContainText('You')
  expect(await stripsAroundBoard(page)).toEqual(['white', 'black'])
})

test('Rematch after an LLM faceoff: the two LLMs change sides, each with its own settings', async ({ page }) => {
  await page.request.post('/e2e/script', { data: { white: ['f3', 'g4'], black: ['e5', 'Qh4#'] } })
  const started = await page.request.post('/api/games', {
    data: {
      mode: 'llm_faceoff',
      white: { player: 'llm', model: 'qwen3.5:9b', thinking: true },
      black: { player: 'llm', model: 'llama3:8b' },
    },
  })
  expect(started.ok()).toBe(true)
  await page.goto('/')
  const card = page.getByRole('region', { name: 'Game' })
  const players = card.getByRole('list', { name: 'Players' }).getByRole('listitem')
  await expect(page.getByTestId('result')).toContainText('by checkmate')
  await expect(players).toHaveText(['White qwen3.5:9b', 'Black llama3:8b'])

  const rematch = card.getByRole('button', { name: 'Rematch' })
  await expect(rematch).toHaveAttribute('aria-description', 'Same settings, the LLMs swap colours')
  await rematch.click()

  await expect(players).toHaveText(['White llama3:8b', 'Black qwen3.5:9b'])
  await expect(card.getByRole('img', { name: 'White: Thinking off' })).toBeVisible()
  await expect(card.getByRole('img', { name: 'Black: Thinking on' })).toBeVisible()
  await expect(page.getByTestId('result')).toContainText('by checkmate')
  await expectOver(page)
})

test('stepping back through the move history and returning to live', async ({ page }) => {
  await playLlm(page, { black: ['e5', 'Nc6'] })
  await move(page, 'e2e4', 'e5')
  await move(page, 'g1f3', 'Nc6')
  await expect(viewedMove(page)).toHaveCount(0)

  await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveText('Nf3')
  await expectPiece(page, 'f3', 'wn')
  await expect(page.locator('.chessboard g[data-piece][data-square="c6"]')).toHaveCount(0)
  await expect(boardTakesMoves(page)).toHaveCount(0)
  // No Back to live button, and no status line.
  await expect(page.getByRole('button', { name: /live/i })).toHaveCount(0)
  await expect(page.getByTestId('status')).toHaveCount(0)

  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveCount(0)
  await expectPiece(page, 'e2', 'wp')
  await page.keyboard.press('ArrowLeft') // no further back than the start
  await expectPiece(page, 'e2', 'wp')
  await expect(boardTakesMoves(page)).toHaveCount(0)

  await page.keyboard.press('ArrowRight')
  await expect(viewedMove(page)).toHaveText('e4')
  await expectPiece(page, 'e4', 'wp')

  await page.getByTestId('moves').getByRole('button', { name: 'e5' }).click()
  await expect(viewedMove(page)).toHaveText('e5')
  await expectPiece(page, 'e5', 'bp')
  await expect(page.locator('.chessboard g[data-piece][data-square="f3"]')).toHaveCount(0)

  // Clicking the latest move returns to live.
  await lastMove(page).click()
  await expect(viewedMove(page)).toHaveCount(0)
  await yourMove(page)
  await expectPiece(page, 'c6', 'bn')
  // The board takes the human's move again.
  await clickMove(page, 'f1c4')
  await expect(page.getByTestId('moves')).toContainText('Bc4')
})

test("an LLM move arriving while a past position is viewed leaves the board there, and the latest move pulses", async ({ page }) => {
  await playLlm(page, { black: ['e5', 'Nc6'] })
  await move(page, 'e2e4', 'e5')
  // The LLM's next move is held back until a past position is viewed.
  let release!: () => void
  const released = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/games/current/llm-turn', async (route) => {
    await released
    await route.continue()
  })

  await clickMove(page, 'g1f3')
  await expect(lastMove(page)).toHaveText('Nf3')
  await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveText('e5')
  // The LLM's move runs on its strip meanwhile.
  await expect(page.getByTestId('strip-black').getByRole('timer')).toBeVisible()
  release()

  await expect(lastMove(page)).toHaveText('Nc6')
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(lastMove(page)).toHaveClass(/arrived/)
  await expect(viewedMove(page)).toHaveText('e5')
  await expect(page.locator('.chessboard g[data-piece][data-square="c6"]')).toHaveCount(0)
  await expect(page.locator('.chessboard g[data-piece][data-square="f3"]')).toHaveCount(0)

  // → up to the latest move returns to live.
  await page.keyboard.press('ArrowRight')
  await expect(viewedMove(page)).toHaveText('Nf3')
  await page.keyboard.press('ArrowRight')
  await yourMove(page)
  await expectPiece(page, 'c6', 'bn')
  await expect(boardTakesMoves(page)).toBeAttached()
})

test('the move history of an LLM faceoff, stepped through after its end', async ({ page }) => {
  await page.request.post('/e2e/script', { data: { white: ['f3', 'g4'], black: ['e5', 'Qh4#'] } })
  await page.request.post('/api/games', {
    data: { mode: 'llm_faceoff', white: { player: 'llm' }, black: { player: 'llm' } },
  })
  await page.goto('/')
  await expect(page.getByTestId('result')).toContainText('by checkmate')

  await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveText('g4')
  await expect(page.locator('.chessboard g[data-piece][data-square="h4"]')).toHaveCount(0)
  await expectPiece(page, 'd8', 'bq')

  await page.keyboard.press('ArrowRight')
  await expectOver(page)
  await expectPiece(page, 'h4', 'bq')
})

/** The Opera game, Morphy's 17 moves, as an LLM faceoff. */
const OPERA = {
  white: ['e4', 'Nf3', 'd4', 'dxe5', 'Qxf3', 'Bc4', 'Qb3', 'Nc3', 'Bg5', 'Nxb5', 'Bxb5+', 'O-O-O', 'Rxd7', 'Rd1', 'Bxd7+', 'Qb8+', 'Rd8#'],
  black: ['e5', 'd6', 'Bg4', 'Bxf3', 'dxe5', 'Nf6', 'Qe7', 'c6', 'b5', 'cxb5', 'Nbd7', 'Rd8', 'Rxd7', 'Qe6', 'Nxd7', 'Nxb8'],
}

test('on a laptop the moves list keeps its height in a long game, about 8 rows, and follows the latest move or the one viewed', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await playLlm(page, {})
  const list = page.locator('.moves-card [data-slot=scroll-area-viewport]')
  const empty = (await list.boundingBox())!.height

  await page.request.post('/e2e/script', { data: OPERA })
  await page.request.post('/api/games', { data: { mode: 'llm_faceoff', white: { player: 'llm' }, black: { player: 'llm' } } })
  await page.reload()
  await expect(page.getByTestId('result')).toContainText('by checkmate')

  const box = (await list.boundingBox())!
  expect(box.height).toBe(empty)
  /** The move numbers whose row shows in full in the list. */
  const rowsInView = () =>
    list.locator('.no').evaluateAll((numbers, [top, bottom]) =>
      numbers
        .filter((number) => {
          const { top: rowTop, bottom: rowBottom } = number.getBoundingClientRect()
          return rowTop >= top - 0.5 && rowBottom <= bottom + 0.5
        })
        .map((number) => number.textContent),
    [box.y, box.y + box.height])
  // Scrolled to the latest move.
  await expect.poll(rowsInView).toEqual(['10', '11', '12', '13', '14', '15', '16', '17'].map((n) => `${n}.`))
  await expect(page.getByTestId('moves').getByRole('button', { name: 'Rd8#' })).toBeInViewport()

  // Stepping back keeps the move viewed in view.
  for (let i = 0; i < 27; i++) await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveText('Bg4')
  await expect.poll(rowsInView).toContain('3.')
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveText('Nf3')
  await expect.poll(rowsInView).toContain('2.')
})

test('the page at / credits the Merida pieces, the move sound and the model logos', async ({ page }) => {
  await playLlm(page, {})

  await expect(page.getByText('Pieces: Merida by Armando Hernandez Marroquin, GPLv2+', { exact: false })).toBeVisible()
  await expect(page.getByText('Move sound: Kenney, CC0', { exact: false })).toBeVisible()
  await expect(page.getByText('Model logos: LobeHub Icons, MIT', { exact: false })).toBeVisible()
  await expect(page.locator('.chessboard g[data-piece="wk"]')).toHaveCount(1)
})

test('Move sound is off until switched on in Preferences; then every move clicks, in this browser across reloads', async ({ page }) => {
  // Counts the sounds the page plays, as the paths of their files.
  await page.addInitScript(() => {
    const played: string[] = []
    Object.assign(window, { played })
    HTMLMediaElement.prototype.play = function (this: HTMLMediaElement) {
      played.push(new URL(this.src).pathname)
      return Promise.resolve()
    }
  })
  const played = () => page.evaluate(() => (window as unknown as { played: string[] }).played)
  await playLlm(page, { black: ['e5', 'Nc6'] })

  await move(page, 'e2e4', 'e5')
  expect(await played()).toEqual([])

  await page.getByRole('button', { name: 'Preferences' }).click()
  const sound = page.getByRole('dialog', { name: 'Preferences' }).getByRole('switch', { name: 'Move sound' })
  await expect(sound).not.toBeChecked()
  await sound.click()
  await expect(sound).toBeChecked()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Preferences' })).toHaveCount(0)

  await move(page, 'g1f3', 'Nc6')
  await expect.poll(played).toEqual(['/static/sounds/move.mp3', '/static/sounds/move.mp3']) // Nf3 and Nc6

  await page.reload()
  await page.getByRole('button', { name: 'Preferences' }).click()
  await expect(page.getByRole('dialog', { name: 'Preferences' }).getByRole('switch', { name: 'Move sound' })).toBeChecked()
})

/** The strips above and below the board, top first, by their side, each checked to be at the board's width. */
async function stripsAroundBoard(page: Page) {
  const board = (await page.locator('.chessboard').boundingBox())!
  const sides: string[] = []
  for (const color of ['white', 'black']) {
    const strip = (await page.getByTestId(`strip-${color}`).boundingBox())!
    expect(Math.abs(strip.width - board.width)).toBeLessThan(2)
    if (strip.y + strip.height <= board.y) sides.unshift(color)
    else if (strip.y >= board.y + board.height) sides.push(color)
  }
  return sides
}

/** Holds every LLM turn the page asks for until it is let go, one at a time, so its move can be seen running. */
async function holdLlmTurns(page: Page) {
  const held: (() => void)[] = []
  await page.route('**/api/games/current/llm-turn', async (route) => {
    await new Promise<void>((resolve) => held.push(resolve))
    await route.continue()
  })
  return async () => {
    await expect.poll(() => held.length).toBe(1)
    held.shift()!()
  }
}

test('the player strips: the LLM above the board with its logo, the ring and the timer during its move', async ({ page }) => {
  await playLlm(page, { black: ['e5'] })
  const white = page.getByTestId('strip-white')
  const black = page.getByTestId('strip-black')

  expect(await stripsAroundBoard(page)).toEqual(['black', 'white'])
  await expect(black).toContainText('llama3:8b')
  await expect(black.getByRole('img', { name: 'Meta' })).toBeVisible()
  await expect(white).toContainText('You')
  await expect(black).not.toHaveAttribute('data-to-move')

  const letGo = await holdLlmTurns(page)
  await clickMove(page, 'e2e4')
  await expect(black).toHaveAttribute('data-to-move')
  await expect(white).not.toHaveAttribute('data-to-move')
  const timer = black.getByRole('timer')
  await expect(timer).toHaveText('0s')
  await expect(timer).toHaveText('2s', { timeout: 5000 })
  await expect(page.getByRole('timer')).toHaveCount(1)

  await letGo()
  await expect(lastMove(page)).toHaveText('e5')
  await yourMove(page)
})

test('in an LLM faceoff White is at the bottom and the timer moves between the strips turn by turn', async ({ page }) => {
  await page.request.post('/e2e/script', { data: { white: ['f3', 'g4'], black: ['e5', 'Qh4#'] } })
  const letGo = await holdLlmTurns(page)
  await page.request.post('/api/games', {
    data: { mode: 'llm_faceoff', white: { player: 'llm' }, black: { player: 'llm' } },
  })
  await page.goto('/')
  const timerOf = (color: string) => page.getByTestId(`strip-${color}`).getByRole('timer')

  await expect(timerOf('white')).toBeVisible()
  expect(await stripsAroundBoard(page)).toEqual(['black', 'white'])
  await expect(timerOf('black')).toHaveCount(0)
  await letGo()
  await expect(timerOf('black')).toBeVisible()
  await expect(timerOf('white')).toHaveCount(0)
  await expect(page.getByTestId('strip-black')).toHaveAttribute('data-to-move')
  await letGo()
  await expect(timerOf('white')).toBeVisible()
  await expect(timerOf('black')).toHaveCount(0)
  await letGo()
  await letGo()
  await expect(page.getByTestId('result')).toContainText('by checkmate')
  await expectOver(page)
})
