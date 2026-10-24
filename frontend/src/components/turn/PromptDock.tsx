// The Prompt lab's dock (CONTEXT.md: Prompt library), opened from the name in the Prompt tab's row: a Prompt template
// in one text box over the lower half of the page, the board enlarged in the top half, so the researcher changes the
// prompt with the position in view. Try probes the turn with the text as it is, saved or not; Save as new version
// adds it to the library with a new ID, and the version it was based on stays as it was. The text being changed is a
// DockDraft the Turn panel holds, so it outlives the panel's tabs.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { EyeOff, Play, Save, X } from 'lucide-react'
import { useEffect, useEffectEvent } from 'react'
import { createPortal } from 'react-dom'
import { hidePromptTemplate, savePromptTemplate } from '@/api/client'
import { promptLibraryQuery } from '@/api/promptLibrary'
import type { Attempt, LlmTurn, Probe, ProbeRequest, PromptTemplateInfo } from '@/api/types'
import type { DockDraft } from '@/components/turn/dockDraft'
import { mono, nameOf, RESULT_NAMES } from '@/components/turn/styles'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import './prompt-dock.css'

const ASK_WITH_TEXT = "Ask the LLM about this turn's position again with the text as it is, saved or not: a Probe."
const PAUSES_FIRST =
  "Pauses the game after the turn running, then asks the LLM about this turn's position again with the text as it is, saved or not: a Probe."
const SAVE = 'Save this as a new Prompt template, with a new ID; the one it is based on stays as it was.'
const UNCHANGED = 'Nothing changed yet: change the text to save it as a new version.'
const BASED_ON = 'The Prompt template the text started from. Saving makes a new one; this one never changes.'
const NAME = 'A name to recognise the new version by, if you like.'
const CLOSE =
  'Close the dock, back to the whole page. Its text is kept for this turn and Prompt template, until the dock opens on another.'
const hideMeaning = (name: string) =>
  `Leave ${name} out of the lists of Prompt templates from now on. The games and probes that played it keep it.`
// The page's side columns, greyed out and inert while the dock is open: only the board and the prompt hold attention.
const SIDE_COLUMNS = '.game-column, .moves-column'

type LlmConstraints = PromptTemplateInfo['fits'][number]

type PromptDockProps = {
  turn: LlmTurn
  draft: DockDraft
  /** The draft changed, or the dock closed (open: false). */
  onDraft: (draft: DockDraft) => void
  /** The side's, which a saved version must fit. */
  llmConstraints: LlmConstraints
  /** The turn's probes, and those asked and not answered yet. */
  probes: Probe[]
  asked: readonly ProbeRequest[]
  /** Asks a Probe as the row's Try does: at once, or after the game pauses. */
  onAsk: (request: ProbeRequest) => void
  /** Why no Probe can be asked now, if none can. */
  askDisabled?: string
  /** Whether asking pauses the running game first. */
  pausesFirst: boolean
  /** A version saved, now in the library. */
  onSaved: (saved: PromptTemplateInfo) => void
}

export function PromptDock(props: PromptDockProps) {
  const { turn, draft, onDraft, llmConstraints, probes, asked, onAsk, askDisabled, pausesFirst, onSaved } = props
  const { from, systemPrompt, turnTemplate, part } = draft
  const edited = systemPrompt !== from.system_prompt || turnTemplate !== from.turn_template
  const change = (changed: Partial<DockDraft>) => onDraft({ ...draft, ...changed })

  const closeDock = () => onDraft({ ...draft, open: false })
  const close = useEffectEvent(closeDock)
  useEffect(() => {
    const columns = document.querySelectorAll(SIDE_COLUMNS)
    document.body.classList.add('prompt-dock-open')
    columns.forEach((column) => column.setAttribute('inert', ''))
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.classList.remove('prompt-dock-open')
      columns.forEach((column) => column.removeAttribute('inert'))
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  const request: ProbeRequest = edited
    ? { ply: turn.ply, color: turn.color, system_prompt: systemPrompt, turn_template: turnTemplate }
    : { ply: turn.ply, color: turn.color, prompt_template_id: from.id }
  // This version's last probe of the turn: one asked with this very text, still being asked or landed.
  const asking = asked.some((each) =>
    edited
      ? each.system_prompt === systemPrompt && each.turn_template === turnTemplate
      : each.prompt_template_id === from.id,
  )
  const landed = probes.findLast(
    (probe) =>
      probe.prompt_template.system_prompt === systemPrompt && probe.prompt_template.turn_template === turnTemplate,
  )

  const queryClient = useQueryClient()
  const hiding = useMutation({
    mutationFn: () => hidePromptTemplate(from.id),
    onSuccess: (listed) => queryClient.setQueryData(promptLibraryQuery.queryKey, listed),
  })
  const saving = useMutation({
    mutationFn: () =>
      savePromptTemplate({
        name: draft.name.trim() || null,
        system_prompt: systemPrompt,
        turn_template: turnTemplate,
        llm_constraints: llmConstraints,
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(promptLibraryQuery.queryKey, (before) => [...(before ?? []), saved])
      hiding.reset()
      onDraft({ ...draft, from: saved, name: '' })
      onSaved(saved)
    },
  })
  const hidden = hiding.isSuccess

  const askMeaning = askDisabled ?? (pausesFirst ? PAUSES_FIRST : ASK_WITH_TEXT)
  const label = part === 'system' ? 'System prompt' : 'Turn template'
  const error = saving.error ?? hiding.error
  return createPortal(
    <div
      role="region"
      aria-label="Dock"
      className="fixed inset-x-0 bottom-0 z-40 flex h-[50svh] flex-col border-t bg-background text-sm shadow-lg"
    >
      <div className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col gap-3 px-6 pt-4 pb-6">
        <div className="flex items-center gap-3">
          <Tooltip>
            <TooltipTrigger render={<span className="text-xs text-muted-foreground" />}>
              {`based on ${nameOf(from)}`}
            </TooltipTrigger>
            <TooltipContent side="top">{BASED_ON}</TooltipContent>
          </Tooltip>
          {from.saved && (
            <Tooltip>
              <TooltipTrigger render={<span />}>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-description={hideMeaning(nameOf(from))}
                  disabled={hidden || hiding.isPending}
                  onClick={() => hiding.mutate()}
                >
                  <EyeOff aria-hidden="true" />
                  {hidden ? 'Hidden' : 'Hide'}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">{hideMeaning(nameOf(from))}</TooltipContent>
            </Tooltip>
          )}
          <Tabs value={part} onValueChange={(value) => change({ part: value as DockDraft['part'] })} className="ml-auto">
            <TabsList aria-label="Part of the prompt">
              <TabsTrigger value="system">System prompt</TabsTrigger>
              <TabsTrigger value="turn">Turn template</TabsTrigger>
            </TabsList>
          </Tabs>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button variant="ghost" size="icon-sm" aria-label="Close" aria-description={CLOSE} onClick={closeDock} />
              }
            >
              <X aria-hidden="true" />
            </TooltipTrigger>
            <TooltipContent side="top">{CLOSE}</TooltipContent>
          </Tooltip>
        </div>
        <textarea
          aria-label={label}
          spellCheck={false}
          className={`${mono} min-h-0 w-full flex-1 resize-none rounded-md border bg-background p-3`}
          value={part === 'system' ? systemPrompt : turnTemplate}
          onChange={(event) =>
            change(part === 'system' ? { systemPrompt: event.target.value } : { turnTemplate: event.target.value })
          }
        />
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error.message}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex flex-col gap-1">
            <AnswerLine label="In the game" attempt={turn.attempts.at(-1) ?? null} />
            <AnswerLine label="This version" attempt={landed?.attempt ?? null} asking={asking} />
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger
                render={
                  <input
                    aria-label="Name"
                    aria-description={NAME}
                    placeholder="Name"
                    value={draft.name}
                    onChange={(event) => change({ name: event.target.value })}
                    className="h-8 w-32 rounded-3xl bg-input/50 px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
                  />
                }
              />
              <TooltipContent side="top">{NAME}</TooltipContent>
            </Tooltip>
            {/* The tooltips hang on wrappers, as a disabled button takes no hover. */}
            <Tooltip>
              <TooltipTrigger render={<span />}>
                <Button
                  variant="outline"
                  size="sm"
                  aria-description={edited ? SAVE : UNCHANGED}
                  disabled={!edited || saving.isPending}
                  onClick={() => saving.mutate()}
                >
                  <Save aria-hidden="true" />
                  Save as new version
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">{edited ? SAVE : UNCHANGED}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger render={<span />}>
                <Button
                  size="sm"
                  aria-description={askMeaning}
                  disabled={askDisabled !== undefined}
                  onClick={() => onAsk(request)}
                >
                  <Play aria-hidden="true" />
                  Try
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">{askMeaning}</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}

/** One answer on one line: its move and result; its Thinking or Reasoning on hover. */
function AnswerLine({ label, attempt, asking = false }: { label: string; attempt: Attempt | null; asking?: boolean }) {
  const move = attempt && (attempt.san ?? attempt.move)
  const result = attempt?.result ? RESULT_NAMES[attempt.result] : ''
  const decision = attempt && (attempt.thinking ?? attempt.reasoning ?? attempt.error)
  const shown = asking ? (
    <Badge variant="outline">asking…</Badge>
  ) : attempt ? (
    <Badge variant={attempt.result === 'legal' ? 'secondary' : 'destructive'} className="max-w-48 truncate">
      {move === null ? result : `${move} · ${result}`}
    </Badge>
  ) : (
    <span className="text-xs text-muted-foreground">Not tried yet</span>
  )
  return (
    <Tooltip disabled={!decision || asking}>
      <TooltipTrigger render={<div className="flex items-center gap-2" />}>
        <span className="w-24 text-xs text-muted-foreground">{label}</span>
        {shown}
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-md">
        {decision}
      </TooltipContent>
    </Tooltip>
  )
}
