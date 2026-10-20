// PROTOTYPE, throwaway: what should the Reasoning panel look like once it grows to show how the LLM decided — the
// prompt sent, its Thinking or Reasoning, and its answer, for the turn on the board? Three variants in the panel's own
// slot (bottom left), switched with ?variant=A|B|C from the bar at the bottom (or [ and ]). The two Preferences
// switches "Show thinking" (on) and "Show prompt" (off) live in ⚙ at the top right; here they are kept in localStorage.
//
// The API doesn't send the prompt yet, so it is rebuilt here from the game state as chessllm/prompt.py builds it:
// the system prompt, the position, and for each retry the reply and the Retry feedback. The Legal-move list and the
// described position aren't in the API, so they show as placeholders. Never ship this: fold the winner into the
// real panel, with the prompt recorded by the backend as sent.
import { Brain, ChevronLeft, ChevronRight, CornerDownLeft, LoaderCircle, MessageSquareText } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Attempt, GameState, LlmTurn } from '@/api/types'
import { PrototypeSwitcher, useVariant } from '@/components/prototype-switcher/PrototypeSwitcher'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { COLOR_NAMES, faceoff } from '@/game/wording'

// --- The two preferences ---------------------------------------------------------------------------------------------

type Pref = 'show-thinking' | 'show-prompt'
const PREF_DEFAULTS: Record<Pref, boolean> = { 'show-thinking': true, 'show-prompt': false }
const readPref = (pref: Pref) => {
  const stored = localStorage.getItem(`prototype-${pref}`)
  return stored === null ? PREF_DEFAULTS[pref] : stored === 'on'
}

function usePref(pref: Pref): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => readPref(pref))
  useEffect(() => {
    const onChange = () => setOn(readPref(pref))
    window.addEventListener('prototype-pref', onChange)
    return () => window.removeEventListener('prototype-pref', onChange)
  }, [pref])
  const set = (value: boolean) => {
    localStorage.setItem(`prototype-${pref}`, value ? 'on' : 'off')
    window.dispatchEvent(new Event('prototype-pref'))
  }
  return [on, set]
}

const PREF_ROWS: { pref: Pref; name: string; explanation: string }[] = [
  {
    pref: 'show-thinking',
    name: 'Show thinking',
    explanation: "The LLM's Thinking, or its Reasoning with thinking off, in the panel under the Game card.",
  },
  {
    pref: 'show-prompt',
    name: 'Show prompt',
    explanation: 'The exact messages sent to the LLM for the turn on the board. Off, they are one click away.',
  },
]

/** The two switches, for the ⚙ Preferences panel. */
export function TurnPanelPrefs() {
  return PREF_ROWS.map((row) => <PrefRow key={row.pref} {...row} />)
}

function PrefRow({ pref, name, explanation }: (typeof PREF_ROWS)[number]) {
  const [on, set] = usePref(pref)
  return (
    <Tooltip>
      <TooltipTrigger render={<label className="mt-2 flex items-center justify-between gap-4 font-medium" />}>
        {name}
        <Switch aria-label={name} aria-description={explanation} checked={on} onCheckedChange={set} />
      </TooltipTrigger>
      <TooltipContent side="bottom">{explanation}</TooltipContent>
    </Tooltip>
  )
}

// --- The turn and its prompt, rebuilt --------------------------------------------------------------------------------

type Role = 'system' | 'user' | 'assistant'
type Message = { role: Role; content: string; label: string }

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

// As chessllm/prompts/*.txt: it says "a human" in an LLM faceoff too, since the template has no opponent kind.
function systemPrompt(color: 'white' | 'black', listed: boolean): string {
  const name = COLOR_NAMES[color]
  const opponent = color === 'white' ? 'Black' : 'White'
  const [pgn, fen, move] = color === 'white' ? ['(no moves yet)', START, 'e4'] : ['1. e4', AFTER_E4, 'e5']
  const head = `You are playing chess as ${name} against a human playing ${opponent}.\n`
  if (!listed) {
    return (
      head +
      'Each turn you get the game so far in PGN and the current position in FEN.\n' +
      'Reply with your next move in SAN (e.g. Nf6, exd5, O-O, e8=Q).\n' +
      'The move must be legal in the current position.\n\n' +
      `Example:\nPGN: ${pgn}\nFEN: ${fen}\nAnswer: {"move": "${move}"}`
    )
  }
  return (
    head +
    'Each turn you get the game so far in PGN, the current position in FEN, and the list of legal moves in SAN.\n' +
    'The list contains every legal move in the current position. Its order is random and means nothing.\n' +
    'Choose your next move from the list and reply with it exactly as written there (e.g. Nf6, exd5, O-O, e8=Q).\n\n' +
    `Example:\nPGN: ${pgn}\nFEN: ${fen}\nLegal moves: …\nAnswer: {"move": "${move}"}`
  )
}

/** The turn on show: as the Reasoning panel picks it, or live while the LLM is asked, the turn in progress. */
function turnShown(game: GameState, ply: number, live: boolean): LlmTurn | null {
  if (live && game.llm_turn && !game.plies[game.llm_turn.ply - 1]) return game.llm_turn
  const upTo = live && game.end_reason === 'forfeit' ? game.plies.length + 1 : ply
  return game.llm_turns.findLast((turn) => turn.ply <= upTo) ?? null
}

function llm(game: GameState, turn: LlmTurn) {
  const side = game.settings[turn.color]
  return side.player === 'llm' ? side : null
}

function positionMessage(game: GameState, turn: LlmTurn): string {
  const before = game.plies.slice(0, turn.ply - 1)
  const pgn = before.map((p, i) => (i % 2 === 0 ? `${i / 2 + 1}. ${p.written}` : p.written)).join(' ')
  const fen = game.plies[turn.ply - 1]?.fen_before ?? game.fen
  const side = llm(game, turn)
  let text = `PGN: ${pgn || '(no moves yet)'}\nFEN: ${fen}`
  if (side?.position === 'described') text += '\n[described position — not in the API yet]'
  if (side?.llm_constraints.startsWith('listed')) text += '\nLegal moves: [shuffled list — not in the API yet]'
  return text
}

type Exchange = { number: number; sent: Message[]; attempt: Attempt | null }

/** Each attempt with the whole chat sent for it (a retry resends the chat so far plus the feedback) and its reply. */
function exchanges(game: GameState, turn: LlmTurn): Exchange[] {
  const listed = !!llm(game, turn)?.llm_constraints.startsWith('listed')
  let sent: Message[] = [
    { role: 'system', content: systemPrompt(turn.color, listed), label: 'System' },
    { role: 'user', content: positionMessage(game, turn), label: 'Position' },
  ]
  const out: Exchange[] = []
  turn.attempts.forEach((attempt, index) => {
    if (index > 0) {
      sent = [
        ...sent,
        { role: 'assistant', content: turn.attempts[index - 1].raw_reply ?? '', label: `Answer ${index}` },
        { role: 'user', content: attempt.feedback_sent ?? '', label: 'Retry feedback' },
      ]
    }
    out.push({ number: index + 1, sent, attempt })
  })
  if (out.length === 0) out.push({ number: 1, sent, attempt: null })
  return out
}

/** The attempt's Thinking (thinking on) or Reasoning (thinking off), and which of the two it is. */
function decision(game: GameState, turn: LlmTurn, attempt: Attempt | null): { kind: string; text: string | null } {
  const thinking = !!llm(game, turn)?.thinking
  return thinking
    ? { kind: 'Thinking', text: attempt?.thinking ?? null }
    : { kind: 'Reasoning', text: attempt?.reasoning ?? null }
}

function moveName(game: GameState, turn: LlmTurn): string {
  const ply = game.plies[turn.ply - 1]
  if (ply) return `${Math.ceil(turn.ply / 2)}${turn.color === 'white' ? '.' : '…'} ${ply.written}`
  return game.end_reason === 'forfeit' ? 'forfeited' : 'thinking…'
}

function heading(game: GameState, turn: LlmTurn): string {
  const model = llm(game, turn)?.model ?? ''
  return `${faceoff(game) ? `${COLOR_NAMES[turn.color]} · ` : ''}${model} · ${moveName(game, turn)}`
}

function prettyReply(attempt: Attempt | null): string {
  if (!attempt?.result) return 'Waiting for the answer…'
  if (attempt.error) return attempt.error
  try {
    return JSON.stringify(JSON.parse(attempt.raw_reply ?? ''), null, 2)
  } catch {
    return attempt.raw_reply ?? ''
  }
}

function ResultBadge({ attempt, number }: { attempt: Attempt | null; number?: number }) {
  if (!attempt?.result) {
    return (
      <Badge variant="outline">
        <LoaderCircle className="animate-spin" /> asking
      </Badge>
    )
  }
  return (
    <Badge variant={attempt.result === 'legal' ? 'secondary' : 'destructive'}>
      {number !== undefined && `${number} · `}
      {attempt.move ?? '—'} · {attempt.result}
      {attempt.latency_s != null && ` · ${attempt.latency_s.toFixed(1)}s`}
    </Badge>
  )
}

const pre = 'font-mono text-xs leading-relaxed whitespace-pre-wrap break-words'

function MessageBlock({ message, defaultOpen = true }: { message: Message; defaultOpen?: boolean }) {
  return (
    <Collapsible defaultOpen={defaultOpen} className="rounded-md border">
      <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-1.5 px-2 py-1 text-xs font-medium text-muted-foreground">
        <ChevronRight className="size-3 transition-transform group-data-[panel-open]:rotate-90" />
        {message.role} · {message.label}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className={`${pre} border-t px-2 py-1.5`}>{message.content}</div>
      </CollapsibleContent>
    </Collapsible>
  )
}

/** A section heading: an icon and a short name, with what it holds on hover. */
function SectionName({ icon, name, hint, children }: { icon: ReactNode; name: string; hint: string; children?: ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
      <Tooltip>
        <TooltipTrigger render={<span className="flex items-center gap-1.5" />}>
          {icon}
          {name}
        </TooltipTrigger>
        <TooltipContent side="right">{hint}</TooltipContent>
      </Tooltip>
      {children}
    </div>
  )
}

const HINTS = {
  Thinking: 'The internal reasoning the model produced before it answered (thinking on).',
  Reasoning: 'The short explanation the LLM wrote in its answer, before its move (thinking off).',
  Prompt: 'Exactly what was sent to the LLM for this attempt: the system prompt, the position, and any retries.',
  Answer: "The LLM's raw reply, and whether its move was legal.",
}

// --- Variant A: stacked sections -------------------------------------------------------------------------------------
// One column for the turn: attempt chips, then Thinking/Reasoning, then the answer, then the prompt (collapsed unless
// Show prompt is on). Picking an attempt chip switches every section to that attempt.

function VariantA({ game, turn }: { game: GameState; turn: LlmTurn }) {
  const [showThinking] = usePref('show-thinking')
  const [showPrompt] = usePref('show-prompt')
  const all = exchanges(game, turn)
  const [picked, setPicked] = useState<number | null>(null)
  const current = all[(picked ?? all.length) - 1] ?? all.at(-1)!
  const { kind, text } = decision(game, turn, current.attempt)
  return (
    <div className="flex flex-col gap-4">
      {all.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          {all.map((exchange) => (
            <button
              key={exchange.number}
              type="button"
              onClick={() => setPicked(exchange.number)}
              className={`cursor-pointer rounded-full ${exchange === current ? 'ring-2 ring-ring' : 'opacity-70'}`}
            >
              <ResultBadge attempt={exchange.attempt} number={exchange.number} />
            </button>
          ))}
        </div>
      )}
      {showThinking && (
        <section className="flex flex-col gap-1.5">
          <SectionName icon={<Brain className="size-3.5" />} name={kind} hint={HINTS[kind as 'Thinking']} />
          <div className="max-h-64 overflow-y-auto leading-relaxed whitespace-pre-wrap">
            {text ?? <span className="text-sm text-muted-foreground">None for this attempt.</span>}
          </div>
        </section>
      )}
      <section className="flex flex-col gap-1.5">
        <SectionName icon={<CornerDownLeft className="size-3.5" />} name="Answer" hint={HINTS.Answer}>
          {all.length === 1 && <ResultBadge attempt={current.attempt} />}
        </SectionName>
        <div className={`${pre} rounded-md bg-muted px-2 py-1.5`}>{prettyReply(current.attempt)}</div>
      </section>
      <Collapsible key={String(showPrompt)} defaultOpen={showPrompt}>
        <CollapsibleTrigger className="group flex cursor-pointer items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          <ChevronRight className="size-3.5 transition-transform group-data-[panel-open]:rotate-90" />
          <MessageSquareText className="size-3.5" /> Prompt
          <span className="font-normal normal-case">· {current.sent.length} messages</span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-1.5 flex max-h-80 flex-col gap-1.5 overflow-y-auto">
            {current.sent.map((message, index) => (
              <MessageBlock key={index} message={message} defaultOpen={message.role !== 'system'} />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}

// --- Variant B: tabs -------------------------------------------------------------------------------------------------
// One pane at a time in a fixed-height box: Thinking | Prompt | Answer as icon tabs, an attempt stepper in the corner.
// The preferences pick which tabs exist; the first one present opens.

type Tab = 'decision' | 'prompt' | 'answer'

function VariantB({ game, turn }: { game: GameState; turn: LlmTurn }) {
  const [showThinking] = usePref('show-thinking')
  const [showPrompt] = usePref('show-prompt')
  const all = exchanges(game, turn)
  const [picked, setPicked] = useState<number | null>(null)
  const index = (picked ?? all.length) - 1
  const current = all[index] ?? all.at(-1)!
  const { kind, text } = decision(game, turn, current.attempt)
  const tabs: { key: Tab; name: string; icon: ReactNode; hint: string }[] = [
    ...(showThinking ? [{ key: 'decision' as Tab, name: kind, icon: <Brain />, hint: HINTS[kind as 'Thinking'] }] : []),
    { key: 'prompt', name: 'Prompt', icon: <MessageSquareText />, hint: HINTS.Prompt },
    { key: 'answer', name: 'Answer', icon: <CornerDownLeft />, hint: HINTS.Answer },
  ]
  const [chosen, setChosen] = useState<Tab | null>(null)
  const preferred: Tab = showThinking ? 'decision' : showPrompt ? 'prompt' : 'answer'
  const tab = chosen && tabs.some((t) => t.key === chosen) ? chosen : preferred
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1 border-b">
        {tabs.map((t) => (
          <Tooltip key={t.key}>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  onClick={() => setChosen(t.key)}
                  className={`-mb-px flex cursor-pointer items-center gap-1.5 border-b-2 px-2 py-1.5 text-xs font-medium [&_svg]:size-3.5 ${
                    tab === t.key ? 'border-foreground' : 'border-transparent text-muted-foreground'
                  }`}
                />
              }
            >
              {t.icon}
              {t.name}
            </TooltipTrigger>
            <TooltipContent side="top">{t.hint}</TooltipContent>
          </Tooltip>
        ))}
        {all.length > 1 && (
          <div className="ml-auto flex items-center gap-0.5 text-xs text-muted-foreground">
            <button type="button" className="cursor-pointer" onClick={() => setPicked(Math.max(1, index))} aria-label="Earlier attempt">
              <ChevronLeft className="size-3.5" />
            </button>
            {current.number}/{all.length}
            <button type="button" className="cursor-pointer" onClick={() => setPicked(Math.min(all.length, index + 2))} aria-label="Later attempt">
              <ChevronRight className="size-3.5" />
            </button>
          </div>
        )}
      </div>
      <div className="h-72 overflow-y-auto">
        {tab === 'decision' && (
          <div className="leading-relaxed whitespace-pre-wrap">
            {text ?? <span className="text-sm text-muted-foreground">None for this attempt.</span>}
          </div>
        )}
        {tab === 'prompt' && (
          <div className="flex flex-col gap-1.5">
            {current.sent.map((message, i) => (
              <MessageBlock key={i} message={message} defaultOpen={message.role !== 'system'} />
            ))}
          </div>
        )}
        {tab === 'answer' && (
          <div className="flex flex-col gap-2">
            <div>
              <ResultBadge attempt={current.attempt} />
            </div>
            <div className={`${pre} rounded-md bg-muted px-2 py-1.5`}>{prettyReply(current.attempt)}</div>
          </div>
        )}
      </div>
    </div>
  )
}

// --- Variant C: the turn as a chat -----------------------------------------------------------------------------------
// The whole turn top to bottom as the conversation it was: what was sent (right), what the LLM thought and answered
// (left), then any retry feedback and the next answer. Show prompt off hides the sent messages except the Retry
// feedback, behind a "what was sent" toggle; Show thinking off folds the Thinking into a one-line row.

function VariantC({ game, turn }: { game: GameState; turn: LlmTurn }) {
  const [showThinking] = usePref('show-thinking')
  const [showPromptPref] = usePref('show-prompt')
  const [peek, setPeek] = useState(false)
  const showPrompt = showPromptPref || peek
  const all = exchanges(game, turn)
  const first = all[0].sent
  const sentBubble = (message: Message, key: string) => (
    <div key={key} className="ml-6 rounded-lg rounded-tr-sm bg-muted px-2.5 py-1.5">
      <div className="mb-0.5 text-[11px] font-medium text-muted-foreground">{message.label}</div>
      {message.role === 'system' ? (
        <Collapsible>
          <CollapsibleTrigger className="group flex cursor-pointer items-center gap-1 text-xs text-muted-foreground">
            <ChevronRight className="size-3 transition-transform group-data-[panel-open]:rotate-90" />
            {message.content.split('\n')[0]}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className={`${pre} mt-1`}>{message.content}</div>
          </CollapsibleContent>
        </Collapsible>
      ) : (
        <div className={pre}>{message.content}</div>
      )}
    </div>
  )
  return (
    <div className="flex max-h-[28rem] flex-col gap-2 overflow-y-auto">
      {!showPromptPref && (
        <button
          type="button"
          onClick={() => setPeek(!peek)}
          className="flex cursor-pointer items-center gap-1.5 self-end text-xs text-muted-foreground"
        >
          <MessageSquareText className="size-3.5" /> {peek ? 'Hide' : 'Show'} what was sent
        </button>
      )}
      {showPrompt && first.map((message, i) => sentBubble(message, `first-${i}`))}
      {all.map((exchange) => {
        const { kind, text } = decision(game, turn, exchange.attempt)
        const feedback = exchange.number > 1 ? exchange.sent.at(-1)! : null
        return (
          <div key={exchange.number} className="flex flex-col gap-2">
            {feedback && sentBubble(feedback, `feedback-${exchange.number}`)}
            <div className="mr-6 flex flex-col gap-1.5 rounded-lg rounded-tl-sm border px-2.5 py-1.5">
              {text && (
                <Collapsible key={String(showThinking)} defaultOpen={showThinking}>
                  <CollapsibleTrigger className="group flex cursor-pointer items-center gap-1 text-[11px] font-medium text-muted-foreground">
                    <ChevronRight className="size-3 transition-transform group-data-[panel-open]:rotate-90" />
                    <Brain className="size-3" /> {kind}
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="mt-1 max-h-56 overflow-y-auto border-l-2 pl-2 text-[13px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
                      {text}
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              )}
              <div className="flex flex-wrap items-center gap-1.5">
                <ResultBadge attempt={exchange.attempt} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// --- The panel -------------------------------------------------------------------------------------------------------

const VARIANTS = [
  { key: 'A', name: 'Stacked sections' },
  { key: 'B', name: 'Tabs' },
  { key: 'C', name: 'Turn as a chat' },
] as const

export function TurnPanelPrototype({ game, ply, live }: { game: GameState; ply: number; live: boolean }) {
  const variant = useVariant(VARIANTS.map((v) => v.key))
  const turn = turnShown(game, ply, live)
  const key = turn ? `${turn.color}-${turn.ply}-${turn.attempts.length}` : 'none'
  return (
    <>
      <Card role="region" aria-label="Turn" className="text-[15px]">
        <CardHeader className="flex flex-wrap items-center gap-2">
          <CardTitle className="font-semibold">Turn</CardTitle>
          {turn && (
            <Badge variant="secondary" className="h-auto max-w-full py-1 whitespace-normal">
              {heading(game, turn)}
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          {!turn ? (
            <p className="text-sm text-muted-foreground">
              {faceoff(game) ? 'No LLM has moved yet.' : 'The LLM has not moved yet.'}
            </p>
          ) : variant === 'A' ? (
            <VariantA key={key} game={game} turn={turn} />
          ) : variant === 'B' ? (
            <VariantB key={key} game={game} turn={turn} />
          ) : (
            <VariantC key={key} game={game} turn={turn} />
          )}
        </CardContent>
      </Card>
      <PrototypeSwitcher variants={VARIANTS} current={variant} />
    </>
  )
}
