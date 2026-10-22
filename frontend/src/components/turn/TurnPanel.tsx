// The Turn panel, under the Game card: how the LLM decided the move on the board, in tabs.
import { Brain, ChevronLeft, ChevronRight, CornerDownLeft, MessageSquareText } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { Attempt, GameState, LlmTurn, PromptMessage } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { faceoff } from '@/game/wording'

type Decision = 'Thinking' | 'Reasoning'
type Tab = 'decision' | 'prompt' | 'answer'

// The tab last chosen, kept in this browser across turns, games and reloads.
const TAB_KEY = 'chessllm.turnTab'
const TABS: readonly Tab[] = ['decision', 'prompt', 'answer']
const storedTab = (): Tab => TABS.find((tab) => tab === localStorage.getItem(TAB_KEY)) ?? 'decision'

type TurnPanelProps = {
  game: GameState
  /** The ply the position on the board follows (0: the start position). */
  ply: number
  /** Whether the board shows the game as it is, rather than a past position in the move history. */
  live: boolean
}

/**
 * The LLM turn that goes with the position after `ply`: the LLM's move there, or its last move before it. Live after
 * a Forfeit, the forfeited turn, which has no ply of its own.
 */
function turnShown(game: GameState, ply: number, live: boolean): LlmTurn | null {
  const upTo = live && game.end_reason === 'forfeit' ? game.plies.length + 1 : ply
  return game.llm_turns.findLast((turn) => turn.ply <= upTo) ?? null
}

/** The turn's move as the move list numbers it, e.g. "10… Nxa1", or "forfeited" for a turn that played none. */
function moveName(game: GameState, turn: LlmTurn): string {
  const ply = game.plies[turn.ply - 1]
  return ply ? `${Math.ceil(turn.ply / 2)}${turn.color === 'white' ? '.' : '…'} ${ply.written}` : 'forfeited'
}

/** Whether the side thinks, so its tab shows the Thinking rather than the Reasoning written in the answer. */
const thinks = (game: GameState, turn: LlmTurn) => {
  const side = game.settings[turn.color]
  return side.player === 'llm' && side.thinking
}

/** The attempt's Thinking or Reasoning, by what its side produces; else why there is none, as a quiet line. */
function decisionOf(kind: Decision, attempt: Attempt | undefined): { text: string; quiet: boolean } {
  const text = kind === 'Thinking' ? attempt?.thinking : attempt?.reasoning
  if (text) return { text, quiet: false }
  const why = attempt?.error ? `It gave no answer, so there is no ${kind}.` : `Its reply has no ${kind}.`
  return { text: why, quiet: true }
}

/** What each message of the Prompt is: the System prompt, the position, then per Retry the answer and the feedback. */
function messageLabel(message: PromptMessage, index: number): string {
  if (message.role === 'system') return 'System prompt'
  if (message.role === 'assistant') return 'Answer'
  return index <= 1 ? 'Position' : 'Retry feedback'
}

// What each tab holds, in its tooltip and aria-description.
const TAB_MEANINGS: Record<Decision | Exclude<Tab, 'decision'>, string> = {
  Thinking: 'The internal reasoning the model produced before it answered.',
  Reasoning: 'The short explanation the LLM wrote in its answer, before its move.',
  prompt: 'Exactly what was sent to the LLM for this attempt.',
  answer: "The LLM's raw reply, and whether its move was legal.",
}

const RESULT_NAMES: Record<NonNullable<Attempt['result']>, string> = {
  legal: 'Legal',
  invalid: 'Invalid',
  illegal: 'Illegal',
  ambiguous: 'Ambiguous',
  timeout: 'Timeout',
  error: 'Error',
  cut_off: 'Cut off',
}

/** The raw reply, its JSON laid out when it parses; else the error of an attempt that got none. */
function replyText(attempt: Attempt): string {
  if (attempt.raw_reply === null) return attempt.error ?? ''
  try {
    return JSON.stringify(JSON.parse(attempt.raw_reply), null, 2)
  } catch {
    return attempt.raw_reply
  }
}

// Three tabs share the quarter column, so they hug their names, and in a narrow panel (the quarter column just above
// 1100px) drop their icons and shrink; each pane scrolls inside a fixed height.
const trigger = 'gap-1 px-1 @max-[17rem]:text-xs @max-[17rem]:[&_svg]:hidden'
const pane = 'max-h-80 overflow-y-auto'
const quiet = 'text-sm text-muted-foreground'
const mono = 'font-mono text-xs leading-relaxed whitespace-pre-wrap break-words'
const prose = 'leading-relaxed whitespace-pre-wrap text-card-foreground'

export function TurnPanel({ game, ply, live }: TurnPanelProps) {
  const turn = turnShown(game, ply, live)
  const move = turn && moveName(game, turn)
  const [tab, setTab] = useState(storedTab)
  const choose = (chosen: Tab) => {
    localStorage.setItem(TAB_KEY, chosen)
    setTab(chosen)
  }
  return (
    <Card role="region" aria-label="Turn" className="text-[15px]">
      <CardHeader className="flex flex-wrap items-center gap-2">
        <CardTitle className="font-semibold">Turn</CardTitle>
        {turn && (
          <Badge variant={move === 'forfeited' ? 'destructive' : 'secondary'} data-testid="turn-move">
            {move}
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {turn ? (
          <TurnTabs
            // A new turn, or a new attempt of the live one, opens on its last attempt.
            key={`${turn.color}-${turn.ply}-${turn.attempts.length}`}
            turn={turn}
            kind={thinks(game, turn) ? 'Thinking' : 'Reasoning'}
            tab={tab}
            onTab={choose}
          />
        ) : (
          <p className={quiet}>{faceoff(game) ? 'No LLM has moved yet.' : 'The LLM has not moved yet.'}</p>
        )}
      </CardContent>
    </Card>
  )
}

type TurnTabsProps = { turn: LlmTurn; kind: Decision; tab: Tab; onTab: (tab: Tab) => void }

function TurnTabs({ turn, kind, tab, onTab }: TurnTabsProps) {
  const count = turn.attempts.length
  const [number, setNumber] = useState(count) // the attempt shown, from 1
  const attempt = turn.attempts[number - 1]
  const decision = decisionOf(kind, attempt)
  const tabs: { value: Tab; name: string; icon: ReactNode }[] = [
    { value: 'decision', name: kind, icon: <Brain aria-hidden="true" /> },
    { value: 'prompt', name: 'Prompt', icon: <MessageSquareText aria-hidden="true" /> },
    { value: 'answer', name: 'Answer', icon: <CornerDownLeft aria-hidden="true" /> },
  ]
  return (
    <Tabs className="@container" value={tab} onValueChange={(value: Tab) => onTab(value)}>
      <TabsList variant="line" className="w-full">
        {tabs.map(({ value, name, icon }) => {
          const meaning = TAB_MEANINGS[value === 'decision' ? kind : value]
          return (
            <Tooltip key={value}>
              <TooltipTrigger
                render={<TabsTrigger className={trigger} value={value} aria-description={meaning} />}
              >
                {icon}
                {name}
              </TooltipTrigger>
              <TooltipContent side="bottom">{meaning}</TooltipContent>
            </Tooltip>
          )
        })}
      </TabsList>
      {count > 1 && (
        <div className="flex items-center justify-end text-xs text-muted-foreground">
          <StepButton
            name="Earlier attempt"
            disabled={number === 1 ? 'This is the first attempt.' : undefined}
            onClick={() => setNumber(number - 1)}
          >
            <ChevronLeft aria-hidden="true" />
          </StepButton>
          <span aria-live="polite">{`Attempt ${number} of ${count}`}</span>
          <StepButton
            name="Later attempt"
            disabled={number === count ? 'This is the last attempt.' : undefined}
            onClick={() => setNumber(number + 1)}
          >
            <ChevronRight aria-hidden="true" />
          </StepButton>
        </div>
      )}
      <TabsContent className={pane} value="decision">
        <p className={decision.quiet ? quiet : prose}>{decision.text}</p>
      </TabsContent>
      <TabsContent className={pane} value="prompt">
        <Prompt messages={attempt?.prompt ?? null} />
      </TabsContent>
      <TabsContent className={pane} value="answer">{attempt && <Answer attempt={attempt} />}</TabsContent>
    </Tabs>
  )
}

/** The messages sent, each under its label; the System prompt folded, as it is the same every turn. */
function Prompt({ messages }: { messages: PromptMessage[] | null }) {
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

/** The reply as it came back, with its result and latency. */
function Answer({ attempt }: { attempt: Attempt }) {
  const result = attempt.result && RESULT_NAMES[attempt.result]
  const latency = attempt.latency_s === null ? '' : ` · ${attempt.latency_s.toFixed(1)} s`
  return (
    <div className="flex flex-col items-start gap-2">
      {result && <Badge variant={attempt.result === 'legal' ? 'secondary' : 'destructive'}>{result + latency}</Badge>}
      <p className={`${mono} w-full rounded-md bg-muted px-2 py-1.5`}>{replyText(attempt)}</p>
    </div>
  )
}

type StepButtonProps = {
  name: string
  /** Why it can't be pressed; it then is disabled, the reason in its tooltip instead of the name. */
  disabled?: string
  onClick: () => void
  children: ReactNode
}

/** A chevron of the attempt stepper, its name or why it is disabled on hover. The tooltip hangs on a wrapper, as a
 * disabled button takes no hover. */
function StepButton({ name, disabled, onClick, children }: StepButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger render={<span />}>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={name}
          aria-description={disabled}
          disabled={disabled !== undefined}
          onClick={onClick}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{disabled ?? name}</TooltipContent>
    </Tooltip>
  )
}
