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

  await yourMove(page)
  await expect.poll(async () => (await (await page.request.get('/api/games/current')).json()).game_id).not.toBe(before)
  await expect(page).toHaveURL(/\/$/)
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

/**
 * The Game card's settings items, line by line: each item's box, whether it is cut off by the line's clip, and
 * whether its "|" (in its left padding) shows; the clip hides it at the start of a line.
 */
async function settingsLines(page: Page) {
  const items = await page.getByTestId('setting').evaluateAll((elements) =>
    elements.map((element) => {
      const box = element.getBoundingClientRect()
      const clip = element.parentElement!.parentElement!.getBoundingClientRect()
      const bar = parseFloat(getComputedStyle(element, '::before').left)
      return {
        top: box.top,
        height: box.height,
        clipped: box.right > clip.right + 0.5 || element.scrollWidth > element.clientWidth,
        barShown: box.left + bar >= clip.left,
      }
    }),
  )
  const lines: (typeof items)[] = []
  items.forEach((item, i) => (i === 0 || item.top !== items[i - 1].top ? lines.push([item]) : lines.at(-1)!.push(item)))
  return lines
}

/** Expects every item shown whole, on one line unless it is alone on its line, and no "|" starting a line. */
function expectWrappedBetweenItems(lines: Awaited<ReturnType<typeof settingsLines>>) {
  const lineHeight = Math.min(...lines.flat().map((item) => item.height))
  for (const line of lines) {
    line.forEach((item, i) => {
      expect(item.clipped).toBe(false)
      expect(item.barShown).toBe(i > 0)
      if (line.length > 1) expect(item.height).toBe(lineHeight)
    })
  }
}

test('the settings line wraps only between items, and no "|" starts a line', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await openGame(page)

  const lines = await settingsLines(page)
  expect(lines.length).toBeGreaterThan(1) // it wraps at this width
  expectWrappedBetweenItems(lines)
})

for (const width of [1101, 761]) {
  test(`at ${width}px a faceoff's per-side settings are shown whole`, async ({ page }) => {
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
    await expect(page.getByTestId('setting').first()).toHaveText('White Listed enforced')

    expectWrappedBetweenItems(await settingsLines(page))
  })
}
