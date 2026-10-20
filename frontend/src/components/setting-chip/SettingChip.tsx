// A small round chip: one icon, its name and meaning in a tooltip (DESIGN.md: the hover rule). The Game card's settings.
import type { LucideProps } from 'lucide-react'
import type { ComponentType } from 'react'
import type { Color } from '@/api/types'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

type SettingChipProps = {
  icon: ComponentType<LucideProps>
  /** The short name: the chip's accessible name, and in its tooltip; shown beside the icon on a button. */
  name: string
  /** What it means or does: in the tooltip, and the chip's `aria-description`. */
  description: string
  /** Whose the chip is, when it is for one side only: a small white or black dot on it. */
  side?: Color | null
  /** Makes the chip a button, its name beside the icon (e.g. Rematch); the tooltip then gives only the description. */
  onClick?: () => void
}

const CHIP =
  'relative inline-flex h-7 flex-none items-center justify-center rounded-full bg-muted text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring'

export function SettingChip({ icon: Icon, name, description, side = null, onClick }: SettingChipProps) {
  const trigger = onClick ? (
    <button
      type="button"
      onClick={onClick}
      aria-description={description}
      className={cn(CHIP, 'cursor-pointer gap-1.5 pr-3 pl-2 text-sm font-medium hover:bg-accent')}
    />
  ) : (
    // Focusable, so the tooltip opens from the keyboard too.
    <span role="img" tabIndex={0} aria-label={name} aria-description={description} className={cn(CHIP, 'w-7 cursor-help')} />
  )
  return (
    <Tooltip>
      <TooltipTrigger delay={150} render={trigger}>
        <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
        {onClick && name}
        {side && (
          <span
            data-side={side}
            aria-hidden="true"
            className={cn(
              'absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-[1.5px] border-foreground',
              side === 'white' ? 'bg-card' : 'bg-foreground',
            )}
          />
        )}
      </TooltipTrigger>
      <TooltipContent className="block max-w-64">
        {onClick ? (
          description
        ) : (
          <>
            <span className="font-semibold">{name}</span> {description}
          </>
        )}
      </TooltipContent>
    </Tooltip>
  )
}
