/*
  Board flashes: a turn's result arrives at once, so its flashes appear together, laid over the board (a child of
  Board). The illegal tries are listed in a card in the middle of the board, and a Notation slip rings the square the
  move landed on. They show whatever the "Show LLM mistakes" switch says, and fade out after 7 seconds.
*/
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { LlmTurn } from '@/api/types'
import { illegalTry, played } from '@/game/chaos'
import type { Flash } from '@/game/gameLoop'
import './flashes.css'

/** How long the flashes stay up: 7 s, then the 0.4 s fade-out of flashes.css. */
const SHOWN_MS = 7400

type Box = { x: number; y: number; width: number; height: number }

// A chaos move was played, so it is shown on the board with its arrow, not as an illegal try here.
function CenterFlash({ turn, maxAttempts }: { turn: LlmTurn; maxAttempts: number }) {
  const illegal = turn.attempts.filter(illegalTry)
  const error = turn.attempts.find((attempt) => attempt.error)?.error // a forfeit with no answer
  const forfeit = !turn.attempts.some(played)
  if (!illegal.length && !forfeit) return null
  const head = !forfeit
    ? `✗ LLM move illegal${illegal.length > 1 ? ` ×${illegal.length}` : ''}`
    : error
      ? '✗ LLM forfeits: no answer'
      : `✗ LLM forfeits: ${illegal.length} illegal moves`
  return (
    <div className="flash center-flash">
      <div className="head">{head}</div>
      {illegal.map((attempt) => {
        const index = turn.attempts.indexOf(attempt)
        return (
          <div className="line" key={index}>
            <s>{attempt.move}</s> <span className="kind">{`${attempt.result} · try ${index + 1} of ${maxAttempts}`}</span>
          </div>
        )
      })}
      {error && (
        <div className="line">
          <span className="kind">{`⚠ ${error}`}</span>
        </div>
      )}
    </div>
  )
}

function TurnFlashes({
  turn,
  landedOn,
  maxAttempts,
}: {
  turn: LlmTurn
  landedOn: string | null
  maxAttempts: number
}) {
  const anchor = useRef<HTMLSpanElement>(null)
  const [shown, setShown] = useState(true)
  const [box, setBox] = useState<Box | null>(null)
  const slip = turn.attempts.find((attempt) => attempt.notation_slip)

  useEffect(() => {
    const timer = setTimeout(() => setShown(false), SHOWN_MS)
    return () => clearTimeout(timer)
  }, [])

  // The slip's square, measured against the board once it is drawn.
  useLayoutEffect(() => {
    const wrap = anchor.current?.closest('.board-wrap')
    const square = slip && landedOn && wrap?.querySelector(`rect.square[data-square="${landedOn}"]`)
    if (!wrap || !square) return
    const outer = wrap.getBoundingClientRect()
    const inner = square.getBoundingClientRect()
    setBox({ x: inner.left - outer.left, y: inner.top - outer.top, width: inner.width, height: inner.height })
  }, [slip, landedOn])

  if (!shown) return null
  return (
    <>
      <span ref={anchor} hidden />
      <CenterFlash turn={turn} maxAttempts={maxAttempts} />
      {slip && box && (
        <>
          <div
            className="flash square-ring"
            style={{ left: `${box.x}px`, top: `${box.y}px`, width: `${box.width}px`, height: `${box.height}px` }}
          />
          <div className="flash bubble" style={{ left: `${box.x + box.width / 2}px`, top: `${box.y}px` }}>
            ⚑ written <code>{`"${slip.move}"`}</code>
            {` → ${slip.san}`}
          </div>
        </>
      )}
    </>
  )
}

/** The flashes of the last LLM turn to land: each landing replaces the last one's. maxAttempts is the game's tries per
 * turn before a forfeit. */
export function BoardFlashes({ flash, maxAttempts }: { flash: Flash | null; maxAttempts: number }) {
  if (!flash) return null
  return <TurnFlashes key={flash.id} turn={flash.turn} landedOn={flash.landedOn} maxAttempts={maxAttempts} />
}
