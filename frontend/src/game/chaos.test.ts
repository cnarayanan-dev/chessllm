import { expect, test } from 'vitest'
import type { Attempt } from '@/api/types'
import { illegalMove, illegalTry } from '@/game/chaos'
import { CHAOS_PLIES, aTurn, chaosAttempt } from '@/test/games'

const legal = aTurn('e5').attempts[0]
const failed = (result: Attempt['result'], overrides: Partial<Attempt> = {}): Attempt => ({
  ...legal,
  san: null,
  result,
  ...overrides,
})
const chaosMove = chaosAttempt('Bb4', CHAOS_PLIES[1][3]!)

test('a badly formed, rule-breaking or ambiguous move is an illegal move, a chaos move included', () => {
  expect([failed('invalid'), failed('illegal'), failed('ambiguous'), chaosMove].map(illegalMove)).toEqual([
    true,
    true,
    true,
    true,
  ])
})

test('a legal move, a cut-off answer and no answer at all are never illegal moves (ADR 0007)', () => {
  const cutOff = failed('cut_off', { move: ' {"mo' })
  const timeout = failed('timeout', { move: null, raw_reply: null, error: 'Too long thinking' })
  const error = failed('error', { move: null, raw_reply: null, error: 'did not reply' })

  expect([legal, cutOff, timeout, error].map(illegalMove)).toEqual([false, false, false, false])
  expect([legal, cutOff, timeout, error].map(illegalTry)).toEqual([false, false, false, false])
})

test('an illegal try is an illegal move that was not played: a chaos move was', () => {
  expect(illegalTry(failed('illegal'))).toBe(true)
  expect(illegalTry(chaosMove)).toBe(false)
})
