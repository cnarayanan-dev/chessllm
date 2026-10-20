// The design language in the built app: the top bar on both pages, the tab icon and the one interface font.
/// <reference lib="dom" />
import { expect, test, type Page } from '@playwright/test'

/** Waits for the human's move as White, live: the turn ring on their strip, no move timer, no past position viewed. */
async function yourMove(page: Page) {
  await expect(page.getByTestId('strip-white')).toHaveAttribute('data-to-move')
  await expect(page.getByTestId('strip-white')).toContainText('You')
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(page.locator('[data-testid="moves"] [aria-current=step]')).toHaveCount(0)
}

/** Opens the game page on a new Play LLM game in which the human plays White. */
async function openGame(page: Page) {
  await page.request.post('/e2e/script', { data: {} })
  const started = await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } },
  })
  expect(started.ok()).toBe(true)
  await page.goto('/')
  await yourMove(page)
}

/** The top bar's links and buttons, in order, by their accessible names. */
const actions = (page: Page) =>
  page
    .getByRole('banner')
    .locator('a, button')
    .evaluateAll((elements) => elements.map((element) => element.getAttribute('aria-label') ?? element.textContent))

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

test('Inter is the only interface font: the game page, the New game sheet and the Analytics page', async ({ page }) => {
  await openGame(page)
  await page.getByRole('banner').getByRole('button', { name: 'New game' }).click()
  await expect(page.getByRole('dialog', { name: 'New game' })).toBeVisible()
  await page.getByRole('button', { name: 'Advanced settings' }).click()
  expect(await fonts(page)).toEqual(INTER)

  expect((await page.request.post('/e2e/leaderboard-games')).ok()).toBe(true)
  await page.goto('/analytics')
  await expect(page.locator('tbody tr')).not.toHaveCount(0)
  expect(await fonts(page)).toEqual(INTER)
})

test('the top bar on the game page: the mark, then Analytics and New game, and Preferences at the end; ⌘K shows only in the tooltip', async ({ page }) => {
  await openGame(page)

  expect(await actions(page)).toEqual(['ChessLLM', 'Analytics', 'New game', 'Preferences'])
  const bar = (await page.getByRole('banner').boundingBox())!
  const preferences = (await page.getByRole('button', { name: 'Preferences' }).boundingBox())!
  expect(bar.x + bar.width - (preferences.x + preferences.width)).toBeLessThan(40) // on the right
  const newGame = page.getByRole('banner').getByRole('button', { name: 'New game' })
  await expect(newGame).toHaveText('New game')

  await newGame.hover()
  await expect(page.locator('[data-slot=tooltip-content]')).toHaveText('New game ⌘K')

  await page.mouse.move(0, 400)
  await page.keyboard.press('ControlOrMeta+k')
  await expect(page.getByRole('dialog', { name: 'New game' })).toBeVisible()
})

test('the top bar on the Analytics page: New game and ⌘K open the New game sheet on the game page', async ({ page }) => {
  await openGame(page)
  const before = (await (await page.request.get('/api/games/current')).json()).game_id
  await page.goto('/analytics')

  expect(await actions(page)).toEqual(['ChessLLM', 'Analytics', 'New game', 'Preferences'])
  await page.getByRole('banner').getByRole('link', { name: 'New game' }).click()
  const sheet = page.getByRole('dialog', { name: 'New game' })
  await expect(sheet).toBeVisible()
  await expect(page).toHaveURL(/\/$/)

  // Closing it leaves the game as it was; starting replaces it.
  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()
  await yourMove(page)
  expect((await (await page.request.get('/api/games/current')).json()).game_id).toBe(before)

  await page.goto('/analytics')
  await page.keyboard.press('ControlOrMeta+k')
  await sheet.getByRole('button', { name: 'Play as White' }).click()
  await yourMove(page)
  await expect.poll(async () => (await (await page.request.get('/api/games/current')).json()).game_id).not.toBe(before)
})

test('the top bar on the Analytics page: Preferences opens there, with Move sound', async ({ page }) => {
  await page.goto('/analytics')

  const preferences = page.getByRole('banner').getByRole('button', { name: 'Preferences' })
  await preferences.hover()
  await expect(page.locator('[data-slot=tooltip-content]')).toHaveText('Preferences')
  await preferences.click()

  await expect(page.getByRole('dialog', { name: 'Preferences' }).getByRole('switch', { name: 'Move sound' })).not.toBeChecked()
  await expect(page).toHaveURL(/\/analytics$/)
})

/** The box of each of the game page's columns. */
async function columns(page: Page) {
  const box = async (testId: string) => (await page.getByTestId(testId).boundingBox())!
  return { game: await box('game-column'), board: await box('board-column'), moves: await box('moves-column') }
}

test('at desktop width the game page has three columns: the Game card ¼, the board ½, the moves ¼', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openGame(page)

  const { game, board, moves } = await columns(page)
  expect(game.x + game.width).toBeLessThan(board.x)
  expect(board.x + board.width).toBeLessThan(moves.x)
  expect(new Set([game.y, board.y, moves.y]).size).toBe(1)
  expect(board.width / game.width).toBeCloseTo(2, 1)
  expect(moves.width).toBeCloseTo(game.width, 0)
  await expect(page.getByRole('region', { name: 'Game' })).toBeVisible()
})

test('between 760px and 1100px: two columns, the board, and the moves with the Game card under them', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 900 })
  await openGame(page)

  const { game, board, moves } = await columns(page)
  expect(board.x + board.width).toBeLessThan(moves.x)
  expect(game.x).toBe(moves.x)
  expect(game.y).toBeGreaterThan(moves.y + moves.height)
})

test('below 760px: one column, the board, the moves, then the Game card', async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 900 })
  await openGame(page)

  const { game, board, moves } = await columns(page)
  expect(new Set([game.x, board.x, moves.x]).size).toBe(1)
  expect(moves.y).toBeGreaterThan(board.y + board.height)
  expect(game.y).toBeGreaterThan(moves.y + moves.height)
})

const settingChips = (page: Page) => page.getByRole('list', { name: 'Settings' }).getByRole('img')

/** Expects every setting chip to be a 28px circle holding one icon, inside the Game card. */
async function expectChipsWhole(page: Page) {
  const card = (await page.getByRole('region', { name: 'Game' }).boundingBox())!
  for (const chip of await settingChips(page).all()) {
    const box = (await chip.boundingBox())!
    expect([box.width, box.height]).toEqual([28, 28])
    expect(box.x).toBeGreaterThanOrEqual(card.x)
    expect(box.x + box.width).toBeLessThanOrEqual(card.x + card.width)
    await expect(chip.locator('svg')).toHaveCount(1)
  }
}

test("the Game card's settings are icons, each explained in a tooltip on hover and on keyboard focus", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openGame(page)

  await expect(settingChips(page)).toHaveCount(5)
  await expectChipsWhole(page)
  await settingChips(page).first().hover()
  const tooltip = page.locator('[data-slot=tooltip-content]')
  await expect(tooltip).toHaveText('Board only (Free) The LLM finds its own moves and can play an illegal one.')
  await expect(tooltip).toBeInViewport({ ratio: 1 })
  await page.mouse.move(0, 0)
  await expect(tooltip).toBeHidden()

  await settingChips(page).nth(1).focus()
  await expect(tooltip).toHaveText('Standard rules Normal chess. Rated.')
})

for (const width of [1101, 761]) {
  test(`at ${width}px a faceoff's per-side settings show whole, each with its side's dot`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.request.post('/e2e/script', { data: {} })
    const started = await page.request.post('/api/games', {
      data: {
        mode: 'llm_faceoff',
        white: { player: 'llm', llm_constraints: 'listed_enforced' },
        black: { player: 'llm', retry_feedback: 'hinted' },
      },
    })
    expect(started.ok()).toBe(true)
    await page.goto('/')
    await expect(settingChips(page).first()).toHaveAccessibleName('White: Shown and kept legal (Listed enforced)')

    await expectChipsWhole(page)
    await expect(settingChips(page).first().locator('[data-side=white]')).toBeVisible()
  })
}
