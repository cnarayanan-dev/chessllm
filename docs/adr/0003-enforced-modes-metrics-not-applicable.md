# Illegal-move metrics are not applicable under Enforced decoding, but every reply is still judged

Under Blind enforced and Listed enforced the LLM's `move` is limited to the legal moves by Ollama's `format` enum, so an illegal move should be impossible. We record the Legal-move streak, the illegal-move counts by kind and the recovered turns as not applicable (`null` in the game log), rather than as their real values (the streak equal to the number of LLM moves, the counts 0). A streak that is true by construction would otherwise sit next to streaks from Free games in a results table and read as a huge improvement. The Settings modal greys out Retry feedback under these LLM constraints, since it can have no effect.

We still run the Move judge on every reply under Enforced decoding. If the enum ever lets an illegal move through, it is handled and logged like any illegal move (retry, mistake chip, board flash, forfeit after four), so the guarantee is checked every game instead of trusted.

## Considered Options

- **Record the real values**: no special cases, but the numbers are misleading in exactly the comparison the benchmark exists for.
- **Skip the judge under Enforced decoding**: slightly simpler, but a broken enum (an Ollama upgrade, a schema bug) would silently produce illegal moves on the board.

## Consequences

- Under Enforced decoding a game can still be forfeited, but only when the LLM gives no answer (timeout or a failed call), or if the enum guarantee breaks.
- Analysis code must treat `null` as "not applicable", never as 0.
- Notation slips need no special case: the enum holds exactly the standard SAN strings (ADR 0002), so none can occur.
