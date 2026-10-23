/*
  The board: cm-chessboard with the Lichess look and Merida pieces. It runs no chess logic (ADR 0001): the backend's
  list of legal moves is all it uses to show where a piece can go and to snap back illegal drops.
*/
import {
  Chessboard,
  COLOR,
  INPUT_EVENT_TYPE,
  type MarkerType,
  type MoveInputEvent,
} from 'cm-chessboard/src/Chessboard.js'
import { Arrows } from 'cm-chessboard/src/extensions/arrows/Arrows.js'
import { Markers } from 'cm-chessboard/src/extensions/markers/Markers.js'
import {
  PROMOTION_DIALOG_RESULT_TYPE,
  PromotionDialog,
} from 'cm-chessboard/src/extensions/promotion-dialog/PromotionDialog.js'
import 'cm-chessboard/assets/chessboard.css'
import 'cm-chessboard/assets/extensions/markers/markers.css'
import 'cm-chessboard/assets/extensions/promotion-dialog/promotion-dialog.css'
import markersSprite from 'cm-chessboard/assets/extensions/markers/markers.svg?no-inline'
import arrowsSprite from 'cm-chessboard/assets/extensions/arrows/arrows.svg?no-inline'
import { useEffect, useRef, type ReactNode } from 'react'
import './board.css'

export type Color = 'white' | 'black'

type BoardProps = {
  /** The position, as FEN. */
  fen: string
  /** The side at the bottom. */
  orientation: Color
  /** The last move, as UCI: both its squares are tinted, or only the target of a drop (a Spawn, Q@d5). */
  lastMove?: string | null
  /**
   * The position before the last move, as FEN, to replay it from the move history: the board puts it up at once,
   * then animates the move into `fen`. Without it, the board animates from whatever it shows.
   */
  animateFrom?: string | null
  /** Whether the side to move is in check: its king glows red. */
  check?: boolean
  /** The side whose pieces the user may move, or null when the board is locked. */
  input?: Color | null
  /** The user's legal moves, as UCI (a promotion once per piece, as e7e8q). None locks the board. */
  legalMoves?: readonly string[]
  /**
   * The move the user made, as UCI, with the promotion piece when promoting. The board then stays locked until the
   * next position or legal moves arrive; giving the same position again snaps the piece back.
   */
  onMove?: (uci: string) => void
  /** Red arrows drawn once the position is set, from→to: a chaos move's. */
  arrows?: readonly (readonly [string, string])[]
  /** The square a Spawn popped in on, marked in purple. */
  spawn?: string | null
  /** Dashed grey arrows drawn once the position is set, from→to: a Legal counterpart's move, never played. */
  ghostArrows?: readonly (readonly [string, string])[]
  /** Laid over the board, such as the board flashes. */
  children?: ReactNode
}

const MARKER = {
  lastMove: { class: 'last-move', slice: 'markerSquare' },
  selected: { class: 'selected', slice: 'markerSquare' },
  targetDot: { class: 'target-dot', slice: 'markerDot', position: 'above' },
  targetRing: { class: 'target-ring', slice: 'markerCircle' },
  check: { class: 'check', slice: 'markerSquare' },
  spawn: { class: 'spawn', slice: 'markerCircle', position: 'above' },
} satisfies Record<string, MarkerType>

const CHAOS_ARROW = { class: 'chaos-arrow' }
const GHOST_ARROW = { class: 'ghost-arrow' }

const SQUARES = [...'abcdefgh'].flatMap((file) => [...'12345678'].map((rank) => file + rank))
const NO_MOVES: readonly string[] = []
const NO_ARROWS: readonly (readonly [string, string])[] = []

// The side to move's king, the side being the FEN's second field.
function showCheck(board: Chessboard, fen: string) {
  const king = fen.split(' ')[1] === 'b' ? 'bk' : 'wk'
  const square = SQUARES.find((square) => board.getPiece(square) === king)
  if (square) board.addMarker(MARKER.check, square)
}

// The picked-up piece's square, and a dot on every square it can reach, a ring where it captures.
function showTargets(board: Chessboard, legalMoves: readonly string[], from: string) {
  clearTargets(board)
  board.addMarker(MARKER.selected, from)
  const targets = new Set(legalMoves.filter((uci) => uci.startsWith(from)).map((uci) => uci.slice(2, 4)))
  for (const to of targets) board.addMarker(board.getPiece(to) ? MARKER.targetRing : MARKER.targetDot, to)
}

function clearTargets(board: Chessboard) {
  for (const type of [MARKER.selected, MARKER.targetDot, MARKER.targetRing]) board.removeMarkers(type)
}

export function Board({
  fen,
  orientation,
  lastMove = null,
  animateFrom = null,
  check = false,
  input = null,
  legalMoves = NO_MOVES,
  arrows = NO_ARROWS,
  spawn = null,
  ghostArrows = NO_ARROWS,
  onMove,
  children,
}: BoardProps) {
  const element = useRef<HTMLDivElement>(null)
  const board = useRef<Chessboard | null>(null)
  // The board's changes are animated, so each waits for the one before it.
  const queue = useRef(Promise.resolve())
  // Brings the board in line with the latest props. The move input handler calls it too, so it lives in a ref.
  const sync = useRef(() => {})
  // The last position drawn, as FEN, and how many times sync was called.
  const drawn = useRef<string | null>(null)
  const syncs = useRef(0)

  // The board is created once, from the first props: later ones reach it through sync.
  const first = useRef({ fen, orientation })

  useEffect(() => {
    const created = new Chessboard(element.current!, {
      position: first.current.fen,
      orientation: COLOR[first.current.orientation],
      style: { cssClass: 'lichess', pieces: { file: '/static/pieces/merida.svg' } },
      extensions: [
        { class: Markers, props: { autoMarkers: null, sprite: markersSprite } },
        { class: Arrows, props: { sprite: arrowsSprite } },
        { class: PromotionDialog },
      ],
    })
    board.current = created
    return () => {
      board.current = null
      created.destroy()
    }
  }, [])

  useEffect(() => {
    function onMoveInput(event: MoveInputEvent): boolean | void {
      const current = board.current!
      switch (event.type) {
        case INPUT_EVENT_TYPE.moveInputStarted: {
          const movable = legalMoves.some((uci) => uci.startsWith(event.squareFrom))
          if (movable) showTargets(current, legalMoves, event.squareFrom)
          return movable
        }
        case INPUT_EVENT_TYPE.moveInputCanceled:
          return clearTargets(current)
        case INPUT_EVENT_TYPE.validateMoveInput: {
          clearTargets(current) // on a drop, or a click on another piece, which picks that one up next
          const uci = event.squareFrom + event.squareTo
          if (legalMoves.includes(uci)) {
            current.disableMoveInput()
            onMove?.(uci)
            return true
          }
          if (legalMoves.includes(uci + 'q')) {
            current.disableMoveInput()
            current.showPromotionDialog(event.squareTo!, COLOR[input!], (result) => {
              if (result.type === PROMOTION_DIALOG_RESULT_TYPE.pieceSelected) onMove?.(uci + result.piece!.charAt(1))
              else sync.current() // the pawn goes back
            })
            return true
          }
          return false
        }
      }
    }

    sync.current = () => {
      const version = ++syncs.current
      queue.current = queue.current.then(async () => {
        const current = board.current
        // Skipped once newer props wait in the queue, so stepping quickly through the history doesn't lag behind.
        if (!current || version !== syncs.current) return
        clearTargets(current)
        current.removeMarkers(MARKER.lastMove)
        current.removeMarkers(MARKER.check) // at once, not after the pieces have moved
        current.removeMarkers(MARKER.spawn)
        current.removeArrows(CHAOS_ARROW)
        current.removeArrows(GHOST_ARROW)
        if (lastMove) {
          // A drop (Q@d5) has a target square only, in the same place as a move's.
          if (!lastMove.includes('@')) current.addMarker(MARKER.lastMove, lastMove.slice(0, 2))
          current.addMarker(MARKER.lastMove, lastMove.slice(2, 4))
        }
        // The board turns after the position is set: an animated turn redraws a stale position.
        const turn = current.getOrientation() !== COLOR[orientation]
        // A replay only when the position changes, not when, say, new legal moves arrive for the same one.
        if (animateFrom && drawn.current !== fen) await current.setPosition(animateFrom, false)
        await current.setPosition(fen, !turn)
        drawn.current = fen
        if (turn) await current.setOrientation(COLOR[orientation])
        if (check) showCheck(current, fen) // once the position is set, so the king is found where it now stands
        // Once the pieces have moved, so the arrows point at where they landed and the spawn pops in on its piece.
        for (const [from, to] of arrows) current.addArrow(CHAOS_ARROW, from, to)
        for (const [from, to] of ghostArrows) current.addArrow(GHOST_ARROW, from, to)
        if (spawn) current.addMarker(MARKER.spawn, spawn)
        current.disableMoveInput()
        if (input && legalMoves.length) current.enableMoveInput(onMoveInput, COLOR[input])
      })
    }
    sync.current()
  }, [fen, orientation, lastMove, animateFrom, check, input, legalMoves, arrows, spawn, ghostArrows, onMove])

  return (
    <div className="board-wrap">
      <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
        <defs>
          {/* The check marker's red glow. */}
          <radialGradient id="check-glow">
            <stop offset="0%" stopColor="#ff0000" />
            <stop offset="25%" stopColor="#e70000" />
            <stop offset="89%" stopColor="#a90000" stopOpacity="0" />
            <stop offset="100%" stopColor="#9e0000" stopOpacity="0" />
          </radialGradient>
        </defs>
      </svg>
      <div ref={element} className="chessboard" />
      {children}
    </div>
  )
}
