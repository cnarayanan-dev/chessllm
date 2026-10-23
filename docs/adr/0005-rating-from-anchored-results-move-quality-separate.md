# The Rating comes only from results against Dragon Anchors; the Move-quality estimate is a separate number

We want a chess.com-comparable Elo for each Player configuration from a handful to a few dozen games. The Rating is fitted only from wins, draws and losses (a Forfeit is a loss) in one maximum-likelihood pool over all games, with Komodo Dragon 1 at Skill 1-7 as Anchors fixed at 125 × (skill + 1) on the chess.com scale (±100), Threads = 1. Anchor matches run unattended as an adaptive ladder (step up a level after scoring over 50%, 30 games per batch, colours alternating), and LLM faceoff games join the pool to place configurations relative to each other. Play LLM games do not count: we will never have enough humans with known ratings to carry the scale. Next to the Rating, and never blended into it, stands the Move-quality estimate: the human rating whose players would most likely have made the same moves (Maia-2 likelihood), per game and per Player configuration. Research is in `docs/research/elo-estimation.md`.

## Considered Options

- **Stockfish `UCI_Elo` / Skill Level as Anchors**: everywhere and easy, but calibrated engine-vs-engine on CCRL from 1320 up. Its own FAQ calls a human mapping "virtually impossible", and 8B LLMs would score 0% against its weakest level.
- **Maia bots as Anchors**: human-like, but Maia-1100 is still far too strong, and Maia-2 at a low rating has never been measured as an opponent.
- **A random legal mover as the floor** (about −122): deferred, not rejected. It is the only Anchor weak LLMs can beat, and is added if the bottom of the leaderboard is all "< X". Added by ADR 0011, which ranks models under Free.
- **Move quality as the Rating** (average centipawn loss → Elo, accuracy, chess.com's Game Rating): works on every game, but per-game centipawn loss explained only 5-7% of rating variance in one sample, the regressions are fitted far above where 8B models play, and forfeits are invisible to it.
- **One blended number**: a single headline, but no source says how to weight the two, and it would no longer mean anything on chess.com.
- **Glicko-style game-by-game updates** (as chess.com does): a Player configuration does not change over time, so order-dependence would only add noise.

## Consequences

- Configurations that lose every anchored game have no finite Rating, only an upper bound ("< X"), and a configuration with no path to an Anchor has none at all.
- Raw W · D · L are not comparable across configurations under the adaptive ladder, since they faced different Anchors; only the Rating is.
- The Move-quality estimate is validated on a Lichess database sample before it is trusted (about ±250 per game, ±100 pooled over 20 games, no bias at ≤600) and shown as unvalidated otherwise. It is converted from Lichess to chess.com, with extra uncertainty below the ChessGoals tables' floor (about chess.com 815).
- Analysis (Maia-2, Stockfish) is written to a separate file per game, naming the versions used, and never into the game log: logs stay the raw record (ADR 0004), and any analysis can be redone.
- Unattended games (Anchor match, LLM faceoff) end in a draw at the Move cap of 150 moves per side.
- The Dragon macOS build is x86_64 only and runs under Rosetta 2. komodochess.com's TLS certificate had expired when it was downloaded, and no checksum is published.
