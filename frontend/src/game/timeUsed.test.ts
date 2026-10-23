import { expect, test } from 'vitest'
import { formatTimeUsed } from '@/game/timeUsed'

test.each([
  [0, '0m 00s'],
  [59, '0m 59s'],
  [59.999, '0m 59s'],
  [3599, '59m 59s'],
  [3600, '1h 00m 00s'],
  [4385, '1h 13m 05s'],
])('Time used of %s s reads %s, in whole seconds', (seconds, shown) => {
  expect(formatTimeUsed(seconds)).toBe(shown)
})
