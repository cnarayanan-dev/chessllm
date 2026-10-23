# A side's prompt is a saved Prompt template, fixed for the game; probes are kept apart from the game's record

The human writes the prompts: a **System prompt** and a **Turn template** with placeholders, saved together as a **Prompt template** in the **Prompt library**, with the **Answer format** added by the benchmark. A side plays the whole game with the Prompt template chosen when the game starts, and the game log records its full text, not a file name or an ID, so a game always says exactly what its LLMs were told even after the library changes. A saved Prompt template never changes: an edit is saved as a new one with a new ID. To see what another prompt would do in a game already played, the human asks a **Probe**: one question about a past turn's position, outside the game, recorded in its own log next to the game's, never in the game log.

## Considered Options

- **Switching a side's prompt mid-game**: a better prompt found during a game could be played at once, but one game would then be played under two prompts, and neither could be credited with its result.
- **Recording the prompt's file name or ID only**, as `prompt_file` did: smaller logs, but editing a file in place silently pooled games played under different texts into one Rating.
- **Probes in the game log**: one file per game, but every reader of the log (the Rating, the analysis, the replay) would have to skip records that were never part of the game.
- **Probes kept only in the browser**: nothing to store, but the finding they are for, which prompt makes a model play legally, needs probes added up across many games.

## Consequences

- The prompt files are no longer re-read every turn: a changed prompt is played from the next game.
- Grouping the leaderboard by prompt comes later; until then, games under different prompts still pool into one Rating, but their logs already hold the text to separate them by.
- A probe never runs alongside a real turn: asking for one in a game whose LLMs move on their own **Pauses** it after the turn running, so **Time used** stays the game's own.
- The described position (`position: described`) is no longer a setting: it is the `$description` placeholder, chosen by the Turn template. The **LLM constraints** still decide the Legal-move list, and a template must agree with them.
- The default Prompt templates live in editable files, so a default's ID carries a version taken from its text (`default@1a2b3c4d`, `described-listed@…`): editing a default file makes a new ID, as saving an edit does, and an ID always means one text.
