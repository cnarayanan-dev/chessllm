# Chaos moves are resolved and applied by our own rules, not by python-chess

Under Chaos rules an LLM's rule-breaking or ambiguous move is played on the board anyway. python-chess cannot do this for us. `parse_san` never resolves to an illegal move, and `Board.push` asserts on an empty from-square, treats any king move from e1 to g1 as castling (deleting the pieces in between), and turns an opponent's piece into the mover's colour. So the backend has its own resolver, which turns the LLM's text into a from-square, a to-square and a piece, and applies that by editing the board directly. The backend also keeps its own list of positions, because python-chess clears its move stack when the board is edited. ADR 0001 still holds: legality, and now chaos resolution, live only in the backend.

The resolver decides once per move, deterministically, and stores the result, so a replay never has to guess again.

1. If the from-square holds one of the mover's own pieces, that piece moves, whatever letter was written. If it holds the opponent's piece or nothing, it is ignored. Pure UCI then has no piece type left and is an invalid move.
2. A file or rank hint (`Rad4`) picks among the mover's pieces of the named type, and is ignored if none matches.
3. Among the candidates, a piece that could reach the target by its own movement pattern on an empty board is preferred. Otherwise the nearest by king-move distance moves, with ties going to the first in a1→h8 order.
4. If the mover has no piece of that type, it is a Spawn on the target square. A king is never spawned.
5. If the only piece of that type already stands on the target square, the move is invalid.
6. Whatever stands on the target square is captured, own pieces and kings included. A pawn reaching the last rank becomes a queen unless another piece is named. An illegal `O-O`/`O-O-O` puts the king on g/c and, if a rook is in that corner, the rook on f/d, capturing whatever is there.
7. After the move the side to move flips, the en passant square is cleared, castling rights are recomputed from where the kings and rooks stand, and the clocks advance.

## Considered Options

- **Reject what python-chess rejects and use `push` for the rest**: no resolver to maintain, but `push` mangles the very moves we want to show, and `parse_san` rejects all of them.
- **Resolve in the browser, as WilyHyperion/IllegalChess does with chess.js**: no backend change, but it breaks ADR 0001, and the game log would not know which piece actually moved.
- **Pick the candidate at random**: more chaotic, but the same game log could then have produced a different board.
- **Trust the piece letter over the from-square, and steal the opponent's piece when the LLM names its square**: both were considered and rejected in favour of "trust what the LLM pointed at, but only its own pieces".

## Consequences

- A game under Chaos rules has no valid PGN once a chaos move is played. The LLM is shown the Move record instead, and the PGN export covers only games under Standard rules or stops at the first chaos move.
- python-chess treats capturing a king that was left in check as a legal move, so King capture is checked explicitly after every move, before checkmate and the draw rules.
- An Anchor engine may refuse positions python-chess calls invalid (no king, too many pawns). Check this before allowing Chaos rules in Anchor matches. Checked for Stockfish 19: it quits on every such position, so the Stockfish Anchor takes an en-prise king, else plays on a copy with back-rank pawns made queens, else a greedy move; Chaos rules are allowed in Anchor matches against it alone (`docs/research/llama3-anchor-matches-2026-10-19.md`).
