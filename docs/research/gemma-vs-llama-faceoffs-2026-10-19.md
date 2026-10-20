# gemma3:12b against llama3:8b: 9 LLM faceoffs, 2026-10-19

Nine games of gemma3:12b against llama3:8b under the default settings. gemma won **5-4**. Every game ended in a forfeit: neither model was ever checkmated, and none of the games was decided by the chess.

## What was done

- **`chessllm.faceoff_batch`.** A new command that plays LLM faceoffs unattended, through the same game session as the app. Before this, a faceoff could only be started from the page. Colours alternate game by game, and each game is analysed with Maia-2 and Stockfish as it ends:

  ```
  uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 9
  ```
- **The settings, the same for both sides:** Free, Standard rules, no thinking, explained Retry feedback, 5 attempts per turn, model-default sampling. gemma3:12b was White in games 1, 3, 5, 7 and 9.
- **The analysis.** `--since` on `scripts/analyse_games.py` now also takes a time, so the 9 games can be selected alone:

  ```
  uv run python -m scripts.analyse_games --mode llm_faceoff --since 2026-10-19T21:49
  ```

## Results

| # | White | Black | Result | Forfeited by | Plies | Forfeiter's material |
|---|---|---|---|---|---|---|
| 1 | gemma3:12b | llama3:8b | 1-0 | llama3:8b | 15 | level |
| 2 | llama3:8b | gemma3:12b | 1-0 | gemma3:12b | 31 | level |
| 3 | gemma3:12b | llama3:8b | 1-0 | llama3:8b | 33 | −3, in check |
| 4 | llama3:8b | gemma3:12b | 0-1 | llama3:8b | 26 | +1 |
| 5 | gemma3:12b | llama3:8b | 0-1 | gemma3:12b | 40 | +4 |
| 6 | llama3:8b | gemma3:12b | 0-1 | llama3:8b | 28 | −2 |
| 7 | gemma3:12b | llama3:8b | 0-1 | gemma3:12b | 8 | −2 |
| 8 | llama3:8b | gemma3:12b | 1-0 | gemma3:12b | 15 | −1 |
| 9 | gemma3:12b | llama3:8b | 1-0 | llama3:8b | 49 | level |

| | gemma3:12b | llama3:8b |
|---|---|---|
| Score | **5 / 9** (3/5 as White, 2/4 as Black) | 4 / 9 (2/4 as White, 2/5 as Black) |
| Turns with an illegal move | 39% | 44% |
| Illegal moves per turn | 0.82 | 0.87 |
| Legal-move streak (mean / median) | 3.8 / 3 | 3.4 / 4 |
| Turns recovered after a retry | 45 | 51 |
| Notation slips | 9 | 7 |
| Average centipawn loss (Stockfish) | 347 | 359 |
| Accuracy | 59.1 | 57.3 |
| Move-quality estimate | below the grid, ≤ 673 | below the grid, ≤ 672 |
| Mean latency per attempt | 6.2 s | 1.5 s |

Games averaged 27 plies, about 14 moves each.

## Findings

1. **The models are indistinguishable at this sample size.** 5-4 is what a coin would give: the 95% interval on gemma's score is roughly 25-85%. Every other number is close too: illegal-move rate, streak, centipawn loss, accuracy. The only clear difference is speed: gemma takes four times as long per move.
2. **Legality decides every game, not chess.** All 9 games were forfeits, after a streak of only 3-4 legal moves. Neither model was ever mated or allowed a mate in one. Twice the forfeiting side was materially ahead: gemma was a rook-for-a-pawn up (+4) when it forfeited game 5.
3. **The commonest illegal move is a move onto one of its own pieces.** 46% of the illegal moves target a square the model's own piece already holds: 56% for gemma, 37% for llama. The model replays a move it has already made. gemma's most common illegal move, Nf3, came 14 times, mostly with a knight already on f3. The rest are moves no piece of that type can make: 49% overall, more for llama.
4. **It loses track of the board.** In llama's forfeits it names pieces on squares they left long ago. In game 1 it tried Nc6-d4 and Bb7-c5 with the knight on a5 and no bishop on b7. In game 6 it tried Nc3-b5 and Qe2-d3 with no knight on c3 and the queen already on d3. Retry feedback doesn't help: each retry tries a different move from the same stale board.
5. **Retries rescue many turns, but not enough.** About 1 in 3 turns needed a retry and got through, 96 in all. The chance of 5 failures in a row is small per turn, but over 13 turns a game it comes up nearly every game.
6. **The move quality is poor on both sides.** Average centipawn loss is about 350 with 58% accuracy, against about 90 and 89% for llama3:8b's moves against Stockfish. With both sides blundering, a single error swings the evaluation far, and nobody punishes it with a mate.
7. **Openings are routine.** 6 of 9 games began 1. e4 e5 2. Nf3 Nc6, and the d4 games went 1. d4 d5 2. c4. The trouble starts after move 4: the first illegal move comes in the opening phase (ply ≤ 20) in 43% of cases.

## Caveats

- 9 games. The 5-4 is not evidence either way.
- Only Free was played. This compares the two models' rule-following more than their chess. Under Listed, llama3:8b's illegal moves fell from 60% of turns to 4% in its Anchor matches (`docs/research/llama3-anchor-matches-2026-10-19.md`), so Listed or Listed enforced would compare the chess itself.
- Faceoffs place the two configurations only relative to each other. Neither has a path to a calibrated Anchor yet, so neither has a Rating.
- The Move-quality estimate is unvalidated at these levels.

## Next

- The same 9 games under Listed and under Listed enforced, to see whether the coin flip turns into a difference once legality is out of the way.
- The prompt: the replayed moves (finding 3) and the stale board (finding 4) suggest it doesn't make clear enough where the pieces are now. The Move record is given; a piece list or a board diagram may help (`docs/research/prompt-tooling.md`).

## Follow-up: 25 attempts per turn instead of 5

The same pairing and settings, but with the forfeit pushed as far as the game allows: 25 attempts per turn (`--max-attempts 25`, the most a Player configuration can have). Planned: 5 games. Played: 2, plus a third cut off at ply 85. The batch hit the 2-hour limit for background jobs; each game took 20-30 minutes, against 2-5 with 5 attempts.

```
uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 5 --max-attempts 25
uv run python -m scripts.analyse_games --mode llm_faceoff --since 2026-10-19T22:26 --include-unfinished
```

| # | White | Black | Result | Plies |
|---|---|---|---|---|
| 1 | gemma3:12b | llama3:8b | 1-0, llama3:8b forfeited after 25 attempts | 89 |
| 2 | llama3:8b | gemma3:12b | 0-1, llama3:8b forfeited after 25 attempts | 92 |
| 3 | gemma3:12b | llama3:8b | unfinished at ply 85 (the batch was stopped) | 85 |

| | gemma3:12b | llama3:8b |
|---|---|---|
| Finished games | **2-0** | 0-2 |
| Turns with an illegal move | 55% | 73% |
| Illegal moves per turn | 1.6 | 2.5 |
| Most attempts in one turn | 11 | 25 (twice) |
| Turns needing more than 5 attempts | 14 of 134 | 20 of 134 |
| Average centipawn loss / accuracy | 432 / 57.3 | 436 / 56.3 |

### What happened

1. **More attempts made the games longer, not better.** Games went from 27 plies to about 90. The share of turns with an illegal move rose (gemma 39% → 55%, llama 44% → 73%) because the games now reach middlegames and endgames: 503 of the 557 illegal moves came in the middlegame. Move quality was no better (centipawn loss about 430).
2. **llama3:8b still forfeited, both times.** Then it failed 25 attempts in a row:
   - **Game 1: it ignored a check.** Black was in check with 8 legal moves (Kd7, Kd6, Kb6, Kb5, Nd5, Qd5, Qxe4, fxe4). In 25 tries it never found one: pawn pushes, queen moves, and king moves from squares its king wasn't on (Kb6-a5, Kd7-d6, Kc7-b6).
   - **Game 2: it played an opening on an endgame board.** White was not in check and had 34 legal moves. Its 25 tries were Ncd5, Bd2, Bc4, Be3, h2, h4, c4, d4, e4: moves for pieces and pawns long gone or far away, as if the board were still near the start.
3. **The difference between the models is in recovering, not in errors.** gemma also needed many retries (up to 11 in a turn) but always got there; llama twice didn't. So with 5 attempts the two forfeited about equally often (findings 1-2 above); with 25, only llama did. The models' illegal-move rates are close, but gemma's retries converge and llama's wander.
4. **Neither was mated or allowed a mate in one,** as before. Every finished game in this pairing, 11 of 11, ended in a forfeit.

### Caveats

- 2 finished games. "gemma recovers, llama doesn't" is a pattern to test, not a result.
- 25 attempts is the cap, not "no forfeit". Truly removing the forfeit would need a new rule for what happens after the last attempt, such as a random legal move played for the LLM; that would be a new Player configuration setting (CONTEXT.md, **Retry**).
- One batch of 5 at this length needs about 2.5 hours. Run the games one or two at a time (`--games 2`).
