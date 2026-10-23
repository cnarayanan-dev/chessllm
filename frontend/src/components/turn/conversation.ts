// An attempt's whole Prompt, rebuilt from the game's records (ADR 0009). A fresh turn records it whole; in a
// conversation kept by Turn memory each attempt records only the messages it added, so the Prompt is the side's
// System prompt, the earlier turns the attempt remembered, and its own turn up to it. The backend rebuilds it the same
// way (full_prompt in chessllm/game/llm_turn/conversation.py), both checked against conversation.fixture.json.
import type { Attempt, LlmTurn, PromptMessage } from '@/api/types'

/** A message of the Prompt with what it is: the System prompt, a turn's message, an Answer or Retry feedback. */
export type LabelledMessage = { message: PromptMessage; label: string }

/** An earlier turn the attempt remembered, numbered among its side's turns from 1. */
export type EarlierTurn = { number: number; messages: LabelledMessage[] }

export type ConversationPrompt = {
  system: PromptMessage | null
  /** The side's earlier turns dropped to fit the model's context, the first and last by number; null when none were. */
  trimmed: { from: number; to: number } | null
  earlier: EarlierTurn[]
  /** The attempt's own turn up to it: its message and, for a Retry, each earlier answer and the feedback after it. */
  current: LabelledMessage[]
}

/** What each message of a fresh Prompt is: the System prompt, the position, then per Retry the answer and feedback. */
function freshLabel(message: PromptMessage, index: number): string {
  if (message.role === 'system') return 'System prompt'
  if (message.role === 'assistant') return 'Answer'
  return index <= 1 ? 'Position' : 'Retry feedback'
}

/** A Prompt recorded whole, a fresh turn's or a Probe's, its messages labelled. */
export function freshPrompt(messages: PromptMessage[]): ConversationPrompt {
  const labelled = messages.map((message, index) => ({ message, label: freshLabel(message, index) }))
  const system = labelled[0]?.message.role === 'system' ? labelled[0].message : null
  return { system, trimmed: null, earlier: [], current: system ? labelled.slice(1) : labelled }
}

/**
 * What a turn's attempts put in the conversation: what each added, and its answer when it was kept: when the next
 * attempt answers it with Retry feedback, or, in a turn that has ended, when it was the last. The turn's message is
 * labelled with its number.
 */
function kept(attempts: Attempt[], number: number, ended: boolean): LabelledMessage[] {
  return attempts.flatMap((attempt, index) => {
    const added = (attempt.prompt ?? [])
      .filter((message) => message.role !== 'system')
      .map((message) => ({ message, label: index === 0 ? `Turn ${number}` : 'Retry feedback' }))
    const following = attempts[index + 1]
    const answerKept = following ? following.feedback_sent !== null : ended
    const answer: LabelledMessage[] =
      answerKept && attempt.raw_reply !== null
        ? [{ message: { role: 'assistant', content: attempt.raw_reply }, label: 'Answer' }]
        : []
    return [...added, ...answer]
  })
}

/** How many earlier turns the last of `attempts` remembered: its turn's, unless the conversation was trimmed within
 * the turn: then what it, or the last before it, records. */
const lastRemembered = (attempts: Attempt[], remembered: number) =>
  attempts.findLast((sent) => sent.remembered != null)?.remembered ?? remembered

/**
 * A Prompt of `turn` in a conversation: the side's System prompt, the earlier turns dropped to fit the context, the
 * `remembered` ones, and `current`, what the turn itself adds.
 */
function inConversation(
  turns: LlmTurn[],
  turn: LlmTurn,
  remembered: number,
  current: (number: number) => LabelledMessage[],
): ConversationPrompt {
  const side = turns.filter((earlier) => earlier.color === turn.color && earlier.ply <= turn.ply)
  const dropped = side.length - 1 - remembered
  return {
    system: side[0].attempts[0].prompt?.find((message) => message.role === 'system') ?? null,
    trimmed: dropped > 0 ? { from: 1, to: dropped } : null,
    earlier: side
      .slice(dropped, -1)
      .map((earlier, index) => ({ number: dropped + index + 1, messages: kept(earlier.attempts, dropped + index + 1, true) })),
    current: current(side.length),
  }
}

/** The Prompt of an attempt (numbered from 1 in its turn) of `turn`, rebuilt from the game's LLM turns. */
export function conversationPrompt(turns: LlmTurn[], turn: LlmTurn, attempt: number): ConversationPrompt {
  if (turn.remembered == null) return freshPrompt(turn.attempts[attempt - 1]?.prompt ?? [])
  const sent = turn.attempts.slice(0, attempt)
  return inConversation(turns, turn, lastRemembered(sent, turn.remembered), (number) => kept(sent, number, false))
}

/**
 * The Prompt of the Legal counterpart of `turn`'s chaos move, as the backend's counterpart_prompt rebuilds it: a fresh
 * side's is recorded whole, as is one with a System prompt, asked before counterparts were asked inside a
 * conversation. Otherwise it was asked at the end of the conversation as the chaos move's turn left it: the turn
 * whole, then the request, which is all it records.
 */
export function counterpartPrompt(turns: LlmTurn[], turn: LlmTurn): ConversationPrompt {
  const asked = turn.legal_counterpart?.attempt
  const recorded = asked?.prompt ?? []
  if (!asked || turn.remembered == null || recorded.some((message) => message.role === 'system')) return freshPrompt(recorded)
  const remembered = lastRemembered([...turn.attempts, asked], turn.remembered)
  return inConversation(turns, turn, remembered, (number) => [
    ...kept(turn.attempts, number, true),
    ...recorded.map((message) => ({ message, label: 'Legal counterpart request' })),
  ])
}

/** A Prompt's messages in the order sent. */
export const messagesOf = (prompt: ConversationPrompt): PromptMessage[] => [
  ...(prompt.system ? [prompt.system] : []),
  ...[...prompt.earlier.flatMap((earlier) => earlier.messages), ...prompt.current].map(({ message }) => message),
]

/** The whole Prompt of the attempt as the LLM received it. */
export const fullPrompt = (turns: LlmTurn[], turn: LlmTurn, attempt: number): PromptMessage[] =>
  messagesOf(conversationPrompt(turns, turn, attempt))
