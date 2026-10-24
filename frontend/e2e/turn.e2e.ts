// The Turn panel under the Game card, against FastAPI with scripted LLM players (tests/e2e/server.py): with thinking
// off each scripted reply carries the Reasoning "Reasoning for <move>.".
import { expect, test, type Page } from '@playwright/test'

/** Scripts Black's LLM, then opens the page on a new Play LLM game in which the human plays White. */
async function playLlm(page: Page, black: string[], thinking = false) {
  await page.request.post('/e2e/script', { data: { black } })
  const started = await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm', model: 'qwen3.5:9b', thinking } },
  })
  expect(started.ok()).toBe(true)
  await page.goto('/')
}

/** Plays the human's move, as UCI (e2e4), by clicking its two squares once the board takes input. */
async function clickMove(page: Page, uci: string) {
  await expect(page.locator('.chessboard .board.input-enabled')).toBeAttached()
  const square = (name: string) => page.locator(`.chessboard rect.square[data-square="${name}"]`)
  await square(uci.slice(0, 2)).click()
  await square(uci.slice(2, 4)).click()
}

const lastMove = (page: Page) => page.locator('[data-testid="moves"] .ply.last')
const panel = (page: Page) => page.getByRole('region', { name: 'Turn' })
const badge = (page: Page) => panel(page).getByTestId('turn-move')
const tab = (page: Page, name: string) => panel(page).getByRole('tab', { name })

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem('chessllm.turnTab'))
})

test('the Turn panel sits under the Game card and follows the move history', async ({ page }) => {
  await playLlm(page, ['e5', 'Nc6'])
  await expect(panel(page)).toContainText('The LLM has not moved yet.')
  const card = await page.getByRole('region', { name: 'Game' }).boundingBox()
  const box = await panel(page).boundingBox()
  expect(box!.y).toBeGreaterThan(card!.y + card!.height)

  await clickMove(page, 'e2e4')
  await expect(lastMove(page)).toHaveText('e5')
  await clickMove(page, 'g1f3')
  await expect(lastMove(page)).toHaveText('Nc6')
  await expect(badge(page)).toHaveText('2… Nc6')
  await expect(panel(page)).toContainText('Reasoning for Nc6.')

  await page.keyboard.press('ArrowLeft') // 2. Nf3, the human's: the LLM's move before it
  await expect(badge(page)).toHaveText('1… e5')
  await expect(panel(page)).toContainText('Reasoning for e5.')

  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await expect(badge(page)).toHaveCount(0)
  await expect(panel(page)).toContainText('The LLM has not moved yet.')
})

test('the Prompt tab shows what was sent, and the Answer tab what came back', async ({ page }) => {
  await playLlm(page, ['e5'])

  await clickMove(page, 'e2e4')
  await expect(badge(page)).toHaveText('1… e5')
  await tab(page, 'Prompt').click()

  await expect(panel(page)).toContainText('PGN: 1. e4')
  await expect(panel(page)).not.toContainText('You are playing chess as Black')
  await panel(page).getByRole('button', { name: 'System prompt' }).click()
  await expect(panel(page)).toContainText('You are playing chess as Black')

  await tab(page, 'Answer').click()
  await expect(panel(page)).toContainText('"move": "e5"')
  await expect(panel(page)).toContainText('Legal')
})

test('with Prompt lab on, a side picked to play Described gets the piece list in every turn', async ({ page }) => {
  await playLlm(page, ['e5']) // a game on the page, so the New game sheet doesn't open by itself
  await page.getByRole('banner').getByRole('button', { name: 'Preferences' }).click()
  await page.getByRole('switch', { name: 'Prompt lab' }).click()
  await page.keyboard.press('Escape')

  await page.getByRole('banner').getByRole('button', { name: 'New game' }).click()
  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('button', { name: 'Advanced settings' }).click()
  await sheet.getByRole('combobox', { name: 'Prompt' }).click()
  await page.getByRole('option', { name: 'Described', exact: true }).click()
  await sheet.getByRole('button', { name: 'Play as White' }).click()

  await clickMove(page, 'e2e4')
  await expect(badge(page)).toHaveText('1… e5')
  await tab(page, 'Prompt').click()
  await expect(panel(page)).toContainText('Your pieces (Black): King e8')
})

test('a side picked to chat with moves remembers the game: the Prompt tab shows the whole conversation', async ({ page }) => {
  await playLlm(page, ['e5', 'Nc6']) // a game on the page, so the New game sheet doesn't open by itself
  await page.getByRole('banner').getByRole('button', { name: 'New game' }).click()
  const sheet = page.getByRole('dialog', { name: 'New game' })
  await sheet.getByRole('button', { name: 'Advanced settings' }).click()
  await sheet.getByRole('radio', { name: 'Chat with moves' }).click()
  await sheet.getByRole('button', { name: 'Play as White' }).click()
  await expect(page.getByRole('list', { name: "Black's settings" })).toHaveText('Chat with moves')

  await clickMove(page, 'e2e4')
  await expect(lastMove(page)).toHaveText('e5')
  await clickMove(page, 'g1f3')
  await expect(badge(page)).toHaveText('2… Nc6')
  await tab(page, 'Prompt').click()

  const turns = panel(page).getByRole('listitem', { name: /^Turn \d$/ })
  await expect(turns).toHaveCount(2)
  await expect(turns.nth(0)).toContainText('Opponent played e4.')
  await expect(turns.nth(0)).toContainText('"move": "e5"')
  await expect(turns.nth(1)).toContainText('Opponent played Nf3.')
})

test("after a Forfeit, the last attempt's Reasoning, marked as forfeited, and every attempt one step away", async ({
  page,
}) => {
  await playLlm(page, ['Qh4', 'Qh4', 'Ke7', 'Ke7', 'Bb4'])

  await clickMove(page, 'e2e4')

  await expect(page.getByTestId('result')).toContainText('by forfeit')
  await expect(badge(page)).toHaveText('forfeited')
  await expect(panel(page)).toContainText('Reasoning for Bb4.')
  await expect(panel(page)).toContainText('Attempt 5 of 5')
  await panel(page).getByRole('button', { name: 'Earlier attempt' }).click()
  await expect(panel(page)).toContainText('Reasoning for Ke7.')
})

test('with thinking on, the tab is Thinking', async ({ page }) => {
  await playLlm(page, ['e5'], true)

  await clickMove(page, 'e2e4')

  await expect(badge(page)).toHaveText('1… e5')
  await expect(tab(page, 'Thinking')).toHaveAttribute('aria-selected', 'true')
})

test("with Prompt lab on, Try probes an illegal move's turn again, its probes and tally kept over a reload", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('chessllm.promptLab', 'on'))
  // Fool's mate after an illegal Qxf2, then the two probes' answers.
  await playLlm(page, ['e5', 'Qxf2', 'Qh4#', 'Qh4#', 'Qxf2'])
  await clickMove(page, 'f2f3')
  await expect(lastMove(page)).toHaveText('e5')
  await clickMove(page, 'g2g4')
  await expect(lastMove(page)).toHaveText('Qh4#')
  await tab(page, 'Prompt').click()

  await panel(page).getByRole('combobox', { name: 'Prompt to probe with' }).click()
  await page.getByRole('option', { name: 'Described' }).click()
  const tryButton = panel(page).getByRole('button', { name: 'Try' })
  const probes = panel(page).getByRole('list', { name: 'Probes' })
  await tryButton.click()
  await expect(probes.getByRole('button')).toHaveCount(1)
  await tryButton.click()

  await expect(probes.getByRole('button')).toHaveCount(2)
  await expect(probes.getByRole('button').first()).toContainText('Qxf2 · Illegal')
  await expect(probes.getByRole('button').last()).toContainText('Qh4# · Legal')
  await expect(panel(page)).toContainText('Described: 1 of 2 legal')
  await probes.getByRole('button').last().click()
  await expect(probes).toContainText('Reasoning for Qh4#.')
  await expect(probes).toContainText('Your pieces (Black)')

  await page.reload()
  await tab(page, 'Prompt').click()
  await expect(panel(page)).toContainText('Described: 1 of 2 legal')
  await expect(panel(page).getByRole('list', { name: 'Probes' }).getByRole('button')).toHaveCount(2)
})

test('with Prompt lab on, the dock opens over the lower half, the board enlarged above, and tries and saves an edit', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 900 })
  await page.addInitScript(() => localStorage.setItem('chessllm.promptLab', 'on'))
  await playLlm(page, ['e5', 'Qxf2'])
  await clickMove(page, 'e2e4')
  await expect(lastMove(page)).toHaveText('e5')
  await tab(page, 'Prompt').click()
  const board = page.locator('.chessboard')
  const before = (await board.boundingBox())!

  await panel(page).getByRole('button', { name: /^Prompt:/ }).click()
  const dock = page.getByRole('region', { name: 'Dock' })
  await expect(dock).toBeVisible()
  const docked = (await dock.boundingBox())!
  expect(docked.y).toBeCloseTo(450, -1)
  await expect(page.getByRole('banner')).toBeHidden()
  await expect(page.getByTestId('strip-white')).toBeHidden()
  await expect(page.getByTestId('game-column')).toHaveAttribute('inert', '')
  const above = (await board.boundingBox())!
  expect(above.y + above.height).toBeLessThanOrEqual(docked.y)

  await dock.getByRole('textbox', { name: 'System prompt' }).fill('You are $color. Answer in JSON.')
  await dock.getByRole('button', { name: 'Try' }).click()
  await expect(dock.getByText('This version').locator('..')).toContainText('Qxf2 · Illegal')
  await dock.getByRole('textbox', { name: 'Name' }).fill('Short')
  await dock.getByRole('button', { name: 'Save as new version' }).click()
  await expect(dock).toContainText('based on Short')
  await dock.getByRole('button', { name: 'Close' }).click()

  await expect(dock).toBeHidden()
  await expect(page.getByRole('banner')).toBeVisible()
  await expect(page.getByTestId('game-column')).not.toHaveAttribute('inert')
  expect((await board.boundingBox())!.width).toBeCloseTo(before.width, 0)
  await expect(panel(page).getByRole('button', { name: /^Prompt:/ })).toContainText('Short')
})
