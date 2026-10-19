# ChessLLM

A benchmark of how well small local LLMs play chess, by playing them against humans and against each other (and later engines).

## Language

### Modes

**Mode**:
Who plays each side of a game, fixed for the whole game. Either **Play LLM** or **LLM faceoff**.
_Avoid_: Matchup, game type, opponent type

**Play LLM**:
The **Mode** in which a human plays one side and an LLM the other.
_Avoid_: Human vs LLM, single-player

**LLM faceoff**:
The **Mode** in which an LLM plays each side, two different models or one model against itself, so models can be compared with each other.
_Avoid_: LLM vs LLM, self-play, tournament

### LLM constraints

**LLM constraints**:
The combination of whether the **Legal-move list** is shown and whether **Enforced decoding** is on, fixed for a whole game. One of four: Free, Listed, Blind enforced, Listed enforced.
_Avoid_: Play mode, mode, game type, variant

**Legal-move list**:
The list of every legal move in the current position, shown to the LLM in its prompt.
_Avoid_: Move options, candidate moves

**Enforced decoding**:
Generation of the LLM's reply under a constraint that only lets it produce one of the legal moves, so it cannot propose an illegal move.
_Avoid_: Constrained decoding, grammar mode, structured output

**Free**:
The **LLM constraints** with no **Legal-move list** and no **Enforced decoding**, so the LLM can propose an illegal move.
_Avoid_: Free mode, unconstrained, open

**Listed**:
The **LLM constraints** in which the LLM is shown the **Legal-move list** but not held to it, so it can still propose an illegal move.
_Avoid_: Listed mode, constrained, limited output, legal-only

**Blind enforced**:
The **LLM constraints** with **Enforced decoding** but no **Legal-move list**: the LLM cannot propose an illegal move and is not told what its options are.
_Avoid_: Blind enforced mode, constrained, grammar mode

**Listed enforced**:
The **LLM constraints** with both the **Legal-move list** and **Enforced decoding**: the LLM sees its options and cannot leave them.
_Avoid_: Listed enforced mode, constrained, fully constrained

### Moves

**Turn**:
One decision by an LLM in a game: it is shown the current position and replies with a move, including any retries. Each turn starts fresh, without the conversation from earlier turns.
_Avoid_: Round, step

**Illegal move**:
A move proposed by the LLM that cannot be played in the current position: badly formed notation, a rule-breaking move, or an ambiguous move all count, each recorded with its kind.
_Avoid_: Invalid move, wrong move

**Notation slip**:
A legal move the LLM writes in anything other than its exact standard SAN, such as UCI, a needless disambiguation, or a missing or false check sign. It is played, and recorded and shown as a slip; it is not an illegal move.
_Avoid_: Format error, non-SAN move

**Retry**:
A further attempt the LLM gets after an illegal move, told why the previous move was rejected. Limited to three per turn, so four attempts in total.
_Avoid_: Re-prompt, second chance

**Retry feedback**:
What the LLM is told after an illegal move. One of three levels: *explained* (the move and the kind of failure, the default), *bare* (only that it was illegal), or *hinted* (also the list of legal moves).
_Avoid_: Error message, hint mode

**Forfeit**:
Loss of the game by an LLM after it uses up its retries without proposing a legal move, or at once when it gives no answer at all (it thinks past the time limit or the call fails).
_Avoid_: Resign, disqualification

**Legal-move streak**:
The number of legal moves an LLM plays in a game before its first illegal move, whether or not a retry later recovers the game. Not applicable under **Enforced decoding**, where it would be true by construction.
_Avoid_: Legal move count, survival length
