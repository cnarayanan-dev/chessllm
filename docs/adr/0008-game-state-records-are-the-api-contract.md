# The game's state records are the API's response models

The game state is built as dictionaries in `GameSession` and described a second time, as Pydantic models, in the API, which validates the one against the other on every response. The two copies had already drifted (the API's attempt results left out `cut_off`). We decided that the game owns one Pydantic model per state record (`Attempt`, `LlmTurn`, `Ply`, the side stats, `GameState`) and the API returns them as they are, with no separate response schemas for the game state. ADR 0001 already makes the page show the backend's state as given, without chess logic of its own, so the API's shape *is* the game's state by design, and there is no second consumer that needs a different view. Request bodies (`NewGame`, `HumanMove`) keep schemas of their own, since what a request may ask for is narrower than what a game holds.

## Considered Options

- **Separate API schemas, mapped from the game's records** (the usual `schemas/` layer): it would let the API's shape differ from the game's, but that is a need nobody has, and it keeps two typed copies and a mapping in step, the same drift as before.
- **Game records as plain dataclasses, the API's models re-exporting them**: one definition, but the API would still need Pydantic to describe them, so the dataclasses would only add a layer.

## Consequences

- Changing a state record changes the API, and so the frontend's generated types (`frontend/src/api/schema.ts`). The page imports 14 of the schema's type names; those must stay stable, other names may change.
- Where the game's working form and its record really differ, the record is a model of its own: a chaos move's resolution works on python-chess squares and pieces, while its record has square names and a piece symbol.
- The records are shaped as a summary base and a detail subclass (`AttemptSummary` and `Attempt`, `LlmTurnSummary` and `LlmTurn`), so that the game state can later carry summaries of past turns and leave their full text to a per-turn endpoint without a rewrite.
- The game log is written from the same records, through a log shape that keeps the log's own format (ADR 0004): the log is not the API.
