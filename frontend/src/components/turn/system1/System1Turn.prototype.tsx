// PROTOTYPE, throwaway: what does a System 1 model's Turn look like in the Turn panel? (ticket 10 of #124, ADR 0012)
// Open /?prototype=system1-turn (scripts/dev.sh, then http://localhost:5173/?prototype=system1-turn). Switch variants
// with [ and ] or the bar; step through the plies with , and . or the buttons. Layout and behaviour only: the design
// language is being reworked separately. The game is FAKE (demo.prototype.json): d3-nano vs d1-2B, made-up
// probabilities; ply 6 (…h6) is a move drawn below the model's top choice.
//   A: a Choice tab next to a Prompt tab: one sentence, then every legal move ranked with a bar, the played one marked.
//   B: on the board: the played move as an arrow, the next choices as dashed arrows; the panel only sums it up.
//   C: as the model saw it: the options in the order sent, with their codes, sortable by probability.
//   D: one strip: the whole distribution as a single bar, each move a segment; hovering one draws it on the board.
// Review 1: in the game page's own layout, the Turn panel under the Game card (bottom left), in its own tab format,
// the request in the Prompt tab; by default the top 5 moves and the played one, the rest on asking.
//   E: the Turn panel's tabs: Choice (top 5 + played, then all), Prompt (question, state, options as sent), Answer.
//   F: E with D's strip over the Choice list; hovering a move or a segment draws it on the board.
import { Brain, CornerDownLeft, MessageSquareText } from 'lucide-react'
import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { PrototypeSwitcher, useVariant } from '@/components/prototype-switcher/PrototypeSwitcher'
import { Board } from '@/components/board/Board'
import { GameLayout } from '@/components/game-layout/GameLayout'
import { mono } from '@/components/turn/styles'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import demo from './demo.prototype.json'

export const system1TurnActive = new URLSearchParams(window.location.search).get('prototype') === 'system1-turn'

type Option = { san: string; uci: string; probability: number }
type Turn = (typeof demo.turns)[number]
type Arrow = readonly [string, string]
type VariantProps = { turn: Turn; onArrows: (arrows: { played?: Arrow[]; ghost?: Arrow[] }) => void }

const VARIANTS = [
  { key: 'E', name: 'Turn panel tabs, top 5' },
  { key: 'F', name: 'Turn panel tabs, top 5 + strip' },
  { key: 'A', name: 'Choice tab, ranked bars' },
  { key: 'B', name: 'On the board' },
  { key: 'C', name: 'As the model saw it' },
  { key: 'D', name: 'One strip' },
] as const

const pct = (p: number) => (p >= 0.995 ? '>99%' : p < 0.005 ? '<1%' : `${Math.round(p * 100)}%`)
const ranked = (turn: Turn): Option[] => [...turn.options].sort((a, b) => b.probability - a.probability)
const rankOf = (turn: Turn) => ranked(turn).findIndex((o) => o.san === turn.played) + 1
const playedOption = (turn: Turn) => turn.options.find((o) => o.san === turn.played)!
const arrow = (uci: string): Arrow => [uci.slice(0, 2), uci.slice(2, 4)]
const ordinal = (n: number) => (n === 1 ? 'top' : `${n}${n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'}`)
const moveName = (turn: Turn) => `${Math.ceil(turn.ply / 2)}${turn.color === 'white' ? '.' : '…'} ${turn.played}`
/** The option codes the request used: A…Z, then AA, AB, … */
const code = (i: number) => (i < 26 ? String.fromCharCode(65 + i) : String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26)))
const quiet = 'text-sm text-muted-foreground'

/** The one sentence every variant can lead with. */
function summary(turn: Turn): string {
  const rank = rankOf(turn)
  const p = pct(playedOption(turn).probability)
  if (rank === 1) return `Played ${turn.played}, its top choice at ${p}.`
  return `Played ${turn.played}, its ${ordinal(rank)} choice at ${p}; it liked ${ranked(turn)[0].san} best (${pct(ranked(turn)[0].probability)}).`
}

function Shell({ turn, children }: { turn: Turn; children: ReactNode }) {
  const side = demo[turn.color as 'white' | 'black']
  return (
    <Card role="region" aria-label="Turn" className="text-[15px]">
      <CardHeader className="flex flex-wrap items-center gap-2">
        <CardTitle className="font-semibold">Turn</CardTitle>
        <Badge variant="secondary">{moveName(turn)}</Badge>
        <span className={quiet}>
          {side.model} · System 1 · T {side.temperature} · {turn.time_s}s
        </span>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function PromptText({ turn, codes = false }: { turn: Turn; codes?: boolean }) {
  return (
    <div className="max-h-80 space-y-3 overflow-y-auto font-mono text-xs whitespace-pre-wrap">
      <div>
        <div className={quiet}>Question</div>
        {turn.question}
      </div>
      <div>
        <div className={quiet}>State</div>
        {turn.state}
      </div>
      {codes && (
        <div>
          <div className={quiet}>Options ({turn.options.length}, in the order sent)</div>
          {turn.options.map((o, i) => `${code(i)}: ${o.san}`).join('\n')}
        </div>
      )}
    </div>
  )
}

// A ---------------------------------------------------------------------------------------------------------------
function VariantA({ turn, onArrows }: VariantProps) {
  const [all, setAll] = useState(false)
  useEffect(() => onArrows({}), [turn, onArrows])
  const list = ranked(turn)
  const shown = all ? list : list.slice(0, 5)
  const max = list[0].probability
  return (
    <Shell turn={turn}>
      <Tabs defaultValue="choice">
        <TabsList>
          <TabsTrigger value="choice">Choice</TabsTrigger>
          <TabsTrigger value="prompt">Prompt</TabsTrigger>
        </TabsList>
        <TabsContent value="choice" className="space-y-2">
          <p>{summary(turn)}</p>
          <ol className="max-h-80 space-y-0.5 overflow-y-auto">
            {shown.map((o, i) => (
              <li key={o.san} className={`flex items-center gap-2 rounded px-1 ${o.san === turn.played ? 'bg-accent font-semibold' : ''}`}>
                <span className="w-5 text-right text-xs text-muted-foreground">{i + 1}</span>
                <span className="w-12 font-mono">{o.san}</span>
                <span className="h-2 flex-1 rounded bg-muted">
                  <span className="block h-2 rounded bg-foreground/60" style={{ width: `${(o.probability / max) * 100}%` }} />
                </span>
                <span className="w-10 text-right font-mono text-xs">{pct(o.probability)}</span>
                {o.san === turn.played && <span className="text-xs">played</span>}
              </li>
            ))}
          </ol>
          {list.length > 5 && (
            <Button variant="ghost" size="sm" onClick={() => setAll(!all)}>
              {all ? 'Top 5 only' : `All ${list.length} legal moves`}
            </Button>
          )}
        </TabsContent>
        <TabsContent value="prompt">
          <PromptText turn={turn} />
        </TabsContent>
      </Tabs>
    </Shell>
  )
}

// B ---------------------------------------------------------------------------------------------------------------
function VariantB({ turn, onArrows }: VariantProps) {
  const list = ranked(turn)
  const alternatives = list.filter((o) => o.san !== turn.played).slice(0, 3)
  useEffect(
    () => onArrows({ played: [arrow(turn.played_uci)], ghost: alternatives.map((o) => arrow(o.uci)) }),
    [turn, onArrows], // eslint-disable-line react-hooks/exhaustive-deps
  )
  const top = list[0].probability
  return (
    <Shell turn={turn}>
      <div className="space-y-3">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-2xl font-semibold">{turn.played}</span>
          <span>{pct(playedOption(turn).probability)}</span>
          <span className={quiet}>{rankOf(turn) === 1 ? 'top choice' : `${ordinal(rankOf(turn))} choice`}</span>
        </div>
        <p className={quiet}>
          On the board: the move played, and dashed, the next three it considered.{' '}
          {top >= 0.5 ? 'It was sure.' : top >= 0.25 ? 'It leaned one way.' : 'It was spread thin.'}
        </p>
        <div className="flex flex-wrap gap-1">
          {alternatives.map((o) => (
            <Badge key={o.san} variant="outline" className="font-mono">
              {o.san} {pct(o.probability)}
            </Badge>
          ))}
          <span className={quiet}>+{turn.options.length - 1 - alternatives.length} more</span>
        </div>
        <details>
          <summary className={`${quiet} cursor-pointer`}>Prompt</summary>
          <PromptText turn={turn} />
        </details>
      </div>
    </Shell>
  )
}

// C ---------------------------------------------------------------------------------------------------------------
function VariantC({ turn, onArrows }: VariantProps) {
  const [byProbability, setByProbability] = useState(false)
  useEffect(() => onArrows({}), [turn, onArrows])
  const rows = turn.options.map((o, i) => ({ ...o, code: code(i), position: i + 1 }))
  const shown = byProbability ? [...rows].sort((a, b) => b.probability - a.probability) : rows
  return (
    <Shell turn={turn}>
      <div className="space-y-2">
        <p>{summary(turn)}</p>
        <div className="flex items-center gap-2 text-sm">
          <span className={quiet}>Order:</span>
          <Button size="sm" variant={byProbability ? 'ghost' : 'secondary'} onClick={() => setByProbability(false)}>
            As sent
          </Button>
          <Button size="sm" variant={byProbability ? 'secondary' : 'ghost'} onClick={() => setByProbability(true)}>
            By probability
          </Button>
        </div>
        <table className="w-full font-mono text-xs">
          <thead className="text-muted-foreground">
            <tr>
              <th className="text-left">#</th>
              <th className="text-left">Code</th>
              <th className="text-left">Move</th>
              <th className="text-right">Probability</th>
            </tr>
          </thead>
        </table>
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full font-mono text-xs">
            <tbody>
              {shown.map((o) => (
                <tr key={o.san} className={o.san === turn.played ? 'bg-accent font-semibold' : ''}>
                  <td className="w-6 text-muted-foreground">{o.position}</td>
                  <td className="w-10">{o.code}</td>
                  <td>
                    {o.san} {o.san === turn.played && '← played'}
                  </td>
                  <td className="text-right">{pct(o.probability)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={quiet}>Shown in position {rows.find((o) => o.san === turn.played)!.position} of {rows.length}. The order is random each turn; it changes these models' answers.</p>
        <details>
          <summary className={`${quiet} cursor-pointer`}>Request as sent</summary>
          <PromptText turn={turn} codes />
        </details>
      </div>
    </Shell>
  )
}

// D ---------------------------------------------------------------------------------------------------------------
function VariantD({ turn, onArrows }: VariantProps) {
  const [hovered, setHovered] = useState<Option | null>(null)
  useEffect(
    () => onArrows({ played: [arrow(turn.played_uci)], ghost: hovered && hovered.san !== turn.played ? [arrow(hovered.uci)] : [] }),
    [turn, hovered, onArrows],
  )
  useEffect(() => setHovered(null), [turn])
  const list = ranked(turn)
  const labelled = list.filter((o) => o.probability >= 0.06)
  const focus = hovered ?? playedOption(turn)
  return (
    <Shell turn={turn}>
      <div className="space-y-3">
        <p>{summary(turn)}</p>
        <div className="flex h-8 w-full overflow-hidden rounded border" onMouseLeave={() => setHovered(null)}>
          {list.map((o, i) => (
            <span
              key={o.san}
              onMouseEnter={() => setHovered(o)}
              title={`${o.san} ${pct(o.probability)}`}
              className={`flex items-center justify-center border-r font-mono text-[10px] last:border-r-0 ${
                o.san === turn.played ? 'bg-foreground text-background' : i % 2 ? 'bg-muted' : 'bg-muted/60'
              } ${hovered?.san === o.san ? 'ring-2 ring-inset ring-ring' : ''}`}
              style={{ width: `${o.probability * 100}%` }}>
              {o.probability >= 0.06 ? o.san : ''}
            </span>
          ))}
        </div>
        <p className="font-mono text-sm">
          {focus.san} {pct(focus.probability)} · {ordinal(list.indexOf(focus) + 1)} of {list.length}
          {focus.san === turn.played ? ' · played' : ' · not played'}
        </p>
        <p className={quiet}>
          Labelled: {labelled.length} moves above 6%, {pct(labelled.reduce((s, o) => s + o.probability, 0))} together; the other {list.length - labelled.length} share the rest. Hover a segment to see it on the board.
        </p>
        <details>
          <summary className={`${quiet} cursor-pointer`}>Prompt</summary>
          <PromptText turn={turn} />
        </details>
      </div>
    </Shell>
  )
}


// E, F ------------------------------------------------------------------------------------------------------------
// The Turn panel's own tab format (TurnPanel.tsx): the decision slot becomes Choice, then Prompt and Answer.
const trigger = 'gap-1 px-1 @max-[17rem]:text-xs @max-[17rem]:[&_svg]:hidden'
const pane = 'max-h-80 overflow-y-auto'
const MEANINGS = {
  choice: 'How likely the model thought each legal move was, and the one drawn from them.',
  prompt: 'Exactly what was sent to the model: the question, the state, and the options in the order sent.',
  answer: "The model's raw answer: a probability for each option's code.",
}

function MoveRow({ o, rank, turn, max, onHover }: { o: Option; rank: number; turn: Turn; max: number; onHover?: (o: Option | null) => void }) {
  const played = o.san === turn.played
  return (
    <li
      className={`flex items-center gap-2 rounded px-1 ${played ? 'bg-accent font-semibold' : ''}`}
      onMouseEnter={() => onHover?.(o)}
      onMouseLeave={() => onHover?.(null)}>
      <span className="w-5 text-right text-xs text-muted-foreground tabular-nums">{rank}</span>
      <span className="w-12 font-mono">{o.san}</span>
      <span className="h-2 flex-1 rounded bg-muted">
        <span className="block h-2 rounded bg-foreground/60" style={{ width: `${(o.probability / max) * 100}%` }} />
      </span>
      <span className="w-10 text-right font-mono text-xs tabular-nums">{pct(o.probability)}</span>
      <span className="w-10 text-xs">{played ? 'played' : ''}</span>
    </li>
  )
}

function Strip({ turn, onHover, hovered }: { turn: Turn; onHover: (o: Option | null) => void; hovered: Option | null }) {
  const list = ranked(turn)
  return (
    <div className="flex h-6 w-full overflow-hidden rounded border" onMouseLeave={() => onHover(null)}>
      {list.map((o, i) => (
        <span
          key={o.san}
          onMouseEnter={() => onHover(o)}
          title={`${o.san} ${pct(o.probability)}`}
          className={`flex items-center justify-center border-r font-mono text-[10px] last:border-r-0 ${
            o.san === turn.played ? 'bg-foreground text-background' : i % 2 ? 'bg-muted' : 'bg-muted/60'
          } ${hovered?.san === o.san ? 'ring-2 ring-inset ring-ring' : ''}`}
          style={{ width: `${o.probability * 100}%` }}>
          {o.probability >= 0.08 ? o.san : ''}
        </span>
      ))}
    </div>
  )
}

function TabbedTurn({ turn, onArrows, strip }: VariantProps & { strip: boolean }) {
  const [all, setAll] = useState(false)
  const [hovered, setHovered] = useState<Option | null>(null)
  useEffect(() => {
    setAll(false)
    setHovered(null)
  }, [turn])
  useEffect(
    () =>
      onArrows(
        strip
          ? { played: [arrow(turn.played_uci)], ghost: hovered && hovered.san !== turn.played ? [arrow(hovered.uci)] : [] }
          : {},
      ),
    [turn, hovered, strip, onArrows],
  )
  const list = ranked(turn)
  const max = list[0].probability
  const rank = rankOf(turn)
  const top = list.slice(0, 5)
  const tabs = [
    { value: 'choice', name: 'Choice', icon: <Brain aria-hidden="true" /> },
    { value: 'prompt', name: 'Prompt', icon: <MessageSquareText aria-hidden="true" /> },
    { value: 'answer', name: 'Answer', icon: <CornerDownLeft aria-hidden="true" /> },
  ] as const
  const answer = {
    choice: code(turn.options.findIndex((o) => o.san === turn.played)),
    probabilities: Object.fromEntries(turn.options.map((o, i) => [code(i), o.probability])),
  }
  return (
    <Shell turn={turn}>
      <Tabs className="@container" defaultValue="choice">
        <TabsList variant="line" className="w-full">
          {tabs.map(({ value, name, icon }) => (
            <Tooltip key={value}>
              <TooltipTrigger render={<TabsTrigger className={trigger} value={value} aria-description={MEANINGS[value]} />}>
                {icon}
                {name}
              </TooltipTrigger>
              <TooltipContent side="bottom">{MEANINGS[value]}</TooltipContent>
            </Tooltip>
          ))}
        </TabsList>
        <TabsContent className={`${pane} space-y-2`} value="choice">
          <p className="leading-relaxed">{summary(turn)}</p>
          {strip && <Strip turn={turn} onHover={setHovered} hovered={hovered} />}
          <ol className="space-y-0.5">
            {(all ? list : top).map((o, i) => (
              <MoveRow key={o.san} o={o} rank={i + 1} turn={turn} max={max} onHover={strip ? setHovered : undefined} />
            ))}
            {!all && rank > 5 && (
              <>
                <li className="pl-7 text-xs text-muted-foreground">…</li>
                <MoveRow o={playedOption(turn)} rank={rank} turn={turn} max={max} onHover={strip ? setHovered : undefined} />
              </>
            )}
          </ol>
          <Button variant="ghost" size="sm" onClick={() => setAll(!all)}>
            {all ? 'Top 5 and the played move' : `All ${list.length} legal moves`}
          </Button>
        </TabsContent>
        <TabsContent className={`${pane} space-y-3`} value="prompt">
          <div>
            <div className={quiet}>Question</div>
            <p className={mono}>{turn.question}</p>
          </div>
          <div>
            <div className={quiet}>State</div>
            <p className={mono}>{turn.state}</p>
          </div>
          <div>
            <div className={quiet}>Options, in the order sent ({turn.options.length})</div>
            <p className={mono}>{turn.options.map((o, i) => `${code(i)}: ${o.san}`).join('\n')}</p>
          </div>
        </TabsContent>
        <TabsContent className={pane} value="answer">
          <p className={`${mono} w-full rounded-md bg-muted px-2 py-1.5`}>{JSON.stringify(answer, null, 2)}</p>
        </TabsContent>
      </Tabs>
    </Shell>
  )
}

const VariantE = (props: VariantProps) => <TabbedTurn {...props} strip={false} />
const VariantF = (props: VariantProps) => <TabbedTurn {...props} strip />

const RENDER = { E: VariantE, F: VariantF, A: VariantA, B: VariantB, C: VariantC, D: VariantD } as const

/** A stand-in for the Game card above the Turn panel, so the panel sits where it does on the game page. */
function GameCardStub() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-semibold">Game</CardTitle>
      </CardHeader>
      <CardContent className={`${quiet} space-y-1`}>
        <p>LLM faceoff · playing</p>
        <p>
          White {demo.white.model} · System 1 · T {demo.white.temperature}
        </p>
        <p>
          Black {demo.black.model} · System 1 · T {demo.black.temperature}
        </p>
      </CardContent>
    </Card>
  )
}

export function System1TurnPrototype() {
  const variant = useVariant(VARIANTS.map((v) => v.key)) as keyof typeof RENDER
  const [index, setIndex] = useState(5) // ply 6, the move drawn below the top choice
  const [arrows, setArrows] = useState<{ played?: Arrow[]; ghost?: Arrow[] }>({})
  const turn = demo.turns[index]
  const step = (by: number) => setIndex((i) => Math.min(demo.turns.length - 1, Math.max(0, i + by)))
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === ',') step(-1)
      if (event.key === '.') step(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  const Variant = RENDER[variant]
  const moves = (
    <Card>
      <CardHeader>
        <CardTitle className="font-semibold">Moves</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <ol className="grid grid-cols-[2rem_1fr_1fr] gap-x-2 font-mono text-sm">
          {demo.turns.map((t, i) => (
            <Fragment key={t.ply}>
              {t.color === 'white' && <span className="text-muted-foreground">{Math.ceil(t.ply / 2)}.</span>}
              <button
                type="button"
                onClick={() => setIndex(i)}
                className={`rounded px-1 text-left ${i === index ? 'bg-accent font-semibold' : ''}`}>
                {t.played}
              </button>
            </Fragment>
          ))}
        </ol>
        <p className={quiet}>, and . step · FAKE demo game</p>
      </CardContent>
    </Card>
  )
  return (
    <>
      <GameLayout
        game={
          <>
            <GameCardStub />
            <Variant turn={turn} onArrows={setArrows} />
          </>
        }
        board={
          <Board
            fen={turn.fen_after}
            orientation="white"
            lastMove={turn.played_uci}
            arrows={arrows.played ?? []}
            ghostArrows={arrows.ghost ?? []}
          />
        }
        moves={moves}
      />
      <PrototypeSwitcher variants={VARIANTS} current={variant} />
    </>
  )
}
