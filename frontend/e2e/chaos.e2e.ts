// The journeys through a game under Chaos rules: the built app at / against FastAPI with scripted LLM players
// (tests/e2e/server.py). The LLMs' illegal moves are played on the board, as the backend resolves them (ADR 0006).
import { expect, test, type Page } from '@playwright/test'

/** Waits for the human's move as White, live: their strip ringed, only their Time used ticking, no past position. */
async function yourMove(page: Page) {
  await expect(page.getByTestId('strip-white')).toHaveAttribute('data-to-move')
  await expect(page.getByTestId('strip-white')).toContainText('You')
  await expect(page.locator('[role=timer][data-ticking]')).toHaveCount(1)
  await expect(page.getByTestId('strip-white').getByRole('timer')).toHaveAttribute('data-ticking')
  await expect(page.locator('[data-testid="moves"] [aria-current=step]')).toHaveCount(0)
}

type Script = { white?: string[]; black?: string[] }

const square = (page: Page, name: string) => page.locator(`.chessboard rect.square[data-square="${name}"]`)
const pieceOn = (page: Page, name: string) => page.locator(`.chessboard g[data-piece][data-square="${name}"]`)
async function expectPiece(page: Page, name: string, piece: string) {
  await expect(pieceOn(page, name)).toHaveCount(1)
  await expect(pieceOn(page, name)).toHaveAttribute('data-piece', piece)
}
const arrows = (page: Page) => page.locator('.chessboard .arrow.chaos-arrow')
const spawnMarker = (page: Page) => page.locator('.chessboard .marker.spawn')
const moves = (page: Page) => page.getByTestId('moves')
const lastMove = (page: Page) => moves(page).locator('.ply.last')
/** The move viewed in the move history. */
const viewedMove = (page: Page) => moves(page).locator('[aria-current=step]')

/** The human's move, as UCI, by clicking its two squares; waits until the move list ends with `then`. */
async function move(page: Page, uci: string, then: string) {
  await yourMove(page)
  await expect(page.locator('.chessboard .board.input-enabled')).toBeAttached()
  await square(page, uci.slice(0, 2)).click()
  await square(page, uci.slice(2, 4)).click()
  await expect(lastMove(page)).toHaveText(then)
}

/** Opens the page on a Standard rules Play LLM game, then sets up the next game in the New game sheet and starts it. */
async function startFromSheet(
  page: Page,
  script: Script,
  setUp: (sheet: ReturnType<Page['getByRole']>) => Promise<void>,
  start = 'Play as White',
) {
  await page.request.post('/e2e/script', { data: script })
  const started = await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } },
  })
  expect(started.ok()).toBe(true)
  await page.goto('/')
  await yourMove(page)
  await expect(page.getByRole('img', { name: 'Standard rules' })).toBeVisible()
  await expect(page.getByRole('img', { name: 'Chaos rules' })).toHaveCount(0)

  await page.getByRole('banner').getByRole('button', { name: 'New game' }).click()
  const sheet = page.getByRole('dialog', { name: 'New game' })
  await setUp(sheet)
  await sheet.getByRole('button', { name: start }).click()
  await expect(sheet).toBeHidden()
}

test('a Play LLM game under Chaos rules: a chaos move, a spawn, an illegal castle, then King capture', async ({ page }) => {
  // Each chaos move is followed by its Legal counterpart, a6, asked for and never played.
  const black = ['Bb4', 'a6', 'Qg5', 'a6', 'e5', 'Qd5', 'a6', 'O-O', 'a6', 'Bxe1', 'a6']
  await startFromSheet(page, { black }, async (sheet) => {
    await sheet.getByRole('radio', { name: 'Chaos' }).click()
    await expect(sheet.getByRole('switch', { name: 'Legal counterpart' })).toBeChecked()
  })
  await expect(page.getByRole('img', { name: 'Chaos rules' })).toBeVisible()

  // The bishop jumps over its own pawn on e7.
  await move(page, 'e2e4', 'Bb4')
  await expect(arrows(page)).toHaveCount(1)
  await expect(arrows(page)).toHaveAttribute('data-arrow', 'f8b4')
  await expectPiece(page, 'b4', 'bb')
  await expect(lastMove(page)).toHaveClass(/chaos/)
  await expect(page.locator('.center-flash')).toHaveCount(0)
  await expect(page.getByRole('group', { name: 'Legal counterpart' }).getByTestId('counterpart-move')).toHaveText('1… a6')

  // The human's move clears the arrow.
  await move(page, 'c2c3', 'Qg5')
  await expect(arrows(page)).toHaveAttribute('data-arrow', 'd8g5')
  await move(page, 'd2d4', 'e5')
  await expect(arrows(page)).toHaveCount(0)

  // The queen is taken, so the next queen move is a spawn.
  await move(page, 'c1g5', 'Qd5')
  await expect(spawnMarker(page)).toHaveCount(1)
  await expect(arrows(page)).toHaveCount(0)
  await expectPiece(page, 'd5', 'bq')
  await expect(lastMove(page)).toHaveClass(/spawn/)
  // White's strip keeps the queen it took; Black's shows the queen it spawned.
  await expect(page.getByTestId('strip-white').getByRole('img', { name: 'Took: queen' })).toBeVisible()
  await expect(page.getByTestId('strip-black').getByRole('img', { name: 'Spawned: queen' })).toBeVisible()

  // Castling with the knight still on g8: the king and the rook move anyway, the knight is taken.
  await move(page, 'g1f3', 'O-O')
  await expect(arrows(page)).toHaveAttribute('data-arrow', 'e8g8')
  await expectPiece(page, 'g8', 'bk')
  await expectPiece(page, 'f8', 'br')
  await expect(pieceOn(page, 'e8')).toHaveCount(0)
  await expect(pieceOn(page, 'h8')).toHaveCount(0)

  // The bishop jumps over the pawn on c3 and the knight on d2, and takes the king.
  await move(page, 'b1d2', 'Bxe1')
  const result = page.getByTestId('result')
  await expect(result).toContainText('Black wins by King capture')
  // The detail is in the result's tooltip.
  await expect(result).toHaveAttribute('aria-description', /.+ took your king/)
  await expect(arrows(page)).toHaveAttribute('data-arrow', 'b4e1')
  await expectPiece(page, 'e1', 'bb')
  const mistakes = page.getByTestId('mistakes-card')
  await expect(mistakes).toContainText('Rule-breaking')
  await expect(mistakes).toContainText('Illegal moves5')
  await expect(mistakes).toContainText('Spawns1')

  // The history replays the spawn and the chaos move, with their marker and arrow.
  for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveText('Qd5')
  await expect(spawnMarker(page)).toHaveCount(1)
  await expectPiece(page, 'd5', 'bq')

  await moves(page).getByRole('button', { name: 'Bb4' }).click()
  await expect(viewedMove(page)).toHaveText('Bb4')
  await expect(arrows(page)).toHaveAttribute('data-arrow', 'f8b4')
  await expect(spawnMarker(page)).toHaveCount(0)
  await expectPiece(page, 'b4', 'bb')
  await expect(pieceOn(page, 'f8')).toHaveCount(0)

  await page.keyboard.press('ArrowLeft')
  await expect(arrows(page)).toHaveCount(0)
  await expectPiece(page, 'f8', 'bb')
})

test('an LLM faceoff under Chaos rules, started from the New game sheet, ends in a King left in check', async ({ page }) => {
  // White's queen jumps to f7; Black ignores the check, and loses at once. Each chaos move is followed by its Legal
  // counterpart.
  await startFromSheet(
    page,
    { white: ['Qxf7', 'e4'], black: ['Nf6', 'Kxf7'] },
    async (sheet) => {
      await sheet.getByRole('radio', { name: 'LLM faceoff' }).click()
      await sheet.getByRole('radio', { name: 'Chaos' }).click()
    },
    'Start faceoff',
  )

  const result = page.getByTestId('result')
  await expect(result).toContainText(/\(White\) wins by a king left in check/)
  await expect(result).toHaveAttribute('aria-description', /.+ \(Black\) left its own king in check/)
  await expect(page.getByRole('img', { name: 'Chaos rules' })).toBeVisible()
  await expect(moves(page).getByRole('button', { name: 'Qxf7' })).toHaveClass(/chaos/)
  await expect(moves(page).getByRole('button', { name: 'Nf6' })).toHaveClass(/chaos/)
  await expect(moves(page).locator('.ply')).toHaveCount(2)
  await expect(page.getByTestId('mistakes-card')).toContainText('1Illegal moves1')
  await expectPiece(page, 'f7', 'wq')
  await expectPiece(page, 'e8', 'bk')

  await page.keyboard.press('ArrowLeft')
  await expect(viewedMove(page)).toHaveText('Qxf7')
  await expect(arrows(page)).toHaveAttribute('data-arrow', 'd1f7')
})

test('Chaos is off limits while an LLM plays under Enforced decoding, the reason in its tooltip', async ({ page }) => {
  await page.request.post('/e2e/script', { data: {} })
  await page.request.post('/api/games', { data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } } })
  await page.goto('/')
  await page.getByRole('banner').getByRole('button', { name: 'New game' }).click()
  const sheet = page.getByRole('dialog', { name: 'New game' })
  const chaos = sheet.getByRole('radio', { name: 'Chaos' })
  await expect(chaos).not.toHaveAttribute('aria-disabled', 'true')

  await sheet.getByRole('button', { name: 'Advanced settings' }).click()
  await sheet.getByRole('radio', { name: /^Kept legal, not told/ }).click()
  await expect(chaos).toHaveAttribute('aria-disabled', 'true')
  await chaos.hover()
  await expect(page.locator('[data-slot=tooltip-content]')).toHaveText(
    'Needs an LLM that can play an illegal move: pick Board only or Board + legal moves in Advanced settings.',
  )

  // In a faceoff customized per LLM, one enforced side is enough.
  await sheet.getByRole('radio', { name: /^Board only/ }).click()
  await sheet.getByRole('radio', { name: 'LLM faceoff' }).click()
  await sheet.getByRole('switch', { name: 'Customize per LLM' }).click()
  await expect(chaos).not.toHaveAttribute('aria-disabled', 'true')
  await sheet.getByRole('radiogroup', { name: 'Black: what the LLM is given' }).getByRole('radio', { name: /^Shown and kept legal/ }).click()
  await expect(chaos).toHaveAttribute('aria-disabled', 'true')
  await expect(chaos).toHaveAttribute(
    'aria-description',
    'Needs every LLM able to play an illegal move: pick Board only or Board + legal moves for Black in Advanced settings.',
  )
})
