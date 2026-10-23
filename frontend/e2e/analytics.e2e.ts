// The analytics page against the app with synthetic game logs (tests/e2e/server.py, POST /e2e/ranking-games, from
// tests/e2e/ranking.py): qwen3.5:9b rated from Anchor matches, llama3:8b losing every anchored game and 4 LLM
// faceoffs to gemma3:12b, mistral:7b in Play LLM games only, and phi4:14b under Listed only; all but phi4 under the
// Reference configuration.
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
const models = async (page: Page) => (await rows(page)).map((cells) => cells[1])
const mode = (page: Page, name: string) => page.getByRole('group', { name: 'Modes' }).getByRole('button', { name })

/** Clicks these Modes in the filter, and waits for the Ranking of exactly the Modes they leave chosen to be shown:
 * each click asks for its own, and the last one shown stays (marked busy) until the next arrives. */
async function narrow(page: Page, clicks: string[], chosen: string[]) {
  const query = chosen.map((key) => `mode=${key}`).join('&')
  const final = page.waitForResponse((response) => response.url().endsWith(`/api/ranking?${query}`))
  for (const name of clicks) await mode(page, name).click()
  await final
  await expect(page.getByRole('table')).toHaveAttribute('aria-busy', 'false')
}

/** Hovers the model's Rating cell, and expects its tooltip to say this. */
async function expectRatingTooltip(page: Page, model: string, says: RegExp) {
  await page.mouse.move(0, 0)
  await page.locator('tbody tr', { hasText: model }).locator('td').nth(2).locator('span').first().hover()
  await expect(page.locator('[data-slot=tooltip-content]').filter({ hasText: says })).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  expect((await page.request.post('/e2e/ranking-games')).ok()).toBe(true)
})

test('the Ranking: models by their Rating under the Reference configuration, narrowed by Mode', async ({ page }) => {
  await page.goto('/analytics')

  await expect(page.getByRole('heading', { name: 'Ranking' })).toBeVisible()
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

  // Ranked: an estimate, then an upper bound; then the unranked, those with reference games first.
  const all = await rows(page)
  expect(await models(page)).toEqual(['qwen3.5:9b', 'llama3:8b', 'gemma3:12b', 'mistral:7b', 'phi4:14b'])
  expect(all.map((cells) => cells[0])).toEqual(['1', '2', '', '', ''])
  const [qwen, llama, gemma, mistral, phi] = all
  expect(qwen![2]).toMatch(/^\d+$/)
  expect(qwen![3]).toMatch(/^\d+ to \d+$/)
  expect(qwen![4]).toMatch(/^\d+\s*unvalidated$/)
  expect(qwen!.slice(5)).toEqual(['20', '10 · 1 · 9', '0'])
  expect(llama![2]).toMatch(/^< \d+$/)
  expect(llama!.slice(3)).toEqual(['—', '—', '14', '0 · 0 · 14', '4'])
  expect(gemma!.slice(2)).toEqual(['—', '—', '—', '4', '4 · 0 · 0', '0'])
  expect(mistral!.slice(2)).toEqual(['—', '—', '—', '25', '0 · 0 · 25', '0'])
  expect(phi!.slice(2)).toEqual(['—', '—', '—', '0', '0 · 0 · 0', '0'])

  // Each missing Rating says why on hover; the upper bound and the unvalidated estimate explain themselves too.
  await expectRatingTooltip(page, 'gemma3:12b', /No path to an Anchor/)
  await expectRatingTooltip(page, 'mistral:7b', /Only Play LLM games/)
  await expectRatingTooltip(page, 'phi4:14b', /No games under the Reference configuration yet/)
  await expectRatingTooltip(page, 'llama3:8b', /An upper bound/)
  await page.getByText('unvalidated').hover()
  await expect(page.locator('[data-slot=tooltip-content]', { hasText: 'has not passed its validation' })).toBeVisible()

  // LLM faceoffs alone: no Rating, and each record is its faceoffs' alone.
  await narrow(page, ['Anchor matches', 'Play LLM'], ['llm_faceoff'])
  await expect(mode(page, 'LLM faceoffs')).toHaveAttribute('aria-pressed', 'true')
  expect(await models(page)).toEqual(['gemma3:12b', 'llama3:8b', 'mistral:7b', 'phi4:14b', 'qwen3.5:9b'])
  expect((await rows(page)).map((cells) => [cells[0], cells[2], cells[5], cells[6]])).toEqual([
    ['', '—', '4', '4 · 0 · 0'],
    ['', '—', '4', '0 · 0 · 4'],
    ['', '—', '0', '0 · 0 · 0'],
    ['', '—', '0', '0 · 0 · 0'],
    ['', '—', '0', '0 · 0 · 0'],
  ])
  await expectRatingTooltip(page, 'llama3:8b', /No path to an Anchor/)
  await expectRatingTooltip(page, 'qwen3.5:9b', /in the Modes chosen/)

  // Anchor matches alone: a pure against-Anchors Rating, the same as with every Mode here, where no faceoff
  // reaches qwen3.5:9b.
  await narrow(page, ['Anchor matches', 'LLM faceoffs'], ['anchor_match'])
  expect((await rows(page)).slice(0, 2).map((cells) => [cells[0], cells[1], cells[5], cells[6]])).toEqual([
    ['1', 'qwen3.5:9b', '20', '10 · 1 · 9'],
    ['2', 'llama3:8b', '10', '0 · 0 · 10'],
  ])
  expect((await rows(page))[0]![2]).toBe(qwen![2])

  // Play LLM alone never gives a Rating, only the record.
  await narrow(page, ['Play LLM', 'Anchor matches'], ['play_llm'])
  expect((await rows(page)).find((cells) => cells[1] === 'mistral:7b')?.[5]).toBe('25')
  expect((await rows(page)).map((cells) => cells[2])).toEqual(['—', '—', '—', '—', '—'])
  await expectRatingTooltip(page, 'mistral:7b', /Only Play LLM games/)
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
  await expect(page.getByText('unvalidated')).toBeVisible()
  await narrow(page, ['Play LLM'], ['anchor_match', 'llm_faceoff']) // a Mode not chosen, too
  await expect(mode(page, 'Play LLM')).toHaveAttribute('aria-pressed', 'false')

  const texts = await contrasts(page)
  // The filter's label and its Modes, chosen or not, the headers, the note and the unvalidated mark are among them.
  for (const text of ['Modes', 'Anchor matches', 'Play LLM', '95% interval', 'unvalidated', 'Only games under']) {
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
