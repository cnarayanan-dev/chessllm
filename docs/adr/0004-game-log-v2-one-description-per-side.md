# Game log version 2: each side describes who played it, with the settings it actually played under

With the LLM faceoff a game can have two LLMs, and the version 1 log only had room for one (`model`, `llm_color`, `thinking`, … at the top level, with the human implied as "the other colour"). In version 2, `game_start` carries `log_version: 2`, the `mode` (`play_llm` or `llm_faceoff`), and a `white` and a `black` object: `{"player": "human"}` or `{"player": "llm", "model", "thinking", "llm_constraints", "retry_feedback"}`. Each LLM side holds its *effective* settings, written out in full even when they were shared, so analysis reads `black.thinking` directly and never has to work out whether a setting was shared or customized. Every `llm_attempt` and `human_move` carries its `color`, and `game_end` puts the stats under `stats.white` and `stats.black`. Logs already written stay version 1 and are not migrated: they are the raw record of what happened, and rewriting them would risk changing the evidence the benchmark rests on.

## Considered Options

- **Shared settings once, plus per-side overrides** (mirroring the settings modal): smaller, but every reader has to merge the two to find out what a side played with, and a missing override would read the same as "shared".
- **Keep the version 1 fields and add `opponent_model` and friends**: no new version, but it makes White and Black unequal, and the human's side would still be implied.
- **Migrate the old logs to version 2**: one format for analysis, but a one-off script edits the only record of past games, and version 1's `"mode": "free"` (which meant LLM constraints) would have to be rewritten correctly by inference.

## Consequences

- Analysis code reads both versions: no `log_version` means version 1, with `model`/`llm_color` mapped onto a side and the human on the other. Version 1's `mode` is the LLM constraints, never the Mode.
- Whether the user customized a setting is not recorded, only what each side played with. Two games with the same effective settings are the same experiment however they were set up.
- A human's side has `null` stats, which is different from ADR 0003's `null` metrics under Enforced decoding: there the side is an LLM and the metric is not applicable, here there is no LLM at all.
- The log and PGN filenames name both sides, White first: `<start>_<white>_vs_<black>.jsonl`, with `human` for a human side.
