# System 1 models choose from the legal moves only, drawing their move from their probabilities

**System 1 models** (decision models such as d3 or StartLux, see `docs/research/system-1-models.md`) play as a second kind of **Model player** next to LLMs. They generate no text: given a state and a question with options, they give a probability for every option in one forward pass. Their options are always exactly the legal moves, in SAN and in random order, so they can never propose an **Illegal move**, and each **Turn** is a single attempt: **LLM constraints**, **Retries**, **Retry feedback** and the **Legal-move streak** don't apply to them. Their move is drawn at random from their probabilities at a **Choice temperature** (1 by default, part of the **Player configuration**), never simply the top option, because these models are deterministic: two that always played their top move would play the same game every time, and the **Rating** would count one game repeated as many independent results. They play with a **Prompt template** (the System prompt is the question, the Turn template the state) and are ranked in the same **Ranking** as the LLMs, under a **Reference configuration** narrowed to the settings that apply to them: **Standard rules**, their default Prompt template and Choice temperature 1 (ADR 0011).

## Considered Options

- **Illegal moves among the options** (pseudo-legal moves that ignore check, moves ignoring blockers, or legal moves plus random decoys), so a System 1 model's rule-following could be compared with an LLM's under **Free**. Rejected for simplicity: it would need a rule for which illegal moves are offered, recorded in the Player configuration, and the share of illegal options would vary by position. The runtimes take up to 255 options, so legal moves alone (at most 218) always fit.
- **Always the top option**, with variety from a list of starting openings: needs a new concept and an opening list, and still gives one game per opening and colour.
- **Separate Modes or a separate Ranking for System 1 models**: the Ratings share one chess.com scale through the Anchors anyway, so splitting would only hide the comparison with LLMs.

## Consequences

- A System 1 model's illegal-move numbers are not comparable with an LLM's: it has none by construction. Comparisons with LLMs are by Rating and **Move-quality estimate** only.
- Option order changes these models' answers, so the game log records every turn's options in the order shown, with each one's probability and the move drawn. This also lets the Turn panel show a System 1 turn later without replaying it.
- Choice temperature 0 (always the top move) is possible for experiments, but such games are not independent samples and should not be read as many results.
- Adding illegal options later is a new Player configuration setting with its own ADR; games played under this ADR remain legal-options-only.
