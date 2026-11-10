// A Hosted model, Claude Haiku 5.5, through the page: the built app at / against FastAPI with a scripted player
// (tests/e2e/server.py, which has a placeholder token, so Claude is offered) and no call to the provider.
import { expect, test, type Page } from '@playwright/test'

const square = (page: Page, name: string) => page.locator(`.chessboard rect.square[data-square="${name}"]`)

/** Plays the human's move by clicking its two squares, once the board takes input. */
async function clickMove(page: Page, uci: string) {
  await expect(page.locator('.chessboard .board.input-enabled')).toBeAttached()
  await square(page, uci.slice(0, 2)).click()
  await square(page, uci.slice(2, 4)).click()
}

/** Opens the New game sheet with Claude Haiku 5.5 as the opponent. */
async function chooseClaude(page: Page) {
  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('combobox', { name: 'Opponent' }).click()
  await page.getByRole('option', { name: /claude-haiku-5-5/ }).click()
  return sheet
}

test('a human plays Claude Haiku 5.5, listed with its Hosted mark, to checkmate', async ({ page }) => {
  await page.request.post('/e2e/restart')
  await page.request.post('/e2e/script', { data: { black: ['f6', 'g5'] } })
  await page.goto('/')

  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('combobox', { name: 'Opponent' }).click()
  await expect(page.getByRole('option', { name: /claude-haiku-5-5/ })).toContainText('Hosted')
  await page.getByRole('option', { name: /claude-haiku-5-5/ }).click()
  await sheet.getByRole('button', { name: 'Play as White' }).click()
  await expect(sheet).toBeHidden()

  await expect(page.getByTestId('strip-black')).toContainText('claude-haiku-5-5')
  await clickMove(page, 'e2e4')
  await expect(page.locator('[data-testid="moves"] .ply.last')).toHaveText('f6')
  await clickMove(page, 'd2d4')
  await expect(page.locator('[data-testid="moves"] .ply.last')).toHaveText('g5')
  await clickMove(page, 'd1h5')
  await expect(page.getByTestId('result')).toContainText('White wins by checkmate')
})

test('a provider failure aborts the game: no result, the reason in a tooltip, and Rematch', async ({ page }) => {
  await page.request.post('/e2e/restart')
  await page.request.post('/e2e/script', {
    data: { provider_failure: 'claude-haiku-5-5: no credit left, or a billing problem' },
  })
  await page.goto('/')

  const sheet = await chooseClaude(page)
  await sheet.getByRole('button', { name: 'Play as White' }).click()
  await expect(sheet).toBeHidden()
  await clickMove(page, 'e2e4')

  const result = page.getByTestId('result')
  await expect(result).toHaveText('Game aborted')
  await expect(result).toHaveAttribute('aria-description', /no credit left/)
  await expect(page.getByRole('region', { name: 'Game' }).getByRole('button', { name: 'Rematch' })).toBeVisible()
  const current = await (await page.request.get('/api/games/current')).json()
  expect(current.status).toBe('aborted')
  expect(current.result).toBeNull()

  // Nobody drives it on: no board input
  await expect(page.locator('.chessboard .board.input-enabled')).not.toBeAttached()
})
