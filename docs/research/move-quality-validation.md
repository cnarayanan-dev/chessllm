# Validation of the Move-quality estimate on Lichess Rapid games

Written by `uv run python -m scripts.validate_move_quality` (#48); rerunning it on the same sample gives this report again. Method and pass mark are in ADR 0005 and the script's docstring.

**Failed**: the leaderboard shows the Move-quality estimate as unvalidated for this move model and grid.

Why it failed:

- Lichess 800-1000: per-game error ±437 exceeds ±250
- Lichess 800-1000: pooled error ±202 exceeds ±100
- Lichess 800-1000 (chess.com ≤ 600): bias +308 exceeds ±100
- Lichess 1000-1200: per-game error ±380 exceeds ±250
- Lichess 1000-1200 (chess.com ≤ 600): bias +155 exceeds ±100
- Lichess 1200-1400: per-game error ±389 exceeds ±250
- Lichess 1400-1600: per-game error ±373 exceeds ±250
- Lichess 1400-1600: pooled error ±133 exceeds ±100
- Lichess 1600-1800: per-game error ±409 exceeds ±250
- Lichess 1600-1800: pooled error ±203 exceeds ±100
- Lichess 1800-2000: per-game error ±382 exceeds ±250
- Lichess 1800-2000: pooled error ±228 exceeds ±100

## Sample

- Source: https://database.lichess.org/standard/lichess_db_standard_rated_2025-01.pgn.zst (the start of the file only)
- Games read from its start until every band had 50 games: 10566
- Sample: `docs/research/move-quality-validation-sample.pgn`, SHA-256 `d06b96dd2b880448a14704739486aa039ae6a1ada3489fedecfb9979c06d60b7`
- Selection: rated Rapid games (Event "Rated Rapid ...", tournaments included) between two humans (no BOT title), ended normally or on time, at least 10 moves a side, both players in the same band; the first games of each band in file order. Each player is a player-game, rated at their rating at the start of the game.
- Move model: maia2 0.11.0, rapid model, opponent rated as the player; grid (Lichess Rapid) 1000-2000: 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000

## Bands

Bands are on the Lichess Rapid scale, the database's. Errors are on the chess.com Rapid scale, the pass mark's: estimate and rating each converted with `chessllm.rating_scales` (ChessGoals' table, extended along its lowest segment below Lichess 1290, chess.com 815, where the conversion is an extrapolation).

| Lichess Rapid | chess.com Rapid | Bias held to ≤ 600 |
| --- | --- | --- |
| 800-1000 | 154-424 | yes |
| 1000-1200 | 424-694 | yes |
| 1200-1400 | 694-964 | no |
| 1400-1600 | 964-1235 | no |
| 1600-1800 | 1235-1505 | no |
| 1800-2000 | 1505-1790 | no |

## Results

Pass mark: per-game error ±250, pooled error over 20 player-games ±100 (root mean square, chess.com), and a bias within ±100 in the bands at or below chess.com 600. Bias is the mean error (estimate less rating); pooled errors pool the moves of consecutive player-games of a band into one estimate, against their mean rating. At the grid's floor or ceiling the grid point is taken as the estimate (the leaderboard shows only a bound there).

| Lichess Rapid | Player-games | Bias | Per-game error | Pooled error (pools) | Bias, Lichess | Per-game error, Lichess | At grid floor | At grid ceiling | Meets the pass mark |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 800-1000 | 100 | +308 | ±437 | ±202 (5) | +228 | ±323 | 47% | 1% | no |
| 1000-1200 | 100 | +155 | ±380 | ±25 (5) | +114 | ±280 | 22% | 4% | no |
| 1200-1400 | 100 | +73 | ±389 | ±59 (5) | +53 | ±286 | 10% | 6% | no |
| 1400-1600 | 100 | -58 | ±373 | ±133 (5) | -44 | ±275 | 4% | 4% | no |
| 1600-1800 | 100 | -90 | ±409 | ±203 (5) | -70 | ±300 | 2% | 18% | no |
| 1800-2000 | 100 | -178 | ±382 | ±228 (5) | -131 | ±278 | 3% | 27% | no |

## Reading it

- The grid's lowest rating, Lichess 1000, stands for every player below the next one, so the estimator cannot say a player is weaker than about chess.com 424. Players below it are estimated at the floor at best, which shows as a positive bias in the bands under it; the share at the grid floor says how often that happened.
- Below Lichess 1290 both the estimate and the rating go through the extrapolated conversion, so the chess.com errors there are 1.35 times the Lichess ones and only as good as the extrapolation.
- Bias by band, lowest to highest: +308, +155, +73, -58, -90, -178. Falling from positive to negative, it means the estimates are pulled towards the middle of the grid: weak players come out too strong and strong players too weak.
