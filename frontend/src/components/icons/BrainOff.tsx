// Thinking off: Lucide has no BrainOff, so it is drawn here in Lucide's line style, as Lucide draws its *Off icons.
import { Icon, type LucideProps } from 'lucide-react'
import { useId } from 'react'
import { cn } from '@/lib/utils'

/** Lucide's `Brain` (ISC licence), path for path. */
const BRAIN = [
  'M12 18V5',
  'M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4',
  'M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5',
  'M17.997 5.125a4 4 0 0 1 2.526 5.77',
  'M18 18a4 4 0 0 0 2-7.464',
  'M19.967 17.483A4 4 0 1 1 12 18a4 4 0 1 1-7.967-.517',
  'M6 18a4 4 0 0 1-2-7.464',
  'M6.003 5.125a4 4 0 0 0-2.526 5.77',
]
/** The slash of Lucide's *Off icons, e.g. `EyeOff`. */
const SLASH = 'm2 2 20 20'

/**
 * Lucide's `Brain` with the slash of its *Off icons. As in those, the brain's lines stop short of the slash: a mask
 * cuts a gap of a stroke's width on each side of it.
 */
export function BrainOff({ className, ...props }: LucideProps) {
  const mask = useId()
  return (
    <Icon iconNode={[]} className={cn('lucide-brain-off', className)} {...props}>
      <mask id={mask}>
        <rect width="24" height="24" fill="white" stroke="none" />
        <path d={SLASH} stroke="black" strokeWidth="6" />
      </mask>
      <g mask={`url(#${mask})`}>
        {BRAIN.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <path d={SLASH} />
    </Icon>
  )
}
