# Spec: Thinking budget, thinking levels and Gemma 4

Draft, 2026-10-20. Published as the spec issue #67, split into tickets #68-#74 (level and budget are benchmark-only; defaults are only recommended). Built on `docs/research/thinking-budget.md`, `docs/research/candidate-models.md`, `docs/research/llm-chess-limitations-solutions.md` (roadmap step 6) and `docs/research/qwen3.8-thinking-vs-gemma-2026-10-20.md`. Meant to become one spec issue plus the tickets below (`## Parent` = the spec), labelled `ready-for-agent` except where marked **you**.

## Problem Statement

Thinking is what makes small models play real chess: qwen3.8 with thinking mated gemma3:12b, with the best move quality measured so far (centipawn loss 207). But thinking time is unbounded. qwen3.8 took from 35 s to over 300 s per move, and it forfeited a game it was 15 points up in on the 300 s limit. So a timeout measures the laptop, not the model, and a 30-game anchored batch of a thinking model takes 15-17 hours. The benchmark also can't say how much thinking a model got: `think=True` silently runs qwen3.8 at `medium`, not the `xhigh` its published rating used, and thinking tokens aren't logged. Gemma 4 (being pulled) is a new thinking model that should fit the same scheme.

## Solution

- **Thinking budget:** a new Player configuration setting, the most tokens of Thinking (and answer) a model may produce in one attempt before it is made to answer. Enforced in two calls: call 1 caps generation with `num_predict`. If it stops on length, call 2 hands back the thinking so far, closes it with "Considering the limited time, I have to give my move now…", and takes the answer under the same JSON schema (and the legal-move enum under Enforced decoding). A budget is in tokens, so a game means the same on any machine. None = unbounded, as today.
- **Thinking level:** `thinking` widens from on/off to on/off or a level the model offers (qwen3.8: low, medium, xhigh), passed to Ollama explicitly. `true` keeps meaning what it means in old logs (Ollama's `medium`).
- **Token logging:** every attempt logs its thinking tokens, answer tokens, prompt tokens, `done_reason` and whether the budget forced the answer.
- **Gemma 4** joins the model list with its thinking capability, once the forced answer is shown to work for it.
- **The 300 s timeout stays as a safety net,** set above the budget's worst case. A timeout is still a Forfeit; with a budget it should become rare.

## User Stories

1. As the benchmark's runner, I set `--thinking-budget 3072` on a batch, so thinking models finish every move and a batch's length is predictable.
2. As the runner, I choose `--thinking-level xhigh` for qwen3.8, so I can play the configuration LLM Chess rated.
3. As an analyst, I see per attempt how many thinking tokens were used and whether the budget cut in, so I can choose budgets from data and spot truncated prompts.
4. As an analyst, games with different budgets or levels are different Player configurations, so they never pool under one Rating.
5. As the runner, I play gemma4 with thinking against gemma3:12b and qwen3.8 with the same tools.

## Implementation Decisions

- **Domain:** add **Thinking budget** and **Thinking level** to `CONTEXT.md` (under Moves, next to **Thinking**). ADR 0007: budget in tokens, enforced by a forced answer, per attempt (a Retry gets a fresh budget), part of the Player configuration, timeout kept as a safety net. The next ADR number is 0007 (0005 is used twice).
- **Settings:** `LlmSide.thinking: bool | ThinkingLevel` and `LlmSide.thinking_budget: int | None`. Logged at `game_start` only when not the default, as `position` is (`LlmSide.log_shape`), so old logs keep their configurations. The same goes for `PlayerConfiguration` (`exclude_if`, so ids don't change) and the API (optional fields, schema regenerated).
- **Models:** `LlmModel.thinking` becomes the tuple of values `ollama show` lists (e.g. `(False, "low", "medium", "xhigh")` for qwen3.8, `(False, True)` for qwen3.5:9b and gemma4). `Settings.problem` refuses a level or budget the model can't take, and a budget with thinking off.
- **Player:** `OllamaPlayer.reply` does the two calls. `LlmReply` gains `thinking_tokens`, `answer_tokens`, `prompt_tokens`, `done_reason` and `forced`, and each `llm_attempt` logs them. If a cut ever comes back without a forced answer, log it as its own result (`"length"`), not as an illegal move.
- **Timeout:** `TIMEOUT_S` becomes per call and is derived when a budget is set: budget ÷ measured tokens/s + margin. Or keep 300 s and refuse budgets that can't fit: the ticket decides after the spike.
- **CLIs:** `--thinking-budget N` and `--thinking-level L` on `faceoff_batch` and `anchor_match`/`anchor_batch`; `--thinking-for` keeps working. `scripts/analyse_games.py` groups by both and reports median/p90 thinking tokens and the forced share.
- **Frontend:** out of scope here (the New game sheet is being reworked); the API accepts the fields.

## Testing Decisions

- Through the existing seams, with a scripted fake chat: a `done_reason == "length"` reply leads to exactly one call 2, with the thinking prefilled and the schema (and enum) unchanged. A reply that stops normally makes one call. Logging follows each case.
- The game log and leaderboard: a default side logs no new fields, and old logs give the same configuration ids (a test like `test_the_default_isnt_logged_so_older_games_keep_their_configuration`).
- `Settings.problem`: a level the model doesn't list, a budget with thinking off and a budget under the answer's own tokens are refused.
- A live test (marked `ollama`): one budgeted qwen3.8 move under Listed enforced returns a move from the list with `forced` true.

## Out of Scope

- The New game sheet in the frontend.
- Ollama's own `think_budget` option (PR #17566, unreleased); switch to it once it ships.
- A cap on the `reasoning` field when thinking is off.
- Calibrated Anchors (roadmap step 3) and the rated-track ADR (step 4), though budgeted thinking games should go into the Rating only after those.

## Further Notes

- **Gemma 4 risk.** Its card says earlier thinking must not be carried in the history, and its template marks thinking with `<|channel>thought … <channel|>`. Ollama's renderer may drop a prefilled `thinking` field for Gemma 4, in which case call 2 must go through `/api/generate` in raw mode with the template written out. Ticket 2 settles this before ticket 4 is built.
- **Starting budgets** (to confirm in ticket 6): qwen3.8 at `medium`, 3,072 tokens (above p90 ~2,050; about 250 s here). gemma4: the p90 of its unbounded thinking, measured in ticket 6. Truncated thinking can be worse than none, so a budget should trim the long tail, not the typical move.

---

## Tickets, in order

| # | Ticket | Blocked by | Who |
|---|---|---|---|
| 1 | Gemma 4 in the model list | pull finished | agent |
| 2 | Spike: does a forced answer work for qwen3.5, qwen3.8 and gemma4? | 1 | agent, with Ollama free |
| 3 | Token logging per attempt | — | agent |
| 4 | Thinking budget (setting, two-call player, CLI, ADR 0007, CONTEXT.md) | 2, 3 | agent |
| 5 | Thinking level (`bool` → level) | 3 | agent |
| 6 | Budget probe on the 60 fixed positions; choose default budgets | 4, 5 | agent writes the script, **you** run it |
| 7 | Games to spec | 6 | **you** |

**1. Gemma 4 in the model list.** Add the pulled tag to `LLM_MODELS` with the thinking values `ollama show` reports, and a dated comment as for the others. One scripted faceoff test with it. Nothing else changes.

**2. Spike: forced answer per model.** For qwen3.5:9b, qwen3.8 and gemma4:
- render a prefilled `thinking` + `content: " "` assistant message with `_debug_render_only` (or the `/api/chat` debug output) and check it closes the thinking block;
- make one real budgeted call (budget 256) under Listed enforced and check the answer is in the enum.

Write the result into `docs/research/thinking-budget.md` (a "Verified" section). If gemma4 fails, describe the raw `/api/generate` route instead. No production code.

**3. Token logging.** `LlmReply` and each `llm_attempt` log `thinking_tokens`, `answer_tokens`, `prompt_tokens`, `done_reason` (from Ollama's `eval_count`, `prompt_eval_count` and `done_reason`; thinking tokens estimated from the share of thinking characters when Ollama gives one combined count). `analyse_games` reports median/p90 per configuration. No setting changes, so no new configuration.

**4. Thinking budget.** As in Implementation Decisions. Includes ADR 0007, the `CONTEXT.md` entries, the API types and `README.md`.

**5. Thinking level.** As in Implementation Decisions. `true` stays valid and means Ollama's default.

**6. Budget probe.** `scripts/probe_thinking_budget.py`, reusing `docs/research/board-images-positions.json` (60 positions) and the probe pattern of `scripts/probe_board_images.py`:
- **Conditions:** per model, thinking off, unbounded, and budgets 512 / 1,024 / 2,048 / 4,096 (qwen3.8 also at `xhigh`).
- **Recorded:** first-attempt legality under Free, Stockfish centipawn loss under Listed enforced, thinking tokens, latency.
- **Output:** a table in `docs/research/thinking-budget.md`, and the chosen default budget per model.

**7. Games to spec.** See the guide below.

## Run guide (for you)

0. **Wait for the pull:** `ollama list | grep gemma4`, then `ollama show gemma4:26b` and note its capabilities (thinking, levels). Close other heavy jobs: one run on Ollama at a time.
1. **Publish:** the spec and tickets 1-6 as GitHub issues (`ready-for-agent`; tickets with `## Parent`), or ask me to.
2. **Implement 1-5:** with `/orchestrate-tickets`, or one at a time. Tickets 3 and 5 can run in parallel; 4 waits for 2 and 3. The spike (2) needs Ollama free for ~15 minutes.
3. **Probe (6), Ollama free:** `uv run python -m scripts.probe_thinking_budget --models qwen3.8:latest gemma4:26b --budgets 0,512,1024,2048,4096 --positions 60`. About 3-6 hours for both models; the script is resumable, so run it in chunks (`--limit 15`). Read the table and set the default budgets.
4. **Smoke test, 2 games, ~30-60 min:**
   ```
   uv run python -m chessllm.faceoff_batch --models gemma4:26b gemma3:12b --thinking-for gemma4:26b \
       --thinking-budget <B> --llm-constraints listed_enforced --games 2
   uv run python -m scripts.analyse_games --mode llm_faceoff --since <start time>
   ```
   It works if there are no timeout forfeits, the log shows `thinking_tokens` and `forced` per attempt, and every forced answer is a legal move.
5. **The pairings, Listed enforced, budgeted, 4-6 games each:**
   - qwen3.8 (`medium`, B) vs gemma3:12b: a replay of 2026-10-20 without the timeout.
   - gemma4 (B) vs qwen3.8 (B): the two thinking models.
   - gemma4 (B) vs gemma3:12b: what thinking adds within one family.

   For each, record score, centipawn loss, forced share and minutes per game.
6. **Anchored games for a Rating:** once the random Anchor and the rated-track ADR exist (roadmap steps 3-4), `anchor_batch --thinking-budget B`, with the stopping rule (roadmap step 7).
