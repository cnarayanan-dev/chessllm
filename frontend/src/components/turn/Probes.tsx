// Probes (CONTEXT.md, ADR 0010), at the top of the Turn panel's Prompt tab with Prompt lab on: one row, the Prompt
// template to probe with and Try, which asks the LLM about the turn's position again, outside the game; then the turn's
// probes, newest first, with a tally per template. The probes come from the game's probe log, so a reload keeps them.
import { useMutation, useMutationState, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, PenLine, Play } from 'lucide-react'
import { askProbe } from '@/api/client'
import { probesQuery } from '@/api/probes'
import { promptLibraryQuery } from '@/api/promptLibrary'
import type { GameState, LlmTurn, Probe, ProbeRequest, PromptTemplateInfo } from '@/api/types'
import { Prompt } from '@/components/turn/PromptMessages'
import { quiet, RESULT_NAMES } from '@/components/turn/styles'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { fittingTemplates } from '@/settings/next-game'

const ASK = "Ask the LLM about this turn's position again with this prompt, outside the game: a Probe."
const TURN_RUNNING = 'An LLM turn is running. Probe once it has landed: a Probe never runs alongside a turn.'
const LOADING = 'The Prompt library is loading.'
const PICKER = 'The Prompt template a Probe asks with. "In the game" is the one the LLM played this game with.'

type ProbesProps = {
  game: GameState
  turn: LlmTurn
  /** Whether an LLM turn is running, so no Probe can be asked. */
  llmTurnRunning: boolean
  /** The Prompt template last picked to probe with, or null for the game's own. */
  pickedTemplateId: string | null
  onPick: (templateId: string) => void
}

const nameOf = (template: { id: string; name: string | null }) => template.name ?? template.id
const sameTurn = (turn: LlmTurn) => (probe: { ply: number; color: string }) =>
  probe.ply === turn.ply && probe.color === turn.color

export function Probes({ game, turn, llmTurnRunning, pickedTemplateId, onPick }: ProbesProps) {
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

  const queryClient = useQueryClient()
  const listed = probesQuery(game.game_id)
  const probes = (useQuery(listed).data ?? []).filter(sameTurn(turn))
  const mutationKey = ['probe', game.game_id]
  const asking = useMutation({
    mutationKey,
    mutationFn: (request: ProbeRequest) => askProbe(request),
    onSuccess: (probe) => queryClient.setQueryData(listed.queryKey, (before) => [...(before ?? []), probe]),
  })
  // Every probe of the turn still being asked, from this panel or another turn's.
  const pending = useMutationState({
    filters: { mutationKey, status: 'pending' },
    select: (mutation) => mutation.state.variables as ProbeRequest,
  }).filter(sameTurn(turn))

  const disabled = llmTurnRunning ? TURN_RUNNING : picked ? undefined : LOADING
  const ask = () => picked && asking.mutate({ ply: turn.ply, color: turn.color, prompt_template_id: picked.id })
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5">
        <Select value={picked?.id ?? null} onValueChange={(id) => id && onPick(id)}>
          <SelectTrigger aria-label="Prompt to probe with" aria-description={PICKER} size="sm" className="min-w-0 flex-1">
            <SelectValue>
              {() => (
                <span className="truncate">
                  <span className="text-muted-foreground">Prompt: </span>
                  {picked ? nameOf(picked) : '…'}
                </span>
              )}
            </SelectValue>
          </SelectTrigger>
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
        {/* The tooltip hangs on a wrapper, as a disabled button takes no hover. */}
        <Tooltip>
          <TooltipTrigger render={<span />}>
            <Button size="sm" aria-description={disabled ?? ASK} disabled={disabled !== undefined} onClick={ask}>
              <Play aria-hidden="true" />
              Try
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">{disabled ?? ASK}</TooltipContent>
        </Tooltip>
      </div>
      {asking.isError && (
        <p role="alert" className="text-sm text-destructive">
          {asking.error.message}
        </p>
      )}
      {(probes.length > 0 || pending.length > 0) && (
        <>
          <Tally probes={probes} />
          <ol aria-label="Probes" className="flex flex-col gap-1.5">
            {pending.map((_, index) => (
              <li key={`pending-${index}`} className="rounded-md border border-dashed px-2 py-1.5">
                <Badge variant="outline">asking…</Badge>
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
