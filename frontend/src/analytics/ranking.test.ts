import { describe, expect, test } from 'vitest'
import {
  ALL_MODES,
  boundReason,
  estimateText,
  intervalText,
  noRatingReason,
  rankingPath,
  toggleMode,
} from '@/analytics/ranking'
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

describe('why a Rating is missing or only a bound', () => {
  test('no games under the Reference configuration, only Play LLM games, or no path to an Anchor', () => {
    expect(noRatingReason('no_reference_games', ALL_MODES)).toBe('No games under the Reference configuration yet.')
    expect(noRatingReason('no_reference_games', ['anchor_match'])).toBe(
      'No games under the Reference configuration in these Modes.',
    )
    expect(noRatingReason('no_rated_games', ALL_MODES)).toMatch(/^Only Play LLM games, which never give a Rating/)
    expect(noRatingReason('no_path_to_anchor', ALL_MODES)).toMatch(/^No path to an Anchor/)
    expect(noRatingReason('no_path_to_anchor', ['llm_faceoff'])).toMatch(/LLM faceoffs alone reach no Anchor/)
  })

  test('an upper bound lost every game leading to an Anchor, a lower bound won every one', () => {
    expect(boundReason(upperBound(70))).toMatch(/^An upper bound/)
    expect(boundReason(lowerBound(1100))).toMatch(/^A lower bound/)
    expect(boundReason(rated(400))).toBeNull()
    expect(boundReason(null)).toBeNull()
  })
})

describe('the Mode filter', () => {
  test('all Modes ask for the whole Ranking; fewer name theirs', () => {
    expect(rankingPath(ALL_MODES)).toBe('/api/ranking')
    expect(rankingPath(['anchor_match'])).toBe('/api/ranking?modes=anchor_match')
    expect(rankingPath(['llm_faceoff', 'anchor_match'])).toBe('/api/ranking?modes=llm_faceoff&modes=anchor_match')
  })

  test("a Mode toggles in and out, kept in the Modes' order, and the last one stays", () => {
    expect(toggleMode(ALL_MODES, 'play_llm')).toEqual(['llm_faceoff', 'anchor_match'])
    expect(toggleMode(['anchor_match'], 'play_llm')).toEqual(['play_llm', 'anchor_match'])
    expect(toggleMode(['anchor_match'], 'anchor_match')).toEqual(['anchor_match'])
  })
})
