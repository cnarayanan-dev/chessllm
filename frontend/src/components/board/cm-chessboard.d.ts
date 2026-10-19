// cm-chessboard ships plain JavaScript. These declare the part of its API the Board uses.

declare module 'cm-chessboard/src/Chessboard.js' {
  export const COLOR: { white: 'w'; black: 'b' }
  export type BoardColor = (typeof COLOR)[keyof typeof COLOR]

  export const INPUT_EVENT_TYPE: {
    moveInputStarted: 'moveInputStarted'
    movingOverSquare: 'movingOverSquare'
    validateMoveInput: 'validateMoveInput'
    moveInputCanceled: 'moveInputCanceled'
    moveInputFinished: 'moveInputFinished'
  }

  export type MoveInputEvent = {
    type: (typeof INPUT_EVENT_TYPE)[keyof typeof INPUT_EVENT_TYPE]
    squareFrom: string
    squareTo?: string
  }

  export type MarkerType = { class: string; slice: string; position?: 'above' }
  export type ArrowType = { class: string }

  export type PromotionResult = { type: 'pieceSelected' | 'canceled'; square: string; piece?: string }

  export type ChessboardProps = {
    position?: string
    orientation?: BoardColor
    assetsUrl?: string
    style?: { cssClass?: string; pieces?: { file?: string } }
    extensions?: { class: unknown; props?: Record<string, unknown> }[]
  }

  export class Chessboard {
    constructor(context: HTMLElement, props?: ChessboardProps)
    setPosition(fen: string, animated?: boolean): Promise<void>
    setOrientation(color: BoardColor, animated?: boolean): Promise<void>
    getOrientation(): BoardColor
    getPiece(square: string): string | null
    enableMoveInput(handler: (event: MoveInputEvent) => boolean | void, color?: BoardColor): void
    disableMoveInput(): void
    destroy(): void
    // Added by the Markers extension.
    addMarker(type: MarkerType, square: string): void
    removeMarkers(type?: MarkerType, square?: string): void
    // Added by the Arrows extension.
    addArrow(type: ArrowType, from: string, to: string): void
    removeArrows(type?: ArrowType, from?: string, to?: string): void
    // Added by the PromotionDialog extension.
    showPromotionDialog(square: string, color: BoardColor, callback: (result: PromotionResult) => void): void
  }
}

declare module 'cm-chessboard/src/extensions/markers/Markers.js' {
  export class Markers {}
}

declare module 'cm-chessboard/src/extensions/arrows/Arrows.js' {
  export class Arrows {}
}

declare module 'cm-chessboard/src/extensions/promotion-dialog/PromotionDialog.js' {
  export const PROMOTION_DIALOG_RESULT_TYPE: { pieceSelected: 'pieceSelected'; canceled: 'canceled' }
  export class PromotionDialog {}
}
