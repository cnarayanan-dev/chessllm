import { describe, expect, test } from 'vitest'
import { ALL_MODES, boundText, estimateText, intervalText, noRatingText, toggleMode } from '@/analytics/ranking'
import { lowerBound, rated, upperBound } from '@/test/ranking'

describe('a Rating or Move-quality estimate as text', () => {
  test('an estimate is its number', () => {
    expect(estimateText({ estimate: 412, low: 270, high: 550 })).toBe('412')
  })

  test('an upper bound reads "< X"', () => {
    expect(estimateText({ estimate: null, low: null, high: 70 })).toBe('< 70')
  })

  test('a lower bound reads "> X"', () => {
    expect(estimateText({ estimate: null, low: 1100, high: null })).toBe('> 1100')
  })

  test('none is a dash', () => {
    expect(estimateText(null)).toBe('—')
  })

  test("the Rating's 95% interval, only for an estimate", () => {
    expect(intervalText(rated(400, 250, 550))).toBe('250 to 550')
    expect(intervalText(upperBound(70))).toBe('—')
    expect(intervalText(null)).toBe('—')
  })
})

describe('what the Rating cell explains on hover', () => {
  test('a bound says which, an estimate nothing', () => {
    expect(boundText(upperBound(70))).toMatch(/^An upper bound/)
    expect(boundText(lowerBound(1100))).toMatch(/^A lower bound/)
    expect(boundText(rated(400))).toBeNull()
    expect(boundText(null)).toBeNull()
  })

  test('no Rating says why', () => {
    expect(noRatingText('no_reference_games', false)).toMatch(/No games under the Reference configuration yet/)
    expect(noRatingText('no_reference_games', true)).toMatch(/in the Modes chosen/)
    expect(noRatingText('play_llm_only', false)).toMatch(/Play LLM games, which never give a Rating/)
    expect(noRatingText('no_anchor_path', true)).toMatch(/No path to an Anchor/)
    expect(noRatingText('no_rated_opponent', false)).toMatch(/against itself or an Anchor of unknown strength/)
  })
})

describe('the Mode filter', () => {
  test('starts with every Mode', () => {
    expect(ALL_MODES).toEqual(['anchor_match', 'llm_faceoff', 'play_llm'])
  })

  test('a click takes a Mode out, or puts it back in its place', () => {
    expect(toggleMode(ALL_MODES, 'llm_faceoff')).toEqual(['anchor_match', 'play_llm'])
    expect(toggleMode(['play_llm'], 'anchor_match')).toEqual(['anchor_match', 'play_llm'])
  })

  test('the last Mode chosen stays', () => {
    expect(toggleMode(['llm_faceoff'], 'llm_faceoff')).toEqual(['llm_faceoff'])
  })
})
