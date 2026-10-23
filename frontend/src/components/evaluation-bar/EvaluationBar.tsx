// The Evaluation bar, left of the board in an LLM faceoff: Black's dark from the top, White's light from the bottom,
// filled by White's win chance, the number at the leading side's end. Its details and the engine are in its tooltip.
// Outlined while it shows a Legal counterpart's position, never played.
import type { ReactNode } from 'react'
import type { Bar } from '@/game/evaluation'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import './evaluation-bar.css'

/** The board, with the bar left of it at its height when there is one. */
export function BesideBoard({ bar, children }: { bar: Bar | null; children: ReactNode }) {
  return (
    <div className="board-beside">
      {bar && <EvaluationBar bar={bar} />}
      <div className="board-beside-main">{children}</div>
    </div>
  )
}

function EvaluationBar({ bar }: { bar: Bar }) {
  return (
    <Tooltip>
      <TooltipTrigger
        delay={150}
        render={
          <div
            className="evaluation-bar"
            data-state={bar.state}
            data-preview={bar.preview || undefined}
            tabIndex={0}
            role="meter"
            aria-label="Evaluation"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(bar.share)}
            aria-valuetext={bar.text}
            aria-description={`${bar.title}. ${bar.detail}`}
          />
        }
      >
        <div className="evaluation-bar-white" style={{ height: `${bar.share}%` }} />
        <span className="evaluation-bar-even" aria-hidden="true" />
        <span className={`evaluation-bar-label ${bar.leader}`} aria-hidden="true">
          {bar.label}
        </span>
      </TooltipTrigger>
      <TooltipContent side="left" className="max-w-60 flex-col items-start gap-0.5">
        <span className="font-semibold">{bar.title}</span>
        <span className="opacity-75">{bar.detail}</span>
      </TooltipContent>
    </Tooltip>
  )
}
