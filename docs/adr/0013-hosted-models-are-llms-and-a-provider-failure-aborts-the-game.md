# Hosted models are LLMs, and a failure of their provider aborts the game instead of losing it

A **Hosted model** (Claude Haiku 5.5, `claude-haiku-5-5`, see CONTEXT.md) is a third kind of thing a **Model player** can be next to a local LLM and a **System 1 model** (ADR 0012), but unlike a System 1 model it is an LLM in everything the game does: it is shown a **Prompt**, replies with a move and **Reasoning** or **Thinking**, gets **Retries** and **Retry feedback**, can keep a conversation (**Turn memory**), can play **Chaos rules**, and is asked for a **Legal counterpart**. So it is no new side kind: it is an `LlmSide` whose model is in `HOSTED_MODELS`, played by a second adapter of the LLM player port (`chessllm/llm/claude_player.py`, through the official `anthropic` SDK) in place of `OllamaPlayer`. Everything above the port, the turn, the log, the API shape and the **Player configuration**, is unchanged; the settings of a Player configuration that its provider allows apply, and the others do not (below).

## The provider's rules decide which settings apply

- **Effort is fixed** at `medium`, the provider's default for this model, and is not a setting, so a Player configuration needs no effort to tell games apart.
- **Thinking** off sends `thinking: disabled`; on sends adaptive thinking with a summarized display, and the recorded **Thinking** is that summary, never the raw reasoning (so its token split between thinking and answer is only estimated, a lower bound for the thinking). Haiku 5.5 accepts `disabled` at effort `high` or below.
- **Sampling is never sent**: the provider answers a non-default `temperature`, `top_p` or `top_k` with a 400. The sampling config file (`sampling.toml`) is for local models; a Hosted model's **Player configuration** records none whatever the file held, so its **Reference configuration** is thinking off and the rest as an LLM's, "its own sampling being the provider's".
- A **Thinking level**, a **Thinking budget** and **Tools** do not apply; `Settings.check` refuses them for a Hosted model, naming the setting. The app has none of them anyway.
- **Enforced decoding** is a structured output (`output_config.format`, a JSON schema) whose `move` is an enum of the legal moves; the answer schemas are the Ollama player's (`MoveAnswer`, `ReasonedMoveAnswer`). No assistant prefill is used (the provider rejects it).
- A **Turn memory** conversation is trimmed to the model's own context (1M tokens, `LlmModel.context_tokens`), not to the 8,192 tokens Ollama loads local models with.

## Access, and how the app and the commands behave without it

The token is the environment variable `CLAUDE_TOKEN`, loaded once in `chessllm/core/config.py` from a `.env` file in the project root (python-dotenv, `override=False`, so a real environment variable wins). `.env` is git-ignored; the token is held only by the SDK client and is never logged, printed or written to a game log. It is not validated ahead of time: a wrong one shows as an **Aborted game**.

With no token the model is hidden: `GET /api/models` does not list it (`offered_models()`), so the New game sheet has no way to choose it, and `POST /api/games` refuses it. A benchmark command asked for it stops before the first game with the reason (`Settings.check_hosted_access`). Ollama is never asked whether it has a Hosted model.

## Forfeit or Aborted game

A reply that times out (the same 300 s limit as Ollama's) or that the model declines for its content (`stop_reason: refusal`) is a **Forfeit**, like any LLM that gives no answer. Anything else that makes a call fail, once the SDK has retried 429, 5xx and dropped connections twice itself, is not the model's play: the provider refuses the token (401, 403), has no credit, limits the use or is down. The player raises `HostedModelFailed`, which the turn lets through instead of recording a failed attempt; the game ends as an **Aborted game**.

An Aborted game is kept in the game log, with its reason, and counts for nothing:

- The log gets one `game_aborted` event (`color`, `ply`, `reason`, `aborted_at`) as its last event **in place of `game_end`** (ADR 0004), after the attempts the failed turn had already made. No result, no PGN, no `stats`.
- Every reader of finished games already asks for `game_end` last (`finished_game`), so the Ranking, the leaderboard, the ladder's history, the analysis and the Rating all leave it out with no change; it is the same as an abandoned game for them. `games-report` tells the two apart (`aborted` against `unfinished` under `--include-unfinished`).
- The game's state (ADR 0008) has `status: "aborted"` and `abort_reason`; `result` and `end_reason` stay null. Further moves and turns are refused with the code `game_aborted`. The page says "Game aborted", the reason in a tooltip, and offers a Rematch.
- A batch prints its summary and **stops** with the reason and the log's path, instead of carrying on to fail every game. Running it again goes on as before, since the aborted game is no game of the ladder.

## Considered Options

- **A `HostedSide`, like `System1Side`**: it would need its own turn, record and log shape for something that is an LLM in every way the game cares about. Rejected: the LLM settings, their log shape and their Player configuration all apply as they are.
- **Every failed call a Forfeit, as for a local LLM**: a revoked token or an empty balance would then be a rated loss for the model, a result from an infrastructure fault, the same reason a missing Ollama model is refused before the game rather than forfeited (CONTEXT.md, Forfeit).
- **An Aborted game written as `game_end` with a special result**: every reader would have to learn to skip it. Leaving out `game_end` makes the existing ones skip it.
- **Checking the token with the provider before a game**: a request per game for nothing the first turn would not show; a wrong token surfaces as an Aborted game.
- **A price table and a spend cap**: no cost features. Token counts are recorded per attempt as for Ollama, and nothing more.

## Consequences

- A Legal counterpart that fails because the provider does is recorded as a failed counterpart and the game goes on; the next turn's failure then aborts it.
- The SDK retries a timed-out request too, so a call that always times out takes up to three times the limit before it is a Forfeit.
- Adding another Hosted model is a line in `HOSTED_MODELS`; one with other capabilities than Haiku 5.5's (Thinking budget, sampling) would need this ADR revisited.
