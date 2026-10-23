// The ⚙ Preferences button at the end of the top bar and its panel: preferences of this browser, not of a game.
import { Settings } from 'lucide-react'
import { useState } from 'react'
import { isMoveSoundOn, setMoveSoundOn } from '@/components/board/moveSound'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { setPromptLabOn, usePromptLab } from '@/settings/promptLab'

const MOVE_SOUND_EXPLANATION = 'A click on every move. Applies at once, in this browser.'
const PROMPT_LAB_EXPLANATION =
  "Tools for experimenting with prompts: pick each LLM's Prompt template in New game's Advanced settings. Off, every LLM plays its default one. In this browser."

export function Preferences() {
  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger
          render={<PopoverTrigger render={<Button variant="ghost" size="icon" aria-label="Preferences" />} />}
        >
          <Settings aria-hidden="true" />
        </TooltipTrigger>
        <TooltipContent side="bottom">Preferences</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" className="w-64">
        <PopoverTitle>Preferences</PopoverTitle>
        <MoveSound />
        <PromptLab />
      </PopoverContent>
    </Popover>
  )
}

function MoveSound() {
  const [on, setOn] = useState(isMoveSoundOn)
  return (
    <PreferenceSwitch
      name="Move sound"
      explanation={MOVE_SOUND_EXPLANATION}
      on={on}
      onChange={(value) => {
        setMoveSoundOn(value)
        setOn(value)
      }}
    />
  )
}

function PromptLab() {
  return <PreferenceSwitch name="Prompt lab" explanation={PROMPT_LAB_EXPLANATION} on={usePromptLab()} onChange={setPromptLabOn} />
}

/** The row is the Tooltip's trigger, so hovering its name or focusing its switch shows the explanation. */
function PreferenceSwitch({
  name,
  explanation,
  on,
  onChange,
}: {
  name: string
  explanation: string
  on: boolean
  onChange: (on: boolean) => void
}) {
  return (
    <Tooltip>
      <TooltipTrigger render={<label className="flex items-center justify-between gap-4 font-medium" />}>
        {name}
        <Switch aria-label={name} aria-description={explanation} checked={on} onCheckedChange={onChange} />
      </TooltipTrigger>
      <TooltipContent side="bottom">{explanation}</TooltipContent>
    </Tooltip>
  )
}
