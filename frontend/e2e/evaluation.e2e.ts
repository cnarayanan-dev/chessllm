// The Evaluation bar in an LLM faceoff, against the real API: the e2e server judges each ply by material alone
// (tests/e2e/server.py), a stand-in for Stockfish.
import { expect, test } from '@playwright/test'

test('an LLM faceoff shows the Evaluation bar left of the board, following the viewed ply, with the result at the end', async ({
  page,
}) => {
  // 1. e4 d5 2. exd5 Qxd5, then White has no reply left and forfeits.
  await page.request.post('/e2e/script', { data: { white: ['e4', 'exd5'], black: ['d5', 'Qxd5'] } })
  await page.request.post('/api/games', {
    data: { mode: 'llm_faceoff', white: { player: 'llm' }, black: { player: 'llm' } },
  })
  await page.goto('/')
  const bar = page.getByRole('meter', { name: 'Evaluation' })

  await expect(page.getByTestId('result')).toContainText('by forfeit')
  await expect(bar).toHaveAttribute('aria-valuetext', '0-1')
  await expect(bar).toHaveAttribute('aria-valuenow', '0')
  // Left of the board, at its height.
  const board = (await page.locator('.board-wrap').boundingBox())!
  const shown = (await bar.boundingBox())!
  expect(shown.x + shown.width).toBeLessThanOrEqual(board.x)
  expect(Math.abs(shown.height - board.height)).toBeLessThan(2)

  await page.keyboard.press('ArrowLeft')
  await expect(bar).toHaveAttribute('aria-valuetext', '+1.0')
  await page.keyboard.press('ArrowLeft')
  await expect(bar).toHaveAttribute('aria-valuetext', '0.0')

  // The details and the engine are in its tooltip, on hover and on keyboard focus.
  const tooltip = page.locator('[data-slot=tooltip-content]')
  await bar.hover()
  await expect(tooltip).toContainText('Evaluation 0.0')
  await expect(tooltip).toContainText('material count · depth 0')
  await page.mouse.move(0, 0)
  await expect(tooltip).toBeHidden()
  await bar.focus()
  await expect(tooltip).toContainText('material count · depth 0')
})

test('Play LLM shows no Evaluation bar', async ({ page }) => {
  await page.request.post('/e2e/script', { data: { black: ['e5'] } })
  await page.request.post('/api/games', {
    data: { mode: 'play_llm', white: { player: 'human' }, black: { player: 'llm' } },
  })
  await page.goto('/')

  await expect(page.locator('.board-wrap')).toBeVisible()
  await expect(page.getByRole('meter', { name: 'Evaluation' })).toHaveCount(0)
})
