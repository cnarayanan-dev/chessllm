# A turn in a conversation records only what it added to the prompt

Under **Turn memory** *chat with position* or *chat with moves*, an LLM's turns share one conversation for the whole game, so each attempt's Prompt holds every earlier turn the LLM still remembers, up to the model's 8,192-token context (about 30 KB). Recording that whole Prompt on every attempt, as a fresh turn does, would make the game state and the game log grow with the square of the game's length: a long game would send megabytes on every state request the page polls. We decided that in a conversation each attempt records only the messages it added, and each turn records how many earlier turns it still remembered after the oldest were dropped whole to fit the context. The system prompt is read once, at the side's first turn, and recorded once for the game. The whole Prompt of any attempt is rebuilt exactly from these records, and the page and the analysis rebuild it the same way.

## Considered Options

- **The whole conversation on every attempt**, as fresh turns do: each attempt reads on its own, but every earlier turn is copied once per later attempt, and the game state outgrows what the page can poll.
- **The whole conversation in the game log, only the additions in the game state**: the log stays self-contained, but there are two record shapes for the same attempt, and the log grows just as in the first option.
- **Letting Ollama cut a conversation that outgrows the context**: nothing to build, but it drops the oldest messages silently, so the records would claim the LLM saw turns it never saw.

## Consequences

- Reading one attempt's Prompt from a raw log means rebuilding the conversation; analysis code does it through one helper rather than by hand.
- The system prompt file is no longer re-read every turn in a conversation: an edit applies from the next game, since rewriting a system prompt already sent would change a past the LLM has seen.
- Fresh turns keep recording their whole Prompt on every attempt; only conversations use the additions.
- A chaos move's **Legal counterpart**, asked at the end of a conversation and then dropped from it, records the same way: its attempt holds only its request, and its whole Prompt is the conversation as the chaos move's turn left it, then the request. Should the request not fit the context, the oldest earlier turns are dropped for it alone, and it records how many it still held.
