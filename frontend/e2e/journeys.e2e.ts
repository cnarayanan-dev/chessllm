// The journeys through the page: the built app at / against FastAPI with scripted LLM players
// (tests/e2e_server.py). Each sets the LLMs' replies, as SAN, before its game starts.
import { expect, test, type Page } from '@playwright/test'

/** Waits for the human's move as White, live: the turn ring on their strip, no move timer, no past position viewed. */
async function yourMove(page: Page) {
  await expect(page.getByTestId('strip-white')).toHaveAttribute('data-to-move')
  await expect(page.getByTestId('strip-white')).toContainText('You')
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(page.getByTestId('status')).toHaveCount(0)
}

/** Expects the game over at the live position: no side has the turn ring, and no move timer runs. */
async function expectOver(page: Page) {
  await expect(page.locator('[data-to-move]')).toHaveCount(0)
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(page.getByTestId('status')).toHaveCount(0)
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
  await expect(page.locator('.chessboard .board.input-enabled')).toBeAttached()
  await square(page, uci.slice(0, 2)).click()
  await square(page, uci.slice(2, 4)).click()
}

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
  await expect(page.getByTestId('moves')).toContainText('✗ Qh4 illegal · try 1')
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
  await expect(page.getByTestId('moves')).toContainText('✗ Bb4 illegal · try 5')
  await expect(page.locator('.chessboard .board.input-enabled')).toHaveCount(0)
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

test('an LLM faceoff started from the settings modal plays to its end', async ({ page }) => {
  await playLlm(page, { white: ['f3', 'g4'], black: ['e5', 'Qh4#'] })

  await page.getByRole('button', { name: /Settings/ }).click()
  const settings = page.getByRole('dialog', { name: 'Settings' })
  await settings.getByRole('radio', { name: /LLM faceoff/ }).click()
  await settings.getByRole('button', { name: 'Start new game' }).click()
  await expect(settings).toBeHidden()

  const result = page.getByTestId('result')
  await expect(result).toContainText(/\(Black\) wins/)
  await expect(result).toContainText('by checkmate')
  await expect(page.getByTestId('moves')).toContainText(/1\.\s*f3\s*e5\s*2\.\s*g4\s*Qh4#/)
  await expectOver(page)
  await expectPiece(page, 'h4', 'bq')
})

test('stepping back through the move history and returning to live', async ({ page }) => {
  await playLlm(page, { black: ['e5', 'Nc6'] })
  await move(page, 'e2e4', 'e5')
  await move(page, 'g1f3', 'Nc6')
  const status = page.getByTestId('status')
  const backToLive = page.getByRole('button', { name: /Back to live/ })
  await expect(backToLive).toHaveCount(0)

  await page.keyboard.press('ArrowLeft')
  await expect(status).toHaveText('Viewing 2. Nf3 · → or Back to live')
  await expectPiece(page, 'f3', 'wn')
  await expect(page.locator('.chessboard g[data-piece][data-square="c6"]')).toHaveCount(0)
  await expect(page.locator('.chessboard .board.input-enabled')).toHaveCount(0)

  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await expect(status).toHaveText('Viewing the start position · → or Back to live')
  await expectPiece(page, 'e2', 'wp')
  await page.keyboard.press('ArrowLeft') // no further back than the start
  await expect(status).toHaveText('Viewing the start position · → or Back to live')

  await page.keyboard.press('ArrowRight')
  await expect(status).toHaveText('Viewing 1. e4 · → or Back to live')
  await expectPiece(page, 'e4', 'wp')

  await page.getByTestId('moves').getByRole('button', { name: 'e5' }).click()
  await expect(status).toHaveText('Viewing 1… e5 · → or Back to live')
  await expectPiece(page, 'e5', 'bp')
  await expect(page.locator('.chessboard g[data-piece][data-square="f3"]')).toHaveCount(0)

  await backToLive.click()
  await yourMove(page)
  await expectPiece(page, 'c6', 'bn')
  await expect(backToLive).toHaveCount(0)
  // The board takes the human's move again.
  await clickMove(page, 'f1c4')
  await expect(page.getByTestId('moves')).toContainText('Bc4')
})

test('the move history of an LLM faceoff, stepped through after its end', async ({ page }) => {
  await page.request.post('/e2e/script', { data: { white: ['f3', 'g4'], black: ['e5', 'Qh4#'] } })
  await page.request.post('/api/games', {
    data: { mode: 'llm_faceoff', white: { player: 'llm' }, black: { player: 'llm' } },
  })
  await page.goto('/')
  await expect(page.getByTestId('result')).toContainText('by checkmate')

  await page.keyboard.press('ArrowLeft')
  await expect(page.getByTestId('status')).toHaveText('Viewing 2. g4 · → or Back to live')
  await expect(page.locator('.chessboard g[data-piece][data-square="h4"]')).toHaveCount(0)
  await expectPiece(page, 'd8', 'bq')

  await page.keyboard.press('ArrowRight')
  await expectOver(page)
  await expectPiece(page, 'h4', 'bq')
})

test('the page at / credits the Merida pieces, the move sound and the model logos', async ({ page }) => {
  await playLlm(page, {})

  await expect(page.getByText('Pieces: Merida by Armando Hernandez Marroquin, GPLv2+', { exact: false })).toBeVisible()
  await expect(page.getByText('Move sound: Kenney, CC0', { exact: false })).toBeVisible()
  await expect(page.getByText('Model logos: LobeHub Icons, MIT', { exact: false })).toBeVisible()
  await expect(page.locator('.chessboard g[data-piece="wk"]')).toHaveCount(1)
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
