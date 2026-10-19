// Stands in for cm-chessboard in tests (jsdom can't draw its SVG). It records what the Board asks of it, and lets a
// test play the user's part: start a drag, drop a piece, pick a promotion piece.
// setup.ts puts it in place of cm-chessboard for every test.
import type {
  BoardColor,
  ChessboardProps,
  MarkerType,
  MoveInputEvent,
  PromotionResult,
} from 'cm-chessboard/src/Chessboard.js'

export const COLOR = { white: 'w', black: 'b' } as const

export const INPUT_EVENT_TYPE = {
  moveInputStarted: 'moveInputStarted',
  movingOverSquare: 'movingOverSquare',
  validateMoveInput: 'validateMoveInput',
  moveInputCanceled: 'moveInputCanceled',
  moveInputFinished: 'moveInputFinished',
} as const

export const PROMOTION_DIALOG_RESULT_TYPE = { pieceSelected: 'pieceSelected', canceled: 'canceled' } as const

export class Markers {}
export class PromotionDialog {}

/** Every board created, in order. Cleared by resetBoards(). */
export const boards: Chessboard[] = []

export function resetBoards() {
  boards.length = 0
}

/** The one board the test rendered. */
export function theBoard(): Chessboard {
  if (boards.length !== 1) throw new Error(`expected one board, found ${boards.length}`)
  return boards[0]
}

export class Chessboard {
  readonly context: HTMLElement
  readonly props: ChessboardProps
  position = '8/8/8/8/8/8/8/8'
  orientation: BoardColor = 'w'
  markers: { class: string; square: string }[] = []
  input: { handler: (event: MoveInputEvent) => boolean | void; color: BoardColor | undefined } | null = null
  promotion: { square: string; color: BoardColor; callback: (result: PromotionResult) => void } | null = null
  destroyed = false

  constructor(context: HTMLElement, props: ChessboardProps = {}) {
    this.context = context
    this.props = props
    // Its squares, as cm-chessboard draws them, for what is laid over a square (a notation slip's flash).
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    for (const square of [...'abcdefgh'].flatMap((file) => [...'12345678'].map((rank) => file + rank))) {
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
      rect.setAttribute('class', 'square')
      rect.setAttribute('data-square', square)
      svg.append(rect)
    }
    context.append(svg)
    if (props.position) this.position = props.position.split(' ')[0]
    if (props.orientation) this.orientation = props.orientation
    boards.push(this)
  }

  async setPosition(fen: string) {
    this.position = fen.split(' ')[0]
  }

  async setOrientation(color: BoardColor) {
    this.orientation = color
  }

  getOrientation() {
    return this.orientation
  }

  getPiece(square: string): string | null {
    const rows = this.position.split('/')
    const row = [...rows[8 - Number(square[1])]].flatMap((c) => (/\d/.test(c) ? Array(Number(c)).fill(null) : [c]))
    const piece: string | null = row['abcdefgh'.indexOf(square[0])]
    if (!piece) return null
    return (piece === piece.toUpperCase() ? 'w' : 'b') + piece.toLowerCase()
  }

  enableMoveInput(handler: (event: MoveInputEvent) => boolean | void, color?: BoardColor) {
    this.input = { handler, color }
  }

  disableMoveInput() {
    this.input = null
  }

  destroy() {
    this.destroyed = true
  }

  addMarker(type: MarkerType, square: string) {
    this.markers.push({ class: type.class, square })
  }

  removeMarkers(type?: MarkerType) {
    this.markers = type ? this.markers.filter((marker) => marker.class !== type.class) : []
  }

  /** The squares that carry a marker of this class. */
  marked(cssClass: string): string[] {
    return this.markers.filter((marker) => marker.class === cssClass).map((marker) => marker.square).sort()
  }

  showPromotionDialog(square: string, color: BoardColor, callback: (result: PromotionResult) => void) {
    this.promotion = { square, color, callback }
  }

  // The user's part.

  /** Picks up the piece on a square. Returns whether the board let it be picked up. */
  pickUp(square: string): boolean {
    if (!this.input) throw new Error('move input is disabled')
    return this.input.handler({ type: INPUT_EVENT_TYPE.moveInputStarted, squareFrom: square }) === true
  }

  /** Drops the piece picked up on `from` onto `to`. Returns whether the board accepted the drop. */
  drop(from: string, to: string): boolean {
    if (!this.input) throw new Error('move input is disabled')
    return this.input.handler({ type: INPUT_EVENT_TYPE.validateMoveInput, squareFrom: from, squareTo: to }) === true
  }

  /** Picks a piece in the open promotion dialog ('q', 'r', 'b' or 'n'), or closes it with null. */
  choosePromotion(piece: string | null) {
    if (!this.promotion) throw new Error('no promotion dialog is open')
    const { square, color, callback } = this.promotion
    this.promotion = null
    callback(
      piece
        ? { type: PROMOTION_DIALOG_RESULT_TYPE.pieceSelected, square, piece: color + piece }
        : { type: PROMOTION_DIALOG_RESULT_TYPE.canceled, square },
    )
  }
}
