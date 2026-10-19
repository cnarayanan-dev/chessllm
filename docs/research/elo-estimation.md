# How do we estimate a human-comparable Elo for an LLM player configuration?

Research date: 2026-10-19. Scope: how a "measurement engine" could take several finished games of one **Player configuration** (an LLM plus every setting it played with, see `CONTEXT.md`) and turn them into an Elo estimate with an honest uncertainty interval, ideally on the chess.com Rapid/Blitz scale. The players are small local models (llama3:8b, qwen 8-9B class via Ollama), playing humans and each other.

Labels used below:
- **[Source]** means the claim is stated in the linked primary source.
- **[Inference]** means it is my reading or extrapolation, not something the source states.
- **[Unverified]** means I could only reach a secondary source or a snippet, not the primary page.

## TL;DR

- **A rating only means something relative to the opponents it was earned against.** [Source] Lichess: "It is best not to think of ratings as absolute numbers, or compare them against other organisations" ([lichess FAQ](https://lichess.org/faq#ratings)). The Stockfish FAQ: "The Elo system is fundamentally relative" ([Stockfish FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html)). To get a chess.com-comparable number, the LLM's games must be connected to opponents whose *chess.com* strength is known.
- **Stockfish's `UCI_Elo` is not a human scale, and it cannot go low enough.** [Source] It is fitted to engine games and "covers CCRL Blitz Elo from 1320 to 3190", anchored only "to within +- 100 Elo of CCRL" ([search.h](https://github.com/official-stockfish/Stockfish/blob/master/src/search.h), [commit a08b8d4](https://github.com/vondele/Stockfish/commit/a08b8d4e9711c2)). A Stockfish maintainer found that a 1500-calibrated build "matches maia5 in a direct match quite well, however, for humans it seems clearly stronger" ([issue #3635](https://github.com/official-stockfish/Stockfish/issues/3635)). Small LLMs will almost certainly score 0% against even its weakest setting.
- **Results-based maximum likelihood against fixed-rated anchors is the standard method, and it is what the LLM benchmarks use.** [Source] LLM Chess fixes each opponent's rating and finds "the maximum-likelihood Elo rating" with a Fisher-information 95% CI, using Komodo Dragon levels calibrated to chess.com (skill 1 ≈ 250, +125 per level) and a random mover ([paper](https://arxiv.org/html/2512.01992v1), [repo](https://github.com/maxim-saplin/llm_chess)). Kaggle Game Arena uses Bradley-Terry with bootstrap CIs and calibrates externally against Stockfish levels ([report](https://arxiv.org/html/2609.31473v1)).
- **Uncertainty from results is wide with few games.** [Inference] With known opponent ratings and no draws, the 95% CI half-width is about ±215 Elo after 10 games, ±150 after 20 and ±95 after 50 at a 50% score. It is much wider when the score is near 0% or 100%, and at exactly 0% the maximum-likelihood estimate is −∞. An all-loss record needs a prior or a weaker anchor (a random mover) to give any finite number.
- **Move-quality estimates (ACPL, accuracy, IPR, Maia likelihood) use every move, but none is calibrated where small LLMs play.** [Source] Regan's IPR is a fitted model with error bars, trained on FIDE-rated games, originally from 1600 Elo ([Regan & Haworth 2011](https://cse.buffalo.edu/~regan/papers/pdf/ReHa11c.pdf)) and later extended down to about 1025 ([Regan 2024 talk](https://cse.buffalo.edu/~regan/Talks/CogSciOct2024np.pdf)). Per-game ACPL explains only 5-7% of rating variance in one Lichess sample ([Coulombe](https://sites.google.com/view/patrick-coulombe-phd/chess-analytics/predicting-rating-from-centipawn-loss)). chess.com's "Game Rating" formula is not published ([chess.com help](https://support.chess.com/en/articles/10773754-how-is-game-rating-calculated-in-game-review)).
- **Scale conversions are rough and have no data at the bottom.** [Source] The ChessGoals survey maps chess.com Blitz 500 → chess.com Rapid 815 → Lichess Rapid 1290, with "±" bands of 70-115 for the middle 50% of players, and has no rows below chess.com Blitz 500 ([ChessGoals](https://www.chessgoals.com/rating-comparison/)). The models in this project probably sit below that.
- **Recommendation** (details at the end). Use a Bayesian/ML Elo fit over one pool that holds every game: LLM-vs-human games (the human anchored with a loose prior at their chess.com rating), LLM-vs-LLM faceoff games, and LLM games against cheap, chess.com-anchored or self-calibrated bots (random mover, Maia, Komodo Dragon 1 low levels). Count forfeits as losses. Report a 95% interval, and report "below X" when the data cannot resolve the number. Use move quality (Maia likelihood, lichess-style accuracy) only as a secondary, clearly labeled diagnostic.

## Summary table

| Method | Inputs needed | Games for a usable CI | Anchors to chess.com? | Main weakness for 8B LLMs | Tooling |
|---|---|---|---|---|---|
| ML / Bayesian Elo vs fixed-rated anchors (BayesElo, Ordo, own MLE) | Results vs opponents of known rating | ~20 for ±150, ~50 for ±100 (at a balanced score) | Only as well as the anchors are anchored | Needs opponents near the LLM's level. A 0% score gives no finite MLE without a prior | [BayesElo](https://www.remi-coulom.fr/Bayesian-Elo/), [Ordo](https://github.com/michiguel/Ordo), scipy |
| Stockfish `UCI_Elo` / Skill Level as opponent | Stockfish 19 | as above | No: CCRL Blitz, range 1320-3190 | Far too strong at its floor. Hardware- and time-dependent | python-chess `chess.engine`, `brew install stockfish` |
| Maia-1 (1100-1900) / Maia-2 as opponent | lc0 + weights, or `pip install maia2` | as above | Lichess scale (via the bots' ratings or training bins), then ChessGoals to chess.com | Maia bots are rated higher than their label. Probably still too strong for 8B LLMs | [maia-chess](https://github.com/CSSLab/maia-chess), [maia2](https://github.com/CSSLab/maia2) |
| Komodo Dragon low skill levels as opponent | Dragon 1 (free) | as above | Yes, claimed: level ℓ ≈ 125(ℓ+1) on chess.com | Calibration is a single benchmark's claim. Platform support unverified | [llm_chess README](https://github.com/maxim-saplin/llm_chess) |
| Glicko-2 from a provisional start | Results in order | RD < 110 ("not provisional" on lichess) takes tens of games | Only via rated opponents | Order-dependent. Built for rating periods of 10-15 games | `glicko2` on PyPI |
| ACPL → Elo regression | Stockfish analysis of the LLM's moves | Many games. Per-game r ≈ 0.2-0.25 | Only if the regression was trained on chess.com players | Very weak per game. Distorted in lost positions | python-chess + Stockfish |
| Lichess accuracy / chess.com CAPS2 / Game Rating | Engine analysis | n/a | chess.com Game Rating is chess.com-scaled but a black box | No published accuracy → rating map. Game Rating needs uploads to chess.com | python-chess `Score.wdl(model="lichess")` |
| Regan IPR | Multi-PV engine analysis + Regan's fitted model | ~200-400 moves for ±200 | FIDE scale, then convert | Fitted on humans ≥ ~1025 FIDE. Model and software not packaged publicly | none public |
| Maia move-matching likelihood | Maia-2 + the game's positions | Unknown. Never validated as a rating estimator | Lichess Rapid scale | Untested method. LLM errors are not human errors | `maia2` (runs on Apple MPS) |

## 1. Results-based rating against calibrated opponents

### How the Elo model turns results into a rating
- [Source] Under the logistic Elo model, a player rated R against an opponent rated R_o has expected score 1/(1+10^((R_o−R)/400)). LLM Chess holds each opponent's rating fixed, codes win/draw/loss as 1/0.5/0, finds the rating where the summed score residuals are zero (the MLE), gets the standard error from the Fisher information, and reports ±1.96 SE ([LLM Chess, App. B.4](https://arxiv.org/html/2512.01992v1)).
- [Source] It adds 35 Elo because the LLM always played Black, from White scoring about 54% between equals ([LLM Chess](https://arxiv.org/html/2512.01992v1)). BayesElo fits a first-move advantage instead (default eloAdvantage = 32.8, eloDraw = 97.3, both fitted on 29,610 games) ([BayesElo](https://www.remi-coulom.fr/Bayesian-Elo/)).
- **How many games.** [Inference] From the Fisher information with known opponent ratings and no draws, SE = (400/ln 10)/√(n·p(1−p)) for score p over n games. 95% half-widths:

  | Games | score 50% | score 25% | score 10% |
  |---|---|---|---|
  | 10 | ±215 | ±249 | ±359 |
  | 20 | ±152 | ±176 | ±254 |
  | 50 | ±96 | ±111 | ±161 |
  | 100 | ±68 | ±79 | ±113 |

  These are lower bounds: uncertainty in the anchors' own ratings adds on top. LLM Chess's own rule is to move to a stronger opponent when the score is above 65% over "roughly 15 to 20 clean games" and to stay in the 35-65% band, "the informative range for Elo estimation" ([llm_chess README](https://github.com/maxim-saplin/llm_chess)).
- **The 0% problem.** [Inference] If the LLM loses every game, the likelihood keeps rising as its rating falls, so the MLE is −∞ and the Fisher CI is undefined. There are three fixes: an opponent weak enough to lose sometimes (LLM Chess's random mover, calibrated at −122 on its chess.com-anchored scale ([paper](https://arxiv.org/html/2512.01992v1))); a Bayesian prior (BayesElo uses one that "increases the likelihood that the ratings of players are close to each other" ([BayesElo](https://www.remi-coulom.fr/Bayesian-Elo/))); or reporting a one-sided bound ("below X with 95% confidence").

### Stockfish at fixed `UCI_Elo` / Skill Level
- **How the levels work.** [Source] "`Skill Level` and `UCI_Elo` make Stockfish play weaker by intentionally choosing suboptimal moves". `UCI_Elo` only applies with `UCI_LimitStrength=true` and is converted internally into a Skill Level ([Stockfish FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html)). The conversion is a cubic in (UCI_Elo − 1320)/(3190 − 1320), clamped to levels 0-19 ([search.h](https://github.com/official-stockfish/Stockfish/blob/master/src/search.h)).
- **Calibration is engine-vs-engine on CCRL, not human.** [Source] The fit is from "games played between master at various skill levels, and various versions of the Stash engine, which have been ranked at CCRL". The README change reads "calibrated at a time control of 120s+1.0s and anchored to +- 100 Elo to CCRL Blitz". The previous calibration was 60s+0.6s against CCRL 40/4 ([commit a08b8d4](https://github.com/vondele/Stockfish/commit/a08b8d4e9711c2)). The source comment: "Skill 0 .. 19 now covers CCRL Blitz Elo from 1320 to 3190, approximately" ([search.h](https://github.com/official-stockfish/Stockfish/blob/master/src/search.h)).
- **CCRL → human.** [Source] The Stockfish FAQ says that rating Stockfish against a human scale such as FIDE Elo "has become virtually impossible" ([FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html)). No official mapping from `UCI_Elo` to human ratings exists. The best primary evidence is maintainer discussion in [issue #3635](https://github.com/official-stockfish/Stockfish/issues/3635):
  - vondele: "1500Elo matches maia5 in a direct match quite well, however, for humans it seems clearly stronger." Another participant equates that lichess-blitz 1500 to "1000 elo blitz on chess.com".
  - "`Skill Level=0` is too strong for beginners". Lichess runs a patched Fairy-Stockfish with Skill Level −20..20 to extend the range downward.
  - A Demolito-vs-Stockfish tournament placed Stockfish Skill 0 more than 500 Elo above Demolito level 1, which a beginner "couldn't even beat".
- **Hardware and time dependence.** [Source] Skill Level picks its move at depth 1 + level ([FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html)), so strength depends on time per move, hardware and version. A 2026 study found `UCI_Elo` compressed in practice, e.g. 2400 vs 2600 ≈ 100 Elo apart rather than 200 ([arXiv 2606.13763](https://arxiv.org/pdf/2606.13763)) [Unverified: search snippet only].
- **Who used it for LLMs.** [Source] Acher played gpt-3.5-turbo-instruct against Stockfish 16 Skill Levels, using level→Elo estimates from community discussion, and computed a FIDE-style performance rating: ~1750 ([Acher](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/)). Kaggle Game Arena calibrates its internal Bradley-Terry scale by "matching models against multiple Stockfish skill levels and interpolating against reference CCRL Elo mappings", noting this "is less reliable outside the engine calibration range" ([Game Arena report](https://arxiv.org/html/2609.31473v1)).
- [Inference] For this project Stockfish is valuable as an **analysis** engine, not as a rating opponent. Its floor is well above where an 8B model in Free mode plays.

### Maia (human-like engines, Lichess-trained)
- **Maia-1.** [Source] Nine networks targeting 1100, 1200, …, 1900, trained on Lichess games from Jan 2017-Nov 2019 split into rating bins. Run them with lc0 at `go nodes 1` (no search) ([maia-chess README](https://github.com/CSSLab/maia-chess)). Maia matches human moves up to "over 52%" of the time, versus 35-40% for weakened Stockfish, and "every curve achieves its maximum accuracy at a different human rating" ([Maia blog](https://www.maiachess.com/blog/maia-v1), [paper](https://arxiv.org/abs/2006.01855)).
- **Maia is stronger than its label.** [Source] The README says the models play "the *average* move of a player at that rating", so they are stronger than the nominal rating ([README](https://github.com/CSSLab/maia-chess)). Live Lichess ratings fetched on 2026-10-19 from `lichess.org/api/user/<bot>`:

  | Bot | Target | Blitz | Rapid | Classical |
  |---|---|---|---|---|
  | maia1 | 1100 | 1389 | 1543 | 1685 |
  | maia5 | 1500 | 1498 | 1649 | 1676 |
  | maia9 | 1900 | 1700 | 1793 | 1815 |

  All three have RD 45 and hundreds of thousands of games. [Inference] These are earned ratings in a mixed bot/human pool, so they are a better anchor than the target label. Use the bot's rating for the matching time control, not the model name.
- **Maia-2.** [Source] One model with "skill-aware attention" that conditions on both players' ratings ([arXiv 2409.20553](https://arxiv.org/abs/2409.20553)). Trained on Lichess **Rapid** only, 169M games, with skill bins from "(0,1000]" through "(2000,+∞)". Top-1 move accuracy averages 53.25% ([HTML](https://arxiv.org/html/2409.20553)). `pip install maia2`, Python 3.10-3.12, "runs on CUDA, Apple MPS, or CPU". `inference_each(model, prepared, fen, elo_self, elo_oppo)` returns move probabilities, and there are separate `rapid` and `blitz` checkpoints ([maia2 README](https://github.com/CSSLab/maia2)).
- **Pool caveat.** [Source] ChessArena put Maia-1100 into its LLM Glicko pool and it came out at 2220 (RD 82, 44 games), against a random player at 1524. The paper calls Maia-1100 roughly 1600 on Lichess ([ChessArena](https://arxiv.org/html/2509.24239v4)). [Inference] An unanchored pool of weak players drifts arbitrarily, so a well-known anchor's rating means nothing unless it is *fixed* in the fit.
- [Inference] Maia-1100's lowest skill (~1400-1550 Lichess, ≈ chess.com Rapid 900-1100 by ChessGoals) is still likely far too strong for an 8B model in Free mode. Maia-2 with `elo_self` set to its lowest bin and sampling instead of argmax would be weaker, but no source calibrates Maia-2 *as an opponent* at a given setting. Its strength would have to be measured, e.g. against Dragon levels or the random mover.

### Komodo Dragon low skill levels (chess.com-anchored)
- [Source] LLM Chess uses "Komodo's Dragon 1 engine", saying "skill 1 is around Elo 250, then each subsequent skill level is a 125 boost in Elo based on chess.com games" ([paper](https://arxiv.org/html/2512.01992v1)). The repo README tabulates Level 1 = 250 … Level 7 = 1000 (Elo = 125 × (level + 1)) and describes the engine as "Elo-rated against chess.com" ([README](https://github.com/maxim-saplin/llm_chess), [notes](https://github.com/maxim-saplin/llm_chess/blob/main/docs/notes.md)). The komodochess.com site lists "Dragon 1 Free" and links a `dragon.zip` download ([komodochess.com](https://komodochess.com/)).
- [Source] Results: o3 (low) ≈ 758, the best model, with 3.0% against skill 10. A random agent sits at −122.3, against a stated average chess.com player of 611 ([paper](https://arxiv.org/html/2512.01992v1)).
- [Inference] This is the only anchor I found that is explicitly on the chess.com scale **at the low end** where small LLMs play. Its calibration rests on one benchmark's claim (chess.com's own bots are built on Komodo, which makes it plausible). I did not verify that Dragon 1 runs natively on Apple Silicon macOS.

### Pooled ML / Bayesian Elo (BayesElo, Ordo)
- **BayesElo.** [Source] Uses a prior that pulls ratings together and accounts for colour. "A high rating difference has to be deserved": 10-0 gives a smaller gap than naive formulas. It estimates confidence intervals "by inversing the Hessian of the log-likelihood" and has a `los` (likelihood of superiority) matrix. `offset 2800 Fruit` shifts the scale so that Fruit is 2800 ([BayesElo](https://www.remi-coulom.fr/Bayesian-Elo/)). DeepMind used BayesElo for its internal tournament, anchored to the Lichess-vs-bots Elo of its 270M model ([Ruoss et al.](https://arxiv.org/html/2402.04494)).
- **Ordo.** [Source] Rates "considering all results at once". `-A <player>` fixes one anchor. `-m FILE` sets multiple fixed anchors. **`-y FILE` sets "loose anchors: file contains rows of "Player",Rating,Uncertainty"**. `-W` fits White advantage. `-s NUM` runs simulations to get errors ("a minimum reasonable number … is about -s 100") ([main.c](https://github.com/michiguel/Ordo/blob/master/main.c), [manual.tex](https://github.com/michiguel/Ordo/blob/master/manual.tex)).
- [Inference] Ordo's loose anchors fit this project well: a human opponent can be entered at their chess.com Rapid rating with uncertainty = their RD (or ~100 if unknown), Dragon levels at 125(ℓ+1) ± ~100, and Maia bots at their Lichess rating converted to chess.com ± the ChessGoals spread. Ordo reads PGN, which this project already writes. A ~50-line scipy MLE with Gaussian priors on anchors does the same in pure Python.

### Glicko-2 from a provisional start
- [Source] Glicko-2 starts an unrated player at rating 1500, RD 350, volatility 0.06. It "works best when the number of games in a rating period is moderate to large, say an average of at least 10-15 games per player". A 95% interval is rating ± 2·RD ([Glickman, glicko2.pdf](http://www.glicko.net/glicko/glicko2.pdf)). Lichess starts at "1500 ± 1000" and marks ratings provisional while "the Glicko-2 deviation is greater than 110" ([lichess FAQ](https://lichess.org/faq#ratings)). chess.com "uses the Glicko rating system" with RD, and its help page states no starting value ([chess.com help](https://support.chess.com/en/articles/8566476-how-do-ratings-work-on-chess-com)). Signup-level starting ratings (400/800/1200/…) appear only in forum posts [Unverified].
- [Source] ChessArena runs Glicko for LLMs (r=1500, RD=350, RD floor 50) and shows players only once RD ≤ 100, "typically" about 30 games ([ChessArena](https://arxiv.org/html/2509.24239v4)).
- [Inference] Glicko-2 is built for an ongoing stream of games from a player whose strength changes. A fixed **Player configuration** does not change strength, and the games are already finished. A batch MLE/Bayesian fit uses the same information without depending on game order, so Glicko-2 adds nothing here except imitating chess.com's display. It is useful only if you want a "live" rating that updates after each game in the UI.

### Mixing in human games and LLM faceoff games
- **Humans of known rating.** [Inference] Treat each human as a player in the pool with a loose anchor at their chess.com rating for the matching time control (Rapid vs Blitz differ by hundreds of points at the low end, see §3). The project's game logs do not record the human's rating today, so that would need a new `game_start` field. A human who plays many games against several configurations can also *become* an anchor whose rating the fit refines.
- **LLM vs LLM faceoffs.** [Inference] These add information about *differences* between configurations, but they cannot set the absolute level. If every faceoff participant only plays other LLMs, the pool is disconnected from the anchors and its absolute position is arbitrary, as in Game Arena's "lowest-rated model = 0" ([report](https://arxiv.org/html/2609.31473v1)) or ChessArena's Maia-1100 at 2220. At least one configuration in each connected group needs anchored games. Ordo has connectivity-group code (`groups.c`), but I did not check how it reports a disconnected pool, so the measurement engine should check connectivity itself.
- **Pool mismatch.** [Source] DeepMind's 270M model rated 2299 against Lichess bots and 2895 against humans. Bot ratings are "dominated by playing against other bots", and the pools are miscalibrated against each other ([Ruoss et al.](https://arxiv.org/html/2402.04494)). [Inference] Engine anchors and human anchors may disagree by hundreds of points for a player with a non-human error profile, and LLMs are such players. Fit them in one pool but also report the human-only and engine-only estimates separately as a sanity check.

## 2. Move-quality-based estimation (no calibrated opponents)

All of these analyse the LLM's own moves with an engine (python-chess `chess.engine.SimpleEngine` + Stockfish; `analyse(..., multipv=k)` returns the top k lines ([python-chess docs](https://python-chess.readthedocs.io/en/latest/engine.html))).

### Average centipawn loss (ACPL) → Elo
- [Source] In 1,846 Lichess games, ACPL explained R² = 0.05 (White) and 0.07 (Black) of rating variance, with slopes of −346 and −442 rating points per unit of ACPL ([Coulombe](https://sites.google.com/view/patrick-coulombe-phd/chess-analytics/predicting-rating-from-centipawn-loss)). [Inference] That is a typical per-game error of about ±230 rating points.
- [Source] Anderson, Kleinberg & Mullainathan found that position difficulty predicts errors much better than player skill or time ([KDD 2016, arXiv 1606.04956](https://arxiv.org/abs/1606.04956)). ACPL partly measures which positions a player reached, not just how well they played.
- [Inference] No ACPL→Elo regression I found is fitted on chess.com players below ~800, and none on non-human players.

### Accuracy: lichess formula, chess.com CAPS2, chess.com "Game Rating"
- **Lichess.** [Source] Win% = 50 + 50·(2/(1+exp(−0.00368208·cp)) − 1). Move accuracy = 103.1668·exp(−0.04354·(Win%before − Win%after)) − 3.1669. Game accuracy is the mean of a volatility-weighted mean and a harmonic mean over sliding windows. Lichess on rating: "there is some correlation … it is not straightforward". Lower-rated players resign less, which drags out lopsided endgames and *raises* accuracy ([lichess accuracy](https://lichess.org/page/accuracy)). python-chess implements the lichess win model as `Score.wdl(model="lichess")` ([docs](https://python-chess.readthedocs.io/en/latest/engine.html)).
- **chess.com CAPS2.** [Source] Accuracy "is now powered by CAPS2", a revision of CAPS, with most scores between about 50 and 95. No formula is published ([chess.com help](https://support.chess.com/en/articles/8708970-how-is-accuracy-in-analysis-determined)).
- **chess.com Game Rating (Game Review's estimated rating).** [Source] It compares move quality "to what's expected from a player at the same rating level". It averages out near the actual rating over time but "can fluctuate significantly" in single games, and is harder to interpret in bot games with large rating gaps. No formula is published ([chess.com help](https://support.chess.com/en/articles/10773754-how-is-game-rating-calculated-in-game-review)).
- [Inference] Game Rating is the only number that is natively on the chess.com scale, but it is a black box, needs manual upload of each PGN, and its inputs include the listed players' ratings. Useful as an anecdotal cross-check on a few games, not as the measurement engine.

### Regan's Intrinsic Performance Rating (IPR)
- [Source] Models each move choice as a function of engine evaluations with two parameters, sensitivity *s* and consistency *c*, fitted to games of players at rating "mileposts" ([Regan & Haworth 2011](https://cse.buffalo.edu/~regan/papers/pdf/ReHa11c.pdf)). The fitted parameters project an expected average error, then IPR = 3571 − 15413·AE_e, with a 2σ interval, and an "actual" interval using 1.4σ ([Intrinsic Ratings Compendium](https://cse.buffalo.edu/~regan/papers/pdf/Reg12IPRs.pdf)).
- **Sample size.** [Source] The compendium shows Mongredien's 133 analysed moves giving IPR 1194 with a 2σ range of 557-1831, and Morphy's 368 moves 2289 (2077-2502) ([Compendium](https://cse.buffalo.edu/~regan/papers/pdf/Reg12IPRs.pdf)). [Inference] That is several hundred analysed moves for ±200, i.e. roughly 10-20 games.
- **Range.** [Source] Originally fitted from 1600 to 2700 FIDE. Regan's 2024 slides describe training sets of players "within 10 Elo of a marker 1025, 1050, …, 2825" ([Regan 2024](https://cse.buffalo.edu/~regan/Talks/CogSciOct2024np.pdf)).
- [Inference] The most principled move-quality method and it comes with error bars, but the fitted model and analysis pipeline are not published as a usable package, it is on the FIDE (classical) scale, and it extrapolates below ~1000.

### Maia move-matching likelihood
- [Inference] Idea: score each LLM move under Maia-2 at each candidate rating (`elo_self` = r, `elo_oppo` = opponent's estimate), sum log-probabilities over the game, and take the r with highest likelihood (or a posterior over r). This follows from Maia's property that each rating's model predicts its own rating's moves best ([Maia blog](https://www.maiachess.com/blog/maia-v1)). It runs locally on MPS.
- [Source] No source I found validates Maia likelihood as a rating *estimator*. The Maia-2 paper uses rating as an input, not an output ([arXiv 2409.20553](https://arxiv.org/html/2409.20553)).
- [Inference] Before trusting it, validate on human games of known rating (your own or a Lichess database sample) and check the error. Expect it to compress at the low end: Maia-2's lowest bin is (0, 1000] Lichess Rapid, which is roughly chess.com Rapid ≤ 500.

### Pitfalls specific to very weak play and LLMs
- [Source] Lichess Win% saturates in lost positions, so moves in already-lost positions cost little "accuracy", and lower-rated players' long lost endgames raise accuracy ([lichess](https://lichess.org/page/accuracy)). Regan skips turns 1-8, repetitions, and positions beyond 3 pawns' advantage ([ReHa11](https://cse.buffalo.edu/~regan/papers/pdf/ReHa11c.pdf)). With an 8B model, a large share of moves may be in such positions.
- [Inference] LLM errors are not human errors. Opening moves are likely memorised (high accuracy), then the model collapses into board-state hallucinations. Regressions fitted on humans assume a human-shaped error distribution, so the same ACPL can mean different results.
- [Inference] An illegal move has no centipawn value, and a forfeit ends the game. Move-quality methods only see the legal moves played, which **overrates** Free-mode configurations that forfeit often. They must be paired with the result.

## 3. Rating-scale conversions

- **chess.com ↔ Lichess ↔ FIDE.** [Source] ChessGoals (updated July 2026; surveys of active players, e.g. chess.com Rapid N=10,156, Lichess Rapid N=1,066; Lichess players with RD < 150) ([ChessGoals](https://www.chessgoals.com/rating-comparison/)):

  | chess.com Blitz | chess.com Rapid (±115) | Lichess Blitz (±70) | Lichess Rapid (±90) | FIDE (±75) |
  |---|---|---|---|---|
  | 500 | 815 | 1090 | 1290 | – |
  | 800 | 1085 | 1290 | 1490 | – |
  | 1000 | 1255 | 1425 | 1615 | – |
  | 1200 | 1420 | 1555 | 1740 | 1670 |
  | 1500 | 1655 | 1755 | 1905 | 1740 |

  The ± values are windows for "roughly 50% of players". There are no rows below chess.com Blitz 500 and no FIDE data below about 1550. Lichess runs much higher at the low end (+490 at chess.com Blitz 800).
- **CCRL → human.** [Source] No official mapping. "Virtually impossible" per Stockfish ([FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html)). A maintainer's anecdote: Lichess-blitz-calibrated 1500 ≈ chess.com blitz 1000, and engines at a given label play "clearly stronger" against humans than the label ([issue #3635](https://github.com/official-stockfish/Stockfish/issues/3635)).
- **Time control.** [Inference] chess.com Rapid and Blitz differ by 200-300 points at the low end, so pick one target scale. The project's LLM turns are untimed, which is closest to Rapid/Daily. Maia-2 is Rapid-trained, and Dragon's chess.com calibration doesn't state a time control.
- [Inference] Each conversion adds roughly ±100 of uncertainty, so a converted rating should carry that in its interval.

## 4. Prior art: how others rated LLMs at chess

| Source | Opponents | Rating method | Anchor | Illegal-move handling | Link |
|---|---|---|---|---|---|
| Acher 2023 | Stockfish 16 Skill Levels (~1300-2000 est.) | FIDE performance rating (avg opp + dp table) | Community Skill→Elo estimates | Two numbers: legal games only 1743, illegal = loss 1696 | [blog](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/) |
| Dynomight 2024 | Stockfish lowest level | No Elo; score by final centipawn eval (±1500 for win/loss) | none | Open models: grammar-constrained to legal moves. OpenAI: 10 tries then a random legal move | [post](https://dynomight.net/chess/) |
| Dynomight 2024 (follow-up) | gpt-3.5-turbo-instruct | Relative score → ~1540 | Assumes 3.5-instruct ≈ 1750 | – | [post](https://dynomight.net/more-chess/) |
| Ruoss et al. (DeepMind) 2024 | Lichess humans and bots, internal engines | Lichess Glicko-2, plus BayesElo for the tournament | Lichess; tournament anchored to the 270M model's bot Elo | n/a (trained model) | [arXiv 2402.04494](https://arxiv.org/html/2402.04494) |
| LLM Chess (Saplin et al.) 2025 | Random mover, Komodo Dragon skill 1-10 | 1-D MLE, Fisher CI, +35 Black correction | chess.com via Dragon = 125(ℓ+1) | Instruction failures and timeouts count as losses vs Dragon | [arXiv 2512.01992](https://arxiv.org/html/2512.01992v1) |
| ChessArena 2025 | LLMs, random player, Maia-1100 | Glicko (1500/350, RD floor 50) | none (Maia-1100 came out at 2220) | Forfeit after 5 failed retries | [arXiv 2509.24239](https://arxiv.org/html/2509.24239v4) |
| Kaggle Game Arena 2025-26 | All-play-all, 40 games per pair | Bradley-Terry, bootstrap CI | Lowest = 0. External calibration via Stockfish levels + CCRL | Retries then loss | [report](https://arxiv.org/html/2609.31473v1) |
| Kaggle Game Arena exhibition 2025 | – | "Estimated human rating" o3 1686, Grok 1395 [Unverified: news report] | Stockfish levels regressed on "Stockfish's estimated human Elos", 500 bootstraps [Unverified: Kaggle page is JS-rendered] | – | [Chessdom](https://www.chessdom.com/o3-openai-wins-kaggle-game-arena-ai-exhibition-chess/) |
| ChessGPT (Feng et al.) 2023 | – | No playing Elo. Elo only as a conditioning input | – | – | [arXiv 2306.09200](https://arxiv.org/html/2306.09200v2) |

- [Inference] The pattern: **fixed-rated engine anchors + MLE/Bradley-Terry + bootstrap or Fisher CI**. Only LLM Chess anchors directly to chess.com, and only via Dragon. Nobody publishes a validated human-scale rating for 8B models: they score 0% in LLM Chess even with a legal-move tool, so they were never placed on its Elo scale.

## 5. Illegal moves, forfeits and Enforced decoding

- [Source] Every benchmark above scores a forfeit (retries exhausted or no answer) as a **loss**: LLM Chess, ChessArena, Game Arena. Acher reports both conventions, and the gap was 1743 vs 1696 for a model with illegal moves in 16% of games ([Acher](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/)).
- [Inference] Recommendations for this project:
  - **A forfeit is a loss** in the rating, because a human opponent would win that game. Excluding forfeited games would rate a different player from the one that was actually tested.
  - **Illegal moves that a retry recovers** affect the rating only through the result. They are already measured separately by the Legal-move streak and the illegal-move counts.
  - **Each Player configuration is its own player in the pool.** Free, Listed, Blind enforced and Listed enforced are different players (as `CONTEXT.md` already requires). The Enforced decoding ratings measure chess skill given guaranteed legality. The Free ratings measure chess skill and rule-following together. Both are valid, but they answer different questions and should not be pooled into one number.
  - **Enforced decoding does not need a special case in the rating.** Unlike the Legal-move streak (ADR 0003), a rating is not true by construction under Enforced decoding: the result still depends on the moves. The forfeits that remain (timeouts, failed calls) still count as losses.
  - **Report the forfeit rate next to the rating**, so a low Free-mode rating can be read as "loses on illegal moves" vs "plays badly".
  - Move-quality diagnostics (accuracy, Maia likelihood) should cover only legal moves and say so.

## Recommendation for this project

Constraints: a handful to dozens of games per Player configuration, local on a Mac, a chess.com-comparable number with an honest interval.

1. **Primary method: one pooled Bayesian/ML Elo fit with loose anchors.**
   - Model: logistic Elo with a White-advantage term, a Gaussian prior on every anchor (rating ± uncertainty), and a weak prior on LLM configurations. Ordo (`-y` loose anchors, `-W`, `-s 1000`) does this from the project's PGNs. A scipy MLE/MAP over the JSONL logs is a small, testable alternative that also yields a posterior.
   - Report the posterior median and 95% interval on the chess.com **Rapid** scale. If a configuration has lost every game, report only an upper bound ("< X, 95%").
2. **Anchors, cheapest first, chosen to sit near the LLM's level** (the 35-65% band is the informative one):
   - **Random legal mover.** Free, and calibrate it once against Dragon or Maia. LLM Chess puts it at about −122 on its chess.com-anchored scale. It is the only anchor likely to lose to an 8B model.
   - **Komodo Dragon 1, skill 1-4** (≈ chess.com 250-625 per LLM Chess). Check that it runs on macOS first.
   - **Humans** (you, friends) entered at their chess.com Rapid rating ± RD. Add the human's rating to the game log.
   - **Maia-2 at a low `elo_self`, sampled** (`pip install maia2`, MPS), measured against the other anchors before use. Maia-1/Lichess bots are likely too strong.
   - Not Stockfish `UCI_Elo`: its floor (CCRL 1320) is far above the target range and not on a human scale.
3. **LLM faceoff games go into the same pool.** They tighten differences between configurations but need at least one anchored configuration per connected group.
4. **Secondary diagnostics, clearly labeled "not a rating":** lichess-formula accuracy and ACPL over legal moves (python-chess + Stockfish 19), and optionally a Maia-2 likelihood rating estimate once it has been validated against human games of known rating.
5. **Expectations.** [Inference] With ~20 anchored games at a balanced score, expect ±150 at best, plus ~100 for anchor and scale-conversion uncertainty. Free-mode 8B configurations will likely end up as upper bounds near or below the random mover. Enforced-decoding configurations are the ones most likely to get a finite, informative number.
