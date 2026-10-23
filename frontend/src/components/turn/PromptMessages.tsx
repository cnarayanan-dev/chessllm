// The Prompt of an attempt, a turn's or a Probe's, as it was sent to the LLM.
import { ChevronRight } from 'lucide-react'
import type { PromptMessage } from '@/api/types'
import { mono, quiet } from '@/components/turn/attempt'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

/** What each message of the Prompt is: the System prompt, the position, then per Retry the answer and the feedback. */
function messageLabel(message: PromptMessage, index: number): string {
  if (message.role === 'system') return 'System prompt'
  if (message.role === 'assistant') return 'Answer'
  return index <= 1 ? 'Position' : 'Retry feedback'
}

/** The messages sent, each under its label; the System prompt folded, as it is the same every turn. */
export function PromptMessages({ messages }: { messages: PromptMessage[] | null }) {
  if (!messages) return <p className={quiet}>The Prompt was not recorded for this turn.</p>
  return (
    <ol className="flex flex-col gap-2">
      {messages.map((message, index) => {
        const label = messageLabel(message, index)
        return (
          <li key={index} className="rounded-md border">
            {message.role === 'system' ? (
              <Collapsible>
                <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-1.5 px-2 py-1 text-xs font-medium text-muted-foreground">
                  <ChevronRight aria-hidden="true" className="size-3 transition-transform group-data-[panel-open]:rotate-90" />
                  {label}
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <p className={`${mono} border-t px-2 py-1.5`}>{message.content}</p>
                </CollapsibleContent>
              </Collapsible>
            ) : (
              <>
                <p className="px-2 pt-1 text-xs font-medium text-muted-foreground">{label}</p>
                <p className={`${mono} px-2 pb-1.5`}>{message.content}</p>
              </>
            )}
          </li>
        )
      })}
    </ol>
  )
}
