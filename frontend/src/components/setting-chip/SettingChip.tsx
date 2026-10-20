// A small round chip: one icon, its name and meaning in a tooltip (DESIGN.md: the hover rule). The Game card's Rules
// and Rematch.
import type { LucideProps } from 'lucide-react'
import type { ComponentType } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

type SettingChipProps = {
  icon: ComponentType<LucideProps>
  /** The short name: the chip's accessible name, and in its tooltip; shown beside the icon on a button. */
  name: string
  /** What it means or does: in the tooltip, and the chip's `aria-description`. */
  description: string
  /** Makes the chip a button, its name beside the icon (e.g. Rematch); the tooltip then gives only the description. */
  onClick?: () => void
  /** Shows the name beside the icon, as the button does, for a setting that matters most (the Game card's Rules). */
  labelled?: boolean
}

const CHIP =
  'relative inline-flex h-7 flex-none items-center justify-center rounded-full bg-muted text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring'

export function SettingChip({ icon: Icon, name, description, onClick, labelled = false }: SettingChipProps) {
  const nameShown = onClick !== undefined || labelled
  const trigger = onClick ? (
    <button
      type="button"
      onClick={onClick}
      aria-description={description}
      className={cn(CHIP, 'cursor-pointer gap-1.5 pr-3 pl-2 text-sm font-medium hover:bg-accent')}
    />
  ) : (
    // Focusable, so the tooltip opens from the keyboard too.
    <span
      role="img"
      tabIndex={0}
      aria-label={name}
      aria-description={description}
      className={cn(CHIP, 'cursor-help', labelled ? 'gap-1.5 pr-3 pl-2 text-sm font-medium' : 'w-7')}
    />
  )
  return (
    <Tooltip>
      <TooltipTrigger delay={150} render={trigger}>
        <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
        {nameShown && name}
      </TooltipTrigger>
      <TooltipContent className="block max-w-64">
        {nameShown ? (
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
