// The journeys through the page: the built app at / against FastAPI with scripted LLM players
// (tests/e2e_server.py). Each sets the LLMs' replies, as SAN, before its game starts.
import { expect, test, type Page } from '@playwright/test'

type Script = { white?: string[]; black?: string[] }

/** Scripts the LLMs, then opens the page on a new Play LLM game in which the human plays White. */
async function playLlm(page: Page, script: Script) {
  await page.request.post('/e2e/script', { data: script })
  const started = await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } },
  })
  expect(started.ok()).toBe(true)
  await page.goto('/')
  await expect(page.getByTestId('status')).toHaveText('Your move (White)')
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
  await expect(page.getByTestId('status')).toHaveText('Your move (White)')
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

  const banner = page.getByTestId('banner')
  await expect(banner).toContainText('White wins')
  await expect(banner).toContainText('by checkmate')
  await expect(page.getByTestId('status')).toHaveText('Game over')
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
  await expect(flash).toContainText('illegal · try 1 of 4')
  await expect(page.getByTestId('moves')).toContainText('✗ Qh4 illegal · try 1')
  await expectPiece(page, 'e5', 'bp')
  await expect(page.getByTestId('status')).toHaveText('Your move (White)')
})

test('the LLM forfeits after its retries', async ({ page }) => {
  await playLlm(page, { black: ['Qh4', 'Qh4', 'Ke7', 'Bb4'] })

  await clickMove(page, 'e2e4')

  const banner = page.getByTestId('banner')
  await expect(banner).toContainText('White wins')
  await expect(banner).toContainText('by forfeit')
  await expect(page.locator('.center-flash')).toContainText('✗ LLM forfeits: 4 illegal moves')
  await expect(page.getByTestId('status')).toHaveText('Game over')
  await expect(page.getByTestId('moves')).toContainText('✗ Bb4 illegal · try 4')
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

  const banner = page.getByTestId('banner')
  await expect(banner).toContainText(/\(Black\) wins/)
  await expect(banner).toContainText('by checkmate')
  await expect(page.getByTestId('moves')).toContainText(/1\.\s*f3\s*e5\s*2\.\s*g4\s*Qh4#/)
  await expect(page.getByTestId('status')).toHaveText('Game over')
  await expectPiece(page, 'h4', 'bq')
})

test('the page at / credits the Merida pieces and the move sound', async ({ page }) => {
  await playLlm(page, {})

  await expect(page.getByText('Pieces: Merida by Armando Hernandez Marroquin, GPLv2+', { exact: false })).toBeVisible()
  await expect(page.getByText('Move sound: Kenney, CC0', { exact: false })).toBeVisible()
  await expect(page.locator('.chessboard g[data-piece="wk"]')).toHaveCount(1)
})
