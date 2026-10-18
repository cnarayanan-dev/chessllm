# The Python backend is the only judge of move legality

The GUI is a static page using cm-chessboard, and all chess rules live in the FastAPI backend in python-chess: the browser runs no chess logic and has no chess.js. We chose this because the benchmark needs one source of truth for legality. The same code must check the human's moves and the LLM's moves, classify every illegal move (invalid, illegal or ambiguous), count the Legal-move streak and write the game log. Duplicating the rules in JavaScript would mean keeping two rule engines in step for no benefit to the measurements.

## Considered Options

- **chess.js in the browser plus python-chess on the server**: instant client-side validation, but two rule engines that can disagree, and legality decisions split across two places.
- **chessground (Lichess's board)**: the most polished board, but GPL-3.0 and normally used with a JavaScript build step.
- **gradio_chessboard (Python only)**: no JavaScript at all, but immature (version 0.0.x) and its maintenance could not be verified.

## Consequences

- With each response the backend sends the list of legal moves for the human, and cm-chessboard uses it to reject illegal drags without a round trip. That keeps the GUI responsive without a second rule engine.
- Anyone tempted to add chess.js "for snappier validation" should first read this ADR. Legality must never be decided in the browser.
