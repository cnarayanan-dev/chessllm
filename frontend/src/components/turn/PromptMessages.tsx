// The Prompt sent for an attempt, as the Turn panel shows it for a turn's attempts and for its Probes: a fresh one as
// recorded, and one in a conversation kept by Turn memory as the API rebuilt it, turn by turn (ADR 0009).
import { useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { turnPromptQuery } from '@/api/turnPrompt'
import type { GameState, LlmTurn, PromptMessage, TurnPrompt } from '@/api/types'
import { mono, quiet } from '@/components/turn/styles'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const TRIMMED = "Dropped from the conversation, oldest first, to fit the model's context."

/** What each message of the Prompt is: the System prompt, the position, then per Retry the answer and the feedback. */
function messageLabel(message: PromptMessage, index: number): string {
  if (message.role === 'system') return 'System prompt'
  if (message.role === 'assistant') return 'Answer'
  return index <= 1 ? 'Position' : 'Retry feedback'
}

/** The messages sent, each under its label; the System prompt folded, as it is the same every turn. */
export function Prompt({ messages }: { messages: PromptMessage[] | null }) {
  if (!messages) return <p className={quiet}>The Prompt was not recorded for this turn.</p>
  return (
    <ol className="flex flex-col gap-2">
      {messages.map((message, index) => (
        <MessageItem key={index} message={message} label={messageLabel(message, index)} />
      ))}
    </ol>
  )
}

type AttemptPromptProps = {
  game: GameState
  turn: LlmTurn
  /** The attempt, numbered from 1. */
  attempt: number
}

/**
 * The whole Prompt of an attempt: a fresh turn's as its attempt recorded it; in a conversation, where each attempt
 * records only what it added, as the API rebuilds it from the records.
 */
export function AttemptPrompt({ game, turn, attempt }: AttemptPromptProps) {
  if (turn.remembered == null) return <Prompt messages={turn.attempts[attempt - 1]?.prompt ?? null} />
  const side = game.settings[turn.color]
  const moves = side.player === 'llm' && side.turn_memory === 'chat_moves'
  return (
    <Conversation
      gameId={game.game_id}
      ply={turn.ply}
      attempt={attempt}
      turnMessage={moves ? "Opponent's move" : 'Position'}
    />
  )
}

type ConversationProps = { gameId: string; ply: number; attempt: number; turnMessage: string }

/** A conversation's whole Prompt, asked of the API; while it comes, or if it can't, a quiet line says so. */
function Conversation({ gameId, ply, attempt, turnMessage }: ConversationProps) {
  const query = useQuery(turnPromptQuery(gameId, ply, attempt))
  if (query.isError) return <p className={quiet}>Could not rebuild the conversation: {query.error.message}</p>
  if (!query.data) return <p className={quiet}>Rebuilding the conversation…</p>
  return <ConversationPrompt prompt={query.data} turnMessage={turnMessage} />
}

type ConversationPromptProps = {
  prompt: TurnPrompt
  /** The label of each turn's message: "Position" under Chat with position, "Opponent's move" under Chat with moves. */
  turnMessage: string
}

/**
 * A conversation's whole Prompt: the System prompt, folded, a marker where its earliest turns were trimmed, then each
 * turn it holds under its number, the attempt's own last.
 */
export function ConversationPrompt({ prompt, turnMessage }: ConversationPromptProps) {
  const label = (message: PromptMessage, index: number) => {
    if (message.role === 'assistant') return 'Answer'
    return index === 0 ? turnMessage : 'Retry feedback'
  }
  return (
    <ol className="flex flex-col gap-2">
      <MessageItem message={prompt.system} label="System prompt" />
      {prompt.trimmed > 0 && (
        <li className="text-center text-xs">
          <Tooltip>
            <TooltipTrigger render={<span tabIndex={0} aria-description={TRIMMED} />} className={`${quiet} cursor-help`}>
              {prompt.trimmed === 1 ? 'Turn 1 trimmed' : `Turns 1–${prompt.trimmed} trimmed`}
            </TooltipTrigger>
            <TooltipContent side="bottom">{TRIMMED}</TooltipContent>
          </Tooltip>
        </li>
      )}
      {prompt.turns.map((turn) => (
        <li key={turn.number} aria-label={`Turn ${turn.number}`} className="flex flex-col gap-1">
          <p className="text-xs font-medium text-muted-foreground">{`Turn ${turn.number}`}</p>
          <ol className="flex flex-col gap-2">
            {turn.messages.map((message, index) => (
              <MessageItem key={index} message={message} label={label(message, index)} />
            ))}
          </ol>
        </li>
      ))}
    </ol>
  )
}

/** One message under its label; the System prompt folded. */
function MessageItem({ message, label }: { message: PromptMessage; label: string }) {
  return (
    <li className="rounded-md border">
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
}
