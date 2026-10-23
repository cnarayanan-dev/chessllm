# Models are ranked under one Reference configuration, with a random legal mover as the lowest Anchor

The question the analytics page has to answer first is how good a model is, not how good each of its Player configurations is. A model's overall number is its **Rating** under one **Reference configuration**, the same settings for every model: thinking off, **Free**, **Standard rules**, 5 attempts with *explained* **Retry feedback**, *fresh* **Turn memory**, no **Tools**, the default **Prompt template** and the model's own sampling. These are what a model can do unaided and what most games were already played under (about 140 of 162 logged LLM sides had thinking off, and Free with Standard rules was the most played), and they are the benchmark's command-line defaults, so a default Anchor match batch plays under them. The **Ranking** of models under it replaces the leaderboard of every Player configuration. Under Free a Forfeit is a loss, so small models would lose every game to Dragon Skill 1 and all read "< 250"; the random legal mover that ADR 0005 deferred is added now as an Anchor at −122 (LLM Chess's calibration), so the bottom of the Ranking has something to score against. How each other setting moves a model's Rating, its **Setting effect**, is a later view, measured from this reference.

## Considered Options

- **Pooled over every configuration**: one Rating from all of a model's games. It depends on which settings each model happened to be tested under, so a model run mostly under Free looks worse than one run mostly under Listed enforced.
- **Best configuration**: a model's highest-rated Player configuration. It favours models tried under more settings, and hides what it took.
- **Thinking as the model ships it** (on for models that can think): measures thinking models as they are meant to be used, but makes the reference differ per model, and few games were played with thinking on.
- **Listed enforced as the reference**: every game is played out, so weak models are told apart by their moves; rejected because the Ranking should measure whether a model can play chess unaided, rule-following included. The random mover is what keeps Free usable at the bottom.

## Consequences

- A model has no place in the Ranking until it has games under the Reference configuration with a path to an Anchor; the games already logged are mostly LLM faceoffs under other settings and do not count.
- The Ranking can be narrowed by **Mode**, and then every number comes from those games alone: LLM faceoffs alone reach no Anchor and give no Rating, and Play LLM games never give one (ADR 0005).
- W · D · L in the Ranking count only games under the Reference configuration, and there is no score column: under the adaptive ladder, models face different Anchors (ADR 0005).
- Changing the Reference configuration later moves every model out of the Ranking until it is replayed under the new one; it is changed only by a new ADR.
- A Setting effect's uncertainty must come from the joint fit, not from adding the two Ratings' intervals: two configurations of one model share the Anchors' uncertainty, which largely cancels in their difference.
