// The game page's grid: the Game card ¼ | the board ½ | the moves ¼, two columns below 1100px, one below 760px.
import type { ReactNode } from 'react'
import './game-layout.css'

type GameLayoutProps = {
  /** The left column: the Game card, and the Turn panel under it. */
  game: ReactNode
  /** The board column's stack, at the board's width: the board, with what goes directly above and below it. */
  board: ReactNode
  /** The right column: the moves. */
  moves: ReactNode
  /** Whether the Prompt lab's dock is open: the board alone in the top half, the side columns greyed out and inert. */
  docked?: boolean
}

export function GameLayout({ game, board, moves, docked = false }: GameLayoutProps) {
  return (
    <main className="game-layout">
      <div className="game-column" data-testid="game-column" inert={docked}>
        {game}
      </div>
      <div className="board-column" data-testid="board-column">
        <div className="board-stack">{board}</div>
      </div>
      <div className="moves-column" data-testid="moves-column" inert={docked}>
        {moves}
      </div>
    </main>
  )
}
