import { describe, expect, test } from 'vitest'
import {
  attemptsLegalText,
  chips,
  columns,
  estimateText,
  intervalText,
  nextSort,
  ranked,
  scoreText,
  sortRows,
  streakText,
  type LeaderboardEntry,
} from '@/analytics/leaderboard'
import { anEntry, lowerBound, moveQuality, rated, upperBound } from '@/test/leaderboard'

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
})

describe('the other numbers as text', () => {
  test("the Rating's 95% interval, only for an estimate", () => {
    expect(intervalText(rated(400, 250, 550))).toBe('250 to 550')
    expect(intervalText(upperBound(70))).toBe('—')
    expect(intervalText(null)).toBe('—')
  })

  test('the score as a percentage', () => {
    expect(scoreText(anEntry('a', { score: 0.625 }))).toBe('63%')
  })

  test('attempts legal and the average streak, or n/a under Enforced decoding', () => {
    const free = anEntry('free', { legal_moves: 300, attempts: 320, average_legal_move_streak: 12.25 })
    const enforced = anEntry('enforced', { attempts: null, average_legal_move_streak: null })

    expect(attemptsLegalText(free)).toBe('94%')
    expect(streakText(free)).toBe('12.3')
    expect(attemptsLegalText(enforced)).toBe('n/a')
    expect(streakText(enforced)).toBe('n/a')
  })

  test('attempts legal is a dash, not n/a, without an attempt', () => {
    expect(attemptsLegalText(anEntry('a', { legal_moves: 0, attempts: 0 }))).toBe('—')
  })
})

describe('the chips', () => {
  test('the LLM constraints coloured, thinking on green, retry feedback grey', () => {
    expect(chips(anEntry('a', { configuration: { llm_constraints: 'blind_enforced', thinking: true } }).configuration)).toEqual([
      { label: 'Blind enforced', hue: 'blind_enforced' },
      { label: 'thinking on', hue: 'thinking' },
      { label: 'feedback explained', hue: null },
    ])
  })

  test('no chip for thinking off', () => {
    expect(chips(anEntry('a').configuration).map((chip) => chip.label)).toEqual(['Free', 'feedback explained'])
  })

  test('grey chips for Chaos rules, sampling and a prompt other than the default', () => {
    const configuration = anEntry('a', {
      configuration: { rules: 'chaos', sampling: { temperature: 0.2, top_k: 40 }, prompt: 'terse.txt' },
    }).configuration

    expect(chips(configuration)).toEqual([
      { label: 'Free', hue: 'free' },
      { label: 'feedback explained', hue: null },
      { label: 'Chaos rules', hue: null },
      { label: 'temperature 0.2 · top_k 40', hue: null },
      { label: 'prompt terse.txt', hue: null },
    ])
  })
})

describe('the ranking', () => {
  test('ranks by Rating: estimates and lower bounds by their number, then upper bounds, then no Rating', () => {
    const entries = [
      anEntry('none', { rating: null }),
      anEntry('low', { rating: rated(120) }),
      anEntry('bound', { rating: upperBound(300) }),
      anEntry('top', { rating: lowerBound(1100) }),
      anEntry('mid', { rating: rated(410) }),
    ]

    expect(ranked(entries).map((entry) => entry.id)).toEqual(['top', 'mid', 'low', 'bound', 'none'])
  })
})

describe('the columns', () => {
  test('by default: rank, Player configuration, Rating, Games and W · D · L', () => {
    expect(columns(false).map((column) => column.label)).toEqual([
      '#',
      'Player configuration',
      'Rating',
      'Games',
      'W · D · L',
    ])
  })

  test('all columns add the interval, Move-quality estimate, score, forfeits and the legal-move metrics', () => {
    expect(columns(true).map((column) => column.label)).toEqual([
      '#',
      'Player configuration',
      'Rating',
      'Games',
      'W · D · L',
      'Rating 95%',
      'Move-quality estimate',
      'Score',
      'Forfeits',
      'Legal moves played',
      'Attempts legal',
      'Avg. Legal-move streak',
    ])
  })

  test('every column sorts but the Player configuration', () => {
    expect(columns(true).filter((column) => !column.sortable).map((column) => column.label)).toEqual([
      'Player configuration',
    ])
  })
})

describe('sorting', () => {
  const ids = (entries: LeaderboardEntry[]) => entries.map((entry) => entry.id)

  test('by a column, either way', () => {
    const entries = [anEntry('a', { games: 4 }), anEntry('b', { games: 12 }), anEntry('c', { games: 8 })]

    expect(ids(sortRows(entries, { key: 'games', direction: 'desc' }))).toEqual(['b', 'c', 'a'])
    expect(ids(sortRows(entries, { key: 'games', direction: 'asc' }))).toEqual(['a', 'c', 'b'])
  })

  test('by rank is by Rating', () => {
    const entries = [anEntry('a', { rating: rated(100) }), anEntry('b', { rating: rated(500) })]

    expect(ids(sortRows(entries, { key: 'rank', direction: 'asc' }))).toEqual(['b', 'a'])
    expect(ids(sortRows(entries, { key: 'rank', direction: 'desc' }))).toEqual(['a', 'b'])
  })

  test('not applicable values stay last whichever way', () => {
    const entries = [
      anEntry('enforced', { attempts: null, configuration: { llm_constraints: 'listed_enforced' } }),
      anEntry('half', { legal_moves: 50, attempts: 100 }),
      anEntry('most', { legal_moves: 90, attempts: 100 }),
    ]

    expect(ids(sortRows(entries, { key: 'attempts_legal', direction: 'desc' }))).toEqual(['most', 'half', 'enforced'])
    expect(ids(sortRows(entries, { key: 'attempts_legal', direction: 'asc' }))).toEqual(['half', 'most', 'enforced'])
  })

  test('the Move-quality estimate sorts like the Rating', () => {
    const entries = [
      anEntry('none', { move_quality: null }),
      anEntry('bound', { move_quality: moveQuality(null, { high: 700 }) }),
      anEntry('high', { move_quality: moveQuality(650) }),
    ]

    expect(ids(sortRows(entries, { key: 'move_quality', direction: 'desc' }))).toEqual(['high', 'bound', 'none'])
  })

  test('a new column sorts highest first, rank first; the same column again turns the order round', () => {
    expect(nextSort({ key: 'rating', direction: 'desc' }, 'games')).toEqual({ key: 'games', direction: 'desc' })
    expect(nextSort({ key: 'rating', direction: 'desc' }, 'rank')).toEqual({ key: 'rank', direction: 'asc' })
    expect(nextSort({ key: 'games', direction: 'desc' }, 'games')).toEqual({ key: 'games', direction: 'asc' })
    expect(nextSort({ key: 'games', direction: 'asc' }, 'games')).toEqual({ key: 'games', direction: 'desc' })
  })
})
