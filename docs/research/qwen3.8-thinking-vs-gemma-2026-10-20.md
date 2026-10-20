# qwen3.8 with thinking against gemma3:12b: 2 LLM faceoffs, 2026-10-20

Two games of qwen3.8:latest (thinking on) against gemma3:12b (which can't think), under Listed enforced so that illegal moves couldn't decide them. Result **1-1**, but qwen3.8 was much the better player in both. It mated gemma in game 1, the first checkmate between two LLMs in this project. In game 2 it was 15 points of material up when it forfeited on the 300 s time limit.

## What was done

- **`--thinking-for MODEL`** on `chessllm.faceoff_batch` turns thinking on for one model only. gemma3:12b can't think (`chessllm/models.py`), so a faceoff with thinking on both sides isn't possible.
- **Settings:** Listed enforced, Standard rules, explained Retry feedback, 5 attempts per turn, model-default sampling, 300 s per LLM call (`OllamaPlayer.TIMEOUT_S`). Thinking was sent as `think=True`, which Ollama runs at qwen3.8's `medium` effort, not its default `xhigh` (`docs/research/thinking-budget.md`).

```
uv run python -m chessllm.faceoff_batch --models qwen3.8:latest gemma3:12b --thinking-for qwen3.8:latest --llm-constraints listed_enforced --games 2
uv run python -m scripts.analyse_games --mode llm_faceoff --since 2026-10-20T13:27
```

## Results

| # | White | Black | Result | Plies | Time |
|---|---|---|---|---|---|
| 1 | qwen3.8 (thinking) | gemma3:12b | **1-0 by checkmate** | 25 | 22 min |
| 2 | gemma3:12b | qwen3.8 (thinking) | 1-0 by forfeit: qwen3.8 thought past 300 s at ply 14 | 13 | 11 min |

| | qwen3.8 (thinking) | gemma3:12b |
|---|---|---|
| Average centipawn loss | **207** | 312 |
| Accuracy | **76.1** | 67.5 |
| Mates in one allowed | 0 | 1 |
| Time per move (median / max) | 68 s / 282 s in game 1; 35 s / 76 s in game 2, then over 300 s | 12 s / 13 s |

**Game 1:** 1. e4 d5 2. exd5 Nf6 3. Nc3 c6 4. Nf3 Ne4 5. Nxe4 cxd5 6. Bc4 dxe4 7. d3 Qc7 8. dxe4 Be6 9. O-O Bd5 10. exd5 e6 11. dxe6 Nc6 12. exf7+ Ke7 13. mate. gemma gave its pieces away (4…Ne4, 9…Bd5); qwen took them and attacked the king.

**Game 2:** 1. e4 e5 2. Nc3 Nc6 3. d4 exd4 4. Bb5 dxc3 5. Qd2 cxd2+ 6. Kd1 dxc1=Q+ 7. Kxc1, then qwen3.8 gave no answer within 5 minutes. Black was 15 points of material up: gemma's pieces had been taken one by one by a single pawn.

## Findings

1. **With thinking, qwen3.8 plays real chess.** This was the first faceoff in the project won by checkmate, and the best move quality measured so far (centipawn loss 207, against 350-430 for gemma and llama under Free). Under Listed enforced it never had to retry.
2. **The time limit, not the opponent, beat it.** It lost a completely won game 2 to a timeout. Its thinking time varies a lot: from 35 s to over 300 s for a move, in an easy position. That is the risk `thinking-budget.md` describes: without a thinking budget, a timeout forfeit measures the laptop, not the model.
3. **gemma3:12b loses material at once when it can't make illegal moves.** It allowed a mate in one in game 1, and in game 2 let one black pawn take its knight, queen and bishop in turn (exd4xc3xd2+xc1=Q+).

## Caveats

- 2 games. The 1-1 hides the gap in move quality; 1-1 is not evidence the models are equal.
- qwen3.8 ran at `medium` effort (about 1,000 thinking tokens a move), not the `xhigh` used for its LLM Chess rating (846, about 12,800 tokens a move). At `xhigh` it would time out far more often under the 300 s limit.
- Times are this machine's (M3 Pro, 36 GB, both models loaded).

## Next

- A thinking budget (`docs/research/thinking-budget.md`), so a long think ends in a forced move rather than a forfeit. Then replay this pairing.
- qwen3.8 thinking against the Anchors, once a calibrated one exists (`docs/research/llm-chess-limitations-solutions.md`, roadmap step 3), for its first Rating.
