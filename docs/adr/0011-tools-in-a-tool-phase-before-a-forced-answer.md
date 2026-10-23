# Tools are called in a tool phase without the answer schema, and the move is always a forced answer after it

In the benchmark only, an LLM side can have Tools (board, move history, legal moves, material) it calls during an attempt through Ollama's native tool calling. An attempt with tools is a loop: calls with `tools=` and no `format`, each tool call answered with a `tool` message, until the model replies without one or has made its 10th call (the Tool-call cap); then exactly one more call with no tools and the answer schema as `format` (under Blind enforced the legal-move enum), which gives the move. The shape is that of the Thinking budget's forced answer (ADR 0007).

- **No schema during the tool phase.** Grammar-constrained decoding can stop open-weight models from making tool calls at all (reported for models on Ollama with a JSON schema in `format`), so one call with both tools and the schema would measure the constraint, not the tools.
- **The move is always asked for, never waited for.** Small models loop on tool calls or never answer; a cap ending in a forced answer means every attempt ends in a move to judge, and a turn is still decided by the usual Retries and Forfeit.
- **Native calls only.** A model without Ollama's `tools` capability (a hand-set flag in the model list, like thinking) can't have tools; a tool call written as text in the reply is not run, ends the tool phase, and is recorded as such.
- **Narrow in v1:** refused before any game unless the side plays under Free or Blind enforced, Standard rules, fresh Turn memory, thinking on and no Thinking budget.

## Considered Options

- **One call with `tools=` and `format=` together**: fewer calls, but at the risk above.
- **A text protocol of our own** (`CALL legal_moves`, parsed from the reply, as maxim-saplin/llm_chess does): works for every model, llama3 included, but measures following our conventions, and its results aren't comparable with native calls.
- **An agent framework** (Pydantic AI, LangChain, OpenAI Agents SDK): they own the loop, which is what is being measured and recorded; the `ollama` SDK already builds a tool's schema from a function's signature and docstring.

## Consequences

- An attempt with tools is up to 11 calls; its latency, tokens and Time used add them all up, and each tool call is recorded in the attempt (`tool_calls`) and in its prompt messages.
- The tool set is part of the Player configuration (ADR 0005), in the ladder's history, the Rating fit and the report's grouping; no tools leaves a configuration and its id as before.
