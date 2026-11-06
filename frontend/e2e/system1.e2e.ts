// A System 1 model as a side, through the page: the built app at / against FastAPI with scripted decision models
// (tests/e2e/server.py), so they run without a model server. Each sets the moves a model plays before its game starts.
import { expect, test, type Page } from '@playwright/test'

const square = (page: Page, name: string) => page.locator(`.chessboard rect.square[data-square="${name}"]`)

/** Plays the human's move by clicking its two squares, once the board takes input. */
async function clickMove(page: Page, uci: string) {
  await expect(page.locator('.chessboard .board.input-enabled')).toBeAttached()
  await square(page, uci.slice(0, 2)).click()
  await square(page, uci.slice(2, 4)).click()
}

test('a human plays a System 1 model from the New game sheet to checkmate, and Rematch keeps its settings', async ({ page }) => {
  await page.request.post('/e2e/restart')
  await page.request.post('/e2e/script', { data: { system1: { 'd1:2b': ['e5', 'Qh4#'] } } })
  await page.goto('/')

  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('radiogroup', { name: 'Opponent kind' }).getByRole('radio', { name: 'System 1' }).click()
  await sheet.getByRole('textbox', { name: 'Opponent' }).fill('d1:2b')
  await sheet.getByRole('button', { name: 'Advanced settings' }).click()
  await sheet.getByRole('spinbutton', { name: 'Choice temperature' }).fill('0.5')
  await sheet.getByRole('button', { name: 'Play as White' }).click()
  await expect(sheet).toBeHidden()

  await expect(page.getByTestId('strip-black')).toContainText('d1:2b')
  await clickMove(page, 'f2f3')
  await expect(page.locator('[data-testid="moves"] .ply.last')).toHaveText('e5')
  await clickMove(page, 'g2g4')
  await expect(page.getByTestId('result')).toContainText('Black wins by checkmate')

  // Its turn has no Thinking or Answer to show, and the Turn panel says so rather than breaking.
  const turn = page.getByRole('region', { name: 'Turn' })
  await expect(turn.getByTestId('turn-move')).toHaveText('2… Qh4#')
  await expect(turn.getByTestId('system1-turn')).toContainText('d1:2b is a System 1 model')
  await expect(turn.getByRole('tab')).toHaveCount(0)

  await page.getByRole('region', { name: 'Game' }).getByRole('button', { name: 'Rematch' }).click()
  await expect(page.getByTestId('strip-white')).toContainText('d1:2b')
  await expect(page.getByTestId('strip-black')).toContainText('You')
  const current = await (await page.request.get('/api/games/current')).json()
  expect(current.settings.white).toEqual({
    player: 'system1',
    model: 'd1:2b',
    base_url: 'http://localhost:11434',
    choice_temperature: 0.5,
  })
})

test('a faceoff between two System 1 models runs on its own to checkmate', async ({ page }) => {
  await page.request.post('/e2e/restart')
  await page.request.post('/e2e/script', {
    data: { system1: { 'd3:2b': ['f3', 'g4'], 'd1:2b': ['e5', 'Qh4#'] } },
  })
  await page.goto('/')

  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('radio', { name: 'LLM faceoff' }).click()
  await sheet.getByRole('radiogroup', { name: 'White kind' }).getByRole('radio', { name: 'System 1' }).click()
  await sheet.getByRole('radiogroup', { name: 'Black kind' }).getByRole('radio', { name: 'System 1' }).click()
  await sheet.getByRole('textbox', { name: 'Black model' }).fill('d1:2b')
  await sheet.getByRole('button', { name: 'Start faceoff' }).click()

  await expect(page.getByTestId('result')).toContainText('d1:2b (Black) wins')
  await expect(page.getByTestId('result')).toContainText('by checkmate')
  await expect(page.getByTestId('moves')).toContainText(/1\.\s*f3\s*e5\s*2\.\s*g4\s*Qh4#/)
})

test('a System 1 model the server lacks is refused at the start: "Could not start a game"', async ({ page }) => {
  await page.request.post('/e2e/restart')
  await page.request.post('/e2e/script', { data: { system1_missing: ['d1:2b'] } })
  await page.goto('/')

  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('radiogroup', { name: 'Opponent kind' }).getByRole('radio', { name: 'System 1' }).click()
  await sheet.getByRole('textbox', { name: 'Opponent' }).fill('d1:2b')
  await sheet.getByRole('button', { name: 'Play as White' }).click()

  const alert = page.getByRole('alert')
  await expect(alert).toContainText('Could not start a game')
  await expect(alert).toContainText("doesn't have d1:2b")
  await expect(page.getByTestId('strip-white')).toHaveCount(0)
})
