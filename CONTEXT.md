# ChessLLM

A benchmark of how well small local LLMs play chess, by playing them against humans (and later engines and each other).

## Language

### Play modes

**Free mode**:
A game in which the LLM is shown the position but not the list of legal moves, so it can propose an illegal move.
_Avoid_: Unconstrained mode, open mode

**Constrained mode**:
A game in which the LLM is given the list of legal moves and must choose one of them.
_Avoid_: Limited output, legal-only mode

### Moves

**Turn**:
One decision by the LLM in a game: it is shown the current position and replies with a move, including any retries. Each turn starts fresh, without the conversation from earlier turns.
_Avoid_: Round, step

**Illegal move**:
A move proposed by the LLM that cannot be played in the current position: badly formed notation, a rule-breaking move, or an ambiguous move all count, each recorded with its kind.
_Avoid_: Invalid move, wrong move

**Retry**:
A further attempt the LLM gets after an illegal move, told why the previous move was rejected. Limited to three per turn.
_Avoid_: Re-prompt, second chance

**Retry feedback**:
What the LLM is told after an illegal move. One of three levels: *explained* (the move and the kind of failure, the default), *bare* (only that it was illegal), or *hinted* (also the list of legal moves).
_Avoid_: Error message, hint mode

**Forfeit**:
Loss of the game by the LLM after it uses up its retries without proposing a legal move.
_Avoid_: Resign, disqualification

**Legal-move streak**:
The number of legal moves the LLM plays in a game before its first illegal move, whether or not a retry later recovers the game.
_Avoid_: Legal move count, survival length
