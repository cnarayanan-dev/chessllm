// Probes (CONTEXT.md, ADR 0010), at the top of the Turn panel's Prompt tab with Prompt lab on: one row, the Prompt
// template to probe with and Try, which asks the LLM about the turn's position again, outside the game; then the turn's
// probes, newest first, with a tally per template. The probes come from the game's probe log, so a reload keeps them.
// In a game that can pause, Try pauses it first and the probe is asked once it is paused (`@/game/gameLoop`).
// The template's name opens it in the dock (PromptDock), to change it, probe with it and save it as a new version; ▾
// lists the library.
import { useMutationState, useQuery } from '@tanstack/react-query'
import { ChevronRight, PenLine, Play } from 'lucide-react'
import { probeMutationKey, probesQuery, useAskProbe } from '@/api/probes'
import { promptLibraryQuery } from '@/api/promptLibrary'
import type { GameState, LlmTurn, Probe, ProbeRequest, PromptTemplateInfo } from '@/api/types'
import { draftFor, draftOf, type DockDraft } from '@/components/turn/dockDraft'
import { PromptDock } from '@/components/turn/PromptDock'
import { Prompt } from '@/components/turn/PromptMessages'
import { nameOf, quiet, RESULT_NAMES } from '@/components/turn/styles'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { PauseState } from '@/game/gameLoop'
import { fittingTemplates } from '@/settings/next-game'

const ASK = "Ask the LLM about this turn's position again with this prompt, outside the game: a Probe."
const PAUSES_FIRST =
  "Pauses the game after the turn running, then asks the LLM about this turn's position again with this prompt, outside the game: a Probe."
const TURN_RUNNING = 'An LLM turn is running. Probe once it has landed: a Probe never runs alongside a turn.'
const LOADING = 'The Prompt library is loading.'
const PICKER = 'Pick the Prompt template a Probe asks with. "In the game" is the one the LLM played this game with.'
const OPEN = 'Open this Prompt template in the dock, the board in view: change it, probe with it, save it as a new version.'

type ProbesProps = {
  game: GameState
  turn: LlmTurn
  /** Whether an LLM turn is running, so no Probe can be asked. */
  llmTurnRunning: boolean
  /** The Prompt template last picked to probe with, or null for the game's own. */
  pickedTemplateId: string | null
  onPick: (templateId: string) => void
  /** The game's Pause, or null when it can't pause (Play LLM): then no Probe is asked while an LLM turn runs. */
  pause?: PauseState | null
  /** Asks a Probe once the game has paused, pausing it first: Try while the game runs. */
  onProbeAfterPause?: (request: ProbeRequest) => void
  /** The Probes waiting for the pause. */
  waiting?: readonly ProbeRequest[]
  /** The dock's text, kept by the Turn panel, so the panel's tabs coming and going never lose it; null before any. */
  dock?: DockDraft | null
  onDock?: (draft: DockDraft) => void
}

const sameTurn = (turn: LlmTurn) => (probe: { ply: number; color: string }) =>
  probe.ply === turn.ply && probe.color === turn.color

const NONE: readonly ProbeRequest[] = []

export function Probes({
  game,
  turn,
  llmTurnRunning,
  pickedTemplateId,
  onPick,
  pause = null,
  onProbeAfterPause,
  waiting = NONE,
  dock = null,
  onDock,
}: ProbesProps) {
  const side = game.settings[turn.color]
  const constraints = side.player === 'llm' ? side.llm_constraints : 'free'
  const library = useQuery(promptLibraryQuery)
  const fitting = fittingTemplates(library.data ?? [], constraints)
  // The template the side played the game with, which the list may not offer: a hidden one, or Moves, which shows a
  // fresh Prompt no position. Then the Default of its constraints is picked first, and nothing is marked.
  const played = game.prompt_templates?.[turn.color]
  const inGame = (template: PromptTemplateInfo) => template.id === played?.id
  const unlisted = played && library.data && !fitting.some(inGame) ? played : undefined
  const picked =
    fitting.find((template) => template.id === pickedTemplateId) ??
    fitting.find(inGame) ??
    fitting.find((template) => template.default_for.includes(constraints)) ??
    fitting[0]

  const probes = (useQuery(probesQuery(game.game_id)).data ?? []).filter(sameTurn(turn))
  const mutationKey = probeMutationKey(game.game_id)
  const asking = useAskProbe(game.game_id)
  // Every probe of the turn still being asked, from this panel, another turn's or after a Pause.
  const pending = useMutationState({
    filters: { mutationKey, status: 'pending' },
    select: (mutation) => mutation.state.variables as ProbeRequest,
  }).filter(sameTurn(turn))
  // The error of the last probe asked, whichever asked it, if it failed.
  const failed = useMutationState({ filters: { mutationKey }, select: (mutation) => mutation.state.error }).at(-1)

  // While the game runs, Try pauses it first, so a probe never runs alongside a turn.
  const pausesFirst = pause === 'playing' || pause === 'pausing'
  const disabled = llmTurnRunning && pause === null ? TURN_RUNNING : picked ? undefined : LOADING
  const ask = (request: ProbeRequest) => {
    if (pausesFirst && onProbeAfterPause) onProbeAfterPause(request)
    else asking.mutate(request)
  }
  // The dock opens on the draft left for this template and turn of the game, or a new one.
  const ours = dock && draftFor(dock, game.game_id, turn) ? dock : null
  const kept = ours && picked && ours.from.id === picked.id ? ours : null
  const openDock = () => picked && onDock?.(kept ? { ...kept, open: true } : draftOf(picked, game.game_id, turn))
  const docked = ours?.open ? ours : null
  const meaning = disabled ?? (pausesFirst ? PAUSES_FIRST : ASK)
  // The probes of the turn waiting for the pause, then those being asked.
  const asked = [...waiting.filter(sameTurn(turn)).map(() => 'after the pause…'), ...pending.map(() => 'asking…')]
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5">
        <div className="flex min-w-0 flex-1 items-center rounded-3xl bg-input/50">
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="sm"
                  aria-description={OPEN}
                  disabled={!picked}
                  className="min-w-0 flex-1 justify-start"
                  onClick={openDock}
                />
              }
            >
              <span className="truncate">
                <span className="text-muted-foreground">Prompt: </span>
                {picked ? nameOf(picked) : '…'}
              </span>
            </TooltipTrigger>
            <TooltipContent side="bottom">{OPEN}</TooltipContent>
          </Tooltip>
          <Select value={picked?.id ?? null} onValueChange={(id) => id && onPick(id)}>
            <Tooltip>
              <TooltipTrigger
                render={
                  <SelectTrigger
                    aria-label="Prompt to probe with"
                    aria-description={PICKER}
                    size="sm"
                    className="shrink-0"
                  />
                }
              />
              <TooltipContent side="bottom">{`Prompt to probe with. ${PICKER}`}</TooltipContent>
            </Tooltip>
            <SelectContent>
              {fitting.map((template) => (
                <SelectItem key={template.id} value={template.id}>
                  {nameOf(template)}
                  {inGame(template) && <span className="text-xs text-muted-foreground"> · in the game</span>}
                </SelectItem>
              ))}
              {unlisted && (
                <p role="note" className="px-3 py-1.5 text-xs text-muted-foreground">
                  {`In the game: ${nameOf(unlisted)}, not in this list.`}
                </p>
              )}
            </SelectContent>
          </Select>
        </div>
        {/* The tooltip hangs on a wrapper, as a disabled button takes no hover. */}
        <Tooltip>
          <TooltipTrigger render={<span />}>
            <Button
              size="sm"
              aria-description={meaning}
              disabled={disabled !== undefined}
              onClick={() => picked && ask({ ply: turn.ply, color: turn.color, prompt_template_id: picked.id })}
            >
              <Play aria-hidden="true" />
              Try
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">{meaning}</TooltipContent>
        </Tooltip>
      </div>
      {failed && (
        <p role="alert" className="text-sm text-destructive">
          {failed.message}
        </p>
      )}
      {docked && onDock && (
        <PromptDock
          turn={turn}
          draft={docked}
          onDraft={onDock}
          llmConstraints={constraints}
          probes={probes}
          asked={[...waiting.filter(sameTurn(turn)), ...pending]}
          onAsk={ask}
          askDisabled={disabled === TURN_RUNNING ? disabled : undefined}
          pausesFirst={pausesFirst}
          onSaved={(saved) => onPick(saved.id)}
        />
      )}
      {(probes.length > 0 || asked.length > 0) && (
        <>
          <Tally probes={probes} />
          <ol aria-label="Probes" className="flex flex-col gap-1.5">
            {asked.map((label, index) => (
              <li key={`pending-${index}`} className="rounded-md border border-dashed px-2 py-1.5">
                <Badge variant="outline">{label}</Badge>
              </li>
            ))}
            {[...probes].reverse().map((probe) => (
              <ProbeRow key={probe.asked_at} probe={probe} chaosRules={game.settings.rules === 'chaos'} />
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

/** "Described: 2 of 3 legal" per template, so a handful of probes read as a small sample, not an anecdote. */
function Tally({ probes }: { probes: Probe[] }) {
  const by = new Map<string, Probe[]>()
  for (const probe of probes) by.set(probe.prompt_template.id, [...(by.get(probe.prompt_template.id) ?? []), probe])
  return (
    <ul aria-label="Tally" className="flex flex-col gap-0.5 text-xs text-muted-foreground">
      {[...by.values()].map((group) => (
        <li key={group[0].prompt_template.id}>
          {`${nameOf(group[0].prompt_template)}: ${group.filter((probe) => probe.attempt.result === 'legal').length} of ${group.length} legal`}
        </li>
      ))}
    </ul>
  )
}

/**
 * One probe: its move and result, a Notation slip marked as the move list marks it (never under Chaos rules), its
 * template and latency; opened, its Thinking or Reasoning and its Prompt.
 */
function ProbeRow({ probe, chaosRules }: { probe: Probe; chaosRules: boolean }) {
  const { attempt } = probe
  const result = attempt.result ? RESULT_NAMES[attempt.result] : ''
  const move = attempt.san ?? attempt.move
  const slip = attempt.notation_slip && !chaosRules
  const decision = (probe.thinking ? attempt.thinking : attempt.reasoning) ?? attempt.error
  return (
    <li className="rounded-md border border-dashed">
      <Collapsible>
        <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-2 px-2 py-1.5 text-left text-sm">
          <ChevronRight aria-hidden="true" className="size-3 shrink-0 transition-transform group-data-[panel-open]:rotate-90" />
          <Badge variant={attempt.result === 'legal' ? 'secondary' : 'destructive'} className="max-w-[50%] truncate">
            {move === null ? result : `${move} · ${result}`}
          </Badge>
          {slip && (
            <span className="flex shrink-0 items-center gap-1 text-xs text-slip">
              <PenLine aria-hidden="true" className="size-3" />
              {`written "${attempt.move}"`}
            </span>
          )}
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{nameOf(probe.prompt_template)}</span>
          {attempt.latency_s !== null && (
            <span className="text-xs text-muted-foreground tabular-nums">{`${attempt.latency_s.toFixed(1)} s`}</span>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent className="flex flex-col gap-2 border-t px-2 py-2">
          <p className={decision ? 'text-sm leading-relaxed whitespace-pre-wrap' : quiet}>
            {decision ?? `Its reply has no ${probe.thinking ? 'Thinking' : 'Reasoning'}.`}
          </p>
          <Prompt messages={attempt.prompt ?? null} />
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}
