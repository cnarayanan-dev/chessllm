// PROTOTYPE — throwaway. Two New game sheets on the game page, switched with ?variant=A|B, answering:
// "Research options as separate controls behind a disclosure (A), or bundled into named presets (B)?"
// Both start the game on confirm (decision 1). Not tested, not for main.
import { useQuery } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'
import { modelsQuery } from '@/api/models'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { isMoveSoundOn, setMoveSoundOn } from '@/components/board/moveSound'
import {
  COLORS,
  MAX_ATTEMPTS_CHOICES,
  type Color,
  type LlmConstraints,
  type Models,
  type NewGame,
  type NextGame,
  type RetryFeedback,
  canThink,
  chaosAllowed,
  chooseHumanColor,
  chooseMaxAttempts,
  chooseMode,
  chooseModel,
  chooseRules,
  enforced,
  newGameRequest,
  other,
  setValue,
  swapSides,
  thinkingAllowed,
  thinkingOn,
  toggleCustomize,
  toggleThinking,
  value,
} from '@/settings/next-game'

export const VARIANTS = { A: 'Separate controls + Research options', B: 'Presets' } as const
export type Variant = keyof typeof VARIANTS

export const prototypeVariant = (): Variant | null => {
  const variant = new URLSearchParams(window.location.search).get('variant')
  return variant && variant in VARIANTS ? (variant as Variant) : null
}

// Plain words first, the glossary term underneath.
const CONSTRAINTS: Record<LlmConstraints, { plain: string; term: string; hint: string }> = {
  free: { plain: 'Board only', term: 'Free', hint: 'Finds its own moves; can play an illegal one' },
  listed: { plain: 'Board + legal moves', term: 'Listed', hint: 'Shown every legal move; can still play an illegal one' },
  blind_enforced: { plain: 'Kept legal, not told', term: 'Blind enforced', hint: "Can't play an illegal move, isn't shown them" },
  listed_enforced: { plain: 'Shown and kept legal', term: 'Listed enforced', hint: 'Shown every legal move and held to them' },
}
const FEEDBACK: Record<RetryFeedback, { plain: string; hint: string }> = {
  explained: { plain: 'Explained', hint: 'The move and why it failed' },
  bare: { plain: 'Bare', hint: 'Only that it was illegal' },
  hinted: { plain: 'Hinted', hint: 'Also the legal moves' },
}
const ICON: Record<Color, string> = { white: '♔', black: '♚' }
const NAME: Record<Color, string> = { white: 'White', black: 'Black' }

type SheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  next: NextGame
  onNextChange: (next: NextGame) => void
  onStart: (request: NewGame) => void
}

export function PrototypeNewGameSheet({ variant, ...props }: SheetProps & { variant: Variant }) {
  const query = useQuery({ ...modelsQuery, refetchOnMount: 'always', enabled: props.open })
  const models: Models = query.isError ? null : (query.data ?? null)
  const start = (next: NextGame) => {
    props.onNextChange(next)
    props.onOpenChange(false)
    props.onStart(newGameRequest(next, models))
  }
  const body = { next: props.next, models, set: props.onNextChange, start }
  return (
    <Dialog open={props.open} onOpenChange={(isOpen) => props.onOpenChange(isOpen)}>
      <DialogContent className="max-h-[90vh] w-[min(560px,94vw)] max-w-none overflow-auto p-0 sm:max-w-none">
        <DialogTitle className="border-b px-6 py-4 text-base">New game</DialogTitle>
        {variant === 'A' ? <VariantA {...body} /> : <VariantB {...body} />}
      </DialogContent>
    </Dialog>
  )
}

type BodyProps = { next: NextGame; models: Models; set: (next: NextGame) => void; start: (next: NextGame) => void }

// ---------- shared bits (header-level only; each variant lays itself out) ----------

function Segmented<T extends string>({
  options,
  value: chosen,
  onChange,
  disabledReason,
}: {
  options: { value: T; label: string; hint?: string; disabled?: boolean }[]
  value: T
  onChange: (value: T) => void
  disabledReason?: string
}) {
  return (
    <div>
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              'cursor-pointer rounded-md border px-3 py-2 text-left hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent',
              chosen === option.value && 'border-primary bg-primary/10',
            )}
          >
            <div className="font-medium">{option.label}</div>
            {option.hint && <div className="text-xs text-muted-foreground">{option.hint}</div>}
          </button>
        ))}
      </div>
      {disabledReason && <div className="mt-1.5 text-xs text-muted-foreground">{disabledReason}</div>}
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div>
        <div className="font-medium">{label}</div>
        {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
      </div>
      {children}
    </div>
  )
}

function ModelSelect({ chosen, models, onChange, label }: { chosen: string; models: Models; onChange: (name: string) => void; label: string }) {
  const names = (models ?? []).map((model) => model.name)
  if (!names.includes(chosen)) names.unshift(chosen)
  return (
    <Select value={chosen} onValueChange={(name) => name && onChange(name)}>
      <SelectTrigger aria-label={label} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {names.map((name) => (
          <SelectItem key={name} value={name}>
            {name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Mode, the model(s), and Thinking: the same top in both variants. */
function Opponent({ next, models, set }: Omit<BodyProps, 'start'>) {
  const faceoff = next.mode === 'llm_faceoff'
  const llm = other(next.human_color)
  const thinkable = thinkingAllowed(next, models)
  return (
    <>
      <Segmented
        options={[
          { value: 'play_llm', label: 'Play LLM', hint: 'You play one side, an LLM the other' },
          { value: 'llm_faceoff', label: 'LLM faceoff', hint: 'An LLM on each side, to compare models' },
        ]}
        value={next.mode}
        onChange={(mode) => set(chooseMode(next, models, mode))}
      />
      {faceoff ? (
        <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
          {COLORS.map((color, index) => (
            <div key={color} className={index === 1 ? 'order-3' : ''}>
              <div className="mb-1 text-xs text-muted-foreground">
                {ICON[color]} {NAME[color]}
              </div>
              <ModelSelect label={`${NAME[color]} model`} chosen={next.models[color]} models={models} onChange={(name) => set(chooseModel(next, color, name))} />
            </div>
          ))}
          <Button variant="outline" className="order-2" aria-label="Swap colours" onClick={() => set(swapSides(next))}>
            ⇄
          </Button>
        </div>
      ) : (
        <Field label="Opponent">
          <ModelSelect label="Model" chosen={next.models[llm]} models={models} onChange={(name) => set(chooseModel(next, llm, name))} />
        </Field>
      )}
      {!next.custom && (
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="font-medium">Thinking</div>
            <div className="text-xs text-muted-foreground">
              {thinkable ? 'Reasons before each move. Slower, likely stronger.' : "This model can't think."}
            </div>
          </div>
          <Switch aria-label="Thinking" checked={thinkingOn(next, models, 'white')} disabled={!thinkable} onCheckedChange={() => set(toggleThinking(next, models, 'white'))} />
        </div>
      )}
    </>
  )
}

/** One line naming the configuration the Start button will play. */
function Summary({ next, models }: { next: NextGame; models: Models }) {
  const parts = (color: Color) => {
    const c = CONSTRAINTS[value(next, color, 'llm_constraints')]
    const bits = [next.models[color], thinkingOn(next, models, color) ? 'thinking' : 'no thinking', c.term]
    if (!enforced(next, color)) bits.push(FEEDBACK[value(next, color, 'retry_feedback')].plain, `${next.max_attempts} tries`)
    return bits.join(' · ')
  }
  const llms = next.mode === 'llm_faceoff' ? COLORS : [other(next.human_color)]
  const rules = next.rules === 'chaos' && chaosAllowed(next) ? 'Chaos rules · unrated' : 'Standard rules'
  return (
    <div className="rounded-md bg-muted px-3 py-2 font-mono text-xs text-muted-foreground">
      {llms.map((color) => (
        <div key={color}>
          {llms.length > 1 && `${ICON[color]} `}
          {parts(color)}
        </div>
      ))}
      <div>{rules}</div>
    </div>
  )
}

/** Lichess-style: in Play LLM the colour you pick is the start button. */
function StartButtons({ next, start }: { next: NextGame; start: (next: NextGame) => void }) {
  if (next.mode === 'llm_faceoff')
    return (
      <Button className="w-full" onClick={() => start(next)}>
        Start faceoff
      </Button>
    )
  return (
    <div className="grid grid-cols-2 gap-2">
      {COLORS.map((color) => (
        <Button key={color} variant={next.human_color === color ? 'default' : 'outline'} onClick={() => start(chooseHumanColor(next, color))}>
          {ICON[color]} Play as {NAME[color]}
        </Button>
      ))}
    </div>
  )
}

function ConstraintCards({ next, set, color }: { next: NextGame; set: (next: NextGame) => void; color: Color }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {(Object.keys(CONSTRAINTS) as LlmConstraints[]).map((choice) => {
        const c = CONSTRAINTS[choice]
        const chosen = value(next, color, 'llm_constraints') === choice
        return (
          <button
            key={choice}
            type="button"
            onClick={() => set(setValue(next, color, 'llm_constraints', choice))}
            className={cn('cursor-pointer rounded-md border px-3 py-2 text-left hover:bg-muted', chosen && 'border-primary bg-primary/10')}
          >
            <div className="font-medium">
              {c.plain} <span className="text-[11px] font-normal text-muted-foreground">{c.term}</span>
            </div>
            <div className="text-xs text-muted-foreground">{c.hint}</div>
          </button>
        )
      })}
    </div>
  )
}

/** Retry feedback and the forfeit limit, hidden where enforced decoding makes them moot. */
function IllegalMoveHandling({ next, set }: { next: NextGame; set: (next: NextGame) => void }) {
  const sides = next.custom ? COLORS : (['white'] as Color[])
  const live = sides.filter((color) => !enforced(next, color))
  if (live.length === 0) return null
  return (
    <>
      {live.map((color) => (
        <Field key={color} label={next.custom ? `${ICON[color]} After an illegal move, tell the LLM` : 'After an illegal move, tell the LLM'}>
          <Segmented
            options={(Object.keys(FEEDBACK) as RetryFeedback[]).map((choice) => ({ value: choice, label: FEEDBACK[choice].plain, hint: FEEDBACK[choice].hint }))}
            value={value(next, color, 'retry_feedback')}
            onChange={(choice) => set(setValue(next, color, 'retry_feedback', choice))}
          />
        </Field>
      ))}
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="font-medium">Illegal moves before forfeit</div>
          <div className="text-xs text-muted-foreground">Per turn. Default 5.</div>
        </div>
        <Select value={String(next.max_attempts)} onValueChange={(choice) => choice && set(chooseMaxAttempts(next, Number(choice)))}>
          <SelectTrigger aria-label="Illegal moves before forfeit" className="min-w-[90px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MAX_ATTEMPTS_CHOICES.map((choice) => (
              <SelectItem key={choice} value={String(choice)}>
                {choice}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
  )
}

/** Customize per LLM (faceoff only) and, when on, each side's thinking and constraints. */
function PerLlm({ next, models, set }: Omit<BodyProps, 'start'>) {
  if (next.mode !== 'llm_faceoff') return null
  return (
    <>
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="font-medium">Customize per LLM</div>
          <div className="text-xs text-muted-foreground">Off: both play under the same settings, a fair comparison.</div>
        </div>
        <Switch aria-label="Customize per LLM" checked={next.custom} onCheckedChange={() => set(toggleCustomize(next, models))} />
      </div>
      {next.custom &&
        COLORS.map((color) => (
          <Field key={color} label={`${ICON[color]} ${NAME[color]} · ${next.models[color]}`}>
            <div className="flex items-center gap-3 text-xs">
              Thinking
              <Switch
                aria-label={`${NAME[color]} thinking`}
                checked={thinkingOn(next, models, color)}
                disabled={!canThink(models, next.models[color])}
                onCheckedChange={() => set(toggleThinking(next, models, color))}
              />
            </div>
            <ConstraintCards next={next} set={set} color={color} />
          </Field>
        ))}
    </>
  )
}

// ---------- Variant A: Rules at the top, the research knobs behind one disclosure ----------

let researchOpen = false // remembered while the page lives (prototype: no persistence)

function VariantA({ next, models, set, start }: BodyProps) {
  const [open, setOpen] = useState(researchOpen)
  const chaosOk = chaosAllowed(next)
  return (
    <div className="flex flex-col gap-5 px-6 py-5">
      <Opponent next={next} models={models} set={set} />
      <Field label="Rules">
        <Segmented
          options={[
            { value: 'standard', label: 'Standard', hint: 'Normal chess. Rated.' },
            { value: 'chaos', label: 'Chaos', hint: "The LLM's illegal moves are played anyway. Unrated.", disabled: !chaosOk },
          ]}
          value={next.rules === 'chaos' && chaosOk ? 'chaos' : 'standard'}
          onChange={(rules) => set(chooseRules(next, rules))}
          disabledReason={chaosOk ? undefined : "Chaos needs an LLM that can play an illegal move: pick 'Board only' or 'Board + legal moves' in Advanced settings."}
        />
      </Field>
      <Collapsible
        open={open}
        onOpenChange={(isOpen) => {
          researchOpen = isOpen
          setOpen(isOpen)
        }}
        className="rounded-md border"
      >
        <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-2 px-3 py-2.5 text-left">
          <span className="text-muted-foreground">{open ? '▾' : '▸'}</span>
          <span className="font-medium">Advanced settings</span>
          <span className="text-xs text-muted-foreground">what the LLM sees, retries, forfeit</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="flex flex-col gap-5 border-t px-3 py-4">
          {!next.custom && (
            <Field label="What the LLM is given" hint="Whether it sees the legal moves, and whether it's held to them.">
              <ConstraintCards next={next} set={set} color="white" />
            </Field>
          )}
          <IllegalMoveHandling next={next} set={set} />
          <PerLlm next={next} models={models} set={set} />
          <MoveSound />
        </CollapsibleContent>
      </Collapsible>
      <StartButtons next={next} start={start} />
    </div>
  )
}

/** Browser-wide, applies at once (default off in the real build). */
function MoveSound() {
  const [on, setOn] = useState(isMoveSoundOn)
  return (
    <div className="flex items-center gap-4">
      <div className="flex-1">
        <div className="font-medium">Move sound</div>
        <div className="text-xs text-muted-foreground">A click on every move. Applies at once, in this browser.</div>
      </div>
      <Switch
        aria-label="Move sound"
        checked={on}
        onCheckedChange={(value) => {
          setMoveSoundOn(value)
          setOn(value)
        }}
      />
    </div>
  )
}

// ---------- Variant B: one preset choice, with Custom opening the knobs ----------

type Preset = 'standard' | 'chaos' | 'training' | 'custom'
const PRESETS: Record<Exclude<Preset, 'custom'>, { label: string; hint: string; constraints: LlmConstraints; rules: 'standard' | 'chaos' }> = {
  standard: { label: 'Standard', hint: 'Normal chess; illegal moves are retried. Rated.', constraints: 'free', rules: 'standard' },
  chaos: { label: 'Chaos', hint: 'Illegal moves are played on the board. Unrated.', constraints: 'free', rules: 'chaos' },
  training: { label: 'Training wheels', hint: "Shown the legal moves and can't leave them.", constraints: 'listed_enforced', rules: 'standard' },
}

function presetOf(next: NextGame): Preset {
  if (next.custom || next.max_attempts !== 5 || value(next, 'white', 'retry_feedback') !== 'explained') return 'custom'
  const constraints = value(next, 'white', 'llm_constraints')
  const rules = next.rules === 'chaos' && chaosAllowed(next) ? 'chaos' : 'standard'
  const found = (Object.keys(PRESETS) as (keyof typeof PRESETS)[]).find(
    (key) => PRESETS[key].constraints === constraints && PRESETS[key].rules === rules,
  )
  return found ?? 'custom'
}

function applyPreset(next: NextGame, models: Models, preset: keyof typeof PRESETS): NextGame {
  let result = next.custom ? toggleCustomize(next, models) : next
  result = setValue(result, 'white', 'llm_constraints', PRESETS[preset].constraints)
  result = setValue(result, 'white', 'retry_feedback', 'explained')
  result = chooseMaxAttempts(result, 5)
  return chooseRules(result, PRESETS[preset].rules)
}

function VariantB({ next, models, set, start }: BodyProps) {
  const matched = presetOf(next)
  // Custom stays open once picked, even if the knobs happen to land on a preset again.
  const [customPicked, setCustomPicked] = useState(matched === 'custom')
  const preset = customPicked ? 'custom' : matched
  const chaosOk = chaosAllowed(next)
  return (
    <div className="flex flex-col gap-5 px-6 py-5">
      <Opponent next={next} models={models} set={set} />
      <Field label="How strict">
        <div className="flex flex-col gap-2">
          {(Object.keys(PRESETS) as (keyof typeof PRESETS)[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                setCustomPicked(false)
                set(applyPreset(next, models, key))
              }}
              className={cn('flex cursor-pointer items-baseline gap-3 rounded-md border px-3 py-2 text-left hover:bg-muted', preset === key && 'border-primary bg-primary/10')}
            >
              <span className="w-32 font-medium">{PRESETS[key].label}</span>
              <span className="text-xs text-muted-foreground">{PRESETS[key].hint}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => setCustomPicked(true)}
            className={cn('flex cursor-pointer items-baseline gap-3 rounded-md border border-dashed px-3 py-2 text-left hover:bg-muted', preset === 'custom' && 'border-solid border-primary bg-primary/10')}
          >
            <span className="w-32 font-medium">Custom…</span>
            <span className="text-xs text-muted-foreground">Set what the LLM sees, retries and forfeit yourself.</span>
          </button>
        </div>
      </Field>
      {preset === 'custom' && (
        <div className="flex flex-col gap-5 rounded-md border px-3 py-4">
          {!next.custom && (
            <Field label="What the LLM is given">
              <ConstraintCards next={next} set={set} color="white" />
            </Field>
          )}
          <IllegalMoveHandling next={next} set={set} />
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="font-medium">Chaos rules</div>
              <div className="text-xs text-muted-foreground">
                {chaosOk ? 'Illegal moves are played on the board. Unrated.' : 'Only when the LLM can play an illegal move.'}
              </div>
            </div>
            <Switch aria-label="Chaos rules" checked={next.rules === 'chaos' && chaosOk} disabled={!chaosOk} onCheckedChange={(on) => set(chooseRules(next, on ? 'chaos' : 'standard'))} />
          </div>
          <PerLlm next={next} models={models} set={set} />
        </div>
      )}
      <Summary next={next} models={models} />
      <StartButtons next={next} start={start} />
    </div>
  )
}

// ---------- the floating switcher ----------

/** Click-only: ← and → already step through the move history on this page. */
export function PrototypeSwitcher({ current }: { current: Variant }) {
  if (!import.meta.env.DEV) return null
  const keys = Object.keys(VARIANTS) as Variant[]
  const go = (by: number) => {
    const key = keys[(keys.indexOf(current) + by + keys.length) % keys.length]
    const url = new URL(window.location.href)
    url.searchParams.set('variant', key)
    window.location.replace(url) // a full load: the page reads ?variant= once
  }
  return (
    <div className="fixed bottom-4 left-1/2 z-[100] flex -translate-x-1/2 items-center gap-3 rounded-full bg-black px-4 py-2 text-sm text-white shadow-lg">
      <button type="button" className="cursor-pointer px-1" onClick={() => go(-1)}>
        ←
      </button>
      <span>
        PROTOTYPE {current} — {VARIANTS[current]}
      </span>
      <button type="button" className="cursor-pointer px-1" onClick={() => go(1)}>
        →
      </button>
    </div>
  )
}
