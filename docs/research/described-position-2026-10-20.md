# The described position: 6 gemma3:12b vs llama3:8b faceoffs, 2026-10-20

Roadmap step 0 of `docs/research/llm-chess-limitations-solutions.md`. The question: does telling the model where every piece stands, what the last move was and whether it is in check (`--position described`) make it play legally more often? Answer: **not enough to matter**. It missed both success marks, and every game still ended in a Forfeit.

## What was done

- The same pairing and settings as the 9-game Free baseline of 2026-10-19 (`gemma-vs-llama-faceoffs-2026-10-19.md`), plus the described position. Settings: Free, Standard rules, no thinking, explained Retry feedback, 5 attempts.
- Each turn's message adds, under the PGN and FEN: the last move; "Your pieces (White): King e1; Queen d1; Rooks a1, h1; …"; "Opponent's pieces (Black): …"; and "You are in check." when it applies.

```
uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 6 --position described
uv run python -m scripts.analyse_games --mode llm_faceoff --since 2026-10-20T15:17
```

## Results

Result 3-3, all 6 games by Forfeit (3 each).

| | Baseline, FEN only (9 games) | Described position (6 games) | Change |
|---|---|---|---|
| gemma3:12b, first-attempt legal | 61% | 66% | +5 points |
| llama3:8b, first-attempt legal | 56% | 51% | −5 points |
| gemma3:12b, Legal-move streak (mean) | 3.8 | 4.3 | ×1.1 |
| llama3:8b, Legal-move streak (mean) | 3.4 | 4.3 | ×1.3 |
| gemma3:12b, illegal moves onto its own piece | 56% | 39% | −17 points |
| llama3:8b, illegal moves onto its own piece | 37% | 33% | −4 points |
| Game length (mean plies) | 27 | 35 | +8 |
| Forfeits | 9 of 9 | 6 of 6 | — |

The success marks were first-attempt legality up 10 points or more and the streak roughly doubled. **Neither was met** for either model.

## Findings

1. **The piece list cut gemma's most typical mistake.** Moves onto its own piece fell from 56% to 39% of its illegal moves. Its first-attempt legality rose 5 points; that's real, but small.
2. **llama3:8b didn't use it.** Legality fell slightly (within noise), and its mistakes stayed the same: pieces moved in ways they can't move (Nc5, Nc6 with no knight that reaches).
3. **Games got a little longer but still ended by Forfeit.** This matches the literature (`llm-chess-limitations.md`, A1): small models don't track the board, and stating the board helps only somewhat. Showing the legal moves (Listed: about 96-98% legal) does far more than describing the position.
4. **Move quality looked worse:** centipawn loss of about 710 against about 350. That is probably the longer games reaching lost, wild positions where every move loses a lot, not the description itself. 6 games can't separate the two.

## Caveats

- 6 games against 9; differences of 5 points are within noise.
- Only Free was tested, where legality is the bottleneck. The described position may matter more for move quality under Listed enforced, and for thinking models; that is untested.

## What it means for the roadmap

- **Keep `described` as an option, but don't build on it** as the fix for forfeits. The forfeit problem is better handled by choosing the rated LLM constraints (roadmap step 4, Listed enforced) and by diagnosed Retry feedback (step 5).
- **The probe of fixed positions (step 5, and the thinking-budget probe in #67) can test `described` cheaply** alongside other prompt changes, without full games.
