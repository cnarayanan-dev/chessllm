// The Prompt tab's Prompt lab row: the Prompt template to Try, Try, and the Probes of the turn shown (CONTEXT.md).
// A probe asks the turn's LLM again about the position before it, outside the game; the game never changes.
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, FlaskConical, PenLine } from 'lucide-react'
import { probesQuery } from '@/api/probes'
import { promptLibraryQuery } from '@/api/promptLibrary'
import type { GameState, LlmTurn, Probe } from '@/api/types'
import { decisionOf, prose, quiet, RESULT_NAMES, templateName } from '@/components/turn/attempt'
import { PromptMessages } from '@/components/turn/PromptMessages'
import { useProbeTurn } from '@/components/turn/useProbeTurn'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { fittingTemplates } from '@/settings/next-game'

const TRY = "Ask the LLM again about the position before this turn, with the Prompt picked. The game doesn't change."
// Try in a running game no human plays: it pauses first, so a probe never runs alongside a real turn.
const TRY_PAUSING = `Pauses the game after the turn running, then asks the LLM again about the position before this turn, with the Prompt picked. The game doesn't change; resume it on the Game card.`
const PICKER = 'The Prompt template to Try. Listed: those that fit what the LLM is given.'
const EDIT = 'Open the Prompt in the editor under the board, to change it, try it and save it as a new version.'

type ProbesProps = {
  game: GameState
  turn: LlmTurn
  /** Why Try can't probe now (an LLM turn runs); undefined when it can. */
  tryBlocked?: string
  /** In a running game no human plays: pauses it, resolving once paused. Try awaits it before it probes. */
  pauseFirst?: () => Promise<void>
  /** The template picked to Try, by its ID; null for the game's own. Kept by the panel from turn to turn. */
  picked: string | null
  onPick: (id: string) => void
  /** Opens the dock on the template named, by its ID, from its name's button, which gets the focus back on close. */
  onEdit?: (id: string, from: HTMLElement) => void
}

/** The probes of the turn shown, in the order asked. */
const probesOf = (probes: Probe[], turn: LlmTurn) =>
  probes.filter((probe) => probe.ply === turn.ply && probe.color === turn.color)

type Tally = { name: string; legal: number; slips: number; total: number }

/** Per template, in the order first tried: how many of its probes gave a legal move, and how many of those were
 * written as a Notation slip. */
function tally(probes: Probe[]): Tally[] {
  const byTemplate = new Map<string, Tally>()
  for (const probe of probes) {
    const key = probe.template.id ?? `unsaved:${probe.template.system_prompt}\0${probe.template.turn_template}`
    const entry = byTemplate.get(key) ?? { name: templateName(probe.template), legal: 0, slips: 0, total: 0 }
    entry.total += 1
    entry.legal += probe.attempt.result === 'legal' ? 1 : 0
    entry.slips += probe.attempt.notation_slip ? 1 : 0
    byTemplate.set(key, entry)
  }
  return [...byTemplate.values()]
}

const tallyLine = ({ name, legal, slips, total }: Tally) =>
  `${name}: ${legal} of ${total} legal${slips > 0 ? ` (${slips} ${slips === 1 ? 'slip' : 'slips'})` : ''}`

export function Probes({ game, turn, tryBlocked, pauseFirst, picked, onPick, onEdit }: ProbesProps) {
  const side = game.settings[turn.color]
  const library = useQuery(promptLibraryQuery)
  const probes = useQuery(probesQuery(game.game_id))
  const { ask, last, waiting } = useProbeTurn(game, turn, pauseFirst)
  if (side.player !== 'llm') return null
  // The template the game recorded for the side, by its versioned ID; offered first when the library no longer lists
  // it (an older version, or a hidden one), and asked for by no ID, so the backend uses the recorded text.
  const inGame = game.prompt_template_ids[turn.color]
  const fitting = fittingTemplates(library.data ?? [], side.llm_constraints)
  const templates: { id: string; name: string | null }[] = fitting.some((entry) => entry.id === inGame)
    ? fitting
    : [...(inGame ? [{ id: inGame, name: null }] : []), ...fitting]
  const chosen = templates.find((entry) => entry.id === picked) ?? templates.find((entry) => entry.id === inGame)
  const blocked =
    tryBlocked ??
    (waiting ??
      (chosen === undefined
        ? library.isPending
          ? 'The Prompt library is loading.'
          : 'No Prompt template fits what this LLM is given.'
        : undefined))
  const tryChosen = () =>
    chosen &&
    ask({
      ply: turn.ply,
      color: turn.color,
      prompt_template_id: chosen.id === inGame ? null : chosen.id,
    })
  const meaning = pauseFirst ? TRY_PAUSING : TRY
  const shown = probesOf(probes.data ?? [], turn)
  return (
    <div role="group" aria-label="Probes of this turn" className="mb-3 flex flex-col gap-2 border-b pb-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-muted-foreground">Prompt:</span>
        {/* The name opens the dock; the arrow beside it drops down the library. */}
        <div className="flex min-w-0 items-center rounded-3xl bg-card">
          <Tooltip>
            <TooltipTrigger render={<span className="min-w-0" />}>
              <Button
                size="sm"
                variant="ghost"
                className="max-w-full rounded-r-none pr-1.5"
                aria-description={EDIT}
                disabled={!onEdit || chosen === undefined}
                onClick={(event) => chosen && onEdit?.(chosen.id, event.currentTarget)}
              >
                <span className="truncate">{chosen ? templateName(chosen) : '…'}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{EDIT}</TooltipContent>
          </Tooltip>
          <Select value={chosen?.id ?? null} onValueChange={(id) => id && onPick(id)}>
            <SelectTrigger
              size="sm"
              aria-label="Prompt to try"
              aria-description={PICKER}
              className="rounded-l-none bg-transparent pl-1"
            >
              <SelectValue className="sr-only">{() => (chosen ? templateName(chosen) : '…')}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {templates.map((entry) => (
                <SelectItem key={entry.id} value={entry.id}>
                  {templateName(entry)}
                  {entry.id === inGame && <span className="text-muted-foreground"> (in the game)</span>}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Tooltip>
          {/* The tooltip hangs on a wrapper, as a disabled button takes no hover. */}
          <TooltipTrigger render={<span />}>
            <Button
              size="sm"
              variant="secondary"
              aria-description={blocked ?? meaning}
              disabled={blocked !== undefined}
              onClick={tryChosen}
            >
              <FlaskConical aria-hidden="true" />
              Try
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">{blocked ?? meaning}</TooltipContent>
        </Tooltip>
      </div>
      {last?.status === 'error' && <p className="text-sm text-destructive">{last.error?.message}</p>}
      {probes.isError && <p className="text-sm text-destructive">{probes.error.message}</p>}
      {library.isError && (
        <p className="text-sm text-destructive">
          {`The Prompt library could not be loaded: ${library.error.message}. Try asks with the game's own Prompt.`}
        </p>
      )}
      {shown.length > 0 && (
        <>
          <p className="text-xs text-muted-foreground" data-testid="probe-tally">
            {tally(shown).map(tallyLine).join(' · ')}
          </p>
          <ol aria-label="Probes" className="flex flex-col gap-1">
            {shown.map((probe, index) => (
              <ProbeItem key={index} probe={probe} />
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

/** One probe on a line, its move, result, template and latency; opened, its Thinking or Reasoning and its Prompt. */
function ProbeItem({ probe }: { probe: Probe }) {
  const { attempt } = probe
  const result = attempt.result && RESULT_NAMES[attempt.result]
  const latency = attempt.latency_s === null ? null : `${attempt.latency_s.toFixed(1)} s`
  const decision = decisionOf(probe.side.thinking ? 'Thinking' : 'Reasoning', attempt)
  return (
    <li className="rounded-md bg-muted">
      <Collapsible>
        <CollapsibleTrigger className="group flex w-full cursor-pointer flex-wrap items-center gap-1.5 px-2 py-1 text-left text-xs">
          <ChevronRight aria-hidden="true" className="size-3 transition-transform group-data-[panel-open]:rotate-90" />
          <span className="font-mono font-medium">{attempt.san ?? attempt.move ?? 'no answer'}</span>
          {result && <Badge variant={attempt.result === 'legal' ? 'secondary' : 'destructive'}>{result}</Badge>}
          {attempt.notation_slip && (
            // A Notation slip, as the moves card shows one: the legal move, and how it was written.
            <span className="inline-flex items-center gap-1 rounded-3xl bg-slip/10 px-2 text-slip">
              <PenLine aria-hidden="true" className="size-3" />
              {`written "${attempt.move}"`}
            </span>
          )}
          <span className="text-muted-foreground">{templateName(probe.template)}</span>
          {latency && <span className="text-muted-foreground tabular-nums">{latency}</span>}
        </CollapsibleTrigger>
        <CollapsibleContent className="flex flex-col gap-2 border-t px-2 py-1.5">
          <p className={decision.quiet ? quiet : `${prose} text-sm`}>{decision.text}</p>
          <PromptMessages messages={attempt.prompt ?? null} />
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}
