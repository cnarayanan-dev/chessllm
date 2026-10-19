import { Radio } from '@base-ui/react/radio'
import { useQuery } from '@tanstack/react-query'
import { type ReactNode, useEffect, useState } from 'react'
import { modelsQuery } from '@/api/models'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { RadioGroup } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { isMoveSoundOn, setMoveSoundOn } from '@/components/board/moveSound'
import {
  COLORS,
  MAX_ATTEMPTS_CHOICES,
  type Color,
  type GameSettings,
  type LlmConstraints,
  type Mode,
  type Models,
  type NewGame,
  type NextGame,
  type RetryFeedback,
  canThink,
  chaosAllowed,
  chooseHumanColor,
  chooseMaxAttempts,
  chooseRules,
  chooseMode,
  chooseModel,
  enforced,
  isPending,
  llmColors,
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

type Options<T extends string> = Record<T, { name: string; description?: string }>

const MODES: Options<Mode> = {
  play_llm: { name: 'Play LLM', description: 'You play one side, an LLM the other' },
  llm_faceoff: { name: 'LLM faceoff', description: 'An LLM on each side, to compare models. It plays itself to the end.' },
}
const COLOR_NAMES: Options<Color> = { white: { name: 'White' }, black: { name: 'Black' } }
const ICON: Record<Color, string> = { white: '♔', black: '♚' }
const LLM_CONSTRAINTS: Options<LlmConstraints> = {
  free: { name: 'Free', description: 'No legal-move list: the LLM finds its own moves' },
  listed: { name: 'Listed', description: 'Shown every legal move, but can still play an illegal one' },
  blind_enforced: { name: 'Blind enforced', description: 'Held to the legal moves without being shown them' },
  listed_enforced: { name: 'Listed enforced', description: 'Shown every legal move and held to them' },
}
const FEEDBACK_LEVELS: Options<RetryFeedback> = {
  explained: { name: 'Explained', description: 'The move and the kind of failure' },
  bare: { name: 'Bare', description: 'Only that it was illegal' },
  hinted: { name: 'Hinted', description: 'Also lists the legal moves (muddies Free)' },
}
const colorName = (color: Color) => COLOR_NAMES[color].name

/** The Chaos rules switch's hint: what it does, or why it can't be on. */
function chaosHint(next: NextGame): string {
  if (chaosAllowed(next))
    return "The LLM's illegal moves are played on the board, as it wrote them, instead of retried. Badly formed notation is still retried. Unrated."
  if (!next.custom) return "Only under Free or Listed: under Enforced decoding the LLM can't play an illegal move."
  const enforcedSides = COLORS.filter((color) => enforced(next, color))
    .map((color) => `${colorName(color)} plays under ${LLM_CONSTRAINTS[value(next, color, 'llm_constraints')].name}`)
    .join(' and ')
  return `Only when every LLM plays under Free or Listed: ${enforcedSides}.`
}

/** The forfeit limit's hint: how many retries it leaves, or why it has no effect. */
function maxAttemptsHint(next: NextGame): string {
  if (llmColors(next).every((color) => enforced(next, color)))
    return 'No effect: under Enforced decoding the LLM never plays an illegal move, so never forfeits for one.'
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

const SECTIONS = { game: '♟ Game', model: '◆ Model', advanced: '⚙ Advanced' }
type Section = keyof typeof SECTIONS

/** The top bar's button that opens the settings, as ⌘K does. */
export function SettingsButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="ghost" className="text-muted-foreground" onClick={onClick}>
      ⚙ Settings
      <kbd className="rounded border bg-muted px-1.5 font-mono text-[11px] text-muted-foreground">⌘K</kbd>
    </Button>
  )
}

type SettingsModalProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The running game's settings: it keeps them, and the changes apply to the next game. */
  running: GameSettings
  next: NextGame
  onNextChange: (next: NextGame) => void
  /** "Start new game": the next game's request, with each side's resulting settings. */
  onStartNext: (request: NewGame) => void
}

/** The settings for the next game, opened and closed with ⌘K (Ctrl+K). */
export function SettingsModal({ open, onOpenChange, ...pane }: SettingsModalProps) {
  // The section stays chosen while the modal is closed.
  const [section, setSection] = useState<Section>('game')

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onOpenChange])

  return (
    <Dialog open={open} onOpenChange={(isOpen) => onOpenChange(isOpen)}>
      <DialogContent className="grid h-[min(560px,88vh)] w-[min(880px,94vw)] max-w-none grid-cols-[220px_1fr] gap-0 overflow-hidden p-0 sm:max-w-none">
        <DialogTitle className="sr-only">Settings</DialogTitle>
        <nav className="bg-muted/60 px-1.5 py-3.5">
          <div className="px-2.5 pt-0.5 pb-2.5 text-xs text-muted-foreground">ChessLLM settings</div>
          {Object.entries(SECTIONS).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-current={section === key ? 'page' : undefined}
              className={cn(
                'flex w-full cursor-pointer rounded-md px-2.5 py-1.5 text-left text-muted-foreground',
                section === key && 'bg-muted font-medium text-foreground',
              )}
              onClick={() => setSection(key as Section)}
            >
              {label}
            </button>
          ))}
        </nav>
        <TooltipProvider>
          <SettingsPane
            {...pane}
            section={section}
            onStartNext={(request) => {
              onOpenChange(false)
              pane.onStartNext(request)
            }}
          />
        </TooltipProvider>
      </DialogContent>
    </Dialog>
  )
}

type PaneProps = Omit<SettingsModalProps, 'open' | 'onOpenChange'> & { section: Section }

// Mounted only while the modal is open, so the models are listed afresh each time: new models and config edits show up.
function SettingsPane({ section, running, next, onNextChange, onStartNext }: PaneProps) {
  const query = useQuery({ ...modelsQuery, refetchOnMount: 'always' })
  const models: Models = query.isError ? null : (query.data ?? null)
  const modelsError = query.isError ? query.error.message : null
  const pending = isPending(next, models, running)

  return (
    <div className="relative overflow-auto px-12 py-8">
      {section === 'game' && <GameSection next={next} models={models} onNextChange={onNextChange} />}
      {section === 'model' && (
        <ModelSection next={next} models={models} modelsError={modelsError} onNextChange={onNextChange} />
      )}
      {section === 'advanced' && <AdvancedSection next={next} models={models} modelsError={modelsError} />}
      <div className="mt-4 flex items-center gap-2 rounded-md bg-muted px-2.5 py-2 text-[12.5px] text-muted-foreground">
        Changes apply when you start a new game.
        {pending && <span className="rounded bg-primary/10 px-2 py-0.5 text-xs text-primary">changes apply next game</span>}
        <span className="flex-1" />
        {pending && (
          <Button size="sm" onClick={() => onStartNext(newGameRequest(next, models))}>
            Start new game
          </Button>
        )}
      </div>
    </div>
  )
}

type SectionProps = { next: NextGame; models: Models; onNextChange: (next: NextGame) => void }

function GameSection({ next, models, onNextChange }: SectionProps) {
  const isFaceoff = next.mode === 'llm_faceoff'
  const [sound, setSound] = useState(isMoveSoundOn)
  // When customizing, a White block and a Black block, each labelled with its side and model; else one for both.
  const shownColors = next.custom ? COLORS : (['white'] as Color[])
  const blocks = (build: (color: Color) => ReactNode) =>
    shownColors.map((color) => (
      <div key={color}>
        {next.custom && (
          <div className="mt-1.5 -mb-2 text-xs text-muted-foreground">
            {ICON[color]} {colorName(color)} · {next.models[color]}
          </div>
        )}
        {build(color)}
      </div>
    ))
  const noEffect = shownColors.filter((color) => enforced(next, color))
  const feedbackHint =
    noEffect.length === shownColors.length
      ? "No effect: under Enforced decoding the LLM can't play an illegal move."
      : 'What the LLM is told after an illegal move.' +
        (noEffect.length
          ? ` No effect for ${colorName(noEffect[0])}: under Enforced decoding it can't play an illegal move.`
          : '')

  return (
    <section>
      <Heading>Game</Heading>
      <Row heading title="Mode" description="Who plays each side, fixed for the whole game." />
      <Cards
        label="Mode"
        options={MODES}
        value={next.mode}
        defaultChoice="play_llm"
        columns={2}
        onChange={(mode) => onNextChange(chooseMode(next, models, mode))}
      />
      {isFaceoff ? (
        <>
          <Row heading title="Players" description="A model for each side. The same model can play itself." />
          <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2.5 py-3.5">
            <PlayerSelect color="white" next={next} models={models} onNextChange={onNextChange} />
            <Button variant="outline" aria-label="Swap colours" title="Swap colours" onClick={() => onNextChange(swapSides(next))}>
              ⇄
            </Button>
            <PlayerSelect color="black" next={next} models={models} onNextChange={onNextChange} />
          </div>
          <Row
            title="Customize per LLM"
            description="Off: both LLMs play under the same settings, a fair comparison. On: set each LLM separately."
          >
            <Switch
              aria-label="Customize per LLM"
              checked={next.custom}
              onCheckedChange={() => onNextChange(toggleCustomize(next, models))}
            />
          </Row>
        </>
      ) : (
        <>
          <Row heading title="Your colour" description="The LLM plays the other colour. White moves first." />
          <Cards
            label="Your colour"
            options={COLOR_NAMES}
            value={next.human_color}
            defaultChoice="white"
            columns={2}
            onChange={(color) => onNextChange(chooseHumanColor(next, color))}
          />
        </>
      )}
      <Row
        heading
        title="LLM constraints"
        description="Whether the LLM is shown the legal moves in each turn's prompt, and whether it is held to them."
      />
      {blocks((color) => (
        <Cards
          label="LLM constraints"
          options={LLM_CONSTRAINTS}
          value={value(next, color, 'llm_constraints')}
          defaultChoice="free"
          columns={2}
          onChange={(choice) => onNextChange(setValue(next, color, 'llm_constraints', choice))}
        />
      ))}
      <Row heading title="Retry feedback" description={feedbackHint} />
      {blocks((color) => (
        <Cards
          label="Retry feedback"
          options={FEEDBACK_LEVELS}
          value={value(next, color, 'retry_feedback')}
          defaultChoice="explained"
          columns={3}
          disabled={enforced(next, color)}
          onChange={(choice) => onNextChange(setValue(next, color, 'retry_feedback', choice))}
        />
      ))}
      <Row title="Illegal moves before forfeit" description={maxAttemptsHint(next)}>
        <Select
          value={String(next.max_attempts)}
          disabled={noEffect.length === shownColors.length}
          onValueChange={(choice) => choice && onNextChange(chooseMaxAttempts(next, Number(choice)))}
        >
          <SelectTrigger aria-label="Illegal moves before forfeit" className="min-w-[110px]">
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
      <Row title="Chaos rules" description={chaosHint(next)}>
        <Switch
          aria-label="Chaos rules"
          checked={next.rules === 'chaos' && chaosAllowed(next)}
          disabled={!chaosAllowed(next)}
          onCheckedChange={(on) => onNextChange(chooseRules(next, on ? 'chaos' : 'standard'))}
        />
      </Row>
      <Row title="Move sound" description="A click on every move, yours and the LLM's. Applies at once, in this browser.">
        <Switch
          aria-label="Move sound"
          checked={sound}
          onCheckedChange={(on) => {
            setMoveSoundOn(on)
            setSound(on)
          }}
        />
      </Row>
    </section>
  )
}

function ModelSection({ next, models, modelsError, onNextChange }: SectionProps & { modelsError: string | null }) {
  const isFaceoff = next.mode === 'llm_faceoff'
  const llmColor = other(next.human_color) // the LLM's side in Play LLM
  const allowed = thinkingAllowed(next, models)
  const cannot = [...new Set(llmColors(next).map((color) => next.models[color]))].filter(
    (name) => !canThink(models, name),
  )
  const thinkingHint = allowed
    ? `The model reasons before answering${isFaceoff ? ', for both LLMs' : ''}. Slower, likely stronger play. The thinking text is saved to the game log.`
    : isFaceoff
      ? `Shared by both LLMs, so only on when both can think: ${cannot.join(' and ')} can't. It reasons in its answer instead, before the move.`
      : `${cannot[0]} can't think: it reasons in its answer instead, before the move.`

  return (
    <section>
      <Heading>Model</Heading>
      {!isFaceoff && (
        <Row
          title="Model"
          description={modelsError ? `Could not list the models: ${modelsError}` : 'The models in chessllm/models.py'}
        >
          <ModelSelect
            label="Model"
            chosen={next.models[llmColor]}
            models={models}
            onChange={(name) => onNextChange(chooseModel(next, llmColor, name))}
          />
        </Row>
      )}
      {next.custom ? (
        COLORS.map((color) => {
          const model = next.models[color]
          return (
            <Row
              key={color}
              title={`${ICON[color]} ${colorName(color)} thinking`}
              description={
                canThink(models, model)
                  ? `${model} reasons before answering. Slower, likely stronger play.`
                  : `${model} can't think: it reasons in its answer instead, before the move.`
              }
            >
              <Switch
                aria-label={`${colorName(color)} thinking`}
                checked={thinkingOn(next, models, color)}
                disabled={!canThink(models, model)}
                onCheckedChange={() => onNextChange(toggleThinking(next, models, color))}
              />
            </Row>
          )
        })
      ) : (
        <Row title="Thinking" description={thinkingHint}>
          <Switch
            aria-label="Thinking"
            checked={thinkingOn(next, models, 'white')}
            disabled={!allowed}
            onCheckedChange={() => onNextChange(toggleThinking(next, models, 'white'))}
          />
        </Row>
      )}
    </section>
  )
}

// Sampling is shared by every LLM, from the config file, over each model's own defaults.
function AdvancedSection({ next, models, modelsError }: { next: NextGame; models: Models; modelsError: string | null }) {
  const names = [...new Set(llmColors(next).map((color) => next.models[color]))]
  const listed = names.map((name) => models?.find((model) => model.name === name))
  const unshown = listed.find((model) => model?.sampling === null)
  const hint = listed.some((model) => !model)
    ? modelsError
      ? `Could not read the sampling settings: ${modelsError}`
      : 'The sampling settings show once the models are listed.'
    : unshown
      ? `Ollama could not show ${unshown.name}. Is it installed, and is Ollama running?`
      : `Sampling for ${names.join(' and ')}: the model's defaults, overridden by chessllm/sampling.toml. Change them in that file.`

  return (
    <section>
      <Heading>Advanced</Heading>
      <Row description={hint} />
      <table className="mt-2 w-full border-collapse">
        <tbody>
          {listed.map((model) => {
            if (!model?.sampling) return null
            const entries = Object.entries(model.sampling)
            return [
              listed.length > 1 && (
                <tr key={`${model.name} head`} className="font-medium">
                  <Cell colSpan={2}>{model.name}</Cell>
                </tr>
              ),
              ...entries.map(([name, setting]) => (
                <tr key={`${model.name} ${name}`}>
                  <Cell>{name}</Cell>
                  <Cell className="text-right text-muted-foreground tabular-nums">{setting}</Cell>
                </tr>
              )),
              entries.length === 0 && (
                <tr key={`${model.name} none`}>
                  <Cell colSpan={2}>No sampling parameters set: Ollama's built-in defaults</Cell>
                </tr>
              ),
            ]
          })}
        </tbody>
      </table>
    </section>
  )
}

function Heading({ children }: { children: ReactNode }) {
  return <h2 className="mb-1 border-b pb-3 text-base font-semibold">{children}</h2>
}

/** A setting's title and description, with its control on the right; a heading row sits over its cards. */
function Row({
  title,
  description,
  heading = false,
  children,
}: {
  title?: string
  description: string
  heading?: boolean
  children?: ReactNode
}) {
  return (
    <div className={cn('flex items-center gap-6 border-b py-4', heading && 'border-0 pb-0')}>
      <div className="flex-1">
        {title && <div className="font-medium">{title}</div>}
        <div className="text-[12.5px] text-muted-foreground">{description}</div>
      </div>
      {children}
    </div>
  )
}

function Cell({ className, ...props }: React.ComponentProps<'td'>) {
  return <td className={cn('border-b py-2.5', className)} {...props} />
}

/** A choice of one, as cards; each card's description shows on hover. */
function Cards<T extends string>({
  label,
  options,
  value: chosen,
  defaultChoice,
  columns,
  disabled = false,
  onChange,
}: {
  label: string
  options: Options<T>
  value: T
  defaultChoice: T
  columns: 2 | 3
  disabled?: boolean
  onChange: (choice: T) => void
}) {
  return (
    <RadioGroup
      aria-label={label}
      value={chosen}
      disabled={disabled}
      onValueChange={(choice) => onChange(choice as T)}
      className={cn('gap-2 py-3.5', columns === 2 ? 'grid-cols-2' : 'grid-cols-3')}
    >
      {(Object.entries(options) as [T, Options<T>[T]][]).map(([choice, { name, description }]) => {
        const card = (
          <Radio.Root
            value={choice}
            className="cursor-pointer rounded-md border px-3 py-2 text-center hover:bg-muted data-checked:border-primary data-checked:bg-primary/10 data-disabled:cursor-default data-disabled:opacity-40 data-disabled:hover:bg-transparent"
          >
            <span className="font-medium">{name}</span>
            {choice === defaultChoice && <span className="ml-1 text-[11px] text-muted-foreground">default</span>}
          </Radio.Root>
        )
        if (!description) return <span key={choice} className="contents">{card}</span>
        return (
          <Tooltip key={choice}>
            <TooltipTrigger render={card} />
            <TooltipContent side="bottom">{description}</TooltipContent>
          </Tooltip>
        )
      })}
    </RadioGroup>
  )
}

/** A model select. The chosen model stays listed until the list has loaded. */
function ModelSelect({
  label,
  chosen,
  models,
  onChange,
  className,
}: {
  label: string
  chosen: string
  models: Models
  onChange: (name: string) => void
  className?: string
}) {
  const names = (models ?? []).map((model) => model.name)
  if (!names.includes(chosen)) names.unshift(chosen)
  return (
    <Select value={chosen} onValueChange={(name) => name && onChange(name)}>
      <SelectTrigger aria-label={label} className={cn('max-w-[260px] min-w-[170px]', className)}>
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

function PlayerSelect({ color, next, models, onNextChange }: SectionProps & { color: Color }) {
  return (
    <div>
      <div className="mb-1 text-xs text-muted-foreground">
        {ICON[color]} {colorName(color)}
      </div>
      <ModelSelect
        label={`${colorName(color)} model`}
        chosen={next.models[color]}
        models={models}
        className="w-full max-w-none"
        onChange={(name) => onNextChange(chooseModel(next, color, name))}
      />
    </div>
  )
}
