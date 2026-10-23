// The Turn panel, under the Game card: how the LLM decided the move on the board, in tabs.
import { Brain, ChevronLeft, ChevronRight, CornerDownLeft, Eye, MessageSquareText, Scale, Undo2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal, flushSync } from 'react-dom'
import type { Attempt, Color, GameState, LlmTurn } from '@/api/types'
import { decisionOf, mono, prose, quiet, RESULT_NAMES, type Decision } from '@/components/turn/attempt'
import { ChaosGainLine } from '@/components/turn/ChaosGainLine'
import { Probes } from '@/components/turn/Probes'
import { conversationPrompt, counterpartPrompt } from '@/components/turn/conversation'
import { PromptDock } from '@/components/turn/PromptDock'
import { ConversationMessages, PromptMessages } from '@/components/turn/PromptMessages'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { shownGain } from '@/game/chaosGain'
import { faceoff } from '@/game/wording'
import { usePromptLab } from '@/settings/promptLab'

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
  /** Whether the board shows the viewed Chaos move's Legal counterpart instead of the Chaos move. */
  previewing?: boolean
  /** Shows the Legal counterpart on the board, or the Chaos move again: its move's button. */
  onPreview?: () => void
  /** Why Try can't probe now (an LLM turn runs), shown on hover; undefined when it can. Only with Prompt lab on. */
  tryBlocked?: string
  /** Called with whether the dock is open, as the page sets itself aside under it, and gives it back once closed. */
  onDock?: (open: boolean) => void
  /** In a running game no human plays: pauses it, resolving once paused, for Try to probe then (Pause). */
  pauseFirst?: () => Promise<void>
}

/** The dock opened from a turn's Prompt row: on that turn of that game, and the template its text starts from, by
 * its ID. */
type Docked = { gameId: string; ply: number; color: Color; baseId: string }

/**
 * The LLM turn that goes with the position after `ply`: the LLM's move there, or its last move before it. Live after
 * a Forfeit, the forfeited turn, which has no ply of its own.
 */
function turnShown(game: GameState, ply: number, live: boolean): LlmTurn | null {
  const upTo = live && game.end_reason === 'forfeit' ? game.plies.length + 1 : ply
  return game.llm_turns.findLast((turn) => turn.ply <= upTo) ?? null
}

/** The turn's move number as the move list has it, e.g. "10…". */
const moveNumber = (turn: LlmTurn) => `${Math.ceil(turn.ply / 2)}${turn.color === 'white' ? '.' : '…'}`

/** The turn's move as the move list numbers it, e.g. "10… Nxa1", or "forfeited" for a turn that played none. */
function moveName(game: GameState, turn: LlmTurn): string {
  const ply = game.plies[turn.ply - 1]
  return ply ? `${moveNumber(turn)} ${ply.written}` : 'forfeited'
}

/** Whether the side thinks, so its tab shows the Thinking rather than the Reasoning written in the answer. */
const thinks = (game: GameState, turn: LlmTurn) => {
  const side = game.settings[turn.color]
  return side.player === 'llm' && side.thinking
}

// What each tab holds, in its tooltip and aria-description.
const TAB_MEANINGS: Record<Decision | Exclude<Tab, 'decision'>, string> = {
  Thinking: 'The internal reasoning the model produced before it answered.',
  Reasoning: 'The short explanation the LLM wrote in its answer, before its move.',
  prompt: 'Exactly what was sent to the LLM for this attempt.',
  answer: "The LLM's raw reply, and whether its move was legal.",
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

export function TurnPanel({ game, ply, live, previewing = false, onPreview, tryBlocked, onDock, pauseFirst }: TurnPanelProps) {
  const turn = turnShown(game, ply, live)
  const move = turn && moveName(game, turn)
  const gain = turn ? shownGain(game, turn) : undefined
  const [tab, setTab] = useState(storedTab)
  const promptLab = usePromptLab()
  // The Prompt template picked to Try, kept from turn to turn; null for the game's own.
  const [tried, setTried] = useState<string | null>(null)
  // The dock is kept here, not with the turn's tabs, so a new attempt or turn landing doesn't drop the text written.
  const [docked, setDocked] = useState<Docked | null>(null)
  const dockedTurn =
    docked && promptLab && docked.gameId === game.game_id
      ? game.llm_turns.find((shown) => shown.ply === docked.ply && shown.color === docked.color)
      : undefined
  const open = dockedTurn !== undefined
  useEffect(() => {
    onDock?.(open)
    return () => onDock?.(false)
  }, [open, onDock])
  // The name's button the dock was opened from, which gets the focus back once the page is given back.
  const openedFrom = useRef<HTMLElement | null>(null)
  const closeDock = () => {
    flushSync(() => {
      setDocked(null)
      onDock?.(false)
    })
    if (openedFrom.current?.isConnected) openedFrom.current.focus()
  }
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
            turns={game.llm_turns}
            kind={thinks(game, turn) ? 'Thinking' : 'Reasoning'}
            tab={tab}
            onTab={choose}
            probes={
              promptLab ? (
                <Probes
                  game={game}
                  turn={turn}
                  tryBlocked={tryBlocked}
                  pauseFirst={pauseFirst}
                  picked={tried}
                  onPick={setTried}
                  onEdit={(baseId, from) => {
                    openedFrom.current = from
                    setDocked({ gameId: game.game_id, ply: turn.ply, color: turn.color, baseId })
                  }}
                />
              ) : undefined
            }
          />
        ) : (
          <p className={quiet}>{faceoff(game) ? 'No LLM has moved yet.' : 'The LLM has not moved yet.'}</p>
        )}
        {turn?.legal_counterpart && turn.ply === ply && (
          <Counterpart
            counterpart={turn.legal_counterpart}
            turns={game.llm_turns}
            turn={turn}
            number={moveNumber(turn)}
            chaosMove={move!}
            previewing={previewing}
            onPreview={onPreview}
          />
        )}
        {turn?.ply === ply && gain && <ChaosGainLine gain={gain} />}
      </CardContent>
      {/* Out of the page's columns, which are set aside (inert) while it is open. */}
      {docked && dockedTurn &&
        createPortal(
          <PromptDock
            key={`${docked.ply}-${docked.color}`}
            game={game}
            turn={dockedTurn}
            baseId={docked.baseId}
            tryBlocked={tryBlocked}
            pauseFirst={pauseFirst}
            onSaved={(saved) => {
              setTried(saved.id)
              setDocked({ ...docked, baseId: saved.id })
            }}
            onClose={closeDock}
          />,
          document.body,
        )}
    </Card>
  )
}

type LegalCounterpart = NonNullable<LlmTurn['legal_counterpart']>

const COUNTERPART_MEANING =
  'The legal move the LLM gave when asked once more in the same position, after its Chaos move. Never played.'

type CounterpartProps = {
  counterpart: LegalCounterpart
  /** The game's LLM turns and the chaos move's, which its whole Prompt is rebuilt from in a conversation. */
  turns: LlmTurn[]
  turn: LlmTurn
  number: string
  /** The Chaos move as the move list numbers it, e.g. "1… Bb4". */
  chaosMove: string
  previewing: boolean
  onPreview?: () => void
}

/**
 * The Chaos move's Legal counterpart, at the bottom of the panel: its name, then its move on a line of its own, a
 * toggle that shows the position it would have left on the board, or "none" when it failed, why in its tooltip, and
 * its Prompt, folded. No time is shown: it is none of the turn's.
 */
function Counterpart({ counterpart, turns, turn, number, chaosMove, previewing, onPreview }: CounterpartProps) {
  // Rebuilt only when the game's turns change, not at every render the page polls.
  const prompt = useMemo(() => counterpartPrompt(turns, turn), [turns, turn])
  const why = counterpart.attempt.error ?? 'Its answer was no legal move.'
  return (
    <div role="group" aria-label="Legal counterpart" className="mt-4 flex flex-col gap-1 border-t pt-3">
      <Tooltip>
        <TooltipTrigger
          render={<span aria-description={COUNTERPART_MEANING} />}
          className="flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground"
        >
          <Scale aria-hidden="true" className="size-4" />
          Legal counterpart
        </TooltipTrigger>
        <TooltipContent side="bottom">{COUNTERPART_MEANING}</TooltipContent>
      </Tooltip>
      {counterpart.san === null ? (
        <Tooltip>
          <TooltipTrigger render={<span aria-description={why} data-testid="counterpart-move" />} className={`${quiet} w-fit`}>
            none
          </TooltipTrigger>
          <TooltipContent side="bottom">{why}</TooltipContent>
        </Tooltip>
      ) : (
        <CounterpartButton
          name={`${number} ${counterpart.san}`}
          chaosMove={chaosMove}
          previewing={previewing}
          onPreview={onPreview}
        />
      )}
      {(prompt.system || prompt.current.length > 0) && (
        <Collapsible className="mt-1">
          <CollapsibleTrigger className="group flex cursor-pointer items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <ChevronRight aria-hidden="true" className="size-3 transition-transform group-data-[panel-open]:rotate-90" />
            Its Prompt
          </CollapsibleTrigger>
          <CollapsibleContent className={`${pane} mt-1`}>
            <ConversationMessages prompt={prompt} />
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}

type CounterpartButtonProps = { name: string; chaosMove: string; previewing: boolean; onPreview?: () => void }

/** The counterpart's move as a toggle, pressed while the board shows the position it would have left. */
function CounterpartButton({ name, chaosMove, previewing, onPreview }: CounterpartButtonProps) {
  const meaning = previewing
    ? `Back to ${chaosMove} on the board.`
    : `Show the position ${name} would have left on the board. It was never played.`
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant={previewing ? 'default' : 'secondary'}
            size="sm"
            aria-pressed={previewing}
            aria-description={meaning}
            data-testid="counterpart-move"
            onClick={onPreview}
          />
        }
        className="w-fit tabular-nums"
      >
        {previewing ? <Undo2 aria-hidden="true" /> : <Eye aria-hidden="true" />}
        {name}
      </TooltipTrigger>
      <TooltipContent side="bottom">{meaning}</TooltipContent>
    </Tooltip>
  )
}

type TurnTabsProps = {
  turn: LlmTurn
  /** The game's LLM turns, which a conversation's whole Prompt is rebuilt from (ADR 0009). */
  turns: LlmTurn[]
  kind: Decision
  tab: Tab
  onTab: (tab: Tab) => void
  /** With Prompt lab on, the Prompt row, Try and the turn's probes, at the top of the Prompt tab. */
  probes?: ReactNode
}

function TurnTabs({ turn, turns, kind, tab, onTab, probes }: TurnTabsProps) {
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
        {probes}
        {attempt?.prompt == null ? (
          <PromptMessages messages={null} />
        ) : (
          <ConversationMessages prompt={conversationPrompt(turns, turn, number)} />
        )}
      </TabsContent>
      <TabsContent className={pane} value="answer">{attempt && <Answer attempt={attempt} />}</TabsContent>
    </Tabs>
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
