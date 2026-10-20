# What limits LLMs at chess, especially small local ones? 2026-10-20

Research date: 2026-10-20. Scope: known limitations of LLMs playing chess, focused on models of about 1-30B parameters run locally (Ollama, 4-bit quantised). This is a literature survey only. Nothing was run, and this repo's own games are not compared here. Related notes: `llm-chess-notation.md` (notation), `board-images.md` (vision probe), `elo-estimation.md` (rating), `candidate-models.md` (which models).

Labels:
- **[Source]**: stated in the linked primary source.
- **[Inference]**: my reading or extrapolation.

Each item gives **What**, **Why** (mechanism), **Symptoms** in games, **Small models** (how much worse, with numbers where they exist) and **Sources**. Dates and model sizes are given with the numbers.

## TL;DR

- **Small non-reasoning models mostly don't lose at chess; they lose at the protocol.** In LLM Chess (Dec 2025), every ~8B model scored 0% wins, and instruction-following errors ended 71.9% of non-reasoning models' games. [Source]
- **They can't track the board.** Qwen2.5-3B/7B and Llama3.1-8B scored **0.0%** on a board-state test (2025). Qwen3-8B played a legal move only **9.8%** of the time without a legal-move list (2025). [Source]
- **A legal-move list or enforced decoding fixes legality, not strength.** With the list, Qwen3-8B was rated below a random mover (1335 vs 1524, ChessArena 2025). Dynomight's grammar-constrained open models (3B-405B) lost every game (2024). [Source]
- **Reasoning is where strength comes from, and it costs thousands of tokens per move.** Reasoning models averaged 45.4% wins vs 0.7% for non-reasoning (LLM Chess). [Source] On a laptop that means minutes per move and timeouts. [Inference]
- **Results are fragile to measure.** Forfeits, 0% scores, wide intervals, prompt-format choice and memorised openings can each dominate a small-model result. [Source]

---

## A. Board state and rules

### A1. Board-state tracking (no reliable world model)
- **What.** The model has no accurate internal picture of where every piece is after a sequence of moves.
- **Why.** [Source] A transformer *can* learn a board from move text: a 50M-parameter model trained only on PGN strings has linearly decodable board state and 99.8% legal moves ([Karvonen 2024](https://arxiv.org/abs/2403.15498), [blog](https://adamkarvonen.github.io/machine_learning/2024/01/03/chess-world-models.html)). General LLMs get far too little chess in pretraining to learn it. Hwang et al. trace their RL plateau to "a deficit in the pretrained models' internal understanding of chess" ([2507.00726](https://arxiv.org/html/2507.00726v3)). State tracking over long move sequences is also a known theoretical weak spot of fixed-depth transformers; Merrill et al. cite tracking chess moves as an example ([Illusion of State, ICML 2024](https://arxiv.org/abs/2404.08819)). Entity tracking emerged only in models pretrained on lots of code (GPT-3.5), not in smaller text-only models ([Kim & Schuster, ACL 2023](https://arxiv.org/abs/2305.02363)).
- **Symptoms.** Moving a piece from a square it left, capturing your own piece, moving a captured piece, "phantom pieces", choosing moves that were legal several plies ago.
- **Small models.** [Source] Hwang et al. (2025): **0.0%** board-state accuracy for Qwen2.5-3B, Qwen2.5-7B and Llama3.1-8B, base and instruct. ChessArena (2025): Qwen3-8B piece-movement accuracy (PMA) 36.0%; thinking models like o3 score near 100%. ChessQA (Oct 2025) names board-state hallucination ("inventing phantom pieces") as a key bottleneck even for large models; adding an explicit piece list raised Claude 3.5 Haiku from 14.5% to 23.5% ([ChessQA](https://arxiv.org/html/2510.23948v1)).

### A2. Legality without a legal-move list
- **What.** Asked for a move with no list, the model proposes an illegal one.
- **Why.** It follows from A1, plus pattern-matching to plausible-looking SAN from memory ([Pleiss et al. 2026](https://arxiv.org/html/2601.16823v2)). [Source]
- **Symptoms.** Illegal moves; retries; forfeits after the retry limit.
- **Small models.** [Source] ChessArena (Sep 2025, Blitz mode): legal rate without a list was **9.8% for Qwen3-8B** and 4.5% for Seed-Coder-8B, against 96.2% and 59.3% with the list ([ChessArena](https://arxiv.org/html/2509.24239v4)). BIG-bench (2022) found legality improves smoothly with scale even while checkmate-in-one stays near zero ([BIG-bench](https://arxiv.org/abs/2206.04615)). Even frontier models fail: GPT-5 played an illegal move in 33.8% of positions given a FEN ([Pleiss](https://arxiv.org/html/2601.16823v2)); o3 lost 87.5% of free-PGN games to an illegal move ([Acher 2025](https://blog.mathieuacher.com/GPTReasoningO3O4miniAndChess-copy/)).

### A3. Check and king safety
- **What.** The model ignores that its king is in check, or plays a move that leaves or puts its king in check.
- **Why.** Checking legality needs a ray scan across the board from the king, which is exactly the spatial state the model lacks (A1). [Inference] In-check positions are also a small share of training positions. [Inference]
- **Symptoms.** A move that doesn't answer check; pinned pieces moved; the king walks into an attack.
- **Small models.** No small-model number found. [Source] Kaggle Game Arena's report gives "a model is in check but proposes a move that fails to resolve the threat" as the typical late-game failure of frontier models ([Game Arena report, 2026](https://arxiv.org/html/2609.31473v1)). Pleiss et al. show GPT-3.5 promoting a pawn while in check, and GPT-5 (minimal reasoning) capturing while in check ([Pleiss](https://arxiv.org/html/2601.16823v2)). [Inference] Expect it to be worse for small models, since they fail more basic tests.

### A4. Square geometry and piece movement
- **What.** The model doesn't know which squares a piece can reach: knight jumps, diagonals, blocked lines.
- **Why.** Squares are tokens, not coordinates; a diagonal is not "visible" in a text string. [Inference] o3 traces showed fewer "spatial hallucinations" than the 3-8B base models ([Hwang](https://arxiv.org/html/2507.00726v3)). [Source]
- **Symptoms.** "Unreachable" moves (right piece, wrong square), sliding through pieces, bishops changing colour.
- **Small models.** [Source] ChessArena: Qwen3-8B PMA 36.0%, precision 14.1%, recall 18.8% when listing a piece's moves; Qwen3-8B-Chess (SFT+RL) reached 79.0%.

### A5. Hidden state and special rules (castling, en passant, promotion, repetition)
- **What.** Rules that depend on history or on details not visible on the board.
- **Why.** FEN gives castling and en-passant rights but no history, so it can't show repetition. PGN gives history but the model must derive rights from it. [Source] DeepMind's searchless transformer couldn't detect threefold repetition from FEN and needed a workaround ([Ruoss et al. 2024](https://arxiv.org/html/2402.04494)).
- **Symptoms.** Castling through or out of check, or after the king has moved; promotions without a piece letter (`e8` for `e8=Q`); unwanted repetition draws.
- **Small models.** [Source] Many of gpt-3.5-turbo-instruct's "illegal" moves were missing promotion letters or a "1-0" output ([Acher 2023](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/)). No small-model rates found.

---

## B. Notation, tokenization and input format

### B1. Output notation (SAN vs UCI)
- **What.** The notation the model must answer in changes how well it plays.
- **Why.** SAN is far more common in pretraining text (PGN files, books); UCI is rare outside engine logs. [Source: Hwang]
- **Symptoms.** Answers in the wrong notation; SAN disambiguation errors (`Rg4` vs `R3g4`, [Acher](https://blog.mathieuacher.com/GPTReasoningO3O4miniAndChess-copy/)); invalid hybrids like "b7g7+" from GPT-4o ([Pleiss](https://arxiv.org/html/2601.16823v2)).
- **Small models.** [Source] For Qwen2.5-7B and Llama3.1-8B, "UCI notation results in substantially degraded performance" vs SAN ([Hwang 2025](https://arxiv.org/html/2507.00726v3)). ChessArena accepted SAN as a fallback to UCI, which suggests models drift between them.

### B2. Tokenization artifacts
- **What.** Small, invisible formatting details change the tokens the model sees and degrade play.
- **Why.** [Source] BPE can merge a trailing space into the next move's token: a prompt ending "1. e4 e5 2. " made open models play "much worse" ([Dynomight, Nov 2024](https://dynomight.net/chess/)). Carlini needed the opposite fix for gpt-3.5's tokenizer ([Carlini 2023](https://nicholas.carlini.com/writing/2023/chess-llm.html)). FEN's digit runs for empty squares make the same region tokenize differently as pieces move, and unusual positions may split into rarely seen fragments ([Pleiss](https://arxiv.org/html/2601.16823v2), untested; [Ruoss](https://arxiv.org/html/2402.04494) padded FEN to a fixed 64 characters).
- **Symptoms.** Garbled or truncated moves ("-O" for "O-O"), sudden drops in quality from prompt whitespace, miscounted files from FEN.
- **Small models.** [Source] Dynomight's effect was for local open models (Llama 3.x, Qwen 2.5, Gemma 2). [Inference] Each tokenizer is different, so this must be checked per model family.

### B3. Board representation sensitivity
- **What.** How the board is shown (FEN, PGN, ASCII grid, Unicode pieces, piece list) changes results.
- **Why.** Formats differ in how familiar they are and in how much work the model must do to recover the state. [Inference]
- **Symptoms.** Different illegal-move rates for the same position under different formats.
- **Small models.** [Source] Hwang (3-8B): FEN vs PGN vs both "not critical". LLM Chess (o4-mini): FEN 95.0% > ASCII 88.3% > Unicode 73.3% win/loss; Grok 3 Mini roughly flat ([LLM Chess](https://arxiv.org/html/2512.01992v1)). ChessQA: adding a piece list helps (A1). See `llm-chess-notation.md`.

### B4. Board images (vision input)
- **What.** Showing a picture of the board instead of, or with, text.
- **Why.** VLMs perceive grids poorly. On counting rows and columns of a plain grid, GPT-4o got 26% ([VLMs are blind, ACCV 2024](https://arxiv.org/html/2407.06581v4)). Image encoders compress a board into a few hundred tokens (Gemma 3: 256 per image, [model card](https://ai.google.dev/gemma/docs/core/model_card_3)). [Source]
- **Symptoms.** Pieces placed on wrong squares, own-piece captures, misread colours.
- **Small models.** [Source] IsoBench (COLM 2024): images cost large models 15-29 points vs text (GPT-4 Turbo −18.7, Claude 3 Opus −28.7) ([IsoBench](https://arxiv.org/abs/2404.01266)). SEAM (2025) is the exception: chess roughly equal from image or FEN, but only for ≥72B models ([SEAM](https://arxiv.org/html/2508.18179v1)). No published 8-12B chess-image results found (see `board-images.md` for this repo's probe).

---

## C. Context, game length and move history

### C1. Collapse after the opening (out of book)
- **What.** Play is decent while the game follows memorised openings and falls apart once it leaves them.
- **Why.** Openings appear thousands of times in pretraining text; middlegame positions are unique. [Source] Pleiss et al. (2026) found illegal moves 4.72× and centipawn loss 7.79× higher on out-of-distribution positions than on well-known ones; Claude Opus went from 0.2% to 51.6% illegal ([Pleiss](https://arxiv.org/html/2601.16823v2)). Game Arena: only 10-20% of weaker models' rethinks happen early, partly from "having memorized standard openings" ([Game Arena](https://arxiv.org/html/2609.31473v1)).
- **Symptoms.** Clean first 5-10 moves, then illegal moves and blunders.
- **Small models.** [Source] Llama-3.2-3B could play "standard openings for a few moves" before collapsing ([Dynomight](https://dynomight.net/chess/)).

### C2. Long move history and context length
- **What.** Errors become more likely as the game, and the prompt, get longer.
- **Why.** More moves to replay mentally (A1), longer prompts, and less familiar positions. Models use information in the middle of long inputs worse than at the start or end ([Liu et al., "Lost in the Middle", TACL 2024](https://arxiv.org/abs/2307.03172)). [Source] Ollama's default context window can also silently truncate a long prompt. [Inference; check per model]
- **Symptoms.** Errors cluster late in the game ([Game Arena](https://arxiv.org/html/2609.31473v1)); thinking models "struggle beyond 90 turns" when reconstructing the board from history ([ChessArena](https://arxiv.org/html/2509.24239v4)).
- **Small models.** No small-model number. [Inference] Smaller models have weaker long-context retrieval, so expect earlier degradation.

### C3. Shortcutting on the last move
- **What.** Instead of reconstructing the board, the model reacts to the last move only.
- **Why.** It is the cheapest heuristic. [Source] In ChessArena's blindfold mode (history only), GPT-4.1, Qwen3-235B and DeepSeek-V3 "mostly base their responses on the last move" and guess.
- **Symptoms.** Recaptures and replies to threats that don't exist; ignoring older threats.
- **Small models.** [Inference] Likely stronger, given 0% board-state accuracy (A1).

### C4. Repetition and inability to convert
- **What.** Shuffling pieces back and forth, drawing by repetition, or failing to finish a won game.
- **Why.** [Source] Without history the model can't see repetitions: ChessArena saw fivefold-repetition draws "frequently" until it added the last 10 moves. Even a strong searchless transformer was "indecisive" in won positions, where many moves look equally winning, and needed a Stockfish tie-break ([Ruoss](https://arxiv.org/html/2402.04494)).
- **Symptoms.** Repetition draws, move-cap draws, long aimless endgames.
- **Small models.** No numbers. LLM Chess draw rates: 24.6% non-reasoning vs 30.2% reasoning ([LLM Chess](https://arxiv.org/html/2512.01992v1)).

---

## D. Playing strength

### D1. No lookahead (tactical depth)
- **What.** The model picks moves from pattern recognition, one ply deep, with no search.
- **Why.** One forward pass per token gives no tree search; a chain of thought is the only lookahead, and only if the model is trained to use it. [Source] Even a 270M model trained on 10M Stockfish-annotated games "does not fully close the gap to Stockfish" without search ([Ruoss](https://arxiv.org/html/2402.04494)).
- **Symptoms.** Hanging pieces, missing mate-in-1, walking into forks.
- **Small models.** [Source] BIG-bench checkmate-in-one: no BIG-G model solved it; Galactica scored 0.43% (1.3B) to 3.03% (120B) ([BIG-bench](https://arxiv.org/abs/2206.04615), [Galactica](https://arxiv.org/abs/2211.09085)). RL on 3-8B models plateaued at 25-30% puzzle accuracy (experts 60-80%) ([Hwang](https://arxiv.org/html/2507.00726v3)). ChessQA short tactics averaged 17.4% across mostly large models. LLM Chess per-ply blunder rate: GPT-4.1-mini 31.3% vs o4-mini 4.2%.

### D2. Weak position judgment
- **What.** The model can't tell which side is better.
- **Why.** Evaluation needs the board (A1) plus chess knowledge few general models have. [Inference]
- **Symptoms.** Aimless moves, trading into lost endgames, resigning-style text in won positions.
- **Small models.** [Source] ChessQA position judgment: best model (GPT-5 thinking) 40% on a 5-way choice (random 20%).

### D3. Below the random-mover floor
- **What.** Many LLMs score worse than an opponent that plays random legal moves.
- **Why.** Forfeits and blunders against an opponent that never forfeits. [Source]
- **Symptoms.** Losses to the random Anchor.
- **Small models.** [Source] ChessArena: Qwen3-8B (with list) 1335 and Seed-Coder-8B 1009 vs random 1524; "no LLM" beat Maia-1100. Pleiss: GPT-3.5, 4o and 5 "perform worse than random play" on most conditions. LLM Chess Elo (data 2026-10-10): qwen3.5-9b −258, llama3.1-8b −796, random −122 ([data](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv)).

---

## E. Model type and training

### E1. Chat/instruction tuning vs base completion
- **What.** Chat-tuned models play worse than the base model they came from.
- **Why.** [Source] Base models predict the next PGN token, which is the format strong play lives in; post-training shifts the distribution toward helpful chat. "In all cases, additional instruction tuning makes the model worse" (Dynomight, Llama 3.2-3B, Llama 3.1-70B, Gemma 2-27B pairs, Nov 2024). The best LLM chess player for years was gpt-3.5-turbo-instruct, a completion model (~1750 Elo, [Acher](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/), [Carlini](https://nicholas.carlini.com/writing/2023/chess-llm.html)), while chat gpt-3.5-turbo made illegal moves in 93% of games. Post-training also reduces calibration ([GPT-4 report](https://arxiv.org/abs/2303.08774), Fig. 8).
- **Symptoms.** Commentary instead of moves, refusals, plausible but weaker moves.
- **Small models.** [Source] The base/instruct gap was "very small" for two open pairs; open base models were terrible too ([Dynomight](https://dynomight.net/chess/)). Karvonen: Llama2-70B chat failed to format moves and the base model hallucinated illegal ones ([chess_gpt_eval](https://github.com/adamkarvonen/chess_gpt_eval)). [Inference] Base models fix format behaviour, not chess knowledge, at this size.

### E2. Chess knowledge scales with size and pretraining
- **What.** The underlying chess knowledge just isn't there below a certain scale.
- **Why.** Chess is a tiny share of web text; legality and board knowledge emerge slowly with scale. [Source: BIG-bench]
- **Symptoms.** All of A and D.
- **Small models.** [Source] ChessGPT-Base (2.8B, chess-trained) converts PGN→FEN at 94.8-96.7% vs <9% for LLaMA-7B ([ChessGPT](https://arxiv.org/html/2306.09200v2)). Fine-tuning helps a lot: Qwen3-8B legal rate without list 9.8% → 87.6% after SFT+RL ([ChessArena](https://arxiv.org/html/2509.24239v4)). But generic RL plateaus without pretraining knowledge ([Hwang](https://arxiv.org/html/2507.00726v3)).

### E3. Quantization
- **What.** 4-bit and lower quantization costs accuracy, more so for small and reasoning models.
- **Why.** Fewer bits per weight add noise; small models have less redundancy; long reasoning chains compound errors. [Source]
- **Symptoms.** More illegal moves and blunders at lower bit widths; no visible error.
- **Small models.** [Source] Liu et al. (Apr/Aug 2025), reasoning benchmarks: 4-bit weights "nearly lossless" (−0.4 to −3.9 points; R1-Distill-Llama-8B −3.9), 3-bit "risky": R1-Distill-Qwen-1.5B −18.6, Qwen3-8B −13.0, 32B −3.9. "Smaller reasoning models tend to suffer more" ([2504.04823](https://arxiv.org/html/2504.04823v2)). Chess directly: LLM Chess rates the same Qwen3.8-27B at 846 (Q4_K_M), 541 (Q2_K_XL) and 403 (ternary) ([data](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv)). No published chess comparison of Q4 vs Q8/FP16 for an 8B model found.

---

## F. Prompting, format and decoding

### F1. Instruction following and format compliance
- **What.** The model doesn't answer in the required format or protocol.
- **Why.** Small models follow multi-part instructions and schemas less reliably. [Source] On entity-tracking tasks, smaller models "often deviat[ed] from the format specified by the prompt" ([Code pretraining & entity tracking, 2024](https://arxiv.org/abs/2405.21068)).
- **Symptoms.** Unparseable replies, extra prose, wrong JSON field, a list of moves instead of one, talking instead of acting (max-turn limits).
- **Small models.** [Source] LLM Chess (Dec 2025): instruction-following errors ended **71.9%** of non-reasoning models' games (24.4% for reasoning). Qwen2.5-7B-Instruct: 100% of games lost to "too many wrong actions"; Qwen2.5-14B: 70% wrong actions + 30% max turns; Gemma 3 27B: 100%. ChessArena reports "substantial parsing error rates across models". gpt-oss-20b's LLM Chess games last about 7 moves because of protocol failures ([candidate-models.md](candidate-models.md), from LLM Chess data).

### F2. Prompt sensitivity
- **What.** Trivial changes to wording or layout change results a lot.
- **Why.** Models key on surface features of the prompt. [Source] Sclar et al. (ICLR 2024) found gaps of up to **76 accuracy points** from formatting alone on LLaMA-2-13B, persisting with size and instruction tuning, and only weakly correlated between models ([FormatSpread](https://arxiv.org/abs/2310.11324)).
- **Symptoms.** A model's ranking flips when the prompt changes; tricks help one model and hurt another.
- **Small models.** [Source] 13B was the worst case in Sclar. Chess-specific: listing legal moves *hurt* gpt-4o, while restating the game ("regurgitation") and 3 few-shot examples helped a lot ([Dynomight 2](https://dynomight.net/more-chess/)). [Inference] So a single fixed prompt biases cross-model comparisons.

### F3. Structured (JSON) output
- **What.** Forcing JSON or a schema may change reasoning quality.
- **Why/Evidence.** [Source] Tam et al. (2024) report reasoning drops under format restrictions ([2408.02442](https://arxiv.org/abs/2408.02442)); .txt's rerun on Llama-3-8B with equal prompts found structured output neutral to slightly better, best with a reasoning field before the answer ([.txt](https://blog.dottxt.ai/say-what-you-mean.html)). No chess-specific study found.
- **Symptoms.** Truncated or empty reasoning, a move field that contradicts the reasoning.

### F4. Enforced decoding and legal lists don't create skill
- **What.** Guaranteeing a legal move removes forfeits but leaves move quality low.
- **Why.** The constraint fixes legality, not evaluation (D1, D2). [Source]
- **Small models.** [Source] Dynomight's grammar-constrained open models (Llama 3.2-3B to 405B, Qwen 2.5-72B, Gemma 2-27B) "always generated legal moves" and still lost every game. Qwen3-8B with the list: 96.2% legal, rated below random (ChessArena).

### F5. Sampling, determinism and degeneration
- **What.** Temperature and decoding settings change strength and stability.
- **Why.** [Source] Low temperature averages away individual mistakes: chess transformers trained on 1000-1300-rated games beat their training players only at low temperature ([Transcendence, NeurIPS 2024](https://arxiv.org/abs/2406.11741)). Acher saw Elo drop at temperature 0.8. But reasoning models can loop at greedy decoding: Qwen3's card says "DO NOT use greedy decoding … endless repetitions" and recommends T=0.6 for thinking ([Qwen3-1.7B card](https://huggingface.co/Qwen/Qwen3-1.7B-MLX-8bit)). Temperature 0 also isn't bit-reproducible in batched serving ([Thinking Machines, 2025](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)).
- **Symptoms.** Random blunders at high temperature; thinking that never ends (timeouts) at low; the same position giving different moves on rerun.
- **Small models.** [Inference] Small models' output distributions are flatter, so sampling noise matters more. No chess numbers.

---

## G. Thinking / reasoning

### G1. Reasoning helps most, but at large token and latency cost
- **What.** Thinking models are much stronger, but each move takes thousands of tokens.
- **Why.** A chain of thought is the model's only search (D1). [Source]
- **Symptoms.** Long waits, timeouts, games abandoned mid-way.
- **Small models.** [Source] LLM Chess: reasoning 45.4% wins vs 0.7%; reasoning-model timeouts counted as model errors; o3 (low) ~1,928 tokens per move. ChessArena: Bullet mode (no reasoning) "severely impairs" play. ChessQA: thinking +14.7 points on average, GPT-5 79.3% vs 44.0%, with ~9,142 vs 1,236 tokens. Pleiss: GPT-5 reasoning cut centipawn loss 71.7%, using 3,400-17,000 reasoning tokens per position. Small thinking models still help: qwen3.5-9b −258 → −200 with thinking, qwen3.8-27b 846 (LLM Chess data). [Inference] At ~10-20 tok/s on a laptop, 5,000 tokens is 4-8 minutes per move.

### G2. Overthinking and diminishing returns
- **What.** More thinking stops helping, or hurts, especially in unfamiliar positions.
- **Why.** [Source] Reasoning models spend far too many tokens on easy problems (QwQ-32B gave 13 solutions to "2+3") ([Chen et al. 2024](https://arxiv.org/abs/2412.21187)). Pleiss: gain per 1,000 reasoning tokens fell from 22.6% on known positions to 3.8% on new ones. Quantized models also "may get worse" past a point of test-time compute ([Liu et al.](https://arxiv.org/html/2504.04823v2)).
- **Symptoms.** Long thoughts ending in an illegal or contradictory move; thinking loops; timeouts on simple recaptures.
- **Small models.** [Inference] Small reasoning models are trained by distillation on short math traces and are more prone to loops (F5).

---

## H. Evaluation pitfalls

### H1. Forfeits dominate the result
- **What.** Win/loss records measure format compliance and illegal moves more than chess.
- **Why.** Protocols end the game after N failed retries. [Source] LLM Chess (71.9%, F1); ChessArena says forfeits are why some models fall below random.
- **Effect.** Two models that never get to the middlegame can't be ranked by chess skill. [Inference] Report forfeit rate separately from results.

### H2. Elo estimation at the bottom of the scale
- **What.** Ratings for very weak players are poorly defined.
- **Why.** [Source] Elo is relative to the opponents; a 0% score gives no finite maximum-likelihood rating; Stockfish's weakest level is ~1320 CCRL and too strong; engine and human scales differ: DeepMind's 270M model was 2895 vs humans but 2299 vs bots on Lichess ([Ruoss](https://arxiv.org/html/2402.04494)). Detail in `elo-estimation.md`.
- **Effect.** Weak models need a random-mover Anchor or a prior to get any number.

### H3. Small samples and noisy opponents
- **What.** Few games give wide intervals.
- **Why.** [Source] LLM Chess intervals for small open models are ±130-280 Elo with ≥33 games per pairing; its Dragon Anchor is stochastic, with metric SDs 10-40% of the mean over 1,000 games. [Inference] ~20 games gives about ±150 Elo at a 50% score.

### H4. Protocols aren't comparable
- **What.** Numbers from different benchmarks can't be mixed.
- **Why.** [Source] LLM Chess gives a legal-move tool, UCI, always Black (+35 Elo correction); Game Arena gives FEN+PGN, SAN, no list, 3-4 tries; ChessArena varies modes and retries (5). Removing LLM Chess's legal-move tool dropped Grok 3 Mini from 61.7% to 36.7%.
- **Effect.** An LLM Chess Elo predicts "with a list" play, not free play.

### H5. Contamination and memorisation
- **What.** Strong results on familiar positions overstate skill.
- **Why.** Openings, famous games and Lichess puzzles are in pretraining data. [Source] Pleiss: 4.72× more illegal moves out of distribution (C1). Game Arena: models "unanimously favor the Sicilian", so it added a forced-opening variant. ChessQA and puzzle sets from Lichess may be seen in training. [Inference]
- **Effect.** Puzzle scores and short games overrate models; start-position-only games test memory.

### H6. Reproducibility
- **What.** The same configuration doesn't replay identically.
- **Why.** Sampling (F5), serving nondeterminism, changing model tags and quantizations, and prompt format (F2). [Source: Thinking Machines; Sclar]
- **Effect.** Log model digest, quantization, sampling settings and prompt version with every game. [Inference]

---

## Most important for small models

1. **Format and instruction-following failures (F1, H1).** The leading cause of lost games for non-reasoning models (71.9% in LLM Chess); every ~8B model there scored 0% wins.
2. **No board-state tracking (A1).** 0.0% board-state accuracy at 3-8B; root cause of illegal moves, own-piece captures and phantom pieces.
3. **Illegal moves without a list, especially in check (A2, A3).** Qwen3-8B 9.8% legal without a list vs 96.2% with it.
4. **Legality isn't strength (F4, D1, D3).** With a list or a grammar, 3-8B models still lose to or rank below a random mover.
5. **Reasoning is the main lever, and it is slow (G1, G2).** 45.4% vs 0.7% wins; thousands of tokens per move risk timeouts on local hardware.
6. **Out-of-book collapse and long games (C1, C2).** Errors cluster after the opening and late in the game.
7. **Quantization hurts small models more (E3).** 4-bit is near-lossless on average but up to −3.9 points at 8B; 2-3-bit is costly (Qwen3.8-27B 846 → 541 Elo).
8. **Measurement fragility (F2, H2, H3).** Prompt format alone can swing small models by tens of points, 0% records need a random Anchor, and ~20 games give ±150 Elo.

## Sources

- Benchmarks: [LLM Chess paper](https://arxiv.org/html/2512.01992v1), [repo](https://github.com/maxim-saplin/llm_chess), [data](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv); [Game Arena report](https://arxiv.org/html/2609.31473v1); [ChessArena](https://arxiv.org/html/2509.24239v4); [ChessQA](https://arxiv.org/html/2510.23948v1); [BIG-bench](https://arxiv.org/abs/2206.04615); [Galactica](https://arxiv.org/abs/2211.09085)
- Chess LLM studies: [Hwang et al. 2025](https://arxiv.org/html/2507.00726v3); [Pleiss et al. 2026](https://arxiv.org/html/2601.16823v2); [ChessGPT](https://arxiv.org/html/2306.09200v2); [Karvonen 2024](https://arxiv.org/abs/2403.15498), [blog](https://adamkarvonen.github.io/machine_learning/2024/01/03/chess-world-models.html), [chess_gpt_eval](https://github.com/adamkarvonen/chess_gpt_eval); [Ruoss et al. (Amortized Planning / GM without search)](https://arxiv.org/html/2402.04494); [Transcendence](https://arxiv.org/abs/2406.11741); [Maia](https://arxiv.org/abs/2006.01855)
- Posts: [Dynomight 1](https://dynomight.net/chess/), [Dynomight 2](https://dynomight.net/more-chess/); [Carlini](https://nicholas.carlini.com/writing/2023/chess-llm.html); Acher [2023](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/), [o3/o4-mini](https://blog.mathieuacher.com/GPTReasoningO3O4miniAndChess-copy/)
- General: [Illusion of State](https://arxiv.org/abs/2404.08819); [Entity tracking](https://arxiv.org/abs/2305.02363), [code pretraining follow-up](https://arxiv.org/abs/2405.21068); [Lost in the Middle](https://arxiv.org/abs/2307.03172); [Sclar et al.](https://arxiv.org/abs/2310.11324); [Tam et al.](https://arxiv.org/abs/2408.02442), [.txt](https://blog.dottxt.ai/say-what-you-mean.html); [Quantization Hurts Reasoning?](https://arxiv.org/html/2504.04823v2); [Overthinking](https://arxiv.org/abs/2412.21187); [Qwen3 card](https://huggingface.co/Qwen/Qwen3-1.7B-MLX-8bit); [Thinking Machines on nondeterminism](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/); [GPT-4 technical report](https://arxiv.org/abs/2303.08774)
- Vision: [VLMs are blind](https://arxiv.org/html/2407.06581v4); [IsoBench](https://arxiv.org/abs/2404.01266); [SEAM](https://arxiv.org/html/2508.18179v1); [Gemma 3 card](https://ai.google.dev/gemma/docs/core/model_card_3)

## Caveats

- Few sources test 1-30B models directly; many numbers are for frontier models, and small-model severity is then marked [Inference].
- Some numbers come from WebFetch summaries of long papers (LLM Chess, ChessArena, Game Arena), whose later sections were not all read.
- The Thinking Machines post and the "Lost in the Middle" figures were reached through the abstract and secondary summaries, not checked in full.
- The Qwen3 sampling advice was confirmed via mirrors of the official card.
