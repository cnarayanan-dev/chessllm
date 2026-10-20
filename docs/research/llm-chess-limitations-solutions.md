# How the top LLM chess benchmarking limitations are usually solved, and what to do here, 2026-10-20

Research date: 2026-10-20. Scope: for each P1 and P2 item in [`llm-chess-limitations-assessment.md`](llm-chess-limitations-assessment.md), plus C2, this note covers four things: how established LLM chess benchmarks, rating tools and eval frameworks deal with it; what each fix costs on small local models (9-30B, Ollama, M3 Pro 36 GB); which fix to use here; and in what order. Nothing was run. Games were playing on Ollama during the research, so the repo was only read.

This note doesn't repeat the work in [`forfeit-solutions-brainstorm.md`](forfeit-solutions-brainstorm.md) (ideas 1-15, referenced as "brainstorm idea n"), [`thinking-budget.md`](thinking-budget.md), [`elo-estimation.md`](elo-estimation.md), [`prompt-tooling.md`](prompt-tooling.md), [`board-images.md`](board-images.md) or [`candidate-models.md`](candidate-models.md). It refers to them instead.

Labels:
- **[Source]**: stated in the linked primary source.
- **[Repo]**: read from this repo's code or docs.
- **[Inference]**: my reading or arithmetic.

## TL;DR

- **Every benchmark that gets numbers for weak models has a floor opponent.** LLM Chess uses a uniform random mover at −122, calibrated with 1,000 games against each of Dragon Skill 1-4. ChessArena has a random player (1524 on its Glicko scale), and Chess LLM Benchmark one pinned at 400 Lichess. Here a random mover is one class plus one `ANCHOR_RATINGS` entry. A one-off engine-vs-engine gauntlet (random ↔ CuckooChess ↔ the Stockfish stand-in) can then put the other Anchors on the same scale without Dragon. [Source + Inference]
- **No benchmark rates small models on free-form legality.** LLM Chess hands out legal moves (a tool), TextArena lists them by default, and ChessArena found that "no legal moves" breaks 8B models. Game Arena is Free, but it rates frontier models. Recommendation: **Listed enforced** carries the headline Rating, and **Free** becomes the legality track, reported by its metrics. A call failure (not a timeout) voids the game instead of forfeiting it, as LLM Chess does with "programmatic errors". [Source + Inference]
- **Eval frameworks identify a run by hashes of what the model saw.** lm-evaluation-harness logs `prompt_hash` per sample, `system_instruction_sha`, `chat_template_sha`, `task_hashes` and `git_hash`. Inspect logs `task_version`, `model_generate_config`, `revision` and `packages`. Here: add a **prompt fingerprint**, a SHA-256 over the rendered messages of a few fixed reference positions plus the answer schema, to `PlayerConfiguration`. Log Ollama's model `digest`, `quantization_level` and version at `game_start`. [Source + Inference]
- **For board state, putting it in the prompt beats tools.** In LLM Chess's ablation, "Always Board State" scored 66.7 / 83.3 against 61.7 / 73.3 with the board-fetching tool (Grok 3 Mini / o4-mini), and "Only make_move" scored best (71.7 / 96.7). `position: described` is exactly this, and it is built. It needs no new code, only games. [Source + Repo]
- **Self-correction without outside facts doesn't work, but correction from outside feedback does.** That favours diagnosed Retry feedback (brainstorm idea 5) over "check your move" loops. [Source: Huang et al., Kamoi et al.]
- **Sample size:** benchmarks use 30-40 games per pairing or level (LLM Chess, Game Arena, ChessArena). Engine testing uses SPRT on colour-swapped pairs. For prompt A/B tests here, use paired replays of frozen positions, which take hundreds of Turns in minutes. Spend games only on Ratings. [Source + Inference]
- **Order:** (0) run `described` now; (1) prompt fingerprint and model digest; (2) token logging and `num_ctx`; (3) random Anchor and calibration; (4) a rated-track ADR; (5) prompt fixes, diagnosed feedback and a repetition line; (6) the thinking budget; (7) big anchored batches with a stopping rule.

## How the reference benchmarks are set up

| | LLM Chess (Saplin) | Kaggle Game Arena | ChessArena | Chess LLM Benchmark | TextArena Chess-v0 |
|---|---|---|---|---|---|
| Board given | Unicode board or FEN via `get_current_board`; legal moves via `get_legal_moves` | FEN + PGN, no list, no tools | FEN (Blindfold: history only), list optional, last 10 moves | FEN + ASCII + history + last move | board + valid moves (`show_valid=True`) |
| Illegal moves | 3 mistakes per dialog, then a loss; at most 10 turns per move | 3 retries ("rethinks"), feedback without diagnostics, then a loss | 5 retries, then a forfeit | 1 retry, a second illegal move forfeits | `error_allowance=1` |
| Game length | 200 plies; draws by fivefold repetition and the 75-move rule | FIDE rules (50-move) | 200 moves; fivefold, 75-move | not stated | `max_turns=100` |
| Rating | 1-D MLE vs fixed anchors, Fisher CI, +35 for always playing Black | Bradley-Terry, bootstrap CI, lowest = 0, calibrated via Stockfish → CCRL | Glicko (1500/350, RD floor 50; shown at RD ≤ 100) | Glicko-2, fixed anchors (random 400, Maia, Eubos), RD floor 30 | TrueSkill |
| Floor anchor | random −122 | none (lowest model = 0) | random 1524 | random 400 | – |
| Games | 30 per level vs random; ≥33 for an Elo | 40 per pair, 20 per colour | ~30 for RD < 100 | "relatively low" | – |
| Errors / timeouts | programmatic error → draw or discard; model errors excluded vs random, counted vs Dragon | not stated | 4,096 / 16,384 token caps | API timeouts | – |

Sources: [LLM Chess README](https://github.com/maxim-saplin/llm_chess), [paper](https://arxiv.org/html/2512.01992v1); [Game Arena report](https://arxiv.org/html/2609.31473v1); [ChessArena](https://arxiv.org/html/2509.24239v4); [Chess LLM Benchmark methodology](https://chessbenchllm.onrender.com/methodology), [repo](https://github.com/lightnesscaster/Chess-LLM-Benchmark); TextArena [paper](https://arxiv.org/abs/2504.11442), [`state.py`](https://github.com/LeonGuertler/TextArena/blob/main/textarena/state.py), [env registration](https://github.com/LeonGuertler/TextArena/blob/main/textarena/envs/__init__.py). GameBench uses Bradley-Terry too, preferring it to Elo because "each agent's ability is fixed" ([GameBench](https://arxiv.org/html/2406.06613v2)). That is the same reason ADR 0005 rejects Glicko.

---

## 1. H2 + D3: no calibrated Anchor, nothing at the bottom of the scale (P1)

**Typical solutions**
- **A random-mover floor.** LLM Chess: uniform random legal moves, Elo −122.3 "calculated when played against 1000 games each of skills 1-4" of Dragon. Models play 30 games as Black against it first, and only those that beat it go on to Dragon ([paper](https://arxiv.org/html/2512.01992v1) §2.1, App. B.5). ChessArena and Chess LLM Benchmark keep a random player in the pool too. [Source]
- **Calibrated engine levels, with a band rule.** LLM Chess: Dragon Skill ℓ = 125(ℓ+1). Stay at a level while the score S is 35-65%, "the informative range for Elo estimation". Move up at 65-80% (more for higher scores) after "roughly 15 to 20 clean games" ([README](https://github.com/maxim-saplin/llm_chess)). Game Arena interpolates against Stockfish levels mapped to CCRL and notes this "is less reliable outside the engine calibration range". [Source]
- **A prior instead of a floor.** BayesElo puts a prior over ratings, so a 10-0 record gets a finite rating ("a high rating difference has to be deserved") ([BayesElo](https://www.remi-coulom.fr/Bayesian-Elo/)). Ordo's `-y` gives "a list of players whose ratings will float around an estimated value", meaning loose anchors with an uncertainty ([Ordo 0.9.6 notes](https://talkchess.com/viewtopic.php?p=587434)). Glicko starts everyone at 1500 ± 350. [Source]
- **Engine-vs-engine calibration chains.** Rating lists such as CCRL rate engines from engine games; cutechess-cli gauntlets do the same ([cutechess-cli](https://github.com/cutechess/cutechess/blob/master/docs/cutechess-cli.6.txt)). LLM Chess's −122 is itself one such link: random vs Dragon. [Source]

**Trade-offs**
- A random mover is free and instant. Its rating holds only if our mover is the same uniform mover. Its scale is LLM Chess's Dragon claim (±100), not a measured chess.com one.
- A prior on LLM configurations always gives a number, but at 0% the number is the prior's. It also pulls weak configurations toward the pool mean. ADR 0005 chose no prior on configurations, and that is still right for the headline. [Inference]
- Chaining engines (random → CuckooChess → Stockfish stand-in) costs only CPU minutes and needs no LLM. But engine-vs-engine Elo doesn't carry over cleanly to engine-vs-LLM: a Stockfish maintainer found an engine "clearly stronger" against humans than its calibration ([issue #3635](https://github.com/official-stockfish/Stockfish/issues/3635), via `elo-estimation.md`). Keep wide priors. [Source + Inference]
- Even a random floor may not be enough for Free play. LLM Chess puts llama3.1-8b at −796, an expected score of about 2% against −122 ([data](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv)). Under Listed enforced, draws at the Move cap count as half points, which gives a finite fit. [Inference]

**Recommended here**
1. **A `RandomAnchor` in `chessllm/anchors.py`.** It plays `random.choice(list(board.legal_moves))`, uniform like LLM Chess's. Add `ANCHOR_RATINGS["anchor:random"] = AnchorRating(-122, 100)` and `"random"` to `AnchorEngine` (`chessllm/anchor_match.py`). Use a seeded RNG and log the seed in the side description, so a game can be replayed.
2. **A random phase in `chessllm/anchor_batch.py`, as in LLM Chess.** `next_skill` gets a floor level below Dragon/Stockfish Skill 1. The batch starts at random and steps up only above 65% over about 10 or more games.
3. **A one-off calibration gauntlet, `scripts/calibrate_anchors.py`, CPU only.** It plays the random mover against CuckooChess at `UCI_Elo` −625, −300, 0 and 250, and CuckooChess against the Stockfish stand-in Skill 1-3. Fit these with `rating.ratings` with random pinned at −122 ± 100, then write the resulting ratings and uncertainties into `ANCHOR_RATINGS`. This replaces the ±300 guess. CuckooChess becomes an Anchor adapter at the same time (`llama3-anchor-matches-2026-10-19.md`, "Next").
4. **Dragon, if it can be obtained.** Rerun 200 games of random vs Dragon 1-2 to check the −122 independently.
5. **Keep upper bounds as the headline for all-loss records.** Show a BayesElo-style MAP with a weak prior only as a labelled diagnostic, if at all.

ADR: a new ADR, "Random mover and calibrated engine Anchors". It amends ADR 0005, whose title says Dragon only and which defers the random mover. CONTEXT.md's **Anchor** already names the random mover. **Effort:** S (the random Anchor), M (gauntlet and CuckooChess adapter).

## 2. H1: forfeits decide the games (P1)

**Typical solutions**
- **Provide legal moves, so the benchmark measures chess.** LLM Chess (a tool), TextArena (`show_valid=True` by default) and ChessArena (optional list; Qwen3-8B 9.8% → 96.2% legal with it). [Source]
- **Allow a few retries, then count a loss, and report the error rate separately.** Game Arena: 3 retries, logged as "rethinks". LLM Chess: 3 mistakes. Chess LLM Benchmark and TextArena: 1. ChessArena: 5. All count a forfeit as a loss ([elo-estimation.md §5](elo-estimation.md)). [Source]
- **A fallback move.** Dynomight gave OpenAI models 10 tries, "then a random legal move" ([Dynomight](https://dynomight.net/chess/)). Brainstorm idea 9 is the better version: escalate the last attempt to Listed enforced. [Source]
- **Infrastructure failures aren't losses.** LLM Chess: programmatic errors become a draw, and throttles or model failures get "manual review, resulting in discard or LLM loss". Model errors are excluded from random-agent games and counted against Dragon. [Source]

**Trade-offs**
- Listed enforced makes forfeits impossible except by timeout (ADR 0003). It drops the legality signal and compares best with LLM Chess (H4). Dynomight found a list hurt gpt-4o's play. The F4 caveat applies: models stay weak.
- Free with a fallback keeps the first attempt Free and decides games by chess. But it needs an ADR, a new term, and an attempt excluded from the illegal-move metrics (ADR 0003).
- Hinted didn't work for llama3:8b (0 of 24 retries picked from the list).

**Recommended here**
- **Decide the tracks in one ADR.**
  - **Rated track: Listed enforced.** It carries the headline Rating.
  - **Legality track: Free.** It is reported by its first-attempt legality, Legal-move streak, illegal Turns and forfeit rate, with a Rating shown only as a bound.
  - Listed and Hinted remain Player configurations like any other; they just aren't headline.
- **Void a game on a call failure.** Change `_play_llm_turn` in `chessllm/game.py` so `result: "error"` (connection refused, Ollama crash) ends the game with a new end reason, `void`, which the leaderboard (`rated_game` in `chessllm/leaderboard.py`) skips. A timeout stays a Forfeit, and the thinking budget (§7) makes it rare.
- **Free + fallback (brainstorm idea 9) later, and only if a chess-decided Free Rating is wanted.** It needs a CONTEXT.md term, **Fallback move**.

ADRs: a new ADR, "Which LLM constraints carry the Rating; failed calls void a game". It amends CONTEXT.md **Forfeit**, which today includes "the call fails", and refines ADR 0005. **Effort:** S (decision and ADR, plus the void end reason); M if the fallback is built.

## 3. H6 + F2: configuration identity and reproducibility (P1)

**Typical solutions**
- **Hash what the model saw.** lm-evaluation-harness writes `doc_hash`, `prompt_hash` and `target_hash` per sample and combines them into `task_hashes` per task. It also logs `system_instruction_sha`, `chat_template_sha`, `git_hash`, environment and tokenizer info ([`evaluation_tracker.py`](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/loggers/evaluation_tracker.py), [`evaluator.py`](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/evaluator.py)). [Source]
- **Version the task and record the whole configuration.** Inspect's `EvalSpec` holds `task_version`, `task_args`, `model`, `model_generate_config`, `model_args`, `revision` (git origin and commit), `packages` (versions) and `dataset` ([`_log.py`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/log/_log.py), [eval logs](https://inspect.aisi.org.uk/eval-logs.html)). [Source]
- **Keep every request.** HELM writes `run_spec.json` (scenario, adapter, metrics) and `scenario_state.json`, which "contains every request to and response from the model" ([HELM tutorial](https://crfm-helm.readthedocs.io/en/latest/tutorial/)). [Source]
- **Pin the model build.** Ollama's `/api/tags` gives each model's `digest` ("SHA256 digest identifier of the model contents") and `details.quantization_level` ([API](https://docs.ollama.com/api/tags)). LLM Chess lists quantised local models by quant (Q4_K_M vs Q2_K_XL rate 846 vs 541). [Source]
- **Seeds help less than they seem.** Ollama has `options.seed`, but batched inference isn't bit-reproducible even at temperature 0 ([Thinking Machines](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)). [Source]

**Trade-offs**
- Hashing template files misses wording built in code (`turn_messages`, `retry_feedback`, `describe_position`, the schemas).
- A hand-bumped `prompt_version` constant catches everything, but only if someone remembers to bump it.
- A hash of the *rendered* output catches every change automatically. Its cost is that a whitespace edit also splits configurations, which is the safe direction.
- Putting the model digest in the configuration id splits games whenever a tag is re-pulled with new weights or template. That is correct, but it may orphan games. [Inference]

**Recommended here**
- **A prompt fingerprint in `PlayerConfiguration`** (`chessllm/leaderboard.py`), in the lm-eval style.
  - Render the Turn messages for 3 frozen reference positions with this configuration's settings: the start position, one in check, one Listed. Render also one `retry_feedback` per level and the answer schema JSON (`MoveAnswer` / `ReasonedMoveAnswer` with the enum shape).
  - Hash all of it with SHA-256 and keep 12 characters.
  - Compute it in `llm_configuration` / `settings_configuration` and log it at `game_start` with the system prompt text (HELM-style). Old logs, which have no fingerprint, map to the fingerprint of the commit they were played at (all of today's logs used today's prompt code, assessment "Pooling risk").
  - A unit test pins the current fingerprint, so any wording change fails CI until it is deliberately accepted.
- **Log the model build at `game_start`.** Per LLM side: `digest`, `quantization_level` and `parameter_size` from `ollama.list()`, the Ollama server version, and the repo's git commit (Inspect's `revision`).
  - Add the digest to the configuration id too.
  - Log the Modelfile's sampling parameters (`ollama show`) when `sampling` is `model_default`, so "model default" is a known value.
- **Fix `scripts/analyse_games.py` grouping.** It should group by `PlayerConfiguration.id()` so max attempts and sampling don't mix (assessment H6).

ADR: a new ADR, "A Player configuration is identified by its prompt fingerprint and model digest". It amends ADR 0004 (new `game_start` fields) and ADR 0005 (pooling). **Effort:** S-M.

## 4. A1: no board-state tracking (P1)

**Typical solutions**
- **Put the state in every prompt.**
  - LLM Chess ablation (Win/Loss %, vs random): baseline with a `get_current_board` tool 61.7 / 73.3 (Grok 3 Mini / o4-mini). "Always Board State" 66.7 / 83.3. "Only make_move" (board and legal moves always given) 71.7 / 96.7. FEN 63.3 / 95.0 vs ASCII 63.3 / 88.3. The authors read this as "reasoning models struggle with agentic tool use" ([paper](https://arxiv.org/html/2512.01992v1), Table 3).
  - Chess LLM Benchmark gives FEN, an ASCII board, the history and the last move.
  - ChessQA: a piece list helped (A1 in the limitations doc).
  - [Source]
- **Tools** (`get_current_board`, `get_legal_moves`): LLM Chess. They are weaker than injection (above), and only qwen3.5:9b has the `tools` capability here (brainstorm idea 12). [Source + Repo]
- **Make the model restate the board.** Dynomight found "regurgitation" (restating the game) and 3 few-shot examples helped gpt-4o ([Dynomight 2](https://dynomight.net/more-chess/)). Brainstorm idea 3. [Source]
- **Self-verification.** LLMs "cannot self-correct reasoning yet" without outside feedback ([Huang et al., ICLR 2024](https://arxiv.org/abs/2310.01798)). Self-correction works when the feedback is reliable and external ([Kamoi et al., TACL 2024](https://arxiv.org/abs/2406.01297)). Here the external check is the judge, so the lever is better feedback (§5), not a "check your move" step. [Source]
- **Lightweight perception and memory scaffolds** (lmgame-Bench) to "stabilize prompt variance" ([lmgame-Bench](https://arxiv.org/abs/2505.15146)). [Source]

**Trade-offs**
- Injection makes the Free track measure move generation from a known board, not memory of the PGN. That is a clearer split, and still Free.
- Every format is a new configuration (B3).
- ASCII is in the LLM Chess ablation, and our probe shows the FEN isn't read. Images don't help ([board-images.md](board-images.md)).
- Regurgitation lengthens each answer, at about 100-200 tokens per Turn [Inference], and gives a free board-tracking metric.

**Recommended here**
- **Play `position: described` now.** It needs zero code and is already part of the configuration.
- **If it helps, add `PositionFormat = "board"`** (the ASCII grid from `str(board)` plus the described lines) in `chessllm/prompt.py`, as the second representation.
- **Regurgitation (brainstorm idea 3) only as a diagnostic experiment later.**
- No ADR. `position` is already a configuration field. **Effort:** S.

## 5. F1: instruction following (P2)

**Typical solutions**
- **Constrain the format.** Structured output with a JSON schema is already used, and JSON failures are nearly nil. ChessArena parses UCI with a SAN fallback. Game Arena normalises minor SAN variants (ADR 0002 already does this). [Source + Repo]
- **Keep the protocol small.** LLM Chess's biggest gain was removing actions ("Only make_move"). [Source]
- **Few-shot examples that match the real answer**, which helped in Dynomight 2. [Source]
- **Feedback on retry.** Game Arena hides diagnostics on purpose and measures rethinks. ChessArena gives "an instruction". Better feedback works only when it is reliable and external (Kamoi). [Source]

**Trade-offs**
- Diagnosed feedback (brainstorm idea 5) leaks facts about the board but not the legal moves. It is a new Retry feedback level, so it fits the configuration model.
- Fresh retries with a rejected-moves list (idea 6) change how every retry works, so they must be a setting or covered by the fingerprint.

**Recommended here (after §3)**
- **Fix the system prompt.**
  - In `chessllm/prompts/system*.txt` and `system_prompt`, replace "against a human" with the actual opponent (a `$opponent_kind` placeholder).
  - Make the example answer match the schema: `{"reasoning": "...", "move": "e5"}` when thinking is off. This needs a second example placeholder.
- **A `diagnosed` Retry feedback level** in `retry_feedback` / `RetryFeedback`. It reuses `chessllm/chaos.py`'s resolution to say "f3 holds your own knight", "you have no knight on c3", "you are in check" or "already tried this turn".
- **Fresh retries (idea 6)**, bundled into `diagnosed` so no existing level changes.
- No ADR (a new enum value), but add the level to CONTEXT.md **Retry feedback**. **Effort:** S (prompt fixes), M (diagnosed).

## 6. A3: check and king safety (P2)

**Typical solutions**
- **State "in check" explicitly.** Chess LLM Benchmark gives the opponent's last move. `described` says "You are in check." Game Arena names "in check but proposes a move that fails to resolve the threat" as the typical late failure, but doesn't say it fixed it. [Source + Repo]
- **Give the legal list in check.** Under Listed it is automatic, since in check the list is short.

**Recommended here**
- **The same run as §4.** In `described` games, measure recovery in in-check Turns separately.
- **Name the checking piece** ("in check from the queen on e4") in `describe_position`, through `board.checkers()`.
- **Make the diagnosed feedback in check** say "the move must get your king out of check".
- **Effort:** S. It comes with §4 and §5.

## 7. G1: reasoning helps, but is slow (P2)

**Typical solutions**
- **Token caps.** ChessArena caps new tokens at 4,096 (no thinking) and 16,384 (thinking). Budget forcing (s1, Qwen3 report) is covered in [thinking-budget.md](thinking-budget.md). [Source]
- **Timeouts as model errors.** LLM Chess counts them against Dragon but excludes them in random-agent games. [Source]

**Recommended here:** exactly [thinking-budget.md](thinking-budget.md)'s recommendations.
- `thinking_budget` in the Player configuration, enforced by `num_predict` plus a forced answer.
- The 300 s timeout stays as a safety net.
- Run its offline probe first.
- No thinking configuration enters a rated pool before this exists.

The budget belongs in the fingerprinted configuration (§3). ADR: as that note proposes, plus a CONTEXT.md term, **Thinking budget**. **Effort:** M.

## 8. H3: small samples (P2)

**Typical solutions**
- **A fixed number of games per pairing.** Game Arena plays 40 per pair (20 per colour) with bootstrap CIs. LLM Chess plays 30 per level and needs ≥33 for an Elo. ChessArena needs ~30 for RD < 100. [Source]
- **A band rule.** LLM Chess stays at the level where the score is 35-65%, where each game carries the most information. [Source]
- **Sequential testing.** fishtest uses GSPRT with bounds in normalised Elo and a pentanomial model of game pairs, and runs "as many games as needed until the test reaches a statistically definitive result" ([fishtest maths](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-Mathematics.html), [first test](https://official-stockfish.github.io/docs/fishtest-wiki/Creating-my-first-test.html)). cutechess-cli `-sprt elo0 elo1 alpha beta` and `-repeat` play each opening twice with colours swapped ([cutechess-cli](https://github.com/cutechess/cutechess/blob/master/docs/cutechess-cli.6.txt)). [Source]

**Arithmetic** [Inference]
- With known Anchors, the 95% half-width is about ±215 Elo at 10 games, ±150 at 20 and ±95 at 50, at a 50% score (`elo-estimation.md`).
- To tell a 0-Elo difference from a 100-Elo one (α = β = 0.05) by games takes about 130 games at a fixed sample size. SPRT takes about half that on average. That is too many for prompt A/B tests at 2-30 minutes a game.
- The same question asked per Turn ("was the first attempt legal?") needs only hundreds of positions. Paired on the same positions (McNemar or a paired bootstrap), it needs fewer still.

**Recommended here**
- **Test prompt and feedback changes on positions, not games.**
  - Use a paired replay of frozen positions: `docs/research/board-images-positions.json` and logged first attempts, as `scripts/probe_board_images.py` does.
  - Promote that pattern to `scripts/replay_positions.py` (prompt-tooling Option C without promptfoo). It is the "offline replay" both the assessment and the brainstorm call step 1.
- **Spend games only on Ratings.**
  - 20-30 anchored games per configuration that matters, in the 35-65% band (random phase first, §1).
  - Faceoffs in colour-swapped pairs, which `faceoff_batch` already alternates.
- **A stopping rule in `anchor_batch`.** Stop a configuration once its 95% interval is ≤ ±150, or after the budget. Report the interval always.
- **Effort:** L wall-clock, S code.

## 9. C4: repetition and failing to convert (P2)

**Typical solutions**
- **Show recent history.** ChessArena added the latest 10 moves because fivefold draws "occurred frequently" without them. [Source]
- **Draw only at fivefold, automatically.** LLM Chess and ChessArena draw at fivefold and the 75-move rule (FIDE's automatic draws). This project draws at threefold the moment it occurs (`_check_end` in `chessllm/game.py`). [Source + Repo]
- **Adjudicate by engine.** cutechess-cli `-resign movecount score` and `-draw movenumber movecount score`, `-maxmoves`, and Syzygy `-tb`. A searchless transformer was "indecisive" in won positions and needed a Stockfish tie-break (Ruoss). [Source]

**Trade-offs**
- A repetition line is a fact about the position ("this position has occurred twice; a third time draws"). It is cheap, it is a prompt change (§3), and it may not be acted on by small models.
- Fivefold gives a model more chances to escape a loop, and longer games. It is a rules change that diverges from the threefold logic in ADR 0006's position list.
- Engine adjudication decides results by Stockfish, not by the game. That suits engine testing but changes what a Rating means here.

**Recommended here**
- **A repetition line in `describe_position`.** Pass the position count from `GameSession._positions`, as in "This position has occurred 2 times. If it occurs again the game is drawn."
- **Report "draws with a material lead ≥ 5"** in `scripts/analyse_games.py`, from the analysis file's evaluations, next to results. Don't adjudicate.
- **Keep threefold.** Revisit fivefold only if the repetition line doesn't cut these draws in Listed enforced games.
- No ADR unless the rule changes (that one would amend ADR 0006). **Effort:** S.

## 10. F4: a legal list fixes legality, not strength (P2)

**Typical solutions**
- **Measure it, don't fix it.** Every benchmark reports both win rate or Elo and legality or error rate (LLM Chess, Game Arena's rethinks, Chess LLM Benchmark's Legal%, Kagi's puzzles beside illegal-move %). [Source]

**Recommended here**
- **Report next to every Rating:** the forfeit rate, first-attempt legality (Free only), centipawn loss and blunder rate (≥ 200 cp, from the analysis files). Do this in the leaderboard (`LeaderboardEntry`) and `analyse_games`.
- **Say that a Listed-enforced Rating is "chess given legal moves"**, comparable to LLM Chess's numbers (H4), not to Game Arena's.
- **Effort:** S.

## 11. C2: context window (P2, next in line)

**Typical solutions**
- **Set the window explicitly and check what was used.**
  - Ollama's default context depends on memory: 4k under 24 GiB of VRAM, 32k for 24-48 GiB, 256k above that. It is set by `OLLAMA_CONTEXT_LENGTH` or `options.num_ctx` and shown in `ollama ps`'s CONTEXT column ([docs](https://docs.ollama.com/context-length), [API](https://docs.ollama.com/api/chat)).
  - Prompts that overflow are cut silently and still return HTTP 200 ([write-up](https://particula.tech/blog/ollama-num-ctx-silent-prompt-truncation), secondary).
  - The response gives `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count` and `done_reason`.
  - [Source]
- **Keep prompts short by design.** A fresh Turn has no conversation (this project; Game Arena sends FEN + PGN each time). [Repo]

**Trade-offs**
- A larger `num_ctx` costs KV-cache memory. With a 27B Q4 model at about 17 GB on 36 GB, 16-32k is likely fine, and 256k is not [Inference].
- Which bucket the M3 Pro falls in depends on what Metal reports as usable memory. Check `ollama ps` when the GPU is free [Inference].

**Recommended here**
- **Log per attempt** in `OllamaPlayer.reply` (via `LlmReply`) and the `llm_attempt` event: `prompt_eval_count`, `eval_count`, `done_reason`.
- **Set `options.num_ctx` explicitly.** Use 8,192 with thinking off and 16,384 with it on (or budget + prompt + margin). Make it part of the configuration so it is fingerprinted.
- **Flag any attempt where `prompt_eval_count + eval_count` ≥ 90% of `num_ctx`.**
- ADR 0004 gets new attempt fields (a small amendment, or part of the §3 ADR). **Effort:** S.

---

## Roadmap, in order

The dependencies are the assessment's. Every step has a cheap check with the existing tools. "Baseline" means the matching earlier games, selected with `--since`.

| Step | What | Depends on | Effort |
|---|---|---|---|
| 0 | Play `position: described` (A1, A3) | nothing: it is already a configuration field | none |
| 1 | Prompt fingerprint + model digest + git commit (H6, F2); analyse_games groups by id; failed calls void (H1 part) | – | S-M + ADR |
| 2 | Token counts and explicit `num_ctx` (C2) | 1 (num_ctx fingerprinted) | S |
| 3 | Random Anchor, random phase in the ladder, calibration gauntlet, CuckooChess adapter (H2, D3) | – (can run alongside 1-2) | S + M + ADR |
| 4 | Rated-track ADR: Listed enforced headline, Free as legality track; the F4 columns | 3 | S |
| 5 | Prompt fixes, `diagnosed` feedback + fresh retries, check line, repetition line (F1, A3, C4); `scripts/replay_positions.py` | 1 | S-M |
| 6 | Thinking budget (G1), per `thinking-budget.md` | 1, 2 | M + ADR |
| 7 | Big anchored batches with a stopping rule (H3) | 3, 4; 6 for thinking models | L wall-clock |

**Validation, one cheap experiment per step**

0. **`described`, free now.**
   ```
   uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 6 --position described
   uv run python -m scripts.analyse_games --mode llm_faceoff --since <start>
   ```
   - *Worked if:* first-attempt legality rises by ≥ 10 points over the 2026-10-19 baseline (41% / 53%); the share of illegal moves onto its own pieces falls from 34% / 46%; the Legal-move streak roughly doubles from ~3.5; and in-check Turns recover more often.
1. **Identity.**
   - Run `chessllm.leaderboard.leaderboard(games/)` offline before and after the change. Every existing configuration must keep one id, and none may merge.
   - Then play `faceoff_batch --games 2` and check that `game_start` has `prompt_fingerprint`, `digest`, `quantization_level` and the commit.
   - Change one word in `retry_feedback` on a branch: the fingerprint test must fail.
2. **Context.** One `faceoff_batch --models qwen3.8:latest gemma3:12b --thinking-for qwen3.8:latest --games 1`.
   - Check the largest `prompt_eval_count + eval_count` against `num_ctx`, and look for `done_reason` other than `stop`.
3. **Anchor.**
   - Gauntlet first, CPU only: CuckooChess at −625 should score clearly above random, and the fitted Stockfish stand-in should land near the 800-900 of the CuckooChess check.
   - Then `uv run python -m chessllm.anchor_batch --model llama3:8b --engine random --llm-constraints listed_enforced --games 6`.
   - *Worked if:* the leaderboard shows a finite Rating or a tighter bound in place of "< 466".
4. **Track.** `anchor_batch --model gemma3:12b --engine random --llm-constraints listed_enforced --games 6` and the same for llama3:8b.
   - *Worked if:* 0 forfeits, end reasons are checkmate, repetition or the Move cap, and the two models separate on score and centipawn loss.
5. **Prompt and feedback.**
   - First replay ~300 logged first attempts per model, old vs new messages, paired. *Worked if:* +10 points of legality.
   - Then `uv run python -m chessllm.anchor_batch --model llama3:8b --engine random --retry-feedback diagnosed --games 4`. *Worked if:* retry success rises above the first-attempt rate and with the attempt number, and no refused move is repeated in a Turn.
   - For repetition: 6 Listed enforced faceoffs, llama3 vs qwen3.8 without thinking. *Worked if:* fewer threefold draws with a material lead ≥ 5 than in 2026-10-19T20-29.
6. **Thinking budget.** The probe in `thinking-budget.md`, then `anchor_batch --model qwen3.5:9b --thinking --engine random --games 2` with the chosen budget.
   - *Worked if:* no timeout forfeits, and `forced` answers are rare.
7. **Samples.** `anchor_batch --games 30` per headline configuration, stopping at ±150.
   - Check that the leaderboard's intervals shrink about as 1/√n, and that faceoff results agree in direction with the anchored Ratings.

**ADRs and terms to write**
- **Identity (step 1):** prompt fingerprint and model digest in the Player configuration. Amends 0004 and 0005.
- **Anchors (step 3):** a random mover and Anchors calibrated by a gauntlet. Amends 0005.
- **Track (steps 1 and 4):** Listed enforced carries the Rating, and a failed call voids a game. Changes CONTEXT.md **Forfeit** and adds a void end reason.
- **Thinking budget (step 6):** as in `thinking-budget.md`. CONTEXT.md gets **Thinking budget**.
- **Optional, later:** **Fallback move** (brainstorm idea 9). Fivefold repetition would amend 0006.

The next free ADR number is 0007; 0005 is used twice.

## Caveats

- **Partly read sources.** LLM Chess, Game Arena and ChessArena facts come from WebFetch summaries that read about the first 100k characters of each paper. The tables and sections cited were in that part.
- **Secondary sources.**
  - The Ordo `-y` description comes from the release notes quoted on TalkChess, not the manual.
  - Ollama's truncation behaviour comes from a secondary write-up; the context-length defaults come from Ollama's docs.
  - Fishtest's exact SPRT bounds weren't on the pages read.
- **The −122 for the random mover is LLM Chess's**, on its Dragon claim. Our mover must be uniform for it to carry over.
- **Engine chains are approximate.** Engine-vs-engine calibration doesn't carry over cleanly to games against LLMs, so keep wide priors.
- **"Chess LLM Arena"** wasn't found as a distinct project. Chess LLM Benchmark (lightnesscaster) is the closest arena-style one and is used instead.

## Sources

- **Benchmarks:**
  - LLM Chess: [paper](https://arxiv.org/html/2512.01992v1), [repo](https://github.com/maxim-saplin/llm_chess), [data](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv)
  - Game Arena: [report](https://arxiv.org/html/2609.31473v1)
  - ChessArena: [paper](https://arxiv.org/html/2509.24239v4)
  - Chess LLM Benchmark: [methodology](https://chessbenchllm.onrender.com/methodology), [repo](https://github.com/lightnesscaster/Chess-LLM-Benchmark)
  - TextArena: [paper](https://arxiv.org/abs/2504.11442), [source](https://github.com/LeonGuertler/TextArena)
  - GameBench: [paper](https://arxiv.org/html/2406.06613v2)
  - lmgame-Bench: [paper](https://arxiv.org/abs/2505.15146)
  - Dynomight: [1](https://dynomight.net/chess/), [2](https://dynomight.net/more-chess/)
- **Rating:**
  - [BayesElo](https://www.remi-coulom.fr/Bayesian-Elo/)
  - Ordo: [repo](https://github.com/michiguel/Ordo), [0.9.6 notes](https://talkchess.com/viewtopic.php?p=587434)
  - [Stockfish issue #3635](https://github.com/official-stockfish/Stockfish/issues/3635)
  - [`elo-estimation.md`](elo-estimation.md)
- **Engine testing:** fishtest [mathematics](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-Mathematics.html), [first test](https://official-stockfish.github.io/docs/fishtest-wiki/Creating-my-first-test.html); [cutechess-cli](https://github.com/cutechess/cutechess/blob/master/docs/cutechess-cli.6.txt); [TalkChess on cutechess SPRT](https://talkchess.com/viewtopic.php?p=906986)
- **Eval frameworks:**
  - lm-evaluation-harness: [`evaluation_tracker.py`](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/loggers/evaluation_tracker.py), [`evaluator.py`](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/evaluator.py)
  - Inspect: [`_log.py`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/log/_log.py), [eval logs](https://inspect.aisi.org.uk/eval-logs.html)
  - [HELM](https://crfm-helm.readthedocs.io/en/latest/tutorial/)
- **Ollama:** [context length](https://docs.ollama.com/context-length), [chat API](https://docs.ollama.com/api/chat), [tags API](https://docs.ollama.com/api/tags), [truncation write-up](https://particula.tech/blog/ollama-num-ctx-silent-prompt-truncation)
- **Self-correction:** [Huang et al. 2024](https://arxiv.org/abs/2310.01798); [Kamoi et al. 2024](https://arxiv.org/abs/2406.01297)
- **Nondeterminism:** [Thinking Machines](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)
