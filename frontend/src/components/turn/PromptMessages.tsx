// The Prompt of an attempt, a turn's or a Probe's, as it was sent to the LLM.
import { ChevronRight, Scissors } from 'lucide-react'
import type { ReactNode } from 'react'
import type { PromptMessage } from '@/api/types'
import { mono, quiet } from '@/components/turn/attempt'
import { freshPrompt, type ConversationPrompt, type LabelledMessage } from '@/components/turn/conversation'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const TRIMMED = "Dropped, oldest first, to fit the model's context: the LLM no longer saw them."

/** The messages sent, each under its label; the System prompt folded, as it is the same every turn. */
export function PromptMessages({ messages }: { messages: PromptMessage[] | null }) {
  if (!messages) return <p className={quiet}>The Prompt was not recorded for this turn.</p>
  return <ConversationMessages prompt={freshPrompt(messages)} />
}

/**
 * A conversation's whole Prompt, rebuilt from the records: the System prompt folded, a marker naming the turns
 * trimmed to fit the context, each earlier turn remembered folded under its number, then the attempt's own turn.
 */
export function ConversationMessages({ prompt }: { prompt: ConversationPrompt }) {
  const { system, trimmed, earlier, current } = prompt
  return (
    <ol className="flex flex-col gap-2">
      {system && (
        <li className="rounded-md border">
          <Folded label="System prompt">
            <p className={`${mono} border-t px-2 py-1.5`}>{system.content}</p>
          </Folded>
        </li>
      )}
      {trimmed && <TrimmedMarker {...trimmed} />}
      {earlier.map((turn) => (
        <li key={turn.number} className="rounded-md border">
          <Folded label={`Turn ${turn.number}`}>
            <ol className="flex flex-col gap-2 border-t p-2">
              {turn.messages.map((message, index) => (
                <Message key={index} {...message} />
              ))}
            </ol>
          </Folded>
        </li>
      ))}
      {current.map((message, index) => (
        <Message key={index} {...message} />
      ))}
    </ol>
  )
}

/** A message open under its label. */
function Message({ message, label }: LabelledMessage) {
  return (
    <li className="rounded-md border">
      <p className="px-2 pt-1 text-xs font-medium text-muted-foreground">{label}</p>
      <p className={`${mono} px-2 pb-1.5`}>{message.content}</p>
    </li>
  )
}

/** A block folded behind its label, as the System prompt is. */
function Folded({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-1.5 px-2 py-1 text-xs font-medium text-muted-foreground">
        <ChevronRight aria-hidden="true" className="size-3 transition-transform group-data-[panel-open]:rotate-90" />
        {label}
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  )
}

/** Where the side's oldest turns were dropped: "Turns 1–5 trimmed", what that means on hover and keyboard focus. */
function TrimmedMarker({ from, to }: { from: number; to: number }) {
  const name = from === to ? `Turn ${from} trimmed` : `Turns ${from}–${to} trimmed`
  return (
    <li>
      <Tooltip>
        <TooltipTrigger
          render={<span role="note" aria-label={name} aria-description={TRIMMED} tabIndex={0} />}
          className="flex w-fit items-center gap-1.5 px-2 text-xs font-medium text-muted-foreground outline-none focus-visible:underline"
        >
          <Scissors aria-hidden="true" className="size-3" />
          {name}
        </TooltipTrigger>
        <TooltipContent side="bottom">{TRIMMED}</TooltipContent>
      </Tooltip>
    </li>
  )
}
