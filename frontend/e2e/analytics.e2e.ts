// The analytics page against the app with synthetic game logs (tests/e2e_server.py, POST /e2e/leaderboard-games):
// qwen3.5:9b Listed enforced rated from Anchor matches, llama3:8b Free losing every anchored game, and
// mistral:7b in Play LLM games only.
import { expect, test, type Page } from '@playwright/test'

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
  await expect(page.getByRole('columnheader')).toHaveText(['#', 'Player configuration', 'Rating↓', 'Games', 'W · D · L'])
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
  await expect(page.getByTestId('status')).toHaveText('Your move (White)')
})
