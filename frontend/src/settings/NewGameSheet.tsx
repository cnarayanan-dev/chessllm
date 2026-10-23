// The New game sheet: sets up the next game and starts it (DESIGN.md: New game sheet). Every option shows an icon
// and its short name; what it means, or why it is disabled, is in a Tooltip and its aria-description.
import { Radio } from '@base-ui/react/radio'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, Bot, ChevronDown, type LucideIcon, User } from 'lucide-react'
import { type ReactElement, type ReactNode, useRef, useState } from 'react'
import { modelsQuery } from '@/api/models'
import { settingIcon } from '@/components/game-card/settingIcons'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { RadioGroup } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { COLOR_NAMES, LLM_CONSTRAINT_WORDS, RETRY_FEEDBACK_WORDS, RULES_WORDS } from '@/game/wording'
import { cn } from '@/lib/utils'
import {
  COLORS,
  MAX_ATTEMPTS_CHOICES,
  type Color,
  type LlmConstraints,
  type Models,
  type NextGame,
  type RetryFeedback,
  type Rules,
  canThink,
  chaosAllowed,
  chooseHumanColor,
  chooseMaxAttempts,
  chooseMode,
  chooseModel,
  chooseRules,
  enforced,
  everyLlmEnforced,
  llmColors,
  other,
  setValue,
  swapSides,
  thinkingAllowed,
  thinkingOn,
  toggleCustomize,
  toggleThinking,
  value,
} from '@/settings/next-game'

const THINKING = 'Reasons before each move. Slower, likely stronger.'
const ADVANCED = 'What the LLM sees, retries, forfeit'
const CUSTOMIZE = 'Off: both LLMs play under the same settings, a fair comparison. On: set each LLM separately.'
/** The constraints under which an LLM can play an illegal move, by their names in the sheet. */
const NOT_ENFORCED = `${LLM_CONSTRAINT_WORDS.free.name} or ${LLM_CONSTRAINT_WORDS.listed.name}`

const cannotThink = (names: string[]) => `${names.join(' and ')} can't think.`

/** Why Chaos rules can't be chosen: an LLM under an enforced constraint, named by its side when customizing. */
function chaosReason(next: NextGame): string {
  if (!next.custom) return `Needs an LLM that can play an illegal move: pick ${NOT_ENFORCED} in Advanced settings.`
  const sides = llmColors(next).filter((color) => enforced(next, color)).map((color) => COLOR_NAMES[color])
  return `Needs every LLM able to play an illegal move: pick ${NOT_ENFORCED} for ${sides.join(' and ')} in Advanced settings.`
}

/** The forfeit limit's explanation: how many retries it leaves. */
function maxAttemptsHint(next: NextGame): string {
  const retries = next.max_attempts - 1
  const shared = next.mode === 'llm_faceoff' ? ' The same for both LLMs.' : ''
  const limit =
    retries === 0
      ? 'The LLM forfeits at its first illegal move, with no retry.'
      : `The LLM forfeits at its ${ordinal(next.max_attempts)} illegal move in a turn: ${retries} ${retries === 1 ? 'retry' : 'retries'}.`
  return `${limit}${shared} Default 5.`
}

const ordinal = (n: number) => {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] ?? 'th')
  return `${n}${suffix}`
}

type NewGameSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /**
   * The settings it opens with, each time: the last game's, or with no game the API's defaults. Closing it drops its
   * changes, so the next opening starts from these again.
   */
  initial: NextGame
  /** Play as White, Play as Black or Start faceoff: the game as set up in the sheet, which then closes. */
  onStart: (next: NextGame) => void
}

export function NewGameSheet({ open, onOpenChange, initial, onStart }: NewGameSheetProps) {
  // Focus goes to the sheet itself rather than its first card, whose tooltip would show at once; Tab goes on from it.
  const sheet = useRef<HTMLDivElement>(null)
  return (
    <Dialog open={open} onOpenChange={(isOpen) => onOpenChange(isOpen)}>
      <DialogContent
        ref={sheet}
        initialFocus={sheet}
        className="max-h-[90vh] w-[min(560px,94vw)] max-w-none gap-0 overflow-y-auto p-0 sm:max-w-none">
        <DialogTitle className="px-6 pt-6 pb-1 text-lg font-semibold tracking-tight">New game</DialogTitle>
        <TooltipProvider>
          <Sheet
            initial={initial}
            onStart={(next) => {
              onOpenChange(false)
              onStart(next)
            }}
          />
        </TooltipProvider>
      </DialogContent>
    </Dialog>
  )
}

// Mounted only while the sheet is open: each opening starts from `initial` and lists the models afresh, so new models
// and config edits show up.
function Sheet({ initial, onStart }: Pick<NewGameSheetProps, 'initial' | 'onStart'>) {
  const [next, set] = useState(initial)
  const [advanced, setAdvanced] = useState(false)
  const query = useQuery({ ...modelsQuery, refetchOnMount: 'always' })
  const models: Models = query.isError ? null : (query.data ?? null)
  const isFaceoff = next.mode === 'llm_faceoff'
  const chaosOk = chaosAllowed(next)
  const sides: SideProps = { next, models, set }

  return (
    <div className="flex flex-col gap-5 px-6 pt-4 pb-6">
      <Choice
        label="Mode"
        hideLabel
        columns={2}
        value={next.mode}
        onChange={(mode) => set(chooseMode(next, models, mode))}
        options={[
          {
            value: 'play_llm',
            name: 'Play LLM',
            icon: <Players first={User} />,
            description: 'You play one side, an LLM the other',
          },
          {
            value: 'llm_faceoff',
            name: 'LLM faceoff',
            icon: <Players first={Bot} />,
            description: 'An LLM on each side, to compare models',
          },
        ]}
      />
      <Opponent {...sides} error={query.isError ? query.error.message : null} />
      {!next.custom && (
        <SwitchRow
          label="Thinking"
          description={
            thinkingAllowed(next, models)
              ? THINKING
              : cannotThink([...new Set(llmColors(next).map((color) => next.models[color]))].filter((name) => !canThink(models, name)))
          }
          checked={thinkingOn(next, models, 'white')}
          disabled={!thinkingAllowed(next, models)}
          onChange={() => set(toggleThinking(next, models, 'white'))}
        />
      )}
      <Choice<Rules>
        label="Rules"
        columns={2}
        value={next.rules === 'chaos' && chaosOk ? 'chaos' : 'standard'}
        onChange={(rules) => set(chooseRules(next, rules))}
        options={(['standard', 'chaos'] as const).map((rules) => ({
          value: rules,
          name: RULES_WORDS[rules].name,
          icon: <SettingIcon setting="rules" value={rules} />,
          description: RULES_WORDS[rules].description,
          disabled: rules === 'chaos' && !chaosOk ? chaosReason(next) : undefined,
        }))}
      />
      <Collapsible open={advanced} onOpenChange={setAdvanced} className="rounded-3xl bg-muted/60">
        <Tip description={ADVANCED}>
          <CollapsibleTrigger
            aria-description={ADVANCED}
            className="flex w-full cursor-pointer items-center gap-2 rounded-3xl px-4 py-3 text-left font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <ChevronDown
              className={cn('size-4 text-muted-foreground transition-transform', !advanced && '-rotate-90')}
              aria-hidden="true"
            />
            Advanced settings
          </CollapsibleTrigger>
        </Tip>
        <CollapsibleContent className="flex flex-col gap-5 px-4 pt-1 pb-4">
          <Advanced {...sides} />
        </CollapsibleContent>
      </Collapsible>
      <StartButtons next={next} onStart={onStart} isFaceoff={isFaceoff} />
    </div>
  )
}

type SideProps = { next: NextGame; models: Models; set: (next: NextGame) => void }

/** The model of the LLM in Play LLM, or of each side in a faceoff, with the swap button between them. */
function Opponent({ next, models, set, error }: SideProps & { error: string | null }) {
  const alert = error && (
    <p role="alert" className="text-xs text-destructive">
      Could not list the models: {error}
    </p>
  )
  if (next.mode === 'play_llm') {
    const llm = other(next.human_color)
    return (
      <Field label="Opponent">
        <ModelSelect label="Opponent" chosen={next.models[llm]} models={models} onChange={(name) => set(chooseModel(next, llm, name))} />
        {alert}
      </Field>
    )
  }
  const side = (color: Color) => (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center gap-2 font-medium">
        <SideDot color={color} />
        {COLOR_NAMES[color]}
      </div>
      <ModelSelect
        label={`${COLOR_NAMES[color]} model`}
        chosen={next.models[color]}
        models={models}
        onChange={(name) => set(chooseModel(next, color, name))}
      />
    </div>
  )
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
        {side('white')}
        <Tip description="Swap colours">
          <Button variant="outline" size="icon" aria-label="Swap colours" onClick={() => set(swapSides(next))}>
            <ArrowLeftRight aria-hidden="true" />
          </Button>
        </Tip>
        {side('black')}
      </div>
      {alert}
    </div>
  )
}

/** A model select. The chosen model stays listed until the list has loaded. */
function ModelSelect({
  label,
  chosen,
  models,
  onChange,
}: {
  label: string
  chosen: string
  models: Models
  onChange: (name: string) => void
}) {
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

/** What the LLM is given, Retry feedback, the forfeit limit and Customize per LLM. */
function Advanced({ next, models, set }: SideProps) {
  return (
    <>
      {!next.custom && <Constraints next={next} set={set} color="white" />}
      {!next.custom && !enforced(next, 'white') && <Feedback next={next} set={set} color="white" />}
      {!everyLlmEnforced(next) && (
        <Row label="Illegal moves before forfeit" description={maxAttemptsHint(next)}>
          <Select value={String(next.max_attempts)} onValueChange={(choice) => choice && set(chooseMaxAttempts(next, Number(choice)))}>
            <SelectTrigger
              aria-label="Illegal moves before forfeit"
              aria-description={maxAttemptsHint(next)}
              className="min-w-[90px] bg-card"
            >
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
        </Row>
      )}
      {next.mode === 'llm_faceoff' && (
        <SwitchRow
          label="Customize per LLM"
          description={CUSTOMIZE}
          checked={next.custom}
          onChange={() => set(toggleCustomize(next, models))}
        />
      )}
      {next.custom &&
        COLORS.map((color) => {
          const model = next.models[color]
          return (
            <section key={color} aria-label={`${COLOR_NAMES[color]} · ${model}`} className="flex flex-col gap-4 rounded-3xl bg-card p-4">
              <div className="flex items-center gap-2 font-medium">
                <SideDot color={color} />
                {COLOR_NAMES[color]} · {model}
              </div>
              <SwitchRow
                label="Thinking"
                ariaLabel={`${COLOR_NAMES[color]} thinking`}
                description={canThink(models, model) ? THINKING : cannotThink([model])}
                checked={thinkingOn(next, models, color)}
                disabled={!canThink(models, model)}
                onChange={() => set(toggleThinking(next, models, color))}
              />
              <Constraints next={next} set={set} color={color} />
              {!enforced(next, color) && <Feedback next={next} set={set} color={color} />}
            </section>
          )
        })}
    </>
  )
}

/** A side's label for a choice made per LLM: "White: what the LLM is given". */
const perSide = (next: NextGame, color: Color, label: string) =>
  next.custom ? `${COLOR_NAMES[color]}: ${label.charAt(0).toLowerCase()}${label.slice(1)}` : label

function Constraints({ next, set, color }: Omit<SideProps, 'models'> & { color: Color }) {
  return (
    <Choice<LlmConstraints>
      label="What the LLM is given"
      ariaLabel={perSide(next, color, 'What the LLM is given')}
      columns={2}
      value={value(next, color, 'llm_constraints')}
      onChange={(choice) => set(setValue(next, color, 'llm_constraints', choice))}
      options={(Object.keys(LLM_CONSTRAINT_WORDS) as LlmConstraints[]).map((choice) => ({
        value: choice,
        name: LLM_CONSTRAINT_WORDS[choice].name,
        term: LLM_CONSTRAINT_WORDS[choice].term,
        icon: <SettingIcon setting="llm_constraints" value={choice} />,
        description: LLM_CONSTRAINT_WORDS[choice].description,
      }))}
    />
  )
}

function Feedback({ next, set, color }: Omit<SideProps, 'models'> & { color: Color }) {
  return (
    <Choice<RetryFeedback>
      label="After an illegal move, tell the LLM"
      ariaLabel={perSide(next, color, 'After an illegal move, tell the LLM')}
      columns={2}
      value={value(next, color, 'retry_feedback')}
      onChange={(choice) => set(setValue(next, color, 'retry_feedback', choice))}
      options={(Object.keys(RETRY_FEEDBACK_WORDS) as RetryFeedback[]).map((choice) => ({
        value: choice,
        name: RETRY_FEEDBACK_WORDS[choice].name,
        icon: <SettingIcon setting="retry_feedback" value={choice} />,
        description: RETRY_FEEDBACK_WORDS[choice].description,
      }))}
    />
  )
}

/** Lichess style: in Play LLM the colour is chosen by the button that starts the game. */
function StartButtons({ next, onStart, isFaceoff }: { next: NextGame; onStart: (next: NextGame) => void; isFaceoff: boolean }) {
  if (isFaceoff)
    return (
      <Button size="lg" onClick={() => onStart(next)}>
        Start faceoff
      </Button>
    )
  return (
    <div className="grid grid-cols-2 gap-2">
      {COLORS.map((color) => (
        <Button
          key={color}
          size="lg"
          variant={next.human_color === color ? 'default' : 'outline'}
          onClick={() => onStart(chooseHumanColor(next, color))}
        >
          <SideDot color={color} />
          Play as {COLOR_NAMES[color]}
        </Button>
      ))}
    </div>
  )
}

/** Shows `description` in a Tooltip on hover and keyboard focus of the element it wraps. */
function Tip({ description, children }: { description: string; children: ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger delay={250} render={children} />
      <TooltipContent className="max-w-64">{description}</TooltipContent>
    </Tooltip>
  )
}

/** The two players of a Mode, facing each other. */
function Players({ first: First }: { first: LucideIcon }) {
  return (
    <span className="flex items-center gap-1.5" aria-hidden="true">
      <First className="size-5" strokeWidth={1.75} />
      <span className="text-[11px] text-muted-foreground">vs</span>
      <Bot className="size-5" strokeWidth={1.75} />
    </span>
  )
}

/** A setting value's icon, as the Game card shows it. */
function SettingIcon({ setting, value: choice }: { setting: 'rules' | 'llm_constraints' | 'retry_feedback'; value: string }) {
  const Icon = settingIcon({ setting, value: choice })
  return <Icon className="size-5" strokeWidth={1.75} aria-hidden="true" />
}

/** White or Black, as a small outlined or filled dot, as in the Game card. */
function SideDot({ color }: { color: Color }) {
  return (
    <span
      data-side-dot={color}
      aria-hidden="true"
      className={cn(
        'size-2.5 flex-none rounded-full border-[1.5px] border-current',
        color === 'black' ? 'bg-current' : 'bg-card',
      )}
    />
  )
}

function Field({ label, hideLabel = false, children }: { label: string; hideLabel?: boolean; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      {!hideLabel && <div className="font-medium">{label}</div>}
      {children}
    </div>
  )
}

/** A setting's name with its control on the right; the row is the Tooltip's trigger, as Move sound in Preferences. */
function Row({ label, description, children }: { label: string; description: string; children: ReactNode }) {
  return (
    <Tip description={description}>
      <div className="flex items-center justify-between gap-4 font-medium">
        {label}
        {children}
      </div>
    </Tip>
  )
}

function SwitchRow({
  label,
  ariaLabel = label,
  description,
  checked,
  disabled = false,
  onChange,
}: {
  label: string
  ariaLabel?: string
  description: string
  checked: boolean
  disabled?: boolean
  onChange: () => void
}) {
  return (
    <Row label={label} description={description}>
      <Switch aria-label={ariaLabel} aria-description={description} checked={checked} disabled={disabled} onCheckedChange={onChange} />
    </Row>
  )
}

type Option<T extends string> = {
  value: T
  name: string
  /** The glossary term, under the name. */
  term?: string
  icon: ReactNode
  description: string
  /** Why it can't be chosen; it then is disabled, the reason in its tooltip instead of the description. */
  disabled?: string
}

/** A choice of one, as cards: the icon above the name, the description (or why it is disabled) on hover. */
function Choice<T extends string>({
  label,
  ariaLabel = label,
  hideLabel = false,
  columns,
  options,
  value: chosen,
  onChange,
}: {
  label: string
  ariaLabel?: string
  hideLabel?: boolean
  columns: 2 | 3
  options: Option<T>[]
  value: T
  onChange: (choice: T) => void
}) {
  return (
    <Field label={label} hideLabel={hideLabel}>
      <RadioGroup
        aria-label={ariaLabel}
        value={chosen}
        onValueChange={(choice) => onChange(choice as T)}
        className={cn('gap-2', columns === 2 ? 'grid-cols-2' : 'grid-cols-3')}
      >
        {options.map((option) => {
          const description = option.disabled ?? option.description
          return (
            <Tip key={option.value} description={description}>
              <Radio.Root
                value={option.value}
                disabled={option.disabled !== undefined}
                aria-description={description}
                className="flex cursor-pointer flex-col items-center gap-1.5 rounded-2xl bg-muted px-3 py-3 text-center transition-colors outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 data-checked:bg-card data-checked:shadow-sm data-checked:ring-2 data-checked:ring-primary data-disabled:cursor-not-allowed data-disabled:opacity-40 data-disabled:hover:bg-muted"
              >
                {option.icon}
                <span className="font-medium">{option.name}</span>
                {option.term && <span className="-mt-1 text-xs text-muted-foreground">{option.term}</span>}
              </Radio.Root>
            </Tip>
          )
        })}
      </RadioGroup>
    </Field>
  )
}
