# llama3:8b in Anchor matches against Stockfish, 2026-10-19

A first look at how llama3:8b plays against an engine: 2 games under each of the four LLM constraints, then 2 under Chaos rules. Ten games in all, every one lost. This is a sample, not a Rating.

## What was done

- **No Dragon.** Komodo Dragon, the designed Anchor (ADR 0005), couldn't be installed: komodochess.com's TLS certificate had expired, and it can't be downloaded here. Stockfish 19 (Homebrew) was added as a stand-in Anchor: `--engine stockfish` on `chessllm.anchor_match` and `chessllm.anchor_batch`.
- **Stockfish's Skill levels.** Stockfish's `UCI_Elo` doesn't go below 1320, so the stand-in's Skill s is a Stockfish `Skill Level` and a search depth (`STOCKFISH_LEVELS` in `chessllm/anchors.py`; Skill 1 is Skill Level 0 at depth 1).
- **Its rating is a guess.** The stand-in at Skill s is rated as Dragon at Skill s, 125 × (s + 1), but with a prior three times as wide (±300). It is logged and rated as its own Anchor (`anchor:stockfish:N`), so its games never mix with Dragon's.
- **The stand-in is stronger than its rating.** A check against CuckooChess, whose `UCI_Elo` reaches −625 and is set from the author's own table, put Stockfish Skill 1 at about 800-900 on CuckooChess's scale, well above the 250 it is rated at. CuckooChess scored 0/4 at Elo 250, 0.5/4 at 625 and 3/4 at 1000 against it. CuckooChess is the better stand-in (see "Next").
- **Chaos rules against an Anchor.** These used to be refused (ADR 0006 asked for a check first). The check: Stockfish 19 quits on every position python-chess calls invalid (a king left en prise, pawns on a back rank, too many pieces). So the Stockfish Anchor, in an invalid position:
  1. takes the enemy king if it can;
  2. else asks Stockfish about a copy with every back-rank pawn made a queen;
  3. else restarts Stockfish and plays `greedy_move` (the most valuable capture, else a check, else the first legal move).

  Chaos rules are allowed in an Anchor match only against the Stockfish Anchor.
- **The analysis script.** `scripts/analyse_games.py` filters the game logs and prints the records, the endings, the themes and the games. Every number below comes from it.
- **Settings.** Every game: llama3:8b, no thinking, explained Retry feedback, 5 attempts per turn, model-default sampling, Stockfish stand-in at Skill 1, one game as White and one as Black.

Commands:

```
uv run python -m chessllm.anchor_batch --model llama3:8b --llm-constraints {free,listed,blind_enforced,listed_enforced} --engine stockfish --skill 1 --games 2
uv run python -m chessllm.anchor_batch --model llama3:8b --llm-constraints free --rules chaos --engine stockfish --skill 1 --games 2
uv run python -m scripts.analyse_games --mode anchor_match
```

## Results

| LLM constraints | Rules | Record | Ended by | Turns with an illegal move | Legal-move streak | Plies (mean) | Avg centipawn loss | Accuracy |
|---|---|---|---|---|---|---|---|---|
| Free | Standard | 0-0-2 | forfeit, forfeit | 60% | 4 | 40 | 82 | 89.6 |
| Listed | Standard | 0-0-2 | checkmate, checkmate | 4% | 17 | 50 | 103 | 86.9 |
| Blind enforced | Standard | 0-0-2 | checkmate, checkmate | (can't happen) | (n/a) | 54 | 76 | 92.7 |
| Listed enforced | Standard | 0-0-2 | checkmate, checkmate | (can't happen) | (n/a) | 45 | 109 | 86.8 |
| Free | Chaos | 0-0-2 | king capture, king capture | 62% | 4 | 26 | 111 | 86.2 |

Overall: **0 wins, 0 draws, 10 losses.**

The Move-quality estimate is below the bottom of Maia-2's grid for every configuration, so only an upper bound is known (about 680 on the chess.com scale for the Standard rules games). The Chaos games score only the LLM's 10 legal moves.

## Themes

1. **Under Free, the rules beat it before Stockfish does.** In the Standard games, 52 illegal moves in 42 turns; both games were forfeited after a streak of 4 legal moves. The illegal moves are mostly knight jumps to squares the knight can't reach (Nc5, Nc6, Nd7), more in the middlegame (34) than the opening (18).
2. **Showing the legal moves nearly fixes legality.** Under Listed, illegal moves fall to 4% of turns and the streak rises to 17, without Enforced decoding.
3. **Every checkmate came right after a mate in one it allowed.** That is all 6 of them; it never missed a mate in one of its own. It doesn't see one-move threats against its king.
4. **Its moves are roughly 80-110 centipawns worse than the engine's on average.** That is about 87-93% accuracy. The games are lost on blunders, not on a steady drift.
5. **No opening theory.** All 10 openings differ, several unusual (1. d4 d6 2. d5 g6; 1. c4 e5 2. a3).

### Under Chaos rules

- **Game 1 (LLM as White, 0-1 by king capture after 30 plies).** Only 2 of its 15 moves were legal. The other 13 were chaos moves, one of them a spawn: a knight appeared on c3 after both knights were gone. The board turned surreal: pawns jumping two files (d4xe5, b2xe5, a2-c5), a bishop going c1-a5 off its diagonal. Stockfish took the pieces as they arrived. At ply 28 Stockfish gave check (Qa5+); llama3 answered Qe4, ignoring the check, and Stockfish took the king.
- **Game 2 (LLM as Black, 1-0 by king capture after 23 plies).** It began as a normal game: 7 legal moves, the Italian-like 1. e4 e5 2. Nf3 Nc6 3. Nc3 Bc5. The first chaos move came after it had lost a piece. Then Qe2+ was answered by the chaos knight move Nc5-c6, ignoring the check, and Stockfish took the king.
- **Chaos made it lose faster, not better.** The chaos moves gave it free material (illegal captures), but it never used them to attack. In both games the end was the same blind spot as under Standard rules: it doesn't respond to a check.
- **The Anchor coped.** Every position before Stockfish's turn stayed valid except the last of each game, where it took the king (step 1 above). Steps 2 and 3 weren't needed in these games, and Stockfish never quit.

## Caveats

- 2 games per configuration. The differences between the four LLM constraints are noise at this sample size; only Free versus the rest (legality) is clear.
- The Stockfish stand-in's rating is uncalibrated and, by the CuckooChess check, too low. Games against it make the LLM look weaker on the Rating scale than it is. Treat these games as a record, not a Rating.
- The Move-quality estimate is unvalidated at these levels (`docs/research/move-quality-validation.md`).

## Next

- **A CuckooChess Anchor.** CuckooChess 1.13a9 is built from the author's source (`peterosterlund2/droidfish`, GPL) with a portable JDK in `~/chess-engines/`. Its `UCI_Elo` reaches Dragon's range directly (250-1000); its scale is the author's, not chess.com's.
- **Larger samples,** with the ladder free to move (`--games 30`), for each constraint.
- **The other models** (gemma3:12b, qwen3.5:9b), especially under Listed and Listed enforced.
