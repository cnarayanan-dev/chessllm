// The game page's grid: the Game card ¼ | the board ½ | the moves ¼, two columns below 1100px, one below 760px.
import type { ReactNode } from 'react'
import './game-layout.css'

type GameLayoutProps = {
  /** The left column: the Game card (and later the Reasoning panel under it). */
  game: ReactNode
  /** The board column's stack, at the board's width: the board, with what goes directly above and below it. */
  board: ReactNode
  /** The right column: the moves, for now with the status line and the Thinking above them. */
  moves: ReactNode
}

export function GameLayout({ game, board, moves }: GameLayoutProps) {
  return (
    <main className="game-layout">
      <div className="game-column" data-testid="game-column">
        {game}
      </div>
      <div className="board-column" data-testid="board-column">
        <div className="board-stack">{board}</div>
      </div>
      <div className="moves-column" data-testid="moves-column">
        {moves}
      </div>
    </main>
  )
}
