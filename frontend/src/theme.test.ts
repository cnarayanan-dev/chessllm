/// <reference types="node" />
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, test } from 'vitest'
import { contrast, variables } from '@/test/contrast'

// Read from the file: Vitest hands CSS imports to the tests empty, `?raw` too.
const theme = variables(readFileSync(path.join(import.meta.dirname, 'index.css'), 'utf8'), ':root')
const colour = (name: string) => {
  const value = theme.get(`--${name}`)
  if (!value) throw new Error(`--${name} is not set`)
  return value
}

test('the contrast is measured as WCAG does', () => {
  // Stock shadcn neutral's muted foreground is #737373: 4.74:1 on white (WebAIM's contrast checker).
  expect(contrast('oklch(0.556 0 0)', 'oklch(1 0 0)')).toBeCloseTo(4.74, 1)
  expect(contrast('oklch(0 0 0)', 'oklch(1 0 0)')).toBeCloseTo(21, 1)
})

describe('the Stone palette passes WCAG AA (4.5:1) for text', () => {
  test.each(['background', 'card', 'popover', 'muted', 'secondary', 'accent'])(
    'secondary text on the %s',
    (surface) => {
      expect(contrast(colour('muted-foreground'), colour(surface))).toBeGreaterThanOrEqual(4.5)
    },
  )

  test.each([
    ['foreground', 'background'],
    ['card-foreground', 'card'],
    ['popover-foreground', 'popover'],
    ['primary-foreground', 'primary'],
    ['secondary-foreground', 'secondary'],
    ['accent-foreground', 'accent'],
    ['destructive', 'card'],
    ['timer-foreground', 'timer'],
    ['slip', 'card'],
    ['spawn', 'card'],
  ])('%s on the %s', (text, surface) => {
    expect(contrast(colour(text), colour(surface))).toBeGreaterThanOrEqual(4.5)
  })

  test('the page is a warm off-white, so the white cards stand out from it', () => {
    expect(contrast(colour('card'), colour('background'))).toBeGreaterThan(1.05)
  })
})
