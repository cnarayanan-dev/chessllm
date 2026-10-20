# Games decided by Forfeits, not chess: ideas to try, 2026-10-20

A brainstorm, not a plan of record. Under **Free**, every finished gemma3:12b vs llama3:8b **LLM faceoff** (11 of 11) and both of llama3:8b's Free **Anchor matches** ended in a **Forfeit**. This lists ways to change that, what each would cost, and what it would do to the benchmark's meaning. Nothing here has been run.

## What the prompt actually shows

- **System message** (`chessllm/prompts/system.txt`): the colour, "against a human" (also in faceoffs and Anchor matches), "you get the game so far in PGN and the current position in FEN", reply in SAN, and an example answer `{"move": "e4"}`. With thinking off the schema is `ReasonedMoveAnswer`, so the real answer starts with a `reasoning` field the example never shows.
- **User message** (`turn_messages` in `chessllm/prompt.py`): `PGN: <Move record>` and `FEN: <fen>`, plus `Legal moves:` under **Listed**. No board, no piece list, no "you are in check", no last move. The model has to rebuild the position from the Move record or decode the FEN itself.
- **Retries** (`_play_llm_turn` in `chessllm/game.py`): the same messages plus each rejected answer and its feedback, so the conversation grows within the **Turn**. **Explained** feedback says `Your move "X" is illegal in this position (kind: illegal move). Attempt n of m. Reply with a different legal move.` 148 of llama's 148 failures in the 25-attempt game were kind "illegal", so for nearly every failure explained tells the model no more than **bare**.

## More evidence from the logs

Computed for this note with a throwaway script over the 2026-10-19 Free, Standard rules games: the llama3 Anchor matches and the gemma/llama faceoffs, 5 and 25 attempts. That is 564 Turns and 824 illegal moves.

| | llama3:8b | gemma3:12b |
|---|---|---|
| Illegal moves | 502 | 322 |
| Legal in one of the side's earlier positions in the game | 59% | 54% |
| Target square held by its own piece | 34% | 46% |
| An exact replay of a move it already played | 21% | 22% |
| Long-form moves (`Qd7-d6`) whose from-square is wrong | 68 of 79 | - |
| Turns in check / illegal moves in those Turns | 7 / 44 (6.3 per Turn) | 1 / 6 |
| First attempt legal | 41% | 53% |
| Retry legal, attempts 2-4 | ~40% each | ~37% each |
| Retry legal, attempts 6-25 | 18% (18 of 102) | 40% (14 of 35) |

- **The board the model plays on is out of date.** Of the illegal moves that were legal earlier in the game, 38% were legal only 10 or more of the side's own moves ago: the opening board.
- **Check is rare but deadly.** About 2% of llama's Turns were in check, yet 3 of the 13 forfeited Turns were.
- **Retries look like fresh draws, not corrections.** For llama a retry succeeds about as often as a first attempt, so the feedback adds nothing. Deep into a failing Turn it drops to 18%. In both 25-attempt forfeits llama fell into a two-move loop, alternating the same two Reasoning sentences ("develops a piece and puts pressure on the kingside" / "supports the pawn on e5") and repeating moves it had already been refused (Qg4, b4-b3, Qd7-c7, Qe7-f6).
- **Native tool calling:** `ollama show` lists `tools` only for qwen3.5:9b. llama3:8b has completion only, gemma3:12b completion and vision.

## The ideas

Each idea: what it is, the problem it targets, the code it touches, what it does to validity, the cost (S/M/L), and a cheap test.

**One prerequisite cuts across several ideas.** `PlayerConfiguration.prompt` (`chessllm/leaderboard.py`) is the system prompt's *file name*, and the user message is built in code. Any change to `turn_messages`, `retry_feedback` or the answer schema therefore changes every configuration's prompt without changing its identity, and Ratings would silently pool old and new games. Before ideas 1-4 and 7 ship as anything but an experiment, the configuration needs a prompt version or hash that covers the user message and feedback wording too (`docs/research/prompt-tooling.md`, "identify a prompt by its content"). That needs an ADR touching ADR 0004 and 0005.

### A. What the model is shown

**1. Show the position, not only the record: a piece list, optionally an ASCII board**
- *What:* add `White: Kg1 Qd3 Rf1 Ra1 Bc2 Nf1 Pa3 ...` / `Black: ...` (and/or python-chess's `str(board)`) to the user message.
- *Targets:* the stale board (55-59% of illegal moves were legal earlier), moves onto its own pieces, wrong from-squares (68 of 79), pieces long gone. ChessQA found an explicit piece arrangement raised accuracy (`docs/research/llm-chess-notation.md`).
- *Code:* `turn_messages` in `chessllm/prompt.py` (a `pieces` line); a new system prompt file that explains it; a way to choose it per side (`LlmSide.prompt`, Option A in `prompt-tooling.md`).
- *Validity:* still **Free**. It gives the state, not the legal moves, so it measures move generation and chess, not memory of the Move record. That is arguably a better split: board tracking from PGN is a separate skill that 8B models score 0% on (Hwang et al.). It is a new prompt, so a new Player configuration.
- *Cost:* S, plus the prompt-identity prerequisite.
- *Test:* replay first attempts of logged positions with the old and new user message (about 300 positions, minutes). Then faceoffs.

**2. State the obvious: status lines and prompt fixes**
- *What:* "You are Black, to move. You are in check from the queen on e4." "Your last move: ...Kg8. Their last move: Qd3." Also drop "against a human" outside Play LLM, and make the example answer match the schema (`{"reasoning": "...", "move": "e5"}`).
- *Targets:* ignoring check (6.3 illegal moves per in-check Turn; 3 of 13 forfeits); the replays of its own previous move.
- *Code:* `turn_messages`, `system.txt`, `system_listed.txt`; `$opponent` wording in `system_prompt`.
- *Validity:* still Free. "In check" is a fact about the position, not a legal move. It is a new prompt.
- *Cost:* S. It bundles naturally with idea 1.
- *Test:* as idea 1. Look at in-check Turns alone: the share recovered within 5 attempts.

**3. Make the model restate the board before it moves ("regurgitation")**
- *What:* the answer schema becomes `{"my_pieces": "...", "reasoning": "...", "move": "..."}`, so the model writes where its pieces stand before choosing. Variant: two calls per Turn, first "list your pieces", then "move".
- *Targets:* the stale board, by forcing the model to commit to a board first. Dynomight found regurgitation helped gpt-4o.
- *Code:* `ReasonedMoveAnswer` in `chessllm/players.py`, `OllamaPlayer.reply`. The `reasoning()` helper and the log carry the extra field in `raw_reply`. The two-call variant touches `_play_llm_turn`.
- *Validity:* still Free. Different from idea 1: the model tracks the board itself, so it measures memory too. Diagnostic bonus: the restated list can be scored against the real board, giving a board-tracking accuracy per Turn. That would be a new metric.
- *Cost:* S (schema); M (two calls).
- *Test:* replay positions; compare first-attempt legality and score the restated piece lists.

**4. Long-form moves (`Nf3-d4`)**
- *What:* ask for the from-square in every move.
- *Targets:* makes stale-board errors explicit and lets idea 5 diagnose them precisely.
- *Code:* prompt wording only. ADR 0002 already accepts long-form SAN, but every such move becomes a **Notation slip**, so the slip count would need to treat it as the requested form.
- *Validity:* a notation change. Hwang et al. found SAN beat UCI at 7-8B; long-form SAN sits between the two, and its effect is unknown. Low priority on its own.
- *Cost:* S, plus an ADR 0002 amendment.

### B. What happens on a retry

**5. Diagnosed Retry feedback (a fourth level)**
- *What:* say *why* the move fails without listing the legal moves. For example: "You have no knight on c3; your knights are on a5 and f3." "f3 holds your own knight." "You are in check: the move must get your king out of check." "Your queen on d3 cannot reach g4." "You already tried Qg4 this turn."
- *Targets:* retries that don't converge (llama: ~40% per retry, 18% deep into a Turn, the two-move loops).
- *Code:* `retry_feedback` and the `RetryFeedback` literal in `chessllm/prompt.py`. A `diagnose(board, written)` helper can reuse the from-square and piece-type parsing in `chessllm/chaos.py`. Add the choice to the batch CLIs and the Settings modal.
- *Validity:* Retry feedback is already part of the **Player configuration**, so this fits the model cleanly. It tells the model facts about the board, more than explained and less than hinted. The **Legal-move streak** is unaffected, since it stops at the first illegal move.
- *Cost:* M.
- *Test:* retry success rate per attempt number should rise above the first-attempt rate and climb with the attempt number, not stay flat.

**6. Fresh retries with a rejected-moves list**
- *What:* each retry gets a fresh prompt (the Turn's messages, plus "Already rejected this turn: a5, Kc5, h5"), not the growing chat of rejected answers.
- *Targets:* llama's loops (repeated Reasoning, repeated refused moves). The growing transcript seems to prime the model to copy itself.
- *Code:* the retry branch of `_play_llm_turn` (`messages = messages + [...]`).
- *Validity:* changes how retries work for every configuration. Make it its own setting, or fold it into the prompt identity; don't change the default silently.
- *Cost:* S.
- *Test:* the share of a Turn's attempts that repeat a refused move (today small but concentrated in the forfeits), and retry success at attempts 6+.

**7. Sampling: temperature, and raising it on retries**
- *What:* a lower temperature for first attempts (Acher found a higher one lowered Elo), and/or a higher temperature or a new seed on each retry to break loops.
- *Targets:* loops on retry. A lower first-attempt temperature might also cut random illegal moves.
- *Code:* a fixed temperature needs no code: `chessllm/sampling.toml`, already part of the Player configuration, though it is shared by every LLM side of a game. A per-retry schedule is a small change in `OllamaPlayer.reply` (options per call) and a new setting.
- *Validity:* sampling is already a configuration setting. A schedule is a new one.
- *Cost:* S.
- *Expectation:* low. The errors come from a wrong board, and sampling doesn't fix the board.

### C. LLM constraints, and what happens after the last attempt

**8. Hinted Retry feedback: Free on the first attempt, Listed on retries**
- *What:* already built. After an illegal move the model is shown the legal moves (`--retry-feedback hinted`).
- *Targets:* forfeits directly. Under Listed llama's illegal Turns fell from 60% to 4%, so a hinted retry should almost always land.
- *Code:* none.
- *Validity:* the first attempt is pure Free, so the Legal-move streak and the illegal-move counts keep their Free meaning. Recovered Turns become "rescued by the list". The Rating then measures chess plus a fallback to the list, which is a clean, existing configuration. Caveat: Dynomight found listing legal moves *hurt* gpt-4o's play; the moves after a hint may be worse.
- *Cost:* zero.
- *Test:* the forfeit share of games, and how games end.

**9. Escalate on the last attempt (Enforced decoding as a fallback)**
- *What:* on the final attempt, switch the call to Listed enforced, so the model picks its own move among the legal ones instead of forfeiting. Variant: play a random legal move (the "fallback move" the 25-attempt write-up mentions). Escalating is better: the move is still the model's choice.
- *Targets:* forfeits, by construction.
- *Code:* `_play_llm_turn` (pass `allowed_moves` and a listed message on the last attempt); a new setting on `LlmSide`/`Settings`; a `fallback_moves` count in `SideStats`; `PlayerConfiguration`; the CLIs and Settings modal.
- *Validity:*
  - It changes what a Forfeit is (CONTEXT.md: forfeit after the retries are used up) and needs an ADR.
  - ADR 0005 counts a Forfeit as a loss; under this setting the Rating would almost never include one. That is fine only because it is a separate Player configuration.
  - ADR 0003: the illegal-move metrics stay applicable to the Free attempts, but the escalated attempt can't be illegal and must not count toward them.
  - `llm-chess-notation.md` warns against enum-constraining a Free game; this is why it must be named and counted, never the default.
  - Rule-following must stay visible: report fallback moves per game next to the Rating.
- *Cost:* M, plus an ADR and a CONTEXT.md term (e.g. **Fallback move**).
- *Test:* as idea 8, plus fallback moves per game.

**10. Rate on Listed / Listed enforced / Blind enforced**
- *What:* already built. Treat Listed or Listed enforced as the configuration that compares the *chess*, and keep Free as the rule-following track.
- *Targets:* sidesteps legality. All six Listed and enforced Anchor games ended in checkmate, not a forfeit.
- *Code:* none.
- *Validity:* ADR 0003 already handles the enforced metrics. Blind enforced is subtle: the model may "mean" an illegal move and be decoded into a nearby legal one, so its moves are partly the decoder's. Two Listed enforced faceoffs, llama3 vs qwen3.8, give a hint: one ended by threefold repetition at 125 plies. Expect draws by repetition and the **Move cap** instead of forfeits.
- *Cost:* zero.
- *Test:* the "Next" of the faceoff write-up, already planned.

### D. Tools and multi-step Turns

**11. Touch-move: name the piece, then choose among its moves**
- *What:* a two-step Turn without native tool calling. The model names a square ("e4"); the backend replies with that piece's legal moves (or "no piece of yours on e4"); the model picks one.
- *Targets:* splits the two failure modes. Naming a wrong square measures board tracking; choosing from the piece's moves can't be illegal.
- *Code:* `_play_llm_turn` gets two calls per attempt; a new answer schema; the log gets a new attempt shape (ADR 0004); the page's Reasoning and attempt panels change.
- *Validity:* a new **LLM constraints** value, between Free and Listed, and a new CONTEXT.md term. Not comparable to anything existing.
- *Cost:* L.

**12. Real tool calls (`legal_moves(square)`, `show_board()`)**
- *What:* Ollama tool calling, like LLM Chess's `get_current_board` / `get_legal_moves`.
- *Targets:* the same as 1 and 11.
- *Problems:* only qwen3.5:9b has the `tools` capability here; llama3:8b and gemma3:12b don't. LLM Chess found ~8B models at 0% win/loss *even with* a legal-move tool, losing to instruction-following errors. It also needs a tool loop in `OllamaPlayer`, logging and a turn budget.
- *Validity:* a new LLM constraints value. A `legal_moves` tool makes it Listed-on-demand.
- *Cost:* L. Not recommended now.

**13. A board image for gemma3 (vision)**
- *What:* send a rendered board as an image.
- *Targets:* the stale board, through another channel.
- *Code:* the image path through `Message` and `OllamaPlayer` for vision models only. M, and it fits one model only, so its configurations can't be compared with the others'. A curiosity, not a fix.

### E. Thinking and model choice

**14. Thinking on (qwen3.5:9b, qwen3.8 only)**
- *What:* already a setting. llama3 and gemma3 can't think.
- *Targets:* board tracking through reasoning. ChessQA and Pleiss et al. saw large gains with reasoning in big models.
- *Risk:* the one qwen3.5:9b thinking faceoff (2026-10-19 14:59) forfeited on move 1 by timeout (300 s).
- *Code:* none.
- *Validity:* an existing setting.
- *Cost:* zero code, high wall-clock cost.
- *Test:* 2 Anchor games with thinking on and 2 with it off; watch timeouts and latency.

**15. Different models**
- *What:* larger (qwen3.8, 27.8B), or a base model continuing raw PGN (Dynomight: instruction tuning hurt every pair).
- *Validity:* raw completion drops the JSON schema and the Reasoning field.
- *Cost:* L for raw mode. A model swap answers "which models can do Free", not "how to stop forfeits".

### F. Not a fix

- **Chaos rules** already play the illegal moves. The games end by **King capture** instead and are unrated (ADR 0006).
- **More attempts** (25) was tried. The games got 3x longer and still ended in forfeits.

## Ranking: what to try first

The two zero-code configurations come first: they answer "do forfeits vanish when legality is helped?" tonight. Then the two cheap prompt and retry changes that keep the first attempt Free. The escalation fallback, which needs an ADR, comes last.

All plans: gemma3:12b vs llama3:8b, no thinking, Standard rules, 5 attempts, model-default sampling, colours alternating. The baseline is the 9 games from 2026-10-19 (`--since 2026-10-19T21:49`, 5 attempts): 9/9 forfeits, illegal Turns 39% (gemma) / 44% (llama), streak 3.8 / 3.4. Use `--since` with the batch's start time for each run.

### 1. Hinted Retry feedback (idea 8): zero code

```
uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 6 --retry-feedback hinted
uv run python -m chessllm.anchor_batch --model llama3:8b --retry-feedback hinted --engine stockfish --skill 1 --games 4
uv run python -m scripts.analyse_games --mode llm_faceoff --since <start>
```

- **Worked if:**
  - forfeits fall from 9/9 to ≤ 1/6;
  - first-attempt illegal Turns stay about 40%, a sanity check that the first attempt is still Free;
  - games end by checkmate, repetition or the Move cap.
- **Watch:** centipawn loss after a hinted retry versus first-attempt moves. If the hint makes the moves worse, that is the Dynomight effect.

### 2. Listed and Listed enforced faceoffs (idea 10): zero code, already the write-up's "Next"

```
uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 6 --llm-constraints listed
uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 6 --llm-constraints listed_enforced
```

- **Worked if:** forfeits are about 0, and the score between the models moves away from a coin flip. A difference in chess becomes visible: gemma and llama separate on score and centipawn loss.
- **Doubles as:** the reference against which 1 and 3 are judged.

### 3. Piece list + status lines (ideas 1 + 2): S, still Free

Build it as an experiment-only prompt variant (a new system prompt file plus a `pieces`/check line in `turn_messages`, behind a side setting), clearly labelled until prompt identity exists.

- **Step 1, offline, minutes.** A small replay script: take the first attempt of every Free llama and gemma Turn in the 2026-10-19 logs (about 560 positions), ask the same model with the old and new user message, and judge each answer with `chessllm.game.judge`.
  - **Worked if:** first-attempt legality rises from 41% / 53% by at least 10 points, and the share of illegal moves that were legal earlier falls well below 55%.
- **Step 2, if step 1 passes.**

  ```
  uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 6
  ```

  Run it with the new prompt.
  - **Worked if:** the Legal-move streak doubles (from about 3.5), there are fewer forfeits than the baseline, and the in-check Turns recover.

### 4. Diagnosed feedback + fresh retries (ideas 5 + 6): M, still Free

Build them together as a new Retry feedback level, e.g. `diagnosed`, so no existing configuration changes.

- **Test first on the llama Anchor match,** where non-convergence is worst:

  ```
  uv run python -m chessllm.anchor_batch --model llama3:8b --retry-feedback diagnosed --engine stockfish --skill 1 --games 4
  ```

  Then 6 faceoffs.
- **Worked if:**
  - llama's retry success rises above its 41% first-attempt rate and grows with the attempt number, instead of 40% flat and then 18%;
  - no refused move is repeated within a Turn;
  - forfeits fall, even with the first attempt unchanged.
- **Optional:** one 25-attempt game to see whether llama now always converges.

### 5. Escalate to Listed enforced on the last attempt (idea 9): M + ADR

Do this only if 1-4 leave forfeits common, or as the way to give Free configurations a Rating decided by chess. Draft the ADR and the CONTEXT.md term (**Fallback move**) first.

- **Run:** 6 faceoffs and 4 Anchor games, as above, with the new setting.
- **Worked if:**
  - zero forfeits;
  - fallback moves per game stay rare (≤ 1-2) and are reported next to the Rating;
  - the end reasons are chess.
- **If fallbacks are frequent,** the configuration is mostly Listed enforced and should be called that.

## Trade-offs and conflicts

- **Chess versus rule-following.** Ideas 8-10 make games about chess but stop measuring whether a model can play legally on its own. Keep the Free configuration as its own track and report the Legal-move streak and illegal-move rates next to any Rating, rather than dropping Free.
- **Prompt identity first.** Ideas 1-4, 6 and the diagnosed level change wording that today isn't part of a configuration's identity. Shipping them to the default prompt before prompt hashing would pool incompatible games under one Rating (ADR 0005).
- **ADR 0003.** An escalated last attempt (idea 9) is enforced inside a Free game. Its attempt must be excluded from the illegal-move metrics, and the judge must still run on it.
- **ADR 0002.** Long-form moves (idea 4) would all be Notation slips unless the rule changes.
- **CONTEXT.md.** A fallback move changes **Forfeit**. Touch-move or tools add an **LLM constraints** value. Both need new terms before code.
- **No Rating exists yet** (no Dragon Anchor, no CuckooChess Anchor). Every experiment above is compared on forfeits, streaks, retry success and centipawn loss, not on Rating.
