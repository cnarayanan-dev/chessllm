// The design language in the built app: the top bar on both pages, the tab icon and the one interface font.
/// <reference lib="dom" />
import { expect, test, type Page } from '@playwright/test'

/** Opens the game page on a new Play LLM game in which the human plays White. */
async function openGame(page: Page) {
  await page.request.post('/e2e/script', { data: {} })
  const started = await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } },
  })
  expect(started.ok()).toBe(true)
  await page.goto('/')
  await expect(page.getByTestId('status')).toHaveText('Your move (White)')
}

/** The top bar's links and buttons, in order. */
const actions = (page: Page) => page.getByRole('banner').locator('a, button')

test('the browser tab shows the rook', async ({ page }) => {
  await openGame(page)

  const href = await page.locator('link[rel=icon]').getAttribute('href')
  const icon = await page.request.get(href!)
  expect(icon.ok()).toBe(true)
  expect(await icon.text()).toContain('Merida rook')
})

/** The fonts of every text outside the board, and the web fonts loaded. */
async function fonts(page: Page) {
  await page.evaluate(() => document.fonts.ready)
  return page.evaluate(() => {
    const hasText = (element: Element) =>
      [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent!.trim())
    const texts = [...document.querySelectorAll('body *')].filter(
      (element) => !element.closest('.board-wrap') && hasText(element),
    )
    return {
      used: [...new Set(texts.map((element) => getComputedStyle(element).fontFamily))],
      loaded: [...new Set([...document.fonts].filter((font) => font.status === 'loaded').map((font) => font.family))],
    }
  })
}

const INTER = { used: ['"Inter Variable", sans-serif'], loaded: ['Inter Variable'] }

test('Inter is the only interface font: the game page, the Settings modal and the Analytics page', async ({ page }) => {
  await openGame(page)
  await page.getByRole('button', { name: 'Settings' }).click()
  await expect(page.getByRole('dialog', { name: 'Settings' })).toBeVisible()
  expect(await fonts(page)).toEqual(INTER)

  expect((await page.request.post('/e2e/leaderboard-games')).ok()).toBe(true)
  await page.goto('/analytics')
  await expect(page.locator('tbody tr')).not.toHaveCount(0)
  expect(await fonts(page)).toEqual(INTER)
})

test('the top bar on the game page: the mark, then Analytics, New game and Settings; ⌘K shows only in the tooltip', async ({ page }) => {
  await openGame(page)

  await expect(actions(page)).toHaveText(['ChessLLM', 'Analytics', 'New game', 'Settings'])
  const settings = page.getByRole('banner').getByRole('button', { name: 'Settings' })
  await expect(settings).toHaveText('Settings')

  await settings.hover()
  await expect(page.locator('[data-slot=tooltip-content]')).toHaveText('Settings ⌘K')

  await page.mouse.move(0, 400)
  await page.keyboard.press('ControlOrMeta+k')
  await expect(page.getByRole('dialog', { name: 'Settings' })).toBeVisible()
})

test('the top bar on the Analytics page: its Settings opens the modal on the game page', async ({ page }) => {
  await openGame(page)
  await page.goto('/analytics')

  await expect(actions(page)).toHaveText(['ChessLLM', 'Analytics', 'New game', 'Settings'])
  await page.getByRole('banner').getByRole('link', { name: 'Settings' }).click()

  await expect(page.getByRole('dialog', { name: 'Settings' })).toBeVisible()
  await expect(page).toHaveURL(/\/$/)
})

test('the top bar on the Analytics page: its New game starts one on the game page', async ({ page }) => {
  await openGame(page)
  const before = (await (await page.request.get('/api/games/current')).json()).game_id
  await page.goto('/analytics')

  await page.getByRole('banner').getByRole('link', { name: 'New game' }).click()

  await expect(page.getByTestId('status')).toHaveText('Your move (White)')
  await expect.poll(async () => (await (await page.request.get('/api/games/current')).json()).game_id).not.toBe(before)
  await expect(page).toHaveURL(/\/$/)
})
