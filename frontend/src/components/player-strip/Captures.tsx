// What follows the name in a player strip: the pieces the side has taken, its spawned pieces in the Spawn purple,
// and +N on the side ahead, all of the position on the board (from `material` in `@/game/material`).
import { Sparkles } from 'lucide-react'
import type { Color } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { KINDS, type Material, type Pieces } from '@/game/material'

const NAME = { p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' } as const

/** Small Merida pieces of one colour, smallest first, the same kind overlapping; named for screen readers. */
function PieceRow({ counts, color, label }: { counts: Pieces; color: Color; label: string }) {
  const kinds = KINDS.filter((kind) => counts[kind] > 0)
  const names = kinds.flatMap((kind) => Array<string>(counts[kind]).fill(NAME[kind]))
  return (
    <span role="img" aria-label={`${label}: ${names.join(', ')}`} className="flex items-center gap-1">
      {kinds.map((kind) => (
        <span key={kind} className="flex [&>svg+svg]:-ml-2.5">
          {Array.from({ length: counts[kind] }, (_, index) => (
            <svg key={index} viewBox="0 0 40 40" aria-hidden="true" className="size-5.5 flex-none">
              <use href={`/static/pieces/merida.svg#${color[0]}${kind}`} />
            </svg>
          ))}
        </span>
      ))}
    </span>
  )
}

const any = (counts: Pieces) => KINDS.some((kind) => counts[kind] > 0)

export function Captures({ material, color }: { material: Material; color: Color }) {
  const { taken, spawned, ahead } = material
  return (
    <span className="flex min-w-0 items-center gap-1.5 overflow-hidden">
      {any(taken) && <PieceRow counts={taken} color={color === 'white' ? 'black' : 'white'} label="Took" />}
      {any(spawned) && (
        <span className="flex flex-none items-center gap-0.5 rounded-full bg-spawn/14 py-0.5 pr-1.5 pl-1 text-spawn">
          <Sparkles className="size-3.5" aria-hidden="true" />
          <PieceRow counts={spawned} color={color} label="Spawned" />
        </span>
      )}
      {ahead > 0 && (
        <Badge data-testid="ahead" variant="secondary" className="tabular-nums">
          +{ahead}
        </Badge>
      )}
    </span>
  )
}
