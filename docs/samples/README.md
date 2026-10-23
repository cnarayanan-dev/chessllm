# Sample games

Four scripted games, written by `uv run python -m scripts.sample_logs` (`scripts/sample_logs.py`), so you can read what
the app writes and see in `git diff` exactly what a change did to it. After each refactor step, run the command and
check the diff by hand: a step that changes no behaviour leaves it empty. No test compares these files automatically;
when a change is meant to alter the log or the API, the diff shows how, and the new files are committed with it.

The LLMs and the Anchor are the scripted fakes of the tests (`tests/fakes.py`), so no Ollama or engine is needed. Every
game is played at the sampling `temperature = 0.7` and `top_k = 40`. Game ids, timestamps, latencies and the repo's
path are replaced with fixed values, and the moves are timed by a fake clock, each scripted move taking a fixed time, so
running the command twice changes nothing.

| Sample game | Shows |
|---|---|
| `play-llm-standard`: Play LLM, Standard rules | a human move, a Notation slip, an illegal move then a Retry, the Reasoning, checkmate; then two Probes of the last turn |
| `llm-faceoff-chaos`: LLM faceoff, Chaos rules | a chaos move, a Spawn, a Retry after badly formed notation, King capture, `rules` and `chaos_plies`; White Listed; each ply's Evaluation, by a material count standing in for Stockfish |
| `anchor-match-standard`: Anchor match, Standard rules (scripted Anchor) | Anchor moves, an ambiguous, an illegal and a badly formed move, a Forfeit after the maximum attempts |
| `llm-faceoff-thinking-budget`: LLM faceoff with a Thinking budget (benchmark sides) | Thinking, a Thinking level, a cut-off forced answer and its Retry, token counts, a timeout |

- `game-logs/`: each game's JSON Lines log and PGN, as the game wrote them, and the Play LLM game's probe log
  (`play-llm-standard.probes.ndjson`), written next to its log.
- `api/`: the API's responses, formatted for reading: the game state after each request of the Play LLM and Chaos
  games (numbered in order), the Play LLM game's Probes and their list, the models (`models.json`, with one model Ollama can't show), the Prompt library's defaults
  (`prompt-templates.json`), the new game's defaults,
  the Ranking of these four games (`ranking.json`; none of them is under the Reference configuration), and the requests the API refuses with their status (`errors.json`). The Anchor
  match and the Thinking budget game are played as the benchmark's commands play them, which no route serves, so they
  have logs only.
