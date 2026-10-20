# LLM chess limitations against this benchmark, ranked, 2026-10-20

This note checks each limitation in [`llm-chess-limitations.md`](llm-chess-limitations.md) (A1-H6) against the project as it stands on 2026-10-20: the code (with the uncommitted opt-in `position: described`), the ADRs and the games in `games/`. Then it ranks them by priority for the goal: a benchmark of how well small local LLMs play chess, with valid **Ratings**, comparable **Player configurations** and games decided by chess. Nothing was run on Ollama. The numbers come from `scripts.analyse_games`, from `chessllm.leaderboard.leaderboard(games/)` run offline, and from throwaway read-only scripts over `games/*.jsonl` (log version 2, Standard rules unless stated).

Priority: **P1** critical (results so far or next are invalid without it), **P2** important (needed before results mean much), **P3** later, **P4** not relevant now. Effort: **S** hours, **M** days, **L** a week or more, or long wall-clock time.

## State of play in one paragraph

There are 74 game logs. 10 are Anchor matches, all against the Stockfish stand-in at Skill 1 (no Dragon), all lost. 30 are LLM faceoffs, mostly gemma3:12b vs llama3:8b under **Free**. Of the 21 finished faceoffs, 20 ended in a **Forfeit** (19 under Free, plus one qwen3.5:9b thinking timeout on move 1) and one in threefold repetition. In today's 6 **Hinted** faceoffs gemma3:12b won 6-0: llama3:8b forfeited every game. In those forfeit Turns none of its 24 answers after the hint was a move from the list, including one Turn in check with only 6 legal moves. No Player configuration has a finite **Rating**. The offline leaderboard gives only upper bounds: llama3:8b < 466 under all four **LLM constraints**, gemma3:12b Free < 505, qwen3.8 Listed enforced < 466. These all rest on 2 games per configuration against an Anchor whose rating is a guess (±300) and is too low. The **Move-quality estimate** failed validation (bias +308 in the lowest band) and every LLM sits below its grid (≤ ~670).

## Top 10, ranked

| # | ID | Limitation | P | Evidence here | Effort |
|---|---|---|---|---|---|
| 1 | [H2](llm-chess-limitations.md#h2-elo-estimation-at-the-bottom-of-the-scale) + [D3](llm-chess-limitations.md#d3-below-the-random-mover-floor) | No usable scale at the bottom: no calibrated Anchor, no random-mover floor | P1 | 0 finite Ratings. All 10 anchored games lost to an uncalibrated Stockfish stand-in (±300, about 800-900 by the CuckooChess check vs the 250 it is rated at). Every bound comes from it | S (random mover) + M (Dragon or CuckooChess) |
| 2 | [H1](llm-chess-limitations.md#h1-forfeits-dominate-the-result) | Forfeits decide the games | P1 | 20 of 21 finished faceoffs and 2 of 2 Free Anchor matches ended in forfeit. Hinted turned gemma–llama from 5-4 into 6-0 on forfeits alone | M (decide the rated track; fallback ADR) |
| 3 | [H6](llm-chess-limitations.md#h6-reproducibility) + [F2](llm-chess-limitations.md#f2-prompt-sensitivity) | Configuration identity: prompt, model build | P1 | `PlayerConfiguration.prompt` is a file name. The user message, Retry feedback wording and schema live in code and aren't part of the id. No model digest, quantisation or Ollama version is logged | S-M + ADR |
| 4 | [A1](llm-chess-limitations.md#a1-board-state-tracking-no-reliable-world-model) | No board-state tracking | P1 | 34% (llama) / 44% (gemma) of illegal moves land on its own piece; 54-59% were legal earlier in the game; gemma read 16% of its pieces correctly from the FEN | S: `position: described` is built, never played (0 logs) |
| 5 | [F1](llm-chess-limitations.md#f1-instruction-following-and-format-compliance) | Instruction following (here: using the list it is given) | P2 | After a hint, legal on retry: gemma 92%, llama 54%. In llama's 6 hinted forfeits, 0 of 24 retries picked from the list. Prompt says "against a human" in every Mode; the example omits the `reasoning` field | S (prompt fixes, after #3) |
| 6 | [A3](llm-chess-limitations.md#a3-check-and-king-safety) | Check and king safety | P2 | llama Free: 8 in-check Turns, 48 illegal moves (6 per Turn), 4 of its 19 forfeits came in check. All 6 Anchor checkmates came right after it allowed a mate in one | S (described's "You are in check") |
| 7 | [G1](llm-chess-limitations.md#g1-reasoning-helps-most-but-at-large-token-and-latency-cost) | Reasoning is the lever, but slow | P2 | qwen3.5:9b thinking forfeited move 1 on the 300 s timeout. In the qwen3.8 thinking game running now, the slowest attempt took 282 s (max ~12,700 thinking characters) | M (thinking budget, `thinking-budget.md`) |
| 8 | [H3](llm-chess-limitations.md#h3-small-samples-and-noisy-opponents) | Small samples | P2 | 2 games per Anchor configuration; 9 faceoffs gave 5-4, a 25-85% interval | L (wall-clock), after #1-#3 |
| 9 | [C4](llm-chess-limitations.md#c4-repetition-and-inability-to-convert) | Repetition and failing to convert | P2 | The one finished Listed enforced faceoff: qwen3.8 was 18 points of material up and drew by threefold repetition at ply 125, giving rook checks. That draw caps qwen3.8 at < 466 | S-M (status line, after #3) |
| 10 | [F4](llm-chess-limitations.md#f4-enforced-decoding-and-legal-lists-dont-create-skill) | A list or Enforced decoding fixes legality, not strength | P2 | llama3:8b under Listed / enforced: 0 forfeits but 6 checkmates in 6 Anchor games; centipawn loss 76-109, about the same as Free (82) | none (an interpretation and track choice) |

Next in line: [C2](llm-chess-limitations.md#c2-long-move-history-and-context-length) (P2, S: `num_ctx` isn't set or logged, and thinking now runs to ~3,200 tokens) and [A2](llm-chess-limitations.md#a2-legality-without-a-legal-move-list) (P2, already measured by the Free track).

## Dependencies

- **#1 → any Rating.** With no calibrated Anchor there is no Rating (ADR 0005), so more faceoffs (#8) only place configurations relative to each other. A random-mover Anchor (S, one `Anchor` class plus an `ANCHOR_RATINGS` entry at about −122) is the only one these models can score against. It turns "< 466" into numbers. Dragon or CuckooChess is needed above it.
- **#3 → every prompt change** (#4 beyond the built variant, #5, #6, #9, diagnosed feedback). Until the configuration id covers the user message, feedback wording and schema, editing `turn_messages` or `retry_feedback` silently pools old and new games under one Rating. `position` already shows how to do it: `described` is a field of the configuration. Any later change to `describe_position`'s wording would not be.
- **#2 needs #1 and a decision.** Which track carries the headline Rating (Free with forfeits, Free + fallback move, or Listed / Listed enforced) decides what #8's games are spent on. A fallback move needs an ADR and a CONTEXT.md term (forfeit brainstorm, idea 9).
- **#4 and #6 are one experiment.** `described` already has the piece list and "You are in check".
- **#7 before thinking models enter any rated pool.** Otherwise a timeout forfeit measures this laptop, not the model. #7 also depends on C2: thinking tokens count against the context window.
- **#9 only matters once #2 is solved.** When forfeits go, repetition draws take their place, as the one Listed enforced game shows.
- **#8 last.** Spending long batches before #1-#3 produces games that can't be rated or can't be pooled.

## Each limitation

Format: **Seen** (evidence here), **Done / gap** (what the project does, what's missing), **Impact** (on the goal and on results so far), then the priority.

### A. Board state and rules

**[A1](llm-chess-limitations.md#a1-board-state-tracking-no-reliable-world-model) Board-state tracking.** P1, S.
- *Seen:* the main cause of illegal moves. Of 662 (llama) and 412 (gemma) illegal moves, 222 and 183 target a square its own piece holds. 54-59% were legal earlier in the game, 38% of those only 10+ own moves before (forfeit brainstorm). In the 25-attempt follow-up llama played opening moves on an endgame board. The perception probe got 16% (gemma) and 28% (qwen3.5) recall from the FEN, 0 lists exactly right (`board-images.md`). The Legal-move streak median is 3.
- *Done / gap:* the prompt gives only PGN + FEN. `describe_position` (pieces by square, last move, check) is built as `position: described` and is part of the configuration, but not one game has used it. The planned offline replay (brainstorm step 1) hasn't been run.
- *Impact:* under Free this is what the benchmark measures today, more than chess. It is the root of #2.

**[A2](llm-chess-limitations.md#a2-legality-without-a-legal-move-list) Legality without a list.** P2, none.
- *Seen:* first-attempt legal under Free: llama 43-45%, gemma 47-54%. Under Listed: 96% / 98%.
- *Done / gap:* the four LLM constraints separate it cleanly; ADR 0003 keeps enforced metrics as n/a. No gap in measurement.
- *Impact:* a valid result in its own right (the Free track). Not a fix target, but the reason the Free track can't rank chess (#2).

**[A3](llm-chess-limitations.md#a3-check-and-king-safety) Check and king safety.** P2, S.
- *Seen:* llama Free: 6 illegal moves per in-check Turn, 4 of 19 forfeits in check. Hinted, game 2026-10-20T11-04: in check, 6 legal moves listed, 5 tries, none from the list (b5, Bd8, Bh7, Kf7, Bxg6). All 6 Anchor checkmates followed an allowed mate in one. In the Chaos games both king captures followed an ignored check.
- *Done / gap:* `described` adds "You are in check." Diagnosed feedback ("you are in check: the move must get your king out of check") is only an idea.
- *Impact:* check Turns are rare (~2-12% of Turns) but decide a large share of forfeits and every Anchor loss.

**[A4](llm-chess-limitations.md#a4-square-geometry-and-piece-movement) Square geometry.** P3, M.
- *Seen:* knight jumps to unreachable squares (Nc5, Nc6, Nd7) in llama's Anchor matches. "Unreachable" was 7 of gemma's 15 text errors in the probe.
- *Done / gap:* nothing targets it directly except Listed. A piece list doesn't give moves; diagnosed feedback ("your queen on d3 cannot reach g4") would.
- *Impact:* second cause of illegal moves after A1. Hard to fix without giving the moves away.

**[A5](llm-chess-limitations.md#a5-hidden-state-and-special-rules-castling-en-passant-promotion-repetition) Hidden state and special rules.** P4.
- *Seen:* 4 illegal castles out of 20 tries; 2 promotions, both legal. Games rarely reach endgames (the probe found no logged position with ≤ 26 points of pieces).
- *Done / gap:* the FEN gives castling and en passant rights; the PGN gives history; the game counts repetition itself.
- *Impact:* negligible now.

### B. Notation, tokenisation, input format

**[B1](llm-chess-limitations.md#b1-output-notation-san-vs-uci) Output notation.** P4.
- *Seen:* 60 Notation slips in all, mostly long-form SAN (68 of 79 long-form moves had a wrong from-square) and check signs. No UCI answers.
- *Done / gap:* SAN is asked for; ADR 0002 judges leniently and records slips. Covered.
- *Impact:* none on results.

**[B2](llm-chess-limitations.md#b2-tokenization-artifacts) Tokenisation artifacts.** P4.
- *Seen:* not observed. The answer is a JSON field under a schema, not a PGN continuation, so the trailing-space effect doesn't apply.
- *Impact:* none now. It matters only if a raw-completion adapter for base models is added (E1).

**[B3](llm-chess-limitations.md#b3-board-representation-sensitivity) Board representation.** P2 (with A1), S.
- *Seen:* not yet measurable. Only one representation (PGN + FEN) has been played. The probe says the FEN isn't read.
- *Done / gap:* `position: described` is the first alternative, and it is an identified configuration setting. Untested.
- *Impact:* the representation is part of what a Rating means. Every result so far is "PGN + FEN".

**[B4](llm-chess-limitations.md#b4-board-images-vision-input) Board images.** P4.
- *Seen:* probed (`board-images.md`): gemma 5/20 legal with text and 5/20 with text + image; moves onto its own pieces 5 → 12.
- *Done / gap:* not built, on purpose.
- *Impact:* none. The recommendation not to build it stands. One uncontended qwen3.5 rerun may be worth doing later.

### C. Context, game length, move history

**[C1](llm-chess-limitations.md#c1-collapse-after-the-opening-out-of-book) Out-of-book collapse.** P3.
- *Seen:* openings are routine (1. e4 e5 2. Nf3 Nc6 in 3 of today's 6). But the collapse comes earlier than "after 5-10 moves": the streak median is 3, and today 52 of 219 illegal moves came in the opening and 167 in the middlegame. Here it is hard to tell apart from A1.
- *Done / gap:* phase is reported by `analyse_games`. Not separable until A1 is addressed.
- *Impact:* small on its own.

**[C2](llm-chess-limitations.md#c2-long-move-history-and-context-length) Long history and context length.** P2, S.
- *Seen:* in the 25-attempt games, 503 of 557 illegal moves came in the middlegame, and the illegal-Turn share rose as games got longer. Context truncation is **not measurable**: `num_ctx` isn't set, and `prompt_eval_count`, `eval_count` and `done_reason` aren't logged. Prompts without thinking are small (an estimated < 2k tokens with 5 retries), but qwen3.8 thinking now produces up to ~3,200 tokens. Ollama's default window could be hit there [Inference; check `ollama show` / the default when the GPU is free].
- *Done / gap:* each Turn starts fresh (CONTEXT.md, **Turn**), which bounds growth. Retries add to it within a Turn.
- *Impact:* a silent truncation would corrupt thinking results without any sign in the log. Logging the token counts is cheap.

**[C3](llm-chess-limitations.md#c3-shortcutting-on-the-last-move) Last-move shortcut.** P4.
- *Seen:* not measured. Exact replays of its own earlier moves (21-22% of illegal moves) suggest pattern repetition rather than reacting to the last move.
- *Done / gap:* `described` adds "Last move: …", which may encourage the shortcut. Worth watching when it is run.

**[C4](llm-chess-limitations.md#c4-repetition-and-inability-to-convert) Repetition and failing to convert.** P2, S-M.
- *Seen:* 2026-10-19T20-29 (llama3 vs qwen3.8, Listed enforced, both thinking off): qwen3.8, 18 points up (rook, bishop, knight and pawns against rook and pawns), drew by threefold repetition at ply 125 with Rc1+/Rc2+ checks. On the leaderboard that draw bounds qwen3.8 by llama3: < 466. The Move cap (150 a side) has never been reached; the longest game was 125 plies.
- *Done / gap:* repetition is counted from the game's own positions (ADR 0006) and the PGN is shown, but the LLM isn't told that a position repeats.
- *Impact:* once forfeits go (#2), this becomes the next way games are decided by something other than chess, and it biases Ratings toward 50%.

### D. Playing strength

**[D1](llm-chess-limitations.md#d1-no-lookahead-tactical-depth) No lookahead.** P3 (measurement only).
- *Seen:* all 6 Anchor checkmates came right after an allowed mate in one. Centipawn loss about 80-110 against Stockfish, 350-510 in faceoffs (511 today, accuracy 50%).
- *Done / gap:* this is what the benchmark is meant to measure, not a defect to fix. The gap is the instrument: the Move-quality estimate failed validation and floors at about 424-670 on the chess.com scale.

**[D2](llm-chess-limitations.md#d2-weak-position-judgment) Weak position judgment.** P3.
- *Seen:* gemma forfeited game 5 four points up; qwen3.8 couldn't convert +18 (C4).
- *Done / gap:* not separately measured; Stockfish evaluations are in the analysis files and could show it.

**[D3](llm-chess-limitations.md#d3-below-the-random-mover-floor) Below the random-mover floor.** P1, with H2 (#1).
- *Seen:* every anchored game is lost, so every configuration with an Anchor path gets only "< X".
- *Done / gap:* ADR 0005 defers a random-mover Anchor "if the bottom of the leaderboard is all < X". It is now, so that condition is met. `ANCHOR_RATINGS` is the one place to add it.

### E. Model type and training

**[E1](llm-chess-limitations.md#e1-chatinstruction-tuning-vs-base-completion) Chat vs base.** P4.
- *Seen:* not testable; only chat models with a JSON schema are used.
- *Gap:* a raw `/api/generate` adapter (M). It answers a different question and loses Reasoning. Later.

**[E2](llm-chess-limitations.md#e2-chess-knowledge-scales-with-size-and-pretraining) Size and pretraining.** P3.
- *Seen:* gemma3:12b recovers on retries and llama3:8b doesn't (Hinted 92% vs 54%), but their first-attempt legality is close.
- *Done / gap:* model choice is in `candidate-models.md` (Qwen3-8B-Chess, Muse Glimmer, Gemma 4). Not the bottleneck while the scale is missing.

**[E3](llm-chess-limitations.md#e3-quantization) Quantisation.** P3 (logging part of #3: S).
- *Seen:* not measured. Every model is its Ollama default tag, and the quantisation isn't logged.
- *Impact:* a tag can be re-pushed with different weights; record the digest and quantisation (H6). A Q4-vs-Q8 comparison is later.

### F. Prompting, format, decoding

**[F1](llm-chess-limitations.md#f1-instruction-following-and-format-compliance) Instruction following.** P2, S.
- *Seen:* JSON format failures are almost nil (1 "invalid" in today's 219 illegal moves), thanks to Ollama's `format` schema. The failure that matters is not using what it is told: in Hinted, legal on retries 2-5 was gemma 73/79 (92%) and llama 72/134 (54%), no better than llama's first attempt. Prompt defects: "against a human" in faceoffs and Anchor matches; the example answer `{"move": …}` doesn't match the thinking-off schema, which puts `reasoning` first.
- *Impact:* Hinted results measure list-following as much as chess. The 6-0 is a real difference between the models, but not a chess one.

**[F2](llm-chess-limitations.md#f2-prompt-sensitivity) Prompt sensitivity.** P1, with H6 (#3).
- *Seen:* not yet measured (one prompt per constraint). The literature's 76-point swings make prompt identity essential before any prompt work.
- *Done / gap:* the system prompt file name and `position` are part of the configuration. The user message, feedback text and schema aren't.

**[F3](llm-chess-limitations.md#f3-structured-json-output) Structured output.** P4.
- *Seen:* no sign of harm. Reasoning before the move matches the .txt finding. qwen3.5:9b with thinking off spent its `reasoning` field decoding the FEN character by character and ran long (probe).
- *Done:* the schema puts reasoning first; Enforced decoding constrains only the move.

**[F4](llm-chess-limitations.md#f4-enforced-decoding-and-legal-lists-dont-create-skill) Legality isn't strength.** P2, none.
- *Seen:* llama3:8b Listed / Blind enforced / Listed enforced: 6 of 6 Anchor games lost by checkmate, centipawn loss 76-109 against 82 under Free. Hinted games ran longer (46 plies), and gemma's centipawn loss rose from 388 (explained) to 512. That may be the Dynomight "list hurts" effect or just longer games; untested.
- *Impact:* choosing Listed / Listed enforced as the rated track removes forfeits but leaves the models below any Anchor except a random mover. This reinforces #1.

**[F5](llm-chess-limitations.md#f5-sampling-determinism-and-degeneration) Sampling.** P3, S.
- *Seen:* model defaults everywhere (`sampling: "model_default"`; gemma3's default temperature is 1.0). Loops in llama's 25-attempt forfeits; rejected moves proposed again in the same Turn are rare (3-5 per configuration).
- *Done / gap:* sampling is part of the configuration, but `sampling.toml` is shared by every LLM side of a game. A thinking qwen (Qwen recommends T = 0.6) can't sample differently from gemma in one faceoff. "model_default" also depends on the tag's Modelfile (H6).

### G. Thinking

**[G1](llm-chess-limitations.md#g1-reasoning-helps-most-but-at-large-token-and-latency-cost) Reasoning cost.** P2, M.
- *Seen:* qwen3.5:9b thinking: one game, forfeited on the 300 s timeout at move 1. qwen3.8 thinking (the faceoff running now): median 44 s, max 282 s per attempt, up to ~12,700 thinking characters. `think=True` means `medium` on qwen3.8, not the configuration LLM Chess rated at 846 (`thinking-budget.md`).
- *Done / gap:* a wall-clock timeout only. A timeout is a Forfeit, so it depends on the machine and on GPU contention (the probe saw swapping with three models loaded). The token budget design (`thinking_budget`, budget forcing) is researched, not built.
- *Impact:* thinking is where small models gain strength. Without a budget, thinking configurations can't be rated fairly or reproduced on other hardware.

**[G2](llm-chess-limitations.md#g2-overthinking-and-diminishing-returns) Overthinking.** P3.
- *Seen:* not yet measurable (11 thinking attempts in the current game).
- *Gap:* comes with G1's budget sweep.

### H. Evaluation

**[H1](llm-chess-limitations.md#h1-forfeits-dominate-the-result) Forfeits dominate.** P1, M.
- *Seen:* see the table (#2). Under Free, raising attempts to 25 made games 3× longer and still ended in forfeits. Hinted made llama forfeit 6 of 6 and gemma 0 of 6.
- *Done / gap:* the forfeit rate, Legal-move streak and recovered Turns are reported next to results. The brainstorm's zero-code options have been partly run (Hinted: done, with the result above; Listed / Listed enforced faceoffs: 7 started, 1 finished, one of them running now). There is no decision yet on which track carries the Rating, and no fallback move.
- *Impact:* every faceoff result so far (5-4, 6-0, gemma "< 505") is a rule-following result, not a chess one.

**[H2](llm-chess-limitations.md#h2-elo-estimation-at-the-bottom-of-the-scale) Elo at the bottom.** P1, S + M.
- *Seen:* see the table (#1). The fit (`rating.py`) handles 0% correctly with upper bounds, but those bounds are as good as the Stockfish stand-in's guessed rating, which the CuckooChess check says is far too low. So "< 466" may be an underestimate of the bound.
- *Done / gap:* ADR 0005's Dragon ladder is built but has never run (download blocked by an expired TLS certificate). CuckooChess is built locally but isn't an Anchor adapter yet. There is no random mover.

**[H3](llm-chess-limitations.md#h3-small-samples-and-noisy-opponents) Small samples.** P2, L.
- *Seen:* 2 games per Anchor configuration, 6-9 per faceoff pairing; a Free 5-attempt faceoff takes 2-5 minutes, a 25-attempt one 20-30, a thinking one much longer.
- *Done / gap:* the Rating gives 95% intervals and bounds; `anchor_batch` defaults to 30 games. Only the wall-clock time is missing, and it is best spent after #1-#3.

**[H4](llm-chess-limitations.md#h4-protocols-arent-comparable) Protocols aren't comparable.** P3.
- *Seen:* this project's qwen3.8 (`think=True` = medium, PGN + FEN, SAN, no tools) is not LLM Chess's qwen3.8 (12,800 tokens per move, tools, UCI).
- *Impact:* use LLM Chess only as a sanity check, compared with Listed rather than Free. Say so wherever it is cited.

**[H5](llm-chess-limitations.md#h5-contamination-and-memorisation) Contamination.** P3, M.
- *Seen:* 6 of 9 faceoffs (2026-10-19) and 3 of 6 today began 1. e4 e5 2. Nf3 Nc6. Every game starts from the initial position.
- *Gap:* no forced-opening or random-start variant (Game Arena's fix). Matters little while games collapse by move 4. Later.

**[H6](llm-chess-limitations.md#h6-reproducibility) Reproducibility.** P1, S-M.
- *Seen:* `game_start` logs the model tag, the effective side settings, sampling (or "model_default") and the prompt file's path. It doesn't log the model digest, quantisation, Ollama version, or a hash of the user-message template, feedback wording and schema. `analyse_games` groups configurations without max attempts or sampling (its 14-game gemma Free row mixes 5 and 25 attempts); the leaderboard splits them correctly.
- *Done / gap:* ADR 0004 logs effective settings per side. A content hash or version of everything the model is shown, plus `ollama show` digest and quantisation at game start, needs an ADR touching 0004 and 0005 (`prompt-tooling.md`, "identify a prompt by its content").

## Validity of results so far

- **Ratings:** none are valid as numbers. The upper bounds rest on 2-game samples against an uncalibrated Anchor.
- **Faceoff scores** (5-4, 2-0, 6-0) are valid as records of rule-following under each setting, not of chess.
- **Legal-move metrics** (streak, illegal Turns, recovered Turns, first-attempt legality) are the most trustworthy numbers the project has. They show a clear, repeatable signal: Free about 45-55% first-attempt legal, Listed 96-98%.
- **Move quality:** centipawn loss and accuracy are usable for comparisons within this project. The Move-quality estimate isn't (unvalidated, below the grid).
- **Pooling risk:** so far none. Every game was played with today's prompt code. But the next edit to `turn_messages` or `retry_feedback` would pool silently (#3).
