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

test('at desktop width the game page has three columns: the Game card, the board, the moves', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openGame(page)

  const { game, board, moves } = await columns(page)
  expect(game.x + game.width).toBeLessThan(board.x)
  expect(board.x + board.width).toBeLessThan(moves.x)
  expect(new Set([game.y, board.y, moves.y]).size).toBe(1)
  expect(moves.width).toBeCloseTo(game.width, 0)
  await expect(page.getByRole('region', { name: 'Game' })).toBeVisible()
})

// The board on a wide window, worked out by hand: the largest square the height allows (the window less 212px), but
// no wider than the larger of half the row and the row less two 300px side columns. The row is the page's width (at
// most 1680px) less its 32px padding and two 32px gaps.
for (const { width, height, size, by } of [
  { width: 1440, height: 900, size: 688, by: 'the height' }, // row 1312: up to max(656, 712)
  { width: 1600, height: 1000, size: 788, by: 'the height' }, // row 1472: up to max(736, 872)
  { width: 1920, height: 800, size: 588, by: 'the height' }, // row 1552: up to max(776, 952)
  { width: 1101, height: 900, size: 486.5, by: 'half the row' }, // row 973: max(486.5, 373); the height allows 688
  { width: 1101, height: 600, size: 388, by: 'the height' }, // row 973: up to 486.5
]) {
  test(`on a wide window, ${width}×${height}, the board is ${size}px, bound by ${by}, the side columns alike`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height })
    await openGame(page)

    const { game, board, moves } = await columns(page)
    expect(Math.abs(board.width - size)).toBeLessThanOrEqual(1)
    expect(moves.width).toBeCloseTo(game.width, 0)
    // A board past half the row leaves each side column 300px at least.
    const row = Math.min(width, 1680) - 64 - 64
    if (size > row / 2) expect(game.width).toBeGreaterThanOrEqual(300)
  })
}

for (const [width, height] of [
  [1440, 900],
  [1101, 600],
]) {
  test(`on a wide window, ${width}×${height}, the game page fits it: no page scroll, the Turn panel scrolls inside itself`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height })
    await openGame(page)

    const page_ = await page.evaluate(() => ({
      scrolls: document.scrollingElement!.scrollHeight - window.innerHeight,
      turnPanel: getComputedStyle(document.querySelector('[data-testid=game-column] > :last-child')!).overflowY,
    }))
    expect(page_.scrolls).toBeLessThanOrEqual(0)
    expect(page_.turnPanel).toBe('auto')
    const { game, board, moves } = await columns(page)
    for (const column of [game, board, moves]) expect(column.y + column.height).toBeLessThanOrEqual(height)
    // The board is the largest square that fits: its stack, with a player strip above and below, fills the
    // column's height, down to where the moves column ends.
    expect(Math.abs(board.y + board.height - (moves.y + moves.height))).toBeLessThanOrEqual(1)
  })
}

test('on a short window under 1100px the board and its player strips fit the window, with no room left under them', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1000, height: 600 })
  await openGame(page)

  const strip = (await page.getByTestId('strip-white').boundingBox())!
  const bottom = strip.y + strip.height
  expect(bottom).toBeLessThanOrEqual(600)
  expect(bottom).toBeGreaterThanOrEqual(600 - 9)
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

const gameCard = (page: Page) => page.getByRole('region', { name: 'Game' })

/** Expects the element to lie whole inside the Game card. */
async function expectInCard(page: Page, element: ReturnType<Page['locator']>) {
  const card = (await gameCard(page).boundingBox())!
  const box = (await element.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(card.x)
  expect(box.x + box.width).toBeLessThanOrEqual(card.x + card.width)
}

test("the Game card's one setting shown is the Rules, an icon named beside it, explained in a tooltip on hover and on keyboard focus", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openGame(page)

  const rules = gameCard(page).getByRole('img', { name: 'Standard rules' })
  await expect(rules).toHaveText('Standard rules')
  await expect(rules.locator('svg')).toHaveCount(1)
  await expectInCard(page, rules)
  // The settings the LLMs share are not shown.
  await expect(gameCard(page).getByRole('list', { name: 'Settings' })).toHaveCount(0)
  await expect(gameCard(page)).not.toContainText('Board only (Free)')

  await rules.hover()
  const tooltip = page.locator('[data-slot=tooltip-content]')
  await expect(tooltip).toHaveText('Normal chess. Rated.')
  await expect(tooltip).toBeInViewport({ ratio: 1 })
  await page.mouse.move(0, 0)
  await expect(tooltip).toBeHidden()

  await rules.focus()
  await expect(tooltip).toHaveText('Normal chess. Rated.')
})

for (const width of [1101, 761]) {
  test(`at ${width}px a faceoff's per-side settings show whole, on each player's row`, async ({ page }) => {
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
    const white = gameCard(page).getByRole('list', { name: "White's settings" })
    const black = gameCard(page).getByRole('list', { name: "Black's settings" })
    await expect(white.getByRole('listitem').first()).toHaveText('Shown and kept legal (Listed enforced)')
    await expect(black).toContainText('Hinted feedback')

    for (const item of [...(await white.getByRole('listitem').all()), ...(await black.getByRole('listitem').all())]) {
      await expect(item).toBeVisible()
      await expectInCard(page, item)
    }
  })
}
