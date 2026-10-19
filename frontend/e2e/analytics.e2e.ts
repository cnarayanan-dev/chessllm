// The analytics page against the app with synthetic game logs (tests/e2e_server.py, POST /e2e/leaderboard-games):
// qwen3.5:9b Listed enforced rated from Anchor matches, llama3:8b Free losing every anchored game, and
// mistral:7b in Play LLM games only.
import { expect, test, type Page } from '@playwright/test'

/** Waits for the human's move as White, live: the turn ring on their strip, no move timer, no past position viewed. */
async function yourMove(page: Page) {
  await expect(page.getByTestId('strip-white')).toHaveAttribute('data-to-move')
  await expect(page.getByTestId('strip-white')).toContainText('You')
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(page.getByTestId('status')).toHaveCount(0)
}

/** The table's rows below the header, each as its cells' text. */
async function rows(page: Page): Promise<string[][]> {
  const body = page.locator('tbody tr')
  const texts: string[][] = []
  for (const row of await body.all()) texts.push(await row.locator('td').allInnerTexts())
  return texts
}
const models = async (page: Page) => (await rows(page)).map((cells) => cells[1]!.split(/\s/)[0])

test.beforeEach(async ({ page }) => {
  expect((await page.request.post('/e2e/leaderboard-games')).ok()).toBe(true)
})

test('the leaderboard: ranked by Rating, sorted by a column, with all columns on demand', async ({ page }) => {
  await page.goto('/analytics')

  // The default columns, ranked by Rating: an estimate, an upper bound, then no Rating.
  await expect(page.getByRole('columnheader')).toHaveText(['#', 'Player configuration', 'Rating', 'Games', 'W · D · L'])
  await expect(page.getByRole('columnheader', { name: 'Rating' })).toHaveAttribute('aria-sort', 'descending')
  await expect(page.locator('tbody tr')).toHaveCount(3)
  const ranked = await rows(page)
  expect(ranked.map((cells) => cells[0])).toEqual(['1', '2', '3'])
  expect(await models(page)).toEqual(['qwen3.5:9b', 'llama3:8b', 'mistral:7b'])
  expect(ranked[0]![2]).toMatch(/^\d+$/)
  expect(ranked[1]![2]).toMatch(/^< \d+$/)
  expect(ranked[2]![2]).toBe('—')
  expect(ranked.map((cells) => [cells[3], cells[4]])).toEqual([
    ['20', '10 · 1 · 9'],
    ['10', '0 · 0 · 10'],
    ['25', '0 · 0 · 25'],
  ])
  await expect(page.locator('tbody tr').first().getByText('Listed enforced')).toHaveAttribute(
    'data-hue',
    'listed_enforced',
  )
  await expect(page.locator('tbody tr').first().getByText('thinking on')).toBeVisible()

  // Sorting by Games, then the other way round.
  await page.getByRole('button', { name: 'Games' }).click()
  await expect.poll(() => models(page)).toEqual(['mistral:7b', 'qwen3.5:9b', 'llama3:8b'])
  await page.getByRole('button', { name: 'Games' }).click()
  await expect.poll(() => models(page)).toEqual(['llama3:8b', 'qwen3.5:9b', 'mistral:7b'])

  // All columns.
  await page.getByRole('switch', { name: 'All columns' }).click()
  await expect(page.getByRole('columnheader')).toHaveCount(12)
  await page.getByRole('button', { name: 'Rating', exact: true }).click()
  await expect.poll(() => models(page)).toEqual(['qwen3.5:9b', 'llama3:8b', 'mistral:7b'])
  const all = await rows(page)
  const qwen = all[0]!
  expect(qwen[5]).toMatch(/^\d+ to \d+$/) // the Rating's 95% interval
  expect(qwen[6]).toMatch(/^\d+\s*unvalidated$/) // the Move-quality estimate, not validated
  expect(qwen.slice(9)).toEqual(['600', 'n/a', 'n/a']) // attempts legal and streak n/a under Enforced decoding
  const llama = all[1]!
  expect(llama[5]).toBe('—')
  expect(llama[8]).toBe('4') // forfeits
  expect(llama.slice(9)).toEqual(['30', '75%', '3.0'])

  await page.getByRole('switch', { name: 'All columns' }).click()
  await expect(page.getByRole('columnheader')).toHaveCount(5)
})

/** Every text on the page with the contrast of its colour against the surface under it, all layers composited. */
async function contrasts(page: Page) {
  return page.evaluate(() => {
    const context = document.createElement('canvas').getContext('2d', { willReadFrequently: true })!
    /** Any CSS colour (oklch, color-mix, ...) as sRGB 0-1 and its alpha, as the browser paints it. */
    const rgba = (colour: string) => {
      context.clearRect(0, 0, 1, 1)
      context.fillStyle = colour
      context.fillRect(0, 0, 1, 1)
      const [red, green, blue, alpha] = context.getImageData(0, 0, 1, 1).data
      return { rgb: [red! / 255, green! / 255, blue! / 255], alpha: alpha! / 255 }
    }
    const over = (top: { rgb: number[]; alpha: number }, under: number[]) =>
      top.rgb.map((value, index) => value * top.alpha + under[index]! * (1 - top.alpha))
    /** The surface under an element: every background from the page down to it, composited. */
    const surface = (element: Element) => {
      const layers: Element[] = []
      for (let at: Element | null = element; at; at = at.parentElement) layers.unshift(at)
      return layers.reduce((under, layer) => over(rgba(getComputedStyle(layer).backgroundColor), under), [1, 1, 1])
    }
    const luminance = (rgb: number[]) => {
      const linear = (value: number) => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
      const [red, green, blue] = rgb.map(linear)
      return 0.2126 * red! + 0.7152 * green! + 0.0722 * blue!
    }
    const hasText = (element: Element) =>
      [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent!.trim())
    return [...document.querySelectorAll('body *')].filter(hasText).map((element) => {
      const under = surface(element)
      const text = over(rgba(getComputedStyle(element).color), under)
      const [light, dark] = [luminance(text), luminance(under)].sort((x, y) => y - x)
      const ratio = Math.round(((light! + 0.05) / (dark! + 0.05)) * 100) / 100
      return { text: element.textContent!.trim().slice(0, 40), ratio }
    })
  })
}

test('every text on the page, the secondary text too, passes WCAG AA (4.5:1)', async ({ page }) => {
  await page.goto('/analytics')
  await page.getByRole('switch', { name: 'All columns' }).click()
  await expect(page.getByText('unvalidated')).toBeVisible()

  const texts = await contrasts(page)
  // The legend, the muted chips, the switch's label, the headers, the note and the unvalidated mark are among them.
  for (const text of ['Blind enforced', 'feedback bare', 'All columns', 'Rating 95%', 'unvalidated', 'The Rating']) {
    expect(texts.map((each) => each.text)).toContainEqual(expect.stringContaining(text))
  }
  expect(texts.filter((each) => each.ratio < 4.5)).toEqual([])
})

test('the game and the analytics page link to each other', async ({ page }) => {
  await page.request.post('/e2e/script', { data: {} })
  await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } },
  })
  await page.goto('/')

  await page.getByRole('link', { name: 'Analytics' }).click()
  await expect(page).toHaveURL(/\/analytics$/)
  await expect(page.getByRole('heading', { name: 'Leaderboard' })).toBeVisible()

  await page.getByRole('link', { name: 'ChessLLM' }).click()
  await yourMove(page)
})
