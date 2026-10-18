# ChessLLM

A benchmark of how well small local LLMs play chess, by playing them against humans (and later engines and each other).

## Language

### Play modes

**Play mode**:
The combination of whether the **Legal-move list** is shown and whether **Enforced decoding** is on, fixed for a whole game. One of four: Free, Listed, Blind enforced, Listed enforced.
_Avoid_: Game type, variant

**Legal-move list**:
The list of every legal move in the current position, shown to the LLM in its prompt.
_Avoid_: Move options, candidate moves

**Enforced decoding**:
Generation of the LLM's reply under a constraint that only lets it produce one of the legal moves, so it cannot propose an illegal move.
_Avoid_: Constrained decoding, grammar mode, structured output

**Free mode**:
A game with no **Legal-move list** and no **Enforced decoding**, so the LLM can propose an illegal move.
_Avoid_: Unconstrained mode, open mode

**Listed mode**:
A game in which the LLM is shown the **Legal-move list** but not held to it, so it can still propose an illegal move.
_Avoid_: Constrained mode, limited output, legal-only mode

**Blind enforced mode**:
A game with **Enforced decoding** but no **Legal-move list**: the LLM cannot propose an illegal move and is not told what its options are.
_Avoid_: Constrained mode, grammar mode

**Listed enforced mode**:
A game with both the **Legal-move list** and **Enforced decoding**: the LLM sees its options and cannot leave them.
_Avoid_: Constrained mode, fully constrained mode

### Moves

**Turn**:
One decision by the LLM in a game: it is shown the current position and replies with a move, including any retries. Each turn starts fresh, without the conversation from earlier turns.
_Avoid_: Round, step

**Illegal move**:
A move proposed by the LLM that cannot be played in the current position: badly formed notation, a rule-breaking move, or an ambiguous move all count, each recorded with its kind.
_Avoid_: Invalid move, wrong move

**Retry**:
A further attempt the LLM gets after an illegal move, told why the previous move was rejected. Limited to three per turn, so four attempts in total.
_Avoid_: Re-prompt, second chance

**Retry feedback**:
What the LLM is told after an illegal move. One of three levels: *explained* (the move and the kind of failure, the default), *bare* (only that it was illegal), or *hinted* (also the list of legal moves).
_Avoid_: Error message, hint mode

**Forfeit**:
Loss of the game by the LLM after it uses up its retries without proposing a legal move, or at once when it gives no answer at all (it thinks past the time limit or the call fails).
_Avoid_: Resign, disqualification

**Legal-move streak**:
The number of legal moves the LLM plays in a game before its first illegal move, whether or not a retry later recovers the game.
_Avoid_: Legal move count, survival length
