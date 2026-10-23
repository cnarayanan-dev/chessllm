// What the Turn panel shows of an attempt, a turn's or a Probe's, and the styles its panes share.
import type { Attempt } from '@/api/types'

export type Decision = 'Thinking' | 'Reasoning'

/** The attempt's Thinking or Reasoning, by what its side produces; else why there is none, as a quiet line. */
export function decisionOf(kind: Decision, attempt: Attempt | undefined): { text: string; quiet: boolean } {
  const text = kind === 'Thinking' ? attempt?.thinking : attempt?.reasoning
  if (text) return { text, quiet: false }
  const why = attempt?.error ? `It gave no answer, so there is no ${kind}.` : `Its reply has no ${kind}.`
  return { text: why, quiet: true }
}

export const RESULT_NAMES: Record<NonNullable<Attempt['result']>, string> = {
  legal: 'Legal',
  invalid: 'Invalid',
  illegal: 'Illegal',
  ambiguous: 'Ambiguous',
  timeout: 'Timeout',
  error: 'Error',
  cut_off: 'Cut off',
}

export const quiet = 'text-sm text-muted-foreground'
export const mono = 'font-mono text-xs leading-relaxed whitespace-pre-wrap break-words'
export const prose = 'leading-relaxed whitespace-pre-wrap text-card-foreground'
