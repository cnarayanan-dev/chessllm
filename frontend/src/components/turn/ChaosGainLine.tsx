// The Chaos gain line of the Turn panel, under the Legal counterpart's move: how much a Chaos move gained its mover
// over its Legal counterpart, as the backend worked it out.
import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import type { ChaosGain } from '@/api/types'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { gainText } from '@/game/chaosGain'

const MEANING =
  'How much breaking the rules gained the LLM: the Evaluation after its Chaos move minus the one after its Legal counterpart, in pawns from its side. Capped at ±20.'
const NOT_JUDGED = 'A position it needs has no Evaluation: it is not valid chess.'

/** "Chaos gain" with a rising, falling or flat icon, then the gain over the Legal counterpart or "not judged". */
export function ChaosGainLine({ gain }: { gain: ChaosGain }) {
  const value = gain.vs_counterpart
  const Icon = value === null || value === 0 ? Minus : value > 0 ? TrendingUp : TrendingDown
  return (
    <div role="group" aria-label="Chaos gain" className="mt-2 flex flex-col gap-1">
      <Tooltip>
        <TooltipTrigger
          render={<span tabIndex={0} aria-description={MEANING} />}
          className="flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground"
        >
          <Icon aria-hidden="true" className="size-4" />
          Chaos gain
        </TooltipTrigger>
        <TooltipContent side="bottom">{MEANING}</TooltipContent>
      </Tooltip>
      {value === null ? (
        <Tooltip>
          <TooltipTrigger
            render={<span tabIndex={0} aria-description={NOT_JUDGED} data-testid="chaos-gain" />}
            className="w-fit text-sm text-muted-foreground"
          >
            not judged
          </TooltipTrigger>
          <TooltipContent side="bottom">{NOT_JUDGED}</TooltipContent>
        </Tooltip>
      ) : (
        <span data-testid="chaos-gain" className="w-fit font-medium tabular-nums">
          {gainText(value)}
        </span>
      )}
    </div>
  )
}
