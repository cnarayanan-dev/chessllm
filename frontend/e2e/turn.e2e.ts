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
