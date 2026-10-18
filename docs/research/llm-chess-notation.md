# Which chess notation works best for LLMs?

Research date: 2026-10-18. Scope: which move notation (SAN, UCI) and position format (PGN history, FEN, ASCII/Unicode board, piece lists) give the best play from LLMs, with a focus on ~8-9B local models running in "free mode" (no legal-move list).

Labels used below:
- **[Source]** means the claim is stated in the linked primary source.
- **[Inference]** means it is my reading or extrapolation, not something the source states.

## TL;DR

- **Few head-to-head notation comparisons exist.** Only three sources compare formats directly. [Hwang et al. 2025](https://arxiv.org/html/2507.00726v2) tested SAN vs UCI and FEN vs PGN vs FEN+PGN on Qwen2.5-7B and Llama3.1-8B. [LLM Chess, Kolasani/Saplin et al. 2025](https://arxiv.org/html/2512.01992v1) tested Unicode vs ASCII vs FEN boards on o4-mini and Grok 3 Mini. [Toshniwal et al. 2021/22](https://ar5iv.labs.arxiv.org/html/2102.13249) tested UCI with and without piece-type tokens, on models trained from scratch.
- **Output notation: SAN beats UCI for 7-8B models.** [Source] Hwang et al. report that "SAN notation enables meaningful learning" while "UCI notation results in substantially degraded performance" for Qwen2.5-7B and Llama3.1-8B ([Appendix C.1, Fig. 7](https://arxiv.org/html/2507.00726v2)). The authors attribute this to SAN being much more common in pretraining data. Benchmarks that chose UCI did so because it is easier to parse ([ChessQA](https://arxiv.org/html/2510.23948v1)), not because models play better with it.
- **Position format: FEN vs PGN matters less, but showing the board explicitly helps.** [Source] Hwang et al. found "board representation choice was not critical" across FEN, PGN and FEN+PGN. LLM Chess found FEN ≥ ASCII > Unicode for o4-mini (95.0% / 88.3% / 73.3% win/loss) and no real difference for Grok 3 Mini. ChessQA found that adding an explicit piece arrangement raised accuracy, and called board-state hallucination a key bottleneck.
- **Every strong LLM result used PGN/SAN continuation.** [Source] gpt-3.5-turbo-instruct at about 1750 Elo ([Acher](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/), [Carlini](https://nicholas.carlini.com/writing/2023/chess-llm.html)) and Dynomight's best gpt-4o setups ([more-chess](https://dynomight.net/more-chess/)) all fed a PGN move list in SAN.
- **Free mode is very hard for small models.** [Source] In ChessArena, Qwen3-8B without legal moves produced a legal move only **9.8%** of the time ([ChessArena](https://arxiv.org/html/2509.24239v4)). In LLM Chess, Llama-3-8B, Llama-3.1-8B, Qwen2.5-7B and Gemma 2 9B all scored 0% win/loss, losing mostly to instruction-following failures, even *with* a legal-move tool ([LLM Chess, Table 6](https://arxiv.org/html/2512.01992v1)).
- **Frontier models fail often in free mode too.** [Source] In Acher's free-mode PGN tests, o3 lost 87.5% of games to an illegal move and o4-mini 94.3% ([Acher, o3/o4-mini](https://blog.mathieuacher.com/GPTReasoningO3O4miniAndChess-copy/)). Kaggle Game Arena uses this protocol (FEN + PGN in, SAN out, no legal list, a few retries) ([Game Arena report](https://arxiv.org/html/2609.31473v1)).

## Summary table

| Source | Year | Models | Notation(s) tested | Key metric / result | Link |
|---|---|---|---|---|---|
| Hwang et al., "Can LLMs Develop Strategic Reasoning? Post-training Insights from Learning Chess" | 2025 | Qwen2.5-3B/7B, Llama3.1-8B (base + instruct) | **Head-to-head:** SAN vs UCI output; FEN vs PGN vs FEN+PGN input; with/without legal-move list | SAN >> UCI. Board format "not critical". Without a legal-move list, models "cannot learn anything meaningful". RL plateau of ~25-30% puzzle accuracy. All 3-8B models score 0.0% on a board-state diagnostic | [arXiv 2507.00726](https://arxiv.org/html/2507.00726v2) |
| Kolasani, Saplin et al., "LLM CHESS" (+ maxim-saplin/llm_chess repo) | 2025 | 50+ models incl. Llama-3/3.1-8B, Qwen2.5-7B/14B, Gemma 2 9B, o4-mini, Grok 3 Mini | UCI output. **Head-to-head boards:** Unicode (default) vs ASCII vs FEN. Ablation removing the legal-move tool | o4-mini: Unicode 73.3%, ASCII 88.3%, FEN 95.0% win/loss. Grok 3 Mini: 61.7 / 63.3 / 63.3. All ~8B models: 0% win/loss, mostly from instruction-following errors | [arXiv 2512.01992](https://arxiv.org/html/2512.01992v1), [repo](https://github.com/maxim-saplin/llm_chess) |
| Liu et al., "ChessArena" | 2025 | Qwen3-8B, Seed-Coder-8B, Qwen3-235B, DeepSeek-V3, GPT-4.1, o3, Claude 3.7, Gemini 2.5 Pro, ... | FEN input, UCI output (SAN fallback). With/without legal moves. No notation ablation | Qwen3-8B blitz without legal moves: legal rate 9.8%. After SFT+RL: 87.6%. Glicko: Qwen3-8B (with legal moves) 1335, below the random player (1524) | [arXiv 2509.24239](https://arxiv.org/html/2509.24239v4) |
| Game Arena (Kaggle / Google DeepMind) | 2025-26 | 11 frontier API models | FEN + full PGN in, SAN out, **no legal list**, retries then forfeit. No ablation | Relative Elo (DeepSeek V3.2 = 0): Gemini 3 Pro 1325, o3 1009, GPT-5.2 933, Claude Opus 4.5 236. Claude Haiku 4.5 / DeepSeek V3.2 often >5 rethinks per game | [arXiv 2609.31473](https://arxiv.org/html/2609.31473v1), [harness](https://github.com/google-deepmind/game_arena) |
| Wen, Tang, Anderson, "ChessQA" | 2025 | 15 LLMs, 7 families (no ~8B) | FEN / PGN / UCI, chosen for parseability. No notation ablation | Adding piece-arrangement context: Claude 3.5 Haiku 14.5% → 23.5%, Gemini 2.5 Flash 24.1% → 31.0%. GPT-5 thinking 79.3% vs 44.0% without | [arXiv 2510.23948](https://arxiv.org/html/2510.23948v1) |
| Pleiss et al., "Disentangling generalization and memorization ... using chess" | 2026 | GPT-3.5, GPT-4o, GPT-5, Claude Opus, Gemini | FEN in, SAN out (UCI collected but unused) | Syntactically invalid SAN: 0.32% of positions. **Illegal** moves: GPT-3.5 74.7%, GPT-4o 41.6%, GPT-5 33.8%. 4.72× more illegal moves in out-of-distribution positions | [arXiv 2601.16823](https://arxiv.org/html/2601.16823v2) |
| Dynomight, "Something weird is happening with LLMs and chess" | 2024 | Llama-3.2-3B, Llama-3.1-70B, Qwen-2.5-72B, Gemma-2-27B, command-r, GPT-3.5/4o/o1-mini | PGN headers + SAN move list (one format) | Only gpt-3.5-turbo-instruct was good. Instruction tuning hurt every pair. A trailing space after the move number badly hurt open models | [dynomight.net/chess](https://dynomight.net/chess/) |
| Dynomight, "OK, I can partly explain the LLM chess weirdness now" | 2024 | gpt-4o, gpt-4o-mini, gpt-3.5-turbo-instruct | PGN/SAN only. Prompt-technique ablations | Listing legal moves **hurt**. Regurgitating the game and few-shot examples **helped**. gpt-4o + both ≈ 1540 Elo vs ≈ 1750 for 3.5-instruct | [dynomight.net/more-chess](https://dynomight.net/more-chess/) |
| Acher, "Debunking the Chessboard" | 2023 | gpt-3.5-turbo-instruct, gpt-4, gpt-3.5-turbo, davinci-003 | PGN headers + SAN (one format) | 3.5-instruct ≈ 1750 Elo, illegal move in 16% of games (≈0.3% of moves). gpt-4 ≈ 1300, 32% of games. gpt-3.5-turbo 93% | [blog](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/) |
| Acher, o3 / o4-mini and chess | 2025 | o3, o4-mini | PGN/SAN in `<played_move>` tags, no legal list | Illegal-move defeats: o3 87.5% (28/32 games), o4-mini 94.3% (33/35) | [blog](https://blog.mathieuacher.com/GPTReasoningO3O4miniAndChess-copy/) |
| Acher, "DeepSeek-R1 is Worse than GPT-2 in Chess" | 2025 | DeepSeek-R1 | PGN/SAN in tags | 57/58 games had an illegal move. ~12% of plies illegal. Mean game length 8.3 moves | [blog](https://blog.mathieuacher.com/DeepSeekR1WorstThanGPT2InChess-copy/) |
| Carlini, "Playing chess with large language models" | 2023 | gpt-3.5-turbo-instruct | PGN headers + SAN | No invalid move in "a few thousand moves". A trailing-space tokenization issue caused "-O" | [blog](https://nicholas.carlini.com/writing/2023/chess-llm.html) |
| Karvonen, Chess-GPT / "Emergent World Models ..." | 2024 | 25M / 50M nanoGPT trained from scratch | Character-level PGN/SAN strings | 99.8% legal moves. ~1300-1500 Elo. Linear probe recovers the board (99.2% of squares) | [blog](https://adamkarvonen.github.io/machine_learning/2024/01/03/chess-world-models.html), [arXiv 2403.15498](https://arxiv.org/abs/2403.15498) |
| Karvonen, chess_gpt_eval | 2023-24 | gpt-3.5-turbo-instruct, GPT-4, Llama2-70B | PGN continuation | 3.5-instruct: <0.1% illegal over 8,205 moves. Llama2-70B base "hallucinates illegal moves" | [repo](https://github.com/adamkarvonen/chess_gpt_eval) |
| Feng et al., "ChessGPT" | 2023 | ChessGPT-Base (RedPajama 2.8B), LLaMA-7B baseline | PGN, UCI, FEN in training data. No controlled comparison | PGN→FEN 94.8-96.7% (ChessGPT) vs <9% (baselines). UCI state tracking 92.8-99.5% vs 23-53% (LLaMA-7B) | [arXiv 2306.09200](https://arxiv.org/html/2306.09200v2) |
| Zhang et al., "Complete Chess Games Enable LLM Become A Chess Master" (ChessLLM) | 2025 | open-llama-3B, fine-tuned | FEN input (argued over PGN, not tested) | 1788 Elo vs Stockfish (with up to 10 samples). 99.11% legal moves in distribution | [arXiv 2501.17186](https://arxiv.org/html/2501.17186v2) |
| Ruoss et al., "Grandmaster-level chess without search" | 2024 | 9M-270M transformers trained from scratch (not LLMs) | FEN in (fixed 77 tokens), UCI action vocabulary of 1968 moves. No representation ablation | 270M: Lichess blitz 2895 vs humans. 95.4% on puzzles | [arXiv 2402.04494](https://arxiv.org/html/2402.04494) |
| Toshniwal et al., "Chess as a Testbed for LM State Tracking" | 2021-22 | GPT-2-style models trained from scratch | **Head-to-head:** UCI vs UCI+RAP (piece-type tokens added during training) | Legal-move accuracy with the small training set: UCI 74.0% vs UCI+RAP 88.4%. Gap closes with more data | [arXiv 2102.13249](https://ar5iv.labs.arxiv.org/html/2102.13249) |
| Tam et al., "Let Me Speak Freely?" + .txt rebuttal | 2024 | Various. Rebuttal used Llama-3-8B-Instruct | JSON/format restrictions (not chess) | Tam et al.: format restrictions degrade reasoning. .txt: with equal prompts, structured output was slightly *better* (GSM8K 0.77 → 0.78) and a reasoning field before the answer worked best | [arXiv 2408.02442](https://arxiv.org/abs/2408.02442), [.txt blog](https://blog.dottxt.ai/say-what-you-mean.html) |

## Per-source details

### Hwang et al. 2025: the only SAN-vs-UCI comparison on 7-8B models
- **Setup.** [Source] RL post-training on Lichess puzzles (19.2k training pairs, 10k held-out puzzles) for Qwen2.5-3B/7B and Llama3.1-8B. The prompt gives the FEN and the list of legal moves in SAN. The answer must be "in SAN notation, strictly using the moving piece and the destination square", inside `<think>`/`<answer>` tags ([Fig. 4, Appendix A](https://arxiv.org/html/2507.00726v2)).
- **Notation result.** [Source] "SAN notation enables meaningful learning ... UCI notation results in substantially degraded performance" (Appendix C.1, Fig. 7, for Qwen2.5-7B and Llama3.1-8B). The authors attribute this to how common each notation is in pretraining data.
  - Caveat: Section 2.1 says only that UCI and full PGN histories "did not yield measurable improvements". The appendix gives the stronger statement.
- **Board result.** [Source] FEN vs PGN vs FEN+PGN: "board representation choice was not critical ... all variants achieved similar performance" (Fig. 8).
- **Legal moves.** [Source] Without an explicit legal-move list, "LLMs cannot learn anything meaningful" (Fig. 6).
- **Board-state diagnostic.** [Source] Every 3-8B model, base and instruct, scored **0.0%** on the board-state task.
- **Caveats.** [Inference] The metric is puzzle accuracy after RL training, not zero-shot game play. Still, it is the closest evidence available for the model size this project uses, and it points toward SAN.

### LLM Chess (Kolasani, Saplin, et al. 2025) and the maxim-saplin/llm_chess repo
- **Setup.** [Source] An agentic dialog with three tools: `get_current_board`, `get_legal_moves`, `make_move <UCI>`. The default board is Unicode. Limits: 10 turns per move and 3 mistakes before the model loses ([repo README](https://github.com/maxim-saplin/llm_chess), [paper](https://arxiv.org/html/2512.01992v1)).
- **Board ablation.** [Source] o4-mini (low): win/loss 73.3% (Unicode), 88.3% (ASCII), 95.0% (FEN). Grok 3 Mini (low): 61.7 / 63.3 / 63.3.
- **No-legal-moves ablation** (FEN baseline). [Source] Grok 3 Mini dropped to 36.7%. o4-mini went to 86.7%.
- **Small models.** [Source] Table 6 lists models at 0% win/loss, almost all from "too many wrong actions":
  - Qwen2.5-7B-Instruct: 100%
  - Llama-3-8B: 90%
  - Llama-3.1-8B: 80%
  - Gemma 2 9B: 100%
  - Gemma 3 12B / 27B: 100%
  - Phi-4: 100%
- **Error rates by model type.** [Source] Non-reasoning models had instruction-following errors in 71.9% of games, reasoning models in 24.4%.
- **Repo notes.** [Source] The [repo notes](https://github.com/maxim-saplin/llm_chess/blob/main/docs/notes.md) say "none of the small reasoning models qualifies above Tier 0". They also report that asking models to reflect before moving made results worse, and that the authors switched to "regex and be tolerant to reply format" parsing.
- **Caveat.** [Inference] The board ablation covers only two strong reasoning models. It shows FEN and ASCII are safe choices, not which one a 9B model prefers.

### ChessArena (Liu et al. 2025)
- **Setup.** [Source] FEN for the board (PGN "cannot directly reveal the piece arrangement"). UCI output, with SAN accepted as a fallback. Modes:
  - Bullet: move only.
  - Blitz: optional reasoning.
  - Standard: chain of thought required.
  - Blindfold: the model receives only the move history.

  Each mode was run with and without a legal-move list ([paper](https://arxiv.org/html/2509.24239v4)).
- **Small-model numbers.** [Source]
  - Qwen3-8B, blitz, without legal moves: legal rate **9.8%**.
  - Qwen3-8B-Chess (SFT+RL): **87.6%**.
  - Glicko ratings with legal moves: Qwen3-8B 1335 and Seed-Coder-8B 1009, both below the random player (1524). Qwen3-8B-Chess: 1776.
- **Notation.** [Source] No UCI-vs-SAN ablation. [Inference] The SAN fallback suggests models often answered in SAN even when asked for UCI.

### Game Arena (Kaggle / Google DeepMind, 2025 exhibition; technical report Sept 2026)
- **Protocol** (closest to this project's free mode). [Source] Each turn the model gets "the current position in Forsyth-Edwards Notation (FEN) and a complete move history in PGN format" and must return "a single valid move in standard algebraic notation (SAN)". The harness "does NOT include the list of valid moves". After an invalid move the model is asked to retry without diagnostics, and loses after the retry limit. The report says both "four attempts" and "three retries" ([report](https://arxiv.org/html/2609.31473v1)).
- **Harness.** [Source] The [open-source harness](https://github.com/google-deepmind/game_arena) parses non-strict SAN and recommends telling the model its previous move was illegal when re-prompting.
- **Results.** [Source] Ratings are relative, anchored at DeepSeek V3.2 = 0:
  - Gemini 3 Pro 1325, Gemini 3 Flash 1297, o3 1009, GPT-5.2 933, Claude Opus 4.5 236.
  - Gemini models averaged <0.2 rethinks per game. Claude Haiku 4.5 and DeepSeek V3.2 often needed >5.
  - Errors cluster late in the game. A typical failure is a move that does not resolve check.
- **Caveats.** No small or open models were tested and there is no notation ablation.

### ChessQA (Wen, Tang, Anderson 2025)
- **Notation choice.** [Source] Uses FEN, PGN and UCI. UCI was chosen over SAN because "UCI is deterministic at the string level", for scoring convenience. No ablation ([paper](https://arxiv.org/html/2510.23948v1)).
- **Board representation.** [Source] Adding an explicit piece-arrangement context raised accuracy: Claude 3.5 Haiku 14.5% → 23.5%, Gemini 2.5 Flash 24.1% → 31.0%. The authors identify board-state hallucination ("phantom pieces") as a significant bottleneck.
- **Thinking.** [Source] GPT-5 scored 79.3% with thinking vs 44.0% without.

### Pleiss, Schiffer, von Weizsaecker 2026
- **Setup.** [Source] Prompt: "Consider the following chess position, denoted as a FEN string: {fen}". The answer is in SAN, with UCI collected only as an unused fallback ([paper](https://arxiv.org/html/2601.16823v2)).
- **Results.** [Source]
  - Syntactically invalid SAN was rare: 0.32% of positions.
  - **Illegal** moves were common: GPT-3.5 74.7%, GPT-4o 41.6%, GPT-5 33.8%. Claude Opus: 0.2% on well-known positions, 51.6% out of distribution.
  - Reasoning cut GPT-5's average centipawn loss by 71.74%.
- **Takeaway.** [Inference] Models format SAN correctly. The failure is legality from a FEN-only position, not syntax. Note that FEN alone gives no move history.

### Dynomight (two posts, Nov 2024)
- **Post 1.** [Source] PGN header tags, then a SAN move list. The model outputs one SAN move. Open models ran locally (Q5_K_M quantization, temperature 0.7) with grammars that forced legal moves ([post 1](https://dynomight.net/chess/)).
  - Every model except gpt-3.5-turbo-instruct lost every game, including Llama-3.2-3B, Llama-3.1-70B, Qwen-2.5-72B and Gemma-2-27B.
  - Instruction tuning made results worse in every base/instruct pair.
  - A trailing space after the move number (e.g. "1. e4 e5 2. ") badly degraded open models because of tokenization.
- **Post 2.** [Source] Prompt-technique ablations, with notation held fixed ([post 2](https://dynomight.net/more-chess/)):
  - Listing legal moves **hurt** badly.
  - Regurgitation (repeating the whole game before the new move) **helped**.
  - Three few-shot examples gave a "very large" benefit.
  - gpt-4o with regurgitation and examples went 10-5-35 against 3.5-instruct, about 1540 Elo.
- **Takeaway.** [Inference] Prompting a chat model to act like a PGN completion model is the most consistently helpful trick across these sources.

### Mathieu Acher (blog, 2023-2025)
- **Debunking the Chessboard (2023).** [Source] ~878 games against Stockfish ([post](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/)):
  - gpt-3.5-turbo-instruct: ~1750 Elo, illegal move in 16% of games (~0.3% of moves). Many of these errors were "1-0" outputs or promotions missing the piece letter, which are easy to fix.
  - gpt-4: ~1300 Elo, 32% of games.
  - gpt-3.5-turbo: 93% of games.
  - Higher temperature (0.8) lowered Elo.
- **o3 / o4-mini (2025).** [Source] Free-mode PGN prompt, move returned in `<played_move>` tags, which Acher calls "very effective" for parsing ([post](https://blog.mathieuacher.com/GPTReasoningO3O4miniAndChess-copy/)).
  - o3 lost 87.5% of games to an illegal move, o4-mini 94.3%.
  - One flagged "illegal" move was actually a SAN disambiguation issue (`Rg4` vs `R3g4`).
- **DeepSeek-R1 (2025).** [Source] 57/58 games had an illegal move, about 12% of plies ([post](https://blog.mathieuacher.com/DeepSeekR1WorstThanGPT2InChess-copy/)).
- **GPT-5 (2025).** [Source] A single-position anecdote: illegal move by move 4 ([post](https://blog.mathieuacher.com/GPT5-IllegalChessBench/)).

### Nicholas Carlini (2023)
- [Source] PGN headers plus a SAN move list sent to gpt-3.5-turbo-instruct. No invalid move in "a few thousand moves". The near-miss "-O" came from a missing space, fixed by adding a trailing space for that tokenizer ([post](https://nicholas.carlini.com/writing/2023/chess-llm.html)).
- [Inference] Dynomight found the opposite fix for Llama tokenizers. Trailing-space handling depends on the tokenizer and should be tested.

### Adam Karvonen (2024)
- **Chess-GPT.** [Source] A 50M character-level nanoGPT trained on PGN strings: 99.8% legal moves, ~1300-1500 Elo. Linear probes recover the board state (99.2% of squares) ([blog](https://adamkarvonen.github.io/machine_learning/2024/01/03/chess-world-models.html), [COLM 2024 paper](https://arxiv.org/abs/2403.15498)).
- **chess_gpt_eval.** [Source] gpt-3.5-turbo-instruct had <0.1% illegal moves over 8,205 moves. Llama2-70B chat didn't format moves and Llama2-70B base hallucinated illegal moves ([repo](https://github.com/adamkarvonen/chess_gpt_eval)).
- [Inference] A PGN/SAN move sequence is enough for a model to build an internal board. Small general LLMs simply lack the training data to do it.

### ChessGPT (Feng et al. 2023), ChessLLM (Zhang et al. 2025), DeepMind (Ruoss et al. 2024), Toshniwal et al.
- **ChessGPT.** [Source] Training data mixes PGN, UCI→FEN and PGN→FEN conversions. ChessGPT-Base (2.8B) reaches 94.8-96.7% PGN→FEN vs <9% for LLaMA-7B and RedPajama baselines. No controlled notation comparison ([paper](https://arxiv.org/html/2306.09200v2)).
- **ChessLLM.** [Source] FEN in, Stockfish best move out, fine-tuned open-llama-3B: 1788 Elo. Argues FEN is better because its length is constant, but runs no PGN ablation ([paper](https://arxiv.org/html/2501.17186v2)).
- **Ruoss et al. (DeepMind).** [Source] FEN in, UCI action vocabulary, trained from scratch: 2895 Lichess blitz vs humans. No representation ablation, and FEN's lack of history means the model can't detect threefold repetition ([paper](https://arxiv.org/html/2402.04494)).
- **Toshniwal et al.** [Source] Models trained from scratch on UCI. Adding piece-type tokens raised legal-move accuracy from 74.0% to 88.4% with little training data, with no gain at large data. Performance also depended on access to the full game history ([paper](https://ar5iv.labs.arxiv.org/html/2102.13249)).
  - [Inference] SAN carries piece type and UCI doesn't. This weakly supports SAN for data-poor learners, but the result comes from from-scratch models, not pretrained LLMs.

### Structured / JSON output
- **Tam et al.** [Source] Report "a significant decline in LLMs reasoning abilities under format restrictions", with stricter formats hurting more ([arXiv 2408.02442](https://arxiv.org/abs/2408.02442)).
- **.txt rebuttal.** [Source] Argues the comparison was flawed (unequal prompts, an LLM used as the parser, and JSON-mode conflated with constrained decoding) ([.txt](https://blog.dottxt.ai/say-what-you-mean.html)).
  - Rerunning with equal prompts on Llama-3-8B-Instruct, structured generation scored slightly higher: GSM8K 0.77 → 0.78, Last Letter 0.73 → 0.77, Shuffle Object 0.41 → 0.44.
  - A schema with a `reasoning` field before the `answer` field performed best.
- **Chess-specific evidence.**
  - [Source] Dynomight constrained open models to legal moves with grammars, and they still lost every game ([post 1](https://dynomight.net/chess/)).
  - [Source] LLM Chess moved to tolerant regex parsing ([notes](https://github.com/maxim-saplin/llm_chess/blob/main/docs/notes.md)). Acher used XML-style tags.
  - No source isolates JSON vs free-text output for chess. **Unknown.**

## Implications for this project

Constraints: a 9B local model via Ollama, free mode (no legal-move list), Pydantic structured output, and the metric "legal moves until the first illegal one".

1. **Output notation: SAN.**
   - Evidence: the only notation comparison at 7-8B scale (Hwang et al.) found SAN much better than UCI. SAN is also the notation behind every strong LLM-chess result and the one Game Arena uses for this exact protocol.
   - Parse with `board.parse_san()`. It handles check suffixes and is lenient about `+`/`#`.
   - [Inference] Also accept UCI as a fallback (`Move.from_uci`, then check membership in `board.legal_moves`), as ChessArena does in the other direction. Decide upfront whether a UCI-formatted legal move counts as legal. I suggest yes, logged separately, so the metric measures chess knowledge rather than format compliance.
   - Normalize trivially fixable outputs before judging legality: missing promotion piece, `0-0` vs `O-O`, and trailing annotations like `!?`. Acher found many "illegal" gpt-3.5 moves were exactly these.
2. **Position presentation: PGN move history (SAN, numbered) + FEN, optionally plus a piece list.**
   - [Source] Game Arena uses FEN + PGN. Hwang et al. found FEN, PGN and both roughly equal at 7-8B. LLM Chess found FEN ≥ ASCII > Unicode on o4-mini. ChessQA found an explicit piece arrangement helps. Toshniwal et al. found full history matters.
   - [Inference] Use PGN as the primary context, since it matches pretraining data and the model's own output notation. Add FEN for side-to-move, castling and en-passant state.
   - [Inference] A plain piece list (e.g. "White: Kg1 Qd1 Rf1 ... Black: ...") is a cheap A/B candidate, given ChessQA's result.
   - Skip the Unicode board. If you want a 2D board, use ASCII (`str(board)` in python-chess).
   - Make the format configurable and A/B it with your own metric. No source tested ASCII vs FEN vs PGN on a 9B model in free mode.
3. **Prompt craft that has evidence behind it.**
   - Few-shot examples help ([Dynomight](https://dynomight.net/more-chess/)).
   - "Regurgitation" helps: have the model restate the game or move list before its move, e.g. as an earlier JSON field ([Dynomight](https://dynomight.net/more-chess/)).
   - Avoid a trailing-space mismatch at the end of the PGN ([Dynomight](https://dynomight.net/chess/), [Carlini](https://nicholas.carlini.com/writing/2023/chess-llm.html)).
   - Use low temperature ([Acher](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/)).
   - [Inference] If the model has a thinking mode, try it. Reasoning helped substantially for larger models ([ChessQA](https://arxiv.org/html/2510.23948v1), [Pleiss et al.](https://arxiv.org/html/2601.16823v2)). LLM Chess saw small reasoning models fail on instruction following and timeouts, so test latency.
   - [Inference] Instruction tuning hurt chess in Dynomight's tests. A base model in Ollama `raw` completion mode, continuing a PGN string, may outperform the instruct model. That would need free-text parsing instead of JSON.
4. **Structured JSON output.**
   - Chess-specific impact: **unknown**.
   - General evidence is mixed: Tam et al. found format restrictions hurt, while the .txt rebuttal found constrained JSON neutral to slightly positive on Llama-3-8B when prompts are equal.
   - [Inference] Recommended schema: `{"reasoning": str (short, optional), "move": str}` with `reasoning` placed *before* `move`, following .txt's best-performing layout.
   - Do **not** constrain `move` to legal moves (e.g. an enum of legal SANs). That would turn free mode into legal-list mode and invalidate the metric. A SAN-shaped regex is fine; whether Ollama enforces JSON-schema `pattern` is unverified.
5. **Expectations.**
   - [Source] Qwen3-8B produced legal moves only 9.8% of the time without a legal list ([ChessArena](https://arxiv.org/html/2509.24239v4)).
   - [Source] Every ~8B model scored 0% in LLM Chess, even with a legal-move tool ([LLM Chess](https://arxiv.org/html/2512.01992v1)).
   - [Source] Llama-3.2-3B could play "standard openings for a few moves" before collapsing ([Dynomight](https://dynomight.net/chess/)).
   - [Inference] Expect a 9B model to manage a handful of legal opening moves before its first illegal move. Notation choices will probably move this by a few plies rather than change the overall picture.
