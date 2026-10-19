# Executing an LLM's illegal chess moves: variants, prior art and python-chess behaviour

Research date: 2026-10-19. Scope: whether any chess variant or project plays illegal moves instead of rejecting them, how other LLM-chess projects handle illegal moves, and what python-chess and the browser board libraries do when given an arbitrary from→to. This is background for Chaos rules (see CONTEXT.md and ADR 0006).

## TL;DR

- **No established variant plays "whatever the player claimed".** Each variant changes the rules, then still checks moves against them. The closest rule to "the LLM ignored check" is Fog of War: there is no check, and you win by capturing the king.
- **There is one direct precedent:** [WilyHyperion/IllegalChess](https://github.com/WilyHyperion/IllegalChess).
  - It tries the move with chess.js first.
  - If that fails, it moves the nearest piece of the named type to the target square, spawning one if none exists.
  - It hardcodes castling, then rewrites the FEN by hand.
- **LLM chess benchmarks all reject illegal moves.** They give a few retries, then the LLM loses.
- **python-chess cannot resolve or apply illegal moves safely.** We need our own resolver and must edit the board by hand.
- **cm-chessboard (already used here) animates any from→to without checks.**

## 1. Variants

- **Kriegspiel:** illegal attempts are rejected ("No"), and the player tries again. https://en.wikipedia.org/wiki/Kriegspiel_(chess)
- **Fog of War / Dark chess:** there is no check, and capturing the king wins. https://support.chess.com/article/1668-what-is-fog-of-war-chess, https://www.pychess.org/variants/fogofwar
- **Atomic, Crazyhouse, Antichess:** well-defined rule changes. https://lichess.org/variant/atomic, https://lichess.org/variant/crazyhouse, https://lichess.org/variant/antichess
- **Fairy-Stockfish:** configurable (`checking=false`, extinction win conditions), but still a legality engine. https://github.com/fairy-stockfish/Fairy-Stockfish/blob/master/src/variants.ini
- **r/AnarchyChess (il vaticano, knight boost, forced en passant):** fan rules with no canonical definition, and implementations disagree. https://github.com/JSerf02/Anarchy-Chess, https://github.com/tsoj/Annie

## 2. Prior art with LLMs

- **IllegalChess (above):**
  - The prompt asks GPT for a move "even if illegal".
  - It uses nearest-piece resolution and spawns a piece when none exists.
  - Afterwards it forces the side to move and clears en passant in the FEN.
- **GothamChess videos:** ChatGPT capturing its own pieces, and pieces teleporting or coming back from the dead. Sources: https://glasp.co/youtube/p/chatgpt-cheated, https://decrypt.co/301127/chatgpt-demolished-in-ai-chess-tournament. Not verified: how those moves were entered on the board.
- **Benchmarks that reject illegal moves:**
  - [maxim-saplin/llm_chess](https://github.com/maxim-saplin/llm_chess): 3 mistakes, then a loss.
  - [google-deepmind/game_arena](https://github.com/google-deepmind/game_arena): re-prompts the LLM.
- **PGN can't hold these games:** a PGN of an LLM game with illegal moves is unreadable by chess apps (https://gist.github.com/libewa/c469a5d6fb7133f4dc5995ebf4647718), so store a position per ply.

## 3. python-chess 1.11.2 (tested)

- **`Board.push` does not check legality**, and gives strange results:
  - An empty from-square raises `AssertionError`, which disappears under `python -O`.
  - Moving the opponent's piece turns it into the mover's colour.
  - `e1g1` / `e1c1` are treated as castling even when blocked, silently deleting the pieces in between.
- **`parse_san` and `find_move` only ever return legal moves.** Illegal SAN raises `IllegalMoveError`, `InvalidMoveError` or `AmbiguousMoveError`.
- **`set_piece_at` / `set_board_fen` clear the move stack.**
- **Missing or extra kings:** `status()` reports `STATUS_NO_*_KING` or `STATUS_TOO_MANY_KINGS`, but `legal_moves` still works. Capturing a king that was left in check comes back as a legal move.
- **The safe way to apply a move:**
  1. `remove_piece_at(from)`, then `set_piece_at(to, piece)`;
  2. flip `turn` and set `ep_square = None`;
  3. `castling_rights = clean_castling_rights()`;
  4. bump the clocks.

## 4. Board libraries and UX

- **cm-chessboard:** `setPosition(fen, animated)` and `movePiece(from, to, animated)` have no legality checks, and the arrows extension is available. https://github.com/shaack/cm-chessboard
- **chessground:** has no chess logic, but `api.move` auto-castles king moves from the e-file to the g- or c-file unless `autoCastle: false`. https://github.com/lichess-org/chessground/blob/master/src/board.ts
- **No viewer was found that replays or highlights illegal moves in a move list.** The UX would be new.
