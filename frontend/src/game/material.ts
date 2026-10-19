/*
  What a player strip shows after the name: the pieces the side has taken, the pieces it spawned, and +N. All of it
  is counted from the piece letters of the FENs the backend sent (ADR 0001): the page knows no chess rules.
*/
import type { Color, Ply } from '@/api/types'

/** A piece kind, as its FEN letter in lower case. */
export type Kind = 'p' | 'n' | 'b' | 'r' | 'q' | 'k'
export type Pieces = Record<Kind, number>

/** The order the pieces are shown in, the smallest first, as lichess does. */
export const KINDS: readonly Kind[] = ['p', 'n', 'b', 'r', 'q', 'k']
const VALUE: Pieces = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 }

const none = (): Pieces => ({ p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 })
const other = (color: Color): Color => (color === 'white' ? 'black' : 'white')

/** Each side's pieces in a FEN's placement field: upper case is White. */
function pieces(fen: string): Record<Color, Pieces> {
  const counts = { white: none(), black: none() }
  for (const letter of fen.split(' ')[0]) {
    const kind = letter.toLowerCase() as Kind
    if (kind in VALUE) counts[letter === kind ? 'black' : 'white'][kind] += 1
  }
  return counts
}

const points = (counts: Pieces) => KINDS.reduce((sum, kind) => sum + VALUE[kind] * counts[kind], 0)

/** A side's strip: what it took and spawned in `plies`, and how far ahead in material it is in `fen` (below 0: behind). */
export type Material = { taken: Pieces; spawned: Pieces; ahead: number }

/**
 * The strip of `color` for the position `fen`, reached by `plies`. Counted ply by ply, so under Chaos rules a Spawn
 * never hides a capture, nor a capture a Spawn.
 */
export function material(plies: readonly Ply[], fen: string, color: Color): Material {
  const taken = none()
  const spawned = none()
  for (const ply of plies) {
    if (ply.color !== color) continue
    const before = pieces(ply.fen_before)
    const after = pieces(ply.fen_after)
    for (const kind of KINDS) taken[kind] += Math.max(0, before[other(color)][kind] - after[other(color)][kind])
    // The side's own new pieces are spawned, but for the promotions its lost pawns explain, the queen first. On a
    // Spawn a lost pawn of its own was taken by the spawned piece, as the backend's resolution says (ADR 0006).
    let promoted = ply.resolution?.kind === 'spawn' ? 0 : Math.max(0, before[color].p - after[color].p)
    for (const kind of [...KINDS].reverse()) {
      const gained = Math.max(0, after[color][kind] - before[color][kind])
      const explained = Math.min(gained, promoted)
      promoted -= explained
      spawned[kind] += gained - explained
    }
  }
  const shown = pieces(fen)
  return { taken, spawned, ahead: points(shown[color]) - points(shown[other(color)]) }
}
