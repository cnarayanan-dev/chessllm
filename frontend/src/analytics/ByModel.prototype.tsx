// PROTOTYPE, throwaway: what should a model-first leaderboard look like, each model's overall number being its Rating
// under the Reference configuration, with a drill-down showing how far each other Player configuration moves it?
// Five variants, switched with ?variant=A|B|C|D|E from the bar at the bottom (or [ and ]). Open
// /analytics?prototype=by-model. Stub data only: every number is invented. Layout and behaviour only: the design
// language is being reworked separately. Never ship this: fold the winner into the real page.
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { PrototypeSwitcher, useVariant } from '@/components/prototype-switcher/PrototypeSwitcher'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------------------------------------------- data

/** A Rating: an estimate with its 95% interval, or only an upper bound when every anchored game was lost. */
type Rating = { estimate: number | null; low: number | null; high: number }

/** One setting changed from the Reference configuration. */
type Setting = { key: string; label: string; group: string }

const SETTINGS: Setting[] = [
  { key: 'thinking', label: 'Thinking on', group: 'Thinking' },
  { key: 'listed', label: 'Listed', group: 'LLM constraints' },
  { key: 'blind_enforced', label: 'Blind enforced', group: 'LLM constraints' },
  { key: 'listed_enforced', label: 'Listed enforced', group: 'LLM constraints' },
  { key: 'attempts1', label: '1 attempt', group: 'Retries' },
  { key: 'hinted', label: 'Hinted feedback', group: 'Retries' },
  { key: 'chat', label: 'Chat with position', group: 'Turn memory' },
  { key: 'tools', label: 'Tools', group: 'Tools' },
]

/** A Player configuration other than the reference: what differs from it, its Rating and its games. */
type Variation = { differs: string[]; rating: Rating; games: number }

type Model = {
  model: string
  canThink: boolean
  reference: Rating | null // null: no games under the Reference configuration yet
  games: number
  wdl: [number, number, number]
  forfeits: number
  variations: Variation[]
  chaosGames: number // under Chaos rules: counted apart and unrated, so never a Rating difference
}

const r = (estimate: number, half: number): Rating => ({ estimate, low: estimate - half, high: estimate + half })
const below = (high: number): Rating => ({ estimate: null, low: null, high })

const MODELS: Model[] = [
  {
    model: 'gemma4-26b',
    canThink: true,
    reference: r(540, 130),
    games: 34,
    wdl: [15, 4, 15],
    forfeits: 6,
    chaosGames: 8,
    variations: [
      { differs: ['thinking'], rating: r(760, 170), games: 20 },
      { differs: ['listed'], rating: r(610, 150), games: 22 },
      { differs: ['listed_enforced'], rating: r(690, 140), games: 30 },
      { differs: ['attempts1'], rating: r(310, 160), games: 20 },
      { differs: ['hinted'], rating: r(580, 150), games: 20 },
      { differs: ['tools'], rating: r(600, 190), games: 12 },
      { differs: ['thinking', 'listed_enforced'], rating: r(880, 180), games: 16 },
    ],
  },
  {
    model: 'qwen3.8',
    canThink: true,
    reference: r(470, 140),
    games: 30,
    wdl: [12, 3, 15],
    forfeits: 9,
    chaosGames: 0,
    variations: [
      { differs: ['thinking'], rating: r(720, 160), games: 24 },
      { differs: ['listed_enforced'], rating: r(560, 140), games: 30 },
      { differs: ['blind_enforced'], rating: r(500, 160), games: 18 },
      { differs: ['chat'], rating: r(390, 200), games: 10 },
      { differs: ['thinking', 'listed'], rating: r(790, 190), games: 12 },
    ],
  },
  {
    model: 'gemma3-12b',
    canThink: false,
    reference: r(260, 150),
    games: 30,
    wdl: [9, 2, 19],
    forfeits: 14,
    chaosGames: 14,
    variations: [
      { differs: ['listed'], rating: r(330, 160), games: 20 },
      { differs: ['listed_enforced'], rating: r(410, 140), games: 30 },
      { differs: ['attempts1'], rating: below(60), games: 20 },
      { differs: ['hinted'], rating: r(340, 170), games: 20 },
    ],
  },
  {
    model: 'qwen3.5-9b',
    canThink: true,
    reference: r(120, 170),
    games: 30,
    wdl: [7, 1, 22],
    forfeits: 18,
    chaosGames: 6,
    variations: [
      { differs: ['thinking'], rating: r(380, 180), games: 18 },
      { differs: ['listed_enforced'], rating: r(330, 150), games: 30 },
      { differs: ['thinking', 'listed_enforced'], rating: r(520, 190), games: 10 },
    ],
  },
  {
    model: 'llama3-8b',
    canThink: false,
    reference: below(-40),
    games: 30,
    wdl: [0, 2, 28],
    forfeits: 25,
    chaosGames: 26,
    variations: [
      { differs: ['listed'], rating: r(-20, 220), games: 20 },
      { differs: ['listed_enforced'], rating: r(150, 160), games: 30 },
      { differs: ['hinted'], rating: below(10), games: 14 },
    ],
  },
  {
    model: 'gemma3-4b',
    canThink: false,
    reference: null,
    games: 0,
    wdl: [0, 0, 0],
    forfeits: 0,
    chaosGames: 4,
    variations: [{ differs: ['listed_enforced'], rating: r(90, 210), games: 8 }],
  },
]

const settingLabel = (key: string) => SETTINGS.find((setting) => setting.key === key)?.label ?? key
const single = (model: Model) => model.variations.filter((variation) => variation.differs.length === 1)
const combined = (model: Model) => model.variations.filter((variation) => variation.differs.length > 1)
const ranked = [...MODELS].sort((a, b) => sortValue(b.reference) - sortValue(a.reference))

function sortValue(rating: Rating | null): number {
  if (rating === null) return -Infinity
  return rating.estimate ?? rating.high - 1000
}

/** The difference from the reference, or null when either is only a bound or missing: no difference can be given. */
function delta(reference: Rating | null, rating: Rating): number | null {
  if (reference?.estimate == null || rating.estimate === null) return null
  return rating.estimate - reference.estimate
}

// ------------------------------------------------------------------------------------------------------------ pieces

function ratingText(rating: Rating | null): string {
  if (rating === null) return '—'
  return rating.estimate === null ? `< ${rating.high}` : String(rating.estimate)
}

function intervalText(rating: Rating | null): string {
  if (rating?.estimate == null || rating.low === null) return '—'
  return `${rating.low} to ${rating.high}`
}

function DeltaText({ value, className }: { value: number | null; className?: string }) {
  if (value === null) return <span className={cn('text-muted-foreground', className)}>no difference</span>
  return (
    <span
      className={cn(
        'font-semibold tabular-nums',
        value > 0 ? 'text-emerald-600' : value < 0 ? 'text-rose-600' : 'text-muted-foreground',
        className,
      )}
    >
      {value > 0 ? '+' : value < 0 ? '−' : '±'}
      {Math.abs(value)}
    </span>
  )
}

function SettingChip({ setting }: { setting: string }) {
  return (
    <Badge variant="secondary" className="font-normal text-muted-foreground">
      {settingLabel(setting)}
    </Badge>
  )
}

function Explain({ children, tip }: { children: ReactNode; tip: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger render={<span />} className="cursor-help underline decoration-dotted underline-offset-4">
        {children}
      </TooltipTrigger>
      <TooltipContent className="max-w-80">{tip}</TooltipContent>
    </Tooltip>
  )
}

const REFERENCE_TIP =
  'Thinking off, Free, Standard rules, 5 attempts with explained Retry feedback, fresh Turn memory, no Tools, the ' +
  'default Prompt template and the model’s own sampling.'

function ReferenceNote() {
  return (
    <p className="text-xs text-muted-foreground">
      A model’s number is its Rating under the <Explain tip={REFERENCE_TIP}>Reference configuration</Explain>. Every
      other configuration is shown by how far it moves that Rating. Chaos rules games are unrated, so they are counted
      but never move it. “No difference” when either Rating is only an upper bound.
    </p>
  )
}

/** A horizontal bar from the zero line: right and green when the setting helps, left and red when it hurts. */
function DeltaBar({ value, scale = 400 }: { value: number | null; scale?: number }) {
  if (value === null) return <div className="h-2" />
  const width = Math.min(50, (Math.abs(value) / scale) * 50)
  return (
    <div className="relative h-2 w-full">
      <div className="absolute inset-y-[-3px] left-1/2 w-px bg-border" />
      <div
        className={cn('absolute h-2 rounded-full', value >= 0 ? 'bg-emerald-500/70' : 'bg-rose-500/70')}
        style={value >= 0 ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }}
      />
    </div>
  )
}

// ---------------------------------------------------------------- variant A: a table of models, each row expanding

function VariantA() {
  const [open, setOpen] = useState<string | null>(ranked[0].model)
  return (
    <Card>
      <CardContent className="px-3">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8" />
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Rating</TableHead>
              <TableHead className="text-right">95% interval</TableHead>
              <TableHead className="text-right">Games</TableHead>
              <TableHead className="text-right">W · D · L</TableHead>
              <TableHead className="text-right">Forfeits</TableHead>
              <TableHead className="text-right">Other configurations</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ranked.map((model, index) => {
              const isOpen = open === model.model
              return [
                <TableRow
                  key={model.model}
                  className="cursor-pointer"
                  onClick={() => setOpen(isOpen ? null : model.model)}
                >
                  <TableCell className="text-muted-foreground">
                    {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                  </TableCell>
                  <TableCell>
                    <span className="mr-2 text-muted-foreground">{model.reference ? index + 1 : ''}</span>
                    <span className="font-semibold">{model.model}</span>
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">{ratingText(model.reference)}</TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">
                    {intervalText(model.reference)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{model.games}</TableCell>
                  <TableCell className="text-right tabular-nums">{model.wdl.join(' · ')}</TableCell>
                  <TableCell className="text-right tabular-nums">{model.forfeits}</TableCell>
                  <TableCell className="text-right tabular-nums">{model.variations.length}</TableCell>
                </TableRow>,
                isOpen && (
                  <TableRow key={`${model.model}-detail`} className="hover:bg-transparent">
                    <TableCell />
                    <TableCell colSpan={7} className="pb-5">
                      <ModelDetailA model={model} />
                    </TableCell>
                  </TableRow>
                ),
              ]
            })}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter>
        <ReferenceNote />
      </CardFooter>
    </Card>
  )
}

function ModelDetailA({ model }: { model: Model }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section>
        <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase">Effect of one setting</h3>
        {model.reference === null && (
          <p className="text-muted-foreground">No games under the Reference configuration yet, so no effects.</p>
        )}
        <div className="grid grid-cols-[10rem_1fr_6rem_3rem] items-center gap-x-3 gap-y-2">
          {single(model).map((variation) => (
            <Row key={variation.differs[0]}>
              <span>{settingLabel(variation.differs[0])}</span>
              <DeltaBar value={delta(model.reference, variation.rating)} />
              <DeltaText value={delta(model.reference, variation.rating)} className="text-right" />
              <span className="text-right text-xs text-muted-foreground tabular-nums">{variation.games} g</span>
            </Row>
          ))}
        </div>
        {!model.canThink && <p className="mt-2 text-xs text-muted-foreground">This model can’t think.</p>}
      </section>
      <section>
        <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase">Combinations</h3>
        {combined(model).length === 0 && <p className="text-muted-foreground">None played.</p>}
        {combined(model).map((variation) => (
          <div key={variation.differs.join()} className="mb-2 flex flex-wrap items-center gap-1.5">
            {variation.differs.map((setting) => (
              <SettingChip key={setting} setting={setting} />
            ))}
            <DeltaText value={delta(model.reference, variation.rating)} className="ml-auto" />
            <span className="w-24 text-right text-xs text-muted-foreground tabular-nums">
              {ratingText(variation.rating)} · {variation.games} g
            </span>
          </div>
        ))}
        {model.chaosGames > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            {model.chaosGames} games under Chaos rules, unrated.
          </p>
        )}
      </section>
    </div>
  )
}

const Row = ({ children }: { children: ReactNode }) => <>{children}</>

// ------------------------------------------------- variant B: a list of models beside one model's Rating on a scale

const AXIS = { min: -300, max: 1200 }
const at = (rating: number) => `${((rating - AXIS.min) / (AXIS.max - AXIS.min)) * 100}%`

function VariantB() {
  const [chosen, setChosen] = useState(ranked[0].model)
  const model = MODELS.find((candidate) => candidate.model === chosen)!
  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <Card>
        <CardContent className="px-2">
          {ranked.map((candidate, index) => (
            <button
              type="button"
              key={candidate.model}
              onClick={() => setChosen(candidate.model)}
              className={cn(
                'flex w-full cursor-pointer items-baseline gap-2 rounded-xl px-3 py-2 text-left hover:bg-muted',
                candidate.model === chosen && 'bg-muted',
              )}
            >
              <span className="w-4 text-muted-foreground">{candidate.reference ? index + 1 : ''}</span>
              <span className="font-semibold">{candidate.model}</span>
              <span className="ml-auto font-semibold tabular-nums">{ratingText(candidate.reference)}</span>
            </button>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <h2 className="text-xl font-semibold">{model.model}</h2>
            <span>
              Rating <b className="tabular-nums">{ratingText(model.reference)}</b>{' '}
              <span className="text-muted-foreground tabular-nums">({intervalText(model.reference)})</span>
            </span>
            <span className="text-muted-foreground tabular-nums">
              {model.games} games · {model.wdl.join(' · ')} · {model.forfeits} forfeits
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <Scale />
          <ScaleRow label="Reference configuration" rating={model.reference} reference strong />
          <h3 className="mt-4 mb-1 text-xs font-medium text-muted-foreground uppercase">One setting changed</h3>
          {single(model).map((variation) => (
            <ScaleRow
              key={variation.differs[0]}
              label={settingLabel(variation.differs[0])}
              rating={variation.rating}
              reference={model.reference}
              games={variation.games}
            />
          ))}
          <h3 className="mt-4 mb-1 text-xs font-medium text-muted-foreground uppercase">Several settings changed</h3>
          {combined(model).length === 0 && <p className="text-muted-foreground">None played.</p>}
          {combined(model).map((variation) => (
            <ScaleRow
              key={variation.differs.join()}
              label={variation.differs.map(settingLabel).join(' + ')}
              rating={variation.rating}
              reference={model.reference}
              games={variation.games}
            />
          ))}
        </CardContent>
        <CardFooter>
          <ReferenceNote />
        </CardFooter>
      </Card>
    </div>
  )
}

function Scale() {
  const ticks = [-300, 0, 300, 600, 900, 1200]
  return (
    <div className="grid grid-cols-[13rem_1fr_7rem] gap-3 text-xs text-muted-foreground">
      <span />
      <div className="relative h-4">
        {ticks.map((tick) => (
          <span key={tick} className="absolute -translate-x-1/2 tabular-nums" style={{ left: at(tick) }}>
            {tick}
          </span>
        ))}
      </div>
      <span />
    </div>
  )
}

/** One configuration on the shared Rating scale: its interval as a line, its estimate as a dot, the reference as a
 * dashed line through every row. An upper bound is an arrow pointing left from it. */
function ScaleRow(props: {
  label: string
  rating: Rating | null
  reference: Rating | null | true
  games?: number
  strong?: boolean
}) {
  const { label, rating, games, strong } = props
  const reference = props.reference === true ? rating : props.reference
  return (
    <div className="grid grid-cols-[13rem_1fr_7rem] items-center gap-3 py-1.5">
      <span className={cn(strong && 'font-semibold')}>
        {label} {games !== undefined && <span className="text-xs text-muted-foreground">· {games} g</span>}
      </span>
      <div className="relative h-5">
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
        {reference?.estimate != null && (
          <div
            className="absolute inset-y-[-6px] border-l border-dashed border-foreground/40"
            style={{ left: at(reference.estimate) }}
          />
        )}
        {rating?.estimate != null && rating.low !== null && (
          <>
            <div
              className={cn('absolute top-1/2 h-1 -translate-y-1/2 rounded-full', strong ? 'bg-sky-500/40' : 'bg-foreground/20')}
              style={{ left: at(rating.low), width: `calc(${at(rating.high)} - ${at(rating.low)})` }}
            />
            <div
              className={cn('absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full', strong ? 'bg-sky-600' : 'bg-foreground')}
              style={{ left: at(rating.estimate) }}
            />
          </>
        )}
        {rating !== null && rating.estimate === null && (
          <div
            className="absolute top-1/2 -translate-x-full -translate-y-1/2 text-xs text-rose-600"
            style={{ left: at(rating.high) }}
          >
            ◀ below {rating.high}
          </div>
        )}
      </div>
      <span className="text-right">
        {strong ? (
          <span className="text-muted-foreground tabular-nums">{ratingText(rating)}</span>
        ) : rating ? (
          <DeltaText value={delta(reference, rating)} />
        ) : null}
      </span>
    </div>
  )
}

// ----------------------------------------------------------- variant C: models against settings, a difference each

function VariantC() {
  const columns = SETTINGS.filter((setting) => MODELS.some((model) => single(model).some((v) => v.differs[0] === setting.key)))
  const cell = (model: Model, setting: string) => single(model).find((variation) => variation.differs[0] === setting)
  const average = (setting: string) => {
    const values = MODELS.map((model) => {
      const found = cell(model, setting)
      return found ? delta(model.reference, found.rating) : null
    }).filter((value): value is number => value !== null)
    return values.length ? { value: Math.round(values.reduce((a, b) => a + b, 0) / values.length), n: values.length } : null
  }
  return (
    <Card>
      <CardContent className="px-3">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Model</TableHead>
              <TableHead className="border-r text-right">Rating</TableHead>
              {columns.map((setting) => (
                <TableHead key={setting.key} className="text-center text-xs">
                  <div className="text-[10px] text-muted-foreground/70 uppercase">{setting.group}</div>
                  {setting.label}
                </TableHead>
              ))}
              <TableHead className="text-right text-xs">Combinations</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ranked.map((model) => (
              <TableRow key={model.model}>
                <TableCell className="font-semibold">{model.model}</TableCell>
                <TableCell className="border-r text-right font-semibold tabular-nums">
                  {ratingText(model.reference)}
                </TableCell>
                {columns.map((setting) => {
                  const found = cell(model, setting.key)
                  if (setting.key === 'thinking' && !model.canThink)
                    return (
                      <TableCell key={setting.key} className="text-center text-xs text-muted-foreground/60">
                        can’t think
                      </TableCell>
                    )
                  if (!found)
                    return (
                      <TableCell key={setting.key} className="text-center text-muted-foreground/40">
                        ·
                      </TableCell>
                    )
                  const value = delta(model.reference, found.rating)
                  return (
                    <TableCell key={setting.key} className="p-1 text-center">
                      <Tooltip>
                        <TooltipTrigger
                          render={<div />}
                          className="rounded-lg py-1.5"
                          style={{ background: heat(value) }}
                        >
                          <DeltaText value={value} className="text-foreground" />
                        </TooltipTrigger>
                        <TooltipContent>
                          {setting.label}: Rating {ratingText(found.rating)} ({intervalText(found.rating)}), {found.games}{' '}
                          games
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                  )
                })}
                <TableCell className="text-right text-xs text-muted-foreground">
                  {combined(model).length ? (
                    <Tooltip>
                      <TooltipTrigger render={<span />} className="cursor-help underline decoration-dotted">
                        {combined(model).length}
                      </TooltipTrigger>
                      <TooltipContent>
                        {combined(model).map((variation) => (
                          <div key={variation.differs.join()}>
                            {variation.differs.map(settingLabel).join(' + ')}: {ratingText(variation.rating)}
                          </div>
                        ))}
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    '—'
                  )}
                </TableCell>
              </TableRow>
            ))}
            <TableRow className="border-t-2 hover:bg-transparent">
              <TableCell className="text-muted-foreground">Across models</TableCell>
              <TableCell className="border-r" />
              {columns.map((setting) => {
                const found = average(setting.key)
                return (
                  <TableCell key={setting.key} className="text-center">
                    {found ? (
                      <>
                        <DeltaText value={found.value} />
                        <div className="text-[10px] text-muted-foreground">over {found.n}</div>
                      </>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                )
              })}
              <TableCell />
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter>
        <ReferenceNote />
      </CardFooter>
    </Card>
  )
}

function heat(value: number | null): string {
  if (value === null) return 'transparent'
  const strength = Math.min(1, Math.abs(value) / 300) * 35
  return `color-mix(in srgb, ${value >= 0 ? '#10b981' : '#f43f5e'} ${strength}%, transparent)`
}

// --------------------------------------- variant D: C's matrix with games and noise, a model's detail underneath

/** The 95% half-width of a difference of two Ratings, from each Rating's own interval (independent, so in quadrature). */
function deltaHalfWidth(reference: Rating | null, rating: Rating): number | null {
  if (reference?.estimate == null || reference.low === null || rating.estimate === null || rating.low === null)
    return null
  const a = (reference.high - reference.low) / 2
  const b = (rating.high - rating.low) / 2
  return Math.round(Math.sqrt(a * a + b * b) / 10) * 10
}

/** Invented W · D · L for a stub configuration, from its games and how far it is from the reference. */
function stubWdl(games: number, shift: number | null): [number, number, number] {
  const score = Math.min(0.95, Math.max(0.03, 0.45 + (shift ?? -300) / 900))
  const draws = Math.round(games * 0.08)
  const wins = Math.round((games - draws) * score)
  return [wins, draws, games - wins - draws]
}

function VariantD() {
  const [open, setOpen] = useState<string | null>(ranked[0].model)
  const columns = SETTINGS.filter((setting) =>
    MODELS.some((model) => single(model).some((v) => v.differs[0] === setting.key)),
  )
  const cell = (model: Model, setting: string) => single(model).find((variation) => variation.differs[0] === setting)
  return (
    <Card>
      <CardContent className="px-3">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-6" />
              <TableHead>Model</TableHead>
              <TableHead className="border-r text-right">Reference</TableHead>
              {columns.map((setting) => (
                <TableHead key={setting.key} className="text-center text-xs">
                  <div className="text-[10px] text-muted-foreground/70 uppercase">{setting.group}</div>
                  {setting.label}
                </TableHead>
              ))}
              <TableHead className="text-right text-xs">Combinations</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ranked.map((model) => {
              const isOpen = open === model.model
              return [
                <TableRow
                  key={model.model}
                  className={cn('cursor-pointer', isOpen && 'bg-muted/50')}
                  onClick={() => setOpen(isOpen ? null : model.model)}
                >
                  <TableCell className="text-muted-foreground">
                    {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                  </TableCell>
                  <TableCell className="font-semibold">{model.model}</TableCell>
                  <TableCell className="border-r text-right tabular-nums">
                    <div className="font-semibold">{ratingText(model.reference)}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {model.games ? `${model.games} g · ${intervalText(model.reference)}` : 'no games'}
                    </div>
                  </TableCell>
                  {columns.map((setting) => {
                    const found = cell(model, setting.key)
                    if (setting.key === 'thinking' && !model.canThink)
                      return (
                        <TableCell key={setting.key} className="text-center text-xs text-muted-foreground/60">
                          can’t think
                        </TableCell>
                      )
                    if (!found)
                      return (
                        <TableCell key={setting.key} className="text-center text-muted-foreground/40">
                          ·
                        </TableCell>
                      )
                    const value = delta(model.reference, found.rating)
                    const noise = deltaHalfWidth(model.reference, found.rating)
                    const real = value !== null && noise !== null && Math.abs(value) > noise
                    return (
                      <TableCell key={setting.key} className="p-1 text-center">
                        <Tooltip>
                          <TooltipTrigger
                            render={<div />}
                            className="rounded-lg py-1"
                            style={{ background: real ? heat(value) : 'transparent' }}
                          >
                            {value === null ? (
                              <span className="text-xs text-muted-foreground">bound only</span>
                            ) : (
                              <DeltaText value={value} className={real ? 'text-foreground' : 'text-muted-foreground font-normal'} />
                            )}
                            <div className="text-[10px] text-muted-foreground tabular-nums">
                              {found.games} g{noise !== null && ` · ±${noise}`}
                            </div>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-72">
                            {setting.label}: Rating {ratingText(found.rating)} ({intervalText(found.rating)}) from{' '}
                            {found.games} games, against the reference’s {ratingText(model.reference)} from {model.games}.
                            {value !== null && noise !== null &&
                              (real
                                ? ` The difference is larger than its ±${noise}: a real effect.`
                                : ` The difference is within its ±${noise}: could be noise.`)}
                            {value === null && ' One of the two Ratings is only an upper bound, so there is no difference.'}
                          </TooltipContent>
                        </Tooltip>
                      </TableCell>
                    )
                  })}
                  <TableCell className="text-right text-xs text-muted-foreground">
                    {combined(model).length || '—'}
                  </TableCell>
                </TableRow>,
                isOpen && (
                  <TableRow key={`${model.model}-detail`} className="hover:bg-transparent">
                    <TableCell colSpan={columns.length + 4} className="bg-muted/30 p-4 whitespace-normal">
                      <ModelDetailD model={model} />
                    </TableCell>
                  </TableRow>
                ),
              ]
            })}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          Each cell: the model’s Rating with that one setting changed, minus its Rating under the{' '}
          <Explain tip={REFERENCE_TIP}>Reference configuration</Explain>, with that configuration’s games and the
          difference’s 95% ±. Coloured only when the difference is larger than its ±. Click a model for every one of its
          configurations.
        </p>
      </CardFooter>
    </Card>
  )
}

function ModelDetailD({ model }: { model: Model }) {
  const rows: { label: ReactNode; rating: Rating | null; games: number; wdl: [number, number, number]; reference: boolean }[] = [
    { label: 'Reference configuration', rating: model.reference, games: model.games, wdl: model.wdl, reference: true },
    ...[...single(model), ...combined(model)].map((variation) => ({
      label: (
        <span className="flex flex-wrap gap-1">
          {variation.differs.map((setting) => (
            <SettingChip key={setting} setting={setting} />
          ))}
        </span>
      ),
      rating: variation.rating,
      games: variation.games,
      wdl: stubWdl(variation.games, delta(model.reference, variation.rating)),
      reference: false,
    })),
  ]
  return (
    <div>
      <div className="grid grid-cols-[15rem_1fr_3.5rem_6.5rem_5rem_5rem_6rem] items-center gap-x-3 text-xs text-muted-foreground">
        <span>Configuration</span>
        <div className="relative h-4">
          {[-300, 0, 300, 600, 900, 1200].map((tick) => (
            <span key={tick} className="absolute -translate-x-1/2 tabular-nums" style={{ left: at(tick) }}>
              {tick}
            </span>
          ))}
        </div>
        <span className="text-right">Games</span>
        <span className="text-right">W · D · L</span>
        <span className="text-right">Rating</span>
        <span className="text-right">Difference</span>
        <span className="text-right">±</span>
      </div>
      {rows.map((row, index) => {
        const value = row.rating && !row.reference ? delta(model.reference, row.rating) : null
        const noise = row.rating && !row.reference ? deltaHalfWidth(model.reference, row.rating) : null
        return (
          <div
            key={index}
            className={cn(
              'grid grid-cols-[15rem_1fr_3.5rem_6.5rem_5rem_5rem_6rem] items-center gap-x-3 border-b border-border/60 py-1.5',
              row.reference && 'font-semibold',
            )}
          >
            <span>{row.label}</span>
            <ScaleBar rating={row.rating} reference={model.reference} strong={row.reference} />
            <span className="text-right tabular-nums">{row.games}</span>
            <span className="text-right tabular-nums">{row.wdl.join(' · ')}</span>
            <span className="text-right tabular-nums">{ratingText(row.rating)}</span>
            <span className="text-right">
              {row.reference ? '' : <DeltaText value={value} />}
            </span>
            <span className="text-right text-xs text-muted-foreground tabular-nums">
              {row.reference ? intervalText(row.rating) : noise !== null ? `±${noise}${value !== null && Math.abs(value) <= noise ? ' · noise' : ''}` : '—'}
            </span>
          </div>
        )
      })}
      {model.chaosGames > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">{model.chaosGames} games under Chaos rules, counted apart and unrated.</p>
      )}
    </div>
  )
}

/** B's scale row without its label and number: the interval, the estimate, the reference as a dashed line. */
function ScaleBar({ rating, reference, strong }: { rating: Rating | null; reference: Rating | null; strong?: boolean }) {
  return (
    <div className="relative h-5">
      <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
      {reference?.estimate != null && (
        <div className="absolute inset-y-[-6px] border-l border-dashed border-foreground/40" style={{ left: at(reference.estimate) }} />
      )}
      {rating?.estimate != null && rating.low !== null && (
        <>
          <div
            className={cn('absolute top-1/2 h-1 -translate-y-1/2 rounded-full', strong ? 'bg-sky-500/40' : 'bg-foreground/20')}
            style={{ left: at(rating.low), width: `calc(${at(rating.high)} - ${at(rating.low)})` }}
          />
          <div
            className={cn('absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full', strong ? 'bg-sky-600' : 'bg-foreground')}
            style={{ left: at(rating.estimate) }}
          />
        </>
      )}
      {rating !== null && rating.estimate === null && (
        <div className="absolute top-1/2 -translate-x-full -translate-y-1/2 text-xs text-rose-600" style={{ left: at(rating.high) }}>
          ◀ below {rating.high}
        </div>
      )}
    </div>
  )
}

// ------------------------------------------- variant E: two views behind a switch, Ranking and Setting effects

function RankingView() {
  return (
    <Card>
      <CardContent className="px-3">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8">#</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Rating</TableHead>
              <TableHead className="text-right">95% interval</TableHead>
              <TableHead className="text-right">Games</TableHead>
              <TableHead className="text-right">W · D · L</TableHead>
              <TableHead className="text-right">Score</TableHead>
              <TableHead className="text-right">Forfeits</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ranked.map((model, index) => {
              const [w, d] = model.wdl
              return (
                <TableRow key={model.model}>
                  <TableCell className="text-muted-foreground">{model.reference ? index + 1 : ''}</TableCell>
                  <TableCell className="font-semibold">{model.model}</TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">{ratingText(model.reference)}</TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">
                    {intervalText(model.reference)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{model.games}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    <b>{w}</b> · {d} · {model.wdl[2]}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {model.games ? `${Math.round((100 * (w + d / 2)) / model.games)}%` : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{model.forfeits}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          Every model under the same <Explain tip={REFERENCE_TIP}>Reference configuration</Explain>, so the Ratings
          compare models and nothing else. “&lt; X” is an upper bound when every anchored game was lost; “—” no games
          under the Reference configuration yet.
        </p>
      </CardFooter>
    </Card>
  )
}

const VIEWS = {
  ranking: {
    label: 'Ranking',
    intro: 'Every model, ranked by its Rating under the Reference configuration, on the chess.com Rapid scale.',
  },
  effects: {
    label: 'Setting effects',
    intro:
      'How far changing one setting moves each model’s Rating from its Rating under the Reference configuration. Click a model for all its configurations.',
  },
} as const

function VariantE() {
  const [view, setView] = useState<keyof typeof VIEWS>('ranking')
  return (
    <>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Leaderboard</h1>
          <p className="mt-1 text-muted-foreground">{VIEWS[view].intro}</p>
        </div>
        <Tabs value={view} onValueChange={(value) => setView(value as keyof typeof VIEWS)}>
          <TabsList>
            {Object.entries(VIEWS).map(([key, { label }]) => (
              <TabsTrigger key={key} value={key}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      {view === 'ranking' ? <RankingView /> : <VariantD />}
    </>
  )
}

// -------------------------------------------------------------------------------------------------------------- page

const VARIANTS = [
  { key: 'A', name: 'Models, each row expanding' },
  { key: 'B', name: 'Model list + Rating scale' },
  { key: 'C', name: 'Models × settings matrix' },
  { key: 'D', name: 'Matrix + games/noise, detail below' },
  { key: 'E', name: 'Ranking | Setting effects switch' },
] as const

export const byModelActive = () => new URLSearchParams(window.location.search).get('prototype') === 'by-model'

export function ByModelPrototype() {
  const variant = useVariant(VARIANTS.map((v) => v.key))
  return (
    <>
      {variant !== 'E' && (
        <>
          <h1 className="text-2xl font-semibold tracking-tight">Leaderboard</h1>
          <p className="mt-1 mb-5 text-muted-foreground">
            Every model, ranked by its Rating under the Reference configuration, on the chess.com Rapid scale.
          </p>
        </>
      )}
      {variant === 'E' && <VariantE />}
      {variant === 'A' && <VariantA />}
      {variant === 'B' && <VariantB />}
      {variant === 'C' && <VariantC />}
      {variant === 'D' && <VariantD />}
      <PrototypeSwitcher variants={VARIANTS} current={variant} />
    </>
  )
}
