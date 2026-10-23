// The dock (Prompt lab): the Prompt template of the Prompt tab's row, written over in one text box docked over the
// lower half of the page, the position still in view above. Try asks with the text as it is, saved or not; Save as new
// version adds it to the Prompt library with a new ID, never changing the template it started from (ADR 0010).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { EyeOff, FlaskConical, Save, X } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { hidePromptTemplate, savePromptTemplate } from '@/api/client'
import { probesQuery } from '@/api/probes'
import { promptLibraryQuery, promptTemplateQuery } from '@/api/promptLibrary'
import type { Attempt, GameState, LlmTurn, PromptTemplateInfo } from '@/api/types'
import { decisionOf, quiet, RESULT_NAMES, templateName } from '@/components/turn/attempt'
import { useProbeTurn } from '@/components/turn/useProbeTurn'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

type Part = 'system_prompt' | 'turn_template'
type Text = Record<Part, string>

const PARTS: { part: Part; name: string; meaning: string }[] = [
  { part: 'system_prompt', name: 'System prompt', meaning: 'The instructions that open every Prompt.' },
  { part: 'turn_template', name: 'Turn template', meaning: "The message of every turn, the position's placeholders filled in." },
]
const TRY = 'Ask the LLM again about the position before this turn, with the text as it is, saved or not.'
const SAVE = 'Add the text to the Prompt library as a new Prompt template, with a new ID. The one it is based on stays as it is.'
const UNCHANGED = 'Nothing has changed yet.'
const NAME = 'A name to recognise it by in the lists; optional.'
const CLOSE = 'Keeps nothing unsaved. (Esc)'
const hideMeaning = (name: string) =>
  `Leave ${name} out of the Prompt pickers for good. It is never deleted: the games and probes that used it keep it.`

type PromptDockProps = {
  game: GameState
  turn: LlmTurn
  /** The template the text starts from, by its ID: the one the row named, listed in the library or not. */
  baseId: string
  /** Why Try can't probe now (an LLM turn runs); undefined when it can. */
  tryBlocked?: string
  /** A Save as new version landed: the template saved, which the text is now based on. */
  onSaved: (template: PromptTemplateInfo) => void
  onClose: () => void
}

/** The dock: it takes the focus when it opens and closes on Esc; its editor once the template's text is in. */
export function PromptDock({ game, turn, baseId, tryBlocked, onSaved, onClose }: PromptDockProps) {
  const queryClient = useQueryClient()
  const base = useQuery(promptTemplateQuery(queryClient, baseId))
  const dock = useRef<HTMLElement>(null)
  // The focus leaves the name's button, set aside under the dock: to the text box once the editor is in (its own
  // effect runs first), else to the dock itself, so Esc is heard.
  useEffect(() => {
    if (!dock.current?.contains(document.activeElement)) dock.current?.focus()
  }, [])
  const closeOnEscape = (event: KeyboardEvent) => {
    if (event.key !== 'Escape' || event.defaultPrevented) return
    event.preventDefault()
    onClose()
  }
  return (
    <section
      ref={dock}
      role="region"
      aria-label="Prompt editor"
      tabIndex={-1}
      onKeyDown={closeOnEscape}
      className="fixed inset-x-0 bottom-0 z-40 flex h-[50svh] flex-col gap-2 border-t bg-card px-4 pt-3 pb-4 text-sm shadow-[0_-8px_24px_rgb(0_0_0/0.08)] outline-none sm:px-8"
    >
      {base.data ? (
        <Editor game={game} turn={turn} base={base.data} tryBlocked={tryBlocked} onSaved={onSaved} onClose={onClose} />
      ) : (
        <div className="flex items-center gap-2">
          <p className={base.isError ? 'text-destructive' : quiet}>
            {base.isError ? base.error.message : `Loading ${baseId}…`}
          </p>
          <CloseButton onClose={onClose} />
        </div>
      )}
    </section>
  )
}

function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <Hinted hint={`Close the editor. ${CLOSE}`}>
      <Button size="icon-sm" variant="ghost" aria-label="Close the editor" aria-description={CLOSE} onClick={onClose}>
        <X aria-hidden="true" />
      </Button>
    </Hinted>
  )
}

type EditorProps = Omit<PromptDockProps, 'baseId'> & { base: PromptTemplateInfo }

function Editor({ game, turn, base, tryBlocked, onSaved, onClose }: EditorProps) {
  const side = game.settings[turn.color]
  const [text, setText] = useState<Text>({ system_prompt: base.system_prompt, turn_template: base.turn_template })
  const [part, setPart] = useState<Part>('system_prompt')
  const [name, setName] = useState('')
  const box = useRef<HTMLTextAreaElement>(null)
  useEffect(() => box.current?.focus(), [])
  const queryClient = useQueryClient()
  const probes = useQuery(probesQuery(game.game_id))
  const { ask, last } = useProbeTurn(game, turn)
  /** The library changed: the template is kept by its ID as it now is, and the list read again. */
  const landed = (template: PromptTemplateInfo) => {
    queryClient.setQueryData(promptTemplateQuery(queryClient, template.id).queryKey, template)
    void queryClient.invalidateQueries({ queryKey: promptLibraryQuery.queryKey })
  }
  const saving = useMutation({
    mutationFn: () =>
      side.player === 'llm'
        ? savePromptTemplate({ name: name.trim() || null, ...text, llm_constraints: side.llm_constraints })
        : Promise.reject(new Error('Only an LLM side has a Prompt template.')),
    onSuccess: (saved) => {
      queryClient.setQueryData(promptLibraryQuery.queryKey, (library = []) =>
        library.some((entry) => entry.id === saved.id) ? library : [...library, saved],
      )
      landed(saved)
      setName('')
      onSaved(saved)
    },
  })
  const hiding = useMutation({ mutationFn: () => hidePromptTemplate(base.id), onSuccess: landed })
  const edit = (changed: Partial<Text>) => {
    setText((now) => ({ ...now, ...changed }))
    saving.reset() // a refused save's reason was about the text as it was
  }
  const changed = text.system_prompt !== base.system_prompt || text.turn_template !== base.turn_template
  const inGame = game.prompt_template_ids[turn.color]
  const tryChosen = () =>
    ask(
      changed
        ? { ply: turn.ply, color: turn.color, ...text }
        : { ply: turn.ply, color: turn.color, prompt_template_id: base.id === inGame ? null : base.id },
    )
  const blocked = tryBlocked ?? (last?.status === 'pending' ? 'Asking the LLM…' : undefined)
  const unsaveable = saving.isPending ? 'Saving…' : changed ? undefined : UNCHANGED
  // This version's last answer: the turn's last probe asked with exactly this text, saved or not.
  const thisVersion = (probes.data ?? [])
    .filter((probe) => probe.ply === turn.ply && probe.color === turn.color)
    .findLast(
      (probe) =>
        probe.template.system_prompt === text.system_prompt && probe.template.turn_template === text.turn_template,
    )
  const kind = side.player === 'llm' && side.thinking ? 'Thinking' : 'Reasoning'
  const shownPart = PARTS.find((entry) => entry.part === part)!
  const baseName = templateName(base)
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Part shown" className="inline-flex rounded-3xl bg-muted p-0.5">
          {PARTS.map((entry) => (
            <Hinted key={entry.part} hint={entry.meaning}>
              <Button
                size="sm"
                variant={part === entry.part ? 'outline' : 'ghost'}
                aria-pressed={part === entry.part}
                aria-description={entry.meaning}
                onClick={() => setPart(entry.part)}
              >
                {entry.name}
              </Button>
            </Hinted>
          ))}
        </div>
        <span className="text-muted-foreground">{`based on ${baseName}${base.hidden ? ' (hidden)' : ''}`}</span>
        <div className="ml-auto flex items-center gap-1">
          {base.saved && !base.hidden && (
            // Only a saved template can be hidden; what hiding does is the confirmation, on hover and focus.
            <Hinted hint={hideMeaning(baseName)}>
              <Button
                size="sm"
                variant="ghost"
                aria-description={hideMeaning(baseName)}
                disabled={hiding.isPending}
                onClick={() => hiding.mutate()}
              >
                <EyeOff aria-hidden="true" />
                Hide
              </Button>
            </Hinted>
          )}
          <CloseButton onClose={onClose} />
        </div>
      </div>
      <textarea
        ref={box}
        aria-label={shownPart.name}
        aria-description={shownPart.meaning}
        value={text[part]}
        onChange={(event) => edit({ [part]: event.target.value })}
        spellCheck={false}
        className="min-h-0 flex-1 resize-none rounded-2xl border bg-background p-3 font-mono text-xs leading-relaxed outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
      />
      <AnswerLine label="In the game" attempt={turn.attempts.at(-1)} kind={kind} testId="in-the-game" />
      <AnswerLine
        label="This version"
        attempt={thisVersion?.attempt}
        kind={kind}
        testId="this-version"
        none={last?.status === 'pending' ? 'asking the LLM…' : 'not tried yet'}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Hinted hint={blocked ?? TRY}>
          <Button size="sm" variant="secondary" aria-description={blocked ?? TRY} disabled={blocked !== undefined} onClick={tryChosen}>
            <FlaskConical aria-hidden="true" />
            Try
          </Button>
        </Hinted>
        <Hinted hint={NAME}>
          <input
            aria-label="Name"
            aria-description={NAME}
            placeholder="Name (optional)"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="h-8 w-44 rounded-3xl border border-transparent bg-input/50 px-3 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
          />
        </Hinted>
        <Hinted hint={unsaveable ?? SAVE}>
          <Button
            size="sm"
            aria-description={unsaveable ?? SAVE}
            disabled={unsaveable !== undefined}
            onClick={() => saving.mutate()}
          >
            <Save aria-hidden="true" />
            Save as new version
          </Button>
        </Hinted>
      </div>
      {saving.isError && <p className="text-destructive">{saving.error.message}</p>}
      {hiding.isError && <p className="text-destructive">{hiding.error.message}</p>}
      {last?.status === 'error' && <p className="text-destructive">{last.error?.message}</p>}
    </>
  )
}

/** A control with its explanation in a Tooltip, on a wrapper, as a disabled button takes no hover. */
function Hinted({ hint, children }: { hint: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger render={<span />}>{children}</TooltipTrigger>
      <TooltipContent side="top">{hint}</TooltipContent>
    </Tooltip>
  )
}

type AnswerLineProps = {
  label: string
  attempt: Attempt | undefined
  kind: 'Thinking' | 'Reasoning'
  testId: string
  /** What the line says without an answer. */
  none?: string
}

/** An answer on one line, its move and result; its Thinking or Reasoning on hover and keyboard focus. */
function AnswerLine({ label, attempt, kind, testId, none = 'none' }: AnswerLineProps) {
  if (!attempt)
    return (
      <p data-testid={testId} className="text-muted-foreground">
        <span className="font-medium">{label}:</span> {none}
      </p>
    )
  const result = attempt.result && RESULT_NAMES[attempt.result]
  const decision = decisionOf(kind, attempt).text
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <p
            data-testid={testId}
            tabIndex={0}
            aria-description={decision}
            className="flex w-fit max-w-full items-center gap-1.5 truncate rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
          />
        }
      >
        <span className="font-medium text-muted-foreground">{label}:</span>{' '}
        <span className="font-mono font-medium">{attempt.san ?? attempt.move ?? 'no answer'}</span>{' '}
        {result && <Badge variant={attempt.result === 'legal' ? 'secondary' : 'destructive'}>{result}</Badge>}
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-md whitespace-pre-wrap">
        {decision}
      </TooltipContent>
    </Tooltip>
  )
}
