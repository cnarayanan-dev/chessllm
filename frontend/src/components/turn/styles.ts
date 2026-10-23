// What the Turn panel's parts share: the text styles of an attempt, and the names of its results.
import type { Attempt } from '@/api/types'

export const quiet = 'text-sm text-muted-foreground'
export const mono = 'font-mono text-xs leading-relaxed whitespace-pre-wrap break-words'

export const RESULT_NAMES: Record<NonNullable<Attempt['result']>, string> = {
  legal: 'Legal',
  invalid: 'Invalid',
  illegal: 'Illegal',
  ambiguous: 'Ambiguous',
  timeout: 'Timeout',
  error: 'Error',
  cut_off: 'Cut off',
}
