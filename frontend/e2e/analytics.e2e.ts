// The analytics page against the app with synthetic game logs (tests/e2e/server.py, POST /e2e/ranking-games, the
// games in tests/e2e/ranking.py): a rated model, one losing every anchored game, one with faceoffs only, one with
// Play LLM games only, and one that never played under the Reference configuration.
import { expect, test, type Page } from '@playwright/test'

/** Waits for the human's move as White, live: their strip ringed, only their Time used ticking, no past position. */
async function yourMove(page: Page) {
  await expect(page.getByTestId('strip-white')).toHaveAttribute('data-to-move')
  await expect(page.getByTestId('strip-white')).toContainText('You')
  await expect(page.locator('[role=timer][data-ticking]')).toHaveCount(1)
  await expect(page.getByTestId('strip-white').getByRole('timer')).toHaveAttribute('data-ticking')
  await expect(page.locator('[data-testid="moves"] [aria-current=step]')).toHaveCount(0)
}

/** The table's rows below the header, each as its cells' text. */
async function rows(page: Page): Promise<string[][]> {
  const body = page.locator('tbody tr')
  const texts: string[][] = []
  for (const row of await body.all()) texts.push(await row.locator('td').allInnerTexts())
  return texts
}
const row = (page: Page, model: string) => page.locator('tbody tr', { hasText: model })
const tooltip = (page: Page) => page.locator('[data-slot=tooltip-content][data-open]')

test.beforeEach(async ({ page }) => {
  expect((await page.request.post('/e2e/ranking-games')).ok()).toBe(true)
})

test('the Ranking: models by their Rating under the Reference configuration, narrowed by Mode', async ({ page }) => {
  await page.goto('/analytics')

  await expect(page.getByRole('columnheader')).toHaveText([
    '#',
    'Model',
    'Rating',
    '95% interval',
    'Move-quality estimate',
    'Games',
    'W · D · L',
    'Forfeits',
  ])
  await expect(page.getByRole('switch', { name: 'All columns' })).toHaveCount(0)
  await expect(page.locator('tbody tr')).toHaveCount(5)
  // Ranked by Rating: an estimate, an upper bound; then the unranked, those with games first. gemma4:26b played only
  // with thinking on under Listed enforced, so none of its wins count.
  const ranked = await rows(page)
  expect(ranked.map((cells) => cells.slice(0, 2))).toEqual([
    ['1', 'qwen3.5:9b'],
    ['2', 'llama3:8b'],
    ['', 'gemma3:12b'],
    ['', 'mistral:7b'],
    ['', 'gemma4:26b'],
  ])
  const [qwen, llama] = ranked
  expect(qwen![2]).toMatch(/^\d+$/)
  expect(qwen![3]).toMatch(/^\d+ to \d+$/)
  expect(qwen![4]).toMatch(/^\d+\s*unvalidated$/)
  expect(llama![2]).toMatch(/^< \d+$/)
  expect(ranked.map((cells) => cells.slice(5))).toEqual([
    ['20', '10 · 1 · 9', '0'],
    ['12', '0 · 0 · 12', '4'],
    ['2', '2 · 0 · 0', '0'],
    ['5', '2 · 0 · 3', '0'],
    ['0', '0 · 0 · 0', '0'],
  ])
  expect(ranked.slice(2).map((cells) => cells[2])).toEqual(['—', '—', '—'])

  // Each bounded or missing Rating, and the unvalidated estimate, say why on hover.
  await row(page, 'llama3:8b').getByText(/^< \d+$/).hover()
  await expect(tooltip(page)).toHaveText(/^An upper bound/)
  await row(page, 'gemma3:12b').getByText('—').first().hover()
  await expect(tooltip(page)).toHaveText(/^No path to an Anchor/)
  await row(page, 'mistral:7b').getByText('—').first().hover()
  await expect(tooltip(page)).toHaveText(/^Only Play LLM games/)
  await row(page, 'gemma4:26b').getByText('—').first().hover()
  await expect(tooltip(page)).toHaveText('No games under the Reference configuration yet.')
  await row(page, 'qwen3.5:9b').getByText('unvalidated').hover()
  await expect(tooltip(page)).toHaveText(/has not passed its validation/)

  // LLM faceoffs alone: no Ratings, and only the faceoffs in the record.
  const modes = page.getByRole('group', { name: 'Modes' })
  await modes.getByRole('button', { name: 'Play LLM' }).click()
  await modes.getByRole('button', { name: 'Anchor matches' }).click()
  await expect(modes.getByRole('button', { name: 'LLM faceoffs' })).toHaveAttribute('aria-disabled', 'true')
  await expect.poll(async () => (await rows(page)).map((cells) => [cells[0], cells[1], cells[2], cells[5]])).toEqual([
    ['', 'gemma3:12b', '—', '2'],
    ['', 'llama3:8b', '—', '2'],
    ['', 'gemma4:26b', '—', '0'],
    ['', 'mistral:7b', '—', '0'],
    ['', 'qwen3.5:9b', '—', '0'],
  ])
  await row(page, 'llama3:8b').getByText('—').first().hover()
  await expect(tooltip(page)).toHaveText(/LLM faceoffs alone reach no Anchor/)

  // Anchor matches alone: the Ratings are back, llama3:8b's record without its faceoffs.
  await modes.getByRole('button', { name: 'Anchor matches' }).click()
  await modes.getByRole('button', { name: 'LLM faceoffs' }).click()
  await expect.poll(async () => (await rows(page)).map((cells) => [cells[0], cells[1], cells[5]])).toEqual([
    ['1', 'qwen3.5:9b', '20'],
    ['2', 'llama3:8b', '10'],
    ['', 'gemma3:12b', '0'],
    ['', 'gemma4:26b', '0'],
    ['', 'mistral:7b', '0'],
  ])
  expect((await rows(page))[1]![2]).toMatch(/^< \d+$/)

  // Play LLM alone: never a Rating, only the record and the Move-quality estimate.
  await modes.getByRole('button', { name: 'Play LLM' }).click()
  await modes.getByRole('button', { name: 'Anchor matches' }).click()
  await expect.poll(async () => (await rows(page)).map((cells) => [cells[0], cells[1], cells[2], cells[5]])).toEqual([
    ['', 'mistral:7b', '—', '5'],
    ['', 'gemma3:12b', '—', '0'],
    ['', 'gemma4:26b', '—', '0'],
    ['', 'llama3:8b', '—', '0'],
    ['', 'qwen3.5:9b', '—', '0'],
  ])
  const mistral = (await rows(page))[0]!
  expect(mistral[4]).toMatch(/^\d+\s*unvalidated$/)
  expect(mistral.slice(6)).toEqual(['2 · 0 · 3', '0'])
  await row(page, 'mistral:7b').getByText('—').first().hover()
  await expect(tooltip(page)).toHaveText(/^Only Play LLM games, which never give a Rating/)
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
  // One Mode off, so a Mode filter button that is off is among them.
  await page.getByRole('group', { name: 'Modes' }).getByRole('button', { name: 'Play LLM' }).click()
  await expect(page.getByText('unvalidated')).toBeVisible()

  const texts = await contrasts(page)
  // The heading, the Mode filter, the headers, the models and the unvalidated mark are among them.
  for (const text of ['Ranking', 'Play LLM', 'Anchor matches', '95% interval', 'unvalidated', 'llama3:8b']) {
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
  await expect(page.getByRole('heading', { name: 'Ranking' })).toBeVisible()

  await page.getByRole('link', { name: 'ChessLLM' }).click()
  await yourMove(page)
})
