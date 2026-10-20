// The ⚙ Preferences button at the end of the top bar and its panel: preferences of this browser, not of a game.
import { Settings } from 'lucide-react'
import { useState } from 'react'
import { isMoveSoundOn, setMoveSoundOn } from '@/components/board/moveSound'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const MOVE_SOUND_EXPLANATION = 'A click on every move. Applies at once, in this browser.'

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
      </PopoverContent>
    </Popover>
  )
}

/** The row is the Tooltip's trigger, so hovering its name or focusing its switch shows the explanation. */
function MoveSound() {
  const [on, setOn] = useState(isMoveSoundOn)
  return (
    <Tooltip>
      <TooltipTrigger render={<label className="flex items-center justify-between gap-4 font-medium" />}>
        Move sound
        <Switch
          aria-label="Move sound"
          aria-description={MOVE_SOUND_EXPLANATION}
          checked={on}
          onCheckedChange={(value) => {
            setMoveSoundOn(value)
            setOn(value)
          }}
        />
      </TooltipTrigger>
      <TooltipContent side="bottom">{MOVE_SOUND_EXPLANATION}</TooltipContent>
    </Tooltip>
  )
}
