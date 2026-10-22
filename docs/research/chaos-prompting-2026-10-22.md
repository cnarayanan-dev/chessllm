# Prompting after chaos moves: how to get a legal move from a history that broke the rules, 2026-10-22

Research date: 2026-10-22. Scope: how the per-turn prompt (`chessllm/prompts/system.txt`, `system_listed.txt`, `turn_messages()` in `chessllm/prompt.py`) should be worded under **Chaos rules**, so that a small local model (llama3:8b, gemma3:12b, qwen3.5:9b, gemma4:26b) plays a legal move in the current position after **Chaos moves** have been played. The prompt must not claim the past moves were legal. It has to say plainly that the **Move record** may contain rule-breaking moves and that the FEN is the actual position. No code or prompt files were changed. The repo numbers below come from a throwaway script over the 18 Chaos-rules logs in `games/`.

This note reuses, without repeating them, [`llm-chess-limitations.md`](llm-chess-limitations.md) (A1 board tracking, A2 legality, C2/C3 history), [`llm-chess-notation.md`](llm-chess-notation.md) (FEN vs PGN), [`described-position-2026-10-20.md`](described-position-2026-10-20.md) (the piece list), [`forfeit-solutions-brainstorm.md`](forfeit-solutions-brainstorm.md) (ideas 1-4, "stale board" numbers), [`illegal-move-execution.md`](illegal-move-execution.md) and ADR 0006.

Labels:
- **[Source]**: stated in the linked primary source.
- **[Repo]**: read from this repo's code, docs or game logs.
- **[Inference]**: my reading or extrapolation.

## TL;DR

- **Today's chaos prompt contradicts itself, twice.** It labels the Move record "PGN", although CONTEXT.md says it may not be PGN. It then shows a history like `6. Nc6`, where a White knight jumped from b1, beside a FEN that disagrees with any legal replay of that history. Nothing tells the model which of the two to believe. [Repo]
- **After the first chaos move, small models play legally less often, at the same move numbers.** First-attempt legality in moves 1-10: llama3:8b 65% under Standard rules vs 47% after a chaos move; gemma3:12b 68% vs 48%. Moves 11-20 are mixed (llama 38% vs 41%, gemma3 46% vs 29%). gemma4:26b stays at 91-96%. The samples are small and confounded: chaos positions are also off-book. [Repo]
- **Models that reason handle it by deciding to trust the FEN.** gemma4:26b: "6. Nc6 is a typo in the user's PGN … Assuming the FEN is the ground truth". qwen3.8: "Let me just trust the FEN". qwen3.5:9b instead tried to replay the record ("Two knights cannot occupy the same square … That's impossible") and then played a chaos move. Saying "trust the FEN" in the prompt makes that choice for every model. [Repo]
- **Literature: an explicit "ignore this" instruction and examples that contain the distraction both help; small models are poor at resolving conflicts on their own.** "Feel free to ignore irrelevant information" raised accuracy by 2.9-5.4 points, and exemplars containing the distraction by 3.2-7.8 points ([Shi et al. 2023](https://ar5iv.labs.arxiv.org/html/2302.00093)). An explicit conflict instruction took Mistral-7B from 2.1% to 20.8% correct on contradictory passages ([WikiContradict](https://arxiv.org/html/2406.13805v1)). Buggy context more than halves code-completion pass rates ([Dinh et al. 2023](https://arxiv.org/abs/2306.03438)). [Source]
- **History is not needed for legality.** Board format (FEN, PGN or both) was "not critical" for 3-8B models ([Hwang et al.](https://arxiv.org/html/2507.00726v2)). Its uses are repetition, which ChessArena added the last 10 moves for, and "what just happened". [Source]
- **Under Listed, the list is the truth and is built from the real board, so the history matters little.** The honest relabel alone is enough there. [Inference]
- **Three options at the end:** (A) an honest relabel and a "trust the FEN" line; (B) position first, with only the last 10 plies of history, marked as possibly rule-breaking; (C) an explicit chaos-aware frame with a worked chaos example and a structured check in the Reasoning. **Recommendation:** ship A as the floor and run a paired replay probe of A, B and C on the roughly 330 logged after-chaos positions. My prior for 8-12B non-thinking models is B.

## 1. What the model sees after a chaos move today [Repo]

The flow is in `GameSession._play_llm_turn` (`chessllm/game.py`):

- Every Turn starts fresh. `turn_messages(pgn, fen, color, prompt_file, listed_moves, description)` builds one system message and one user message: `PGN: <Move record>\nFEN: <fen>`, optionally followed by the described position and `Legal moves: …`.
- `judge()` reads `{"move": …}` (or `{"reasoning": …, "move": …}` with thinking off, `ReasonedMoveAnswer`) and parses the SAN on the real board.
- Under Chaos rules, a move that is illegal or ambiguous but well formed is resolved by `chaos.resolve` and **played at once, without a Retry**. Only badly formed notation gets retries. **First-attempt legality is therefore the whole legality metric under Chaos rules.**
- `_pgn()` writes the Move record "a chaos move in the LLM's own spelling". The model is never told that a move broke the rules.

A real case (`2026-10-20T18-32-40_llama3-8b_vs_gemma4-26b`): llama3 wrote `6. Nc6` (resolver: "no knight can reach c6 by its movement; b1 is nearest"). At ply 18 gemma4 was sent:

```
PGN: 1. d4 Nf6 2. d5 c6 3. d6 cxd6 4. c3 e5 5. e4 Bc5 6. Nc6 Nxc6 7. Nf3 d5 8. Nc5 b6 9. Nd2
FEN: r1bqk2r/p2p1ppp/1pn2n2/3pp3/4P3/2P5/PP1N1PPP/R1BQKB1R b KQkq - 1 9
```

The record also has a second chaos move (`8. Nc5`). The system prompt promises "the game so far in PGN" and "The move must be legal in the current position". The prompt never says which part to trust.

Two smaller issues the brainstorm already noted affect all options: "against a human" is wrong outside Play LLM, and the example answer `{"move": "e4"}` doesn't match the thinking-off schema, which starts with `reasoning`. I keep the first line unchanged in all three options, so they differ only in the chaos framing.

## 2. Repo evidence: legality before and after the first chaos move

First attempts only, Free, FEN position, thinking off. The Standard rows are every Standard-rules game in `games/`. "After chaos" means plies after the game's first chaos move, by either side.

| Model | Moves | Standard rules | After a chaos move |
|---|---|---|---|
| llama3:8b | 1-10 | 136/210 (65%) | 28/60 (47%) |
| llama3:8b | 11-20 | 53/141 (38%) | 33/81 (41%) |
| llama3:8b | 21-40 | 21/107 (20%) | 10/27 (37%) |
| gemma3:12b | 1-10 | 120/176 (68%) | 12/25 (48%) |
| gemma3:12b | 11-20 | 58/125 (46%) | 14/49 (29%) |
| gemma3:12b | 21-40 | 36/98 (37%) | 9/25 (36%) |
| gemma4:26b | 1-20 | – | 48/51 (94%) |

Over all moves after the first chaos move: llama3 71/168 (42%), gemma3 35/99 (35%), qwen3.5:9b 0/8, gemma4:26b 48/51, qwen3.8 (thinking) 8/8. The Standard figures over whole games are 47% and 52%.

- **The early-game drop is the clearest signal.** For both small models, legality falls by about 20 points in moves 1-10 once the record contains a chaos move.
- **Later buckets don't separate.** Standard games get worse with length (C2 in the limitations note), so by move 20 both conditions are poor.
- **Confounds.** A chaos position is out of distribution by construction, and Pleiss et al. found illegal moves 4.72× more common out of distribution even with FEN-only input (`llm-chess-limitations.md`, C1). The two sets also select differently: the "after" set exists only because some model already broke the rules. The table cannot separate "the corrupted history confuses the model" from "the position is weird". A paired replay can (section 6).
- **The mechanism fits the stale-board finding.** In Standard games, 54-59% of illegal moves were legal in an earlier position (brainstorm). A model that rebuilds the board from the record gets a wrong board whenever the record contains a teleport or a spawn. [Inference]
- **Thinking traces show both strategies.**
  - gemma4:26b and qwen3.8 noticed the contradiction and chose the FEN. gemma4 still misread the history ("must mean 6. Nc3").
  - qwen3.5:9b spent its reasoning replaying the record into contradictions ("White Knight on e5. Black Knight on e5? That's impossible").
  - gemma3:12b once took the contradiction as the position being illegal: "The position after the given move is illegal … The move in the PGN seems to be a typo."
  - Only 8 of about 330 after-chaos first attempts mention the inconsistency at all. Most non-thinking answers say nothing about it.

## 3. What the literature says

### 3.1 Does the (corrupted) move history help or hurt?

- **For legality, history adds little over the FEN.** [Source] Hwang et al. found FEN, PGN and FEN+PGN "not critical" for Qwen2.5-7B and Llama3.1-8B ([2507.00726](https://arxiv.org/html/2507.00726v2); `llm-chess-notation.md`). In ChessArena, large non-thinking models were about as legal with history only as with FEN (GPT-4.1 72.7% vs 71.6%). Thinking models were much worse with history only (DeepSeek-R1 44.6% vs 82.5%), and the authors conclude "longer conversations impede board reconstruction" ([ChessArena](https://arxiv.org/html/2509.24239v4)).
- **History is used shallowly.** [Source] With history only, ChessArena's non-thinking models "mostly base their responses on the last move" (`llm-chess-limitations.md`, C3). Small models scored 0% on board-state tracking (A1). A small model therefore can't use a long record to rebuild the board, so it gains little from a correct record. [Inference] It can still be misled by a wrong one, through the last move or a remembered pattern.
- **History has one real use: repetition.** [Source] ChessArena added "the latest 10 moves as partial move history" because fivefold repetitions "occurred frequently" without it ([ChessArena](https://arxiv.org/html/2509.24239v4)). This repo's draw rules count every position anyway (`_check_end`), so only the model's own *avoidance* of repetition needs the history.
- **Corrupted context gets continued.** [Source]
  - In code, "a single potential bug in the context" made CodeGen-2B-mono's pass rate on buggy-HumanEval "drop more than 50%" ([Dinh et al. 2023](https://arxiv.org/abs/2306.03438)).
  - In chess, a transformer trained on games and started from 20 random moves "predict[s] moves as if both players had low skill". A positive skill intervention lifted its win rate 2-2.6× (16.7% → 43.2%, 15.7% → 31.3%) ([Karvonen 2024, Table 3](https://arxiv.org/html/2403.15498)).
  - [Inference] A record full of teleports is the language-model equivalent of "low-skill" or "buggy" context. It may make rule-breaking continuations more likely, whatever the instruction says.

### 3.2 Should the prompt say "earlier moves may have broken the rules; the FEN is authoritative"?

- **An explicit instruction to ignore misleading context helps, but only modestly.** [Source] Shi et al. prepended "Feel free to ignore irrelevant information given in the questions" and got, on GSM-IC with CoT, 72.4 → 77.8 (code-davinci-002) and 68.4 → 71.3 (text-davinci-003). Exemplars that themselves contained irrelevant context did about as well (72.4 → 76.8), and clean-problem accuracy barely moved: 60.3 → 58.8 for CoT with the instruction ([Shi et al., ICML 2023](https://ar5iv.labs.arxiv.org/html/2302.00093)).
- **Naming a conflict explicitly matters most for small models.** [Source] On two contradictory passages, an instruction to account for the conflict moved Mistral-7B-instruct from 2.1% to 20.8% correct and Llama-3-70B from 10.4% to 43.8% ([WikiContradict, Table 2](https://arxiv.org/html/2406.13805v1)). The task there is to *report* the conflict, not to choose a side, and n = 48, so only the direction carries over.
- **Without guidance, models lean on earlier evidence and on what fits their priors.** [Source] A 2026 study found "a consistent model bias towards earlier evidence" in in-context conflicts ([2609.03148](https://arxiv.org/abs/2609.03148)). Xie et al. found "a strong confirmation bias when the external evidence contains some information that is consistent" with the model's memory ([2305.13300](https://arxiv.org/abs/2305.13300)). Here the Move record comes *first* and looks like familiar PGN, so both biases favour it over the FEN. [Inference]
- **Position in the prompt matters.** [Source] Models use the start and end of the input best, and the middle worst ([Lost in the Middle](https://arxiv.org/abs/2307.03172), in `llm-chess-limitations.md` C2). Putting the FEN first, or the instruction last, is a cheap lever. [Inference]
- **Wording risk.** [Inference] "Earlier moves broke the rules" could read as permission to break them. Every option below pairs the warning with "your move must still be legal".

### 3.3 Does brief reasoning or a candidate step help small models play legally?

- **The thinking-off schema already makes the model reason before it moves** (`ReasonedMoveAnswer`: `reasoning` first, then `move`), and Standard-rules legality is still 47-52% for llama3 and gemma3. Free-form reasoning alone isn't the fix. [Repo] The brainstorm also showed llama looping on two stock Reasoning sentences. [Repo]
- **CoT helps mostly on symbolic or rule-following steps, and only when the model can carry them out.** [Source] "Much of CoT's gain comes from improving symbolic execution", and it trails real tools ([Sprague et al. 2024](https://arxiv.org/abs/2409.12183)). Chain-of-thought gains originally emerged only "in sufficiently large language models" ([Wei et al. 2022](https://arxiv.org/abs/2201.11903)). Checking legality is a symbolic step. A *structured* check is more promising for an 8B model than open reasoning: name the piece, the square the FEN puts it on, and the target. [Inference]
- **Self-checking without outside facts doesn't work** (Huang et al., Kamoi et al., in `llm-chess-limitations-solutions.md`). Here the FEN, or the piece list, *is* the outside fact, so the check should point the model at it rather than ask "is this legal?". [Inference]
- **Saying where the piece stands helps the model trained on it.** [Source] Adding piece-type tokens raised legal-move accuracy 74.0% → 88.4% in small-data training ([Toshniwal et al.](https://ar5iv.labs.arxiv.org/html/2102.13249)). Regurgitation and three short examples helped gpt-4o a lot ([Dynomight](https://dynomight.net/more-chess/)). Regurgitating the *history* would copy the corruption here, so restate the *position* instead. [Inference]
- **The piece list alone was weak in this repo:** gemma3 +5 points, llama3 −5 (`described-position-2026-10-20.md`). Expect any one lever to be small. Combining them (honest frame + position first + structured check) is the untested bet. [Repo + Inference]

### 3.4 Vendor guidance that constrains the wording

- **Gemma 3 has no system role.** [Source] Google's guide says to "provide system-level instructions directly within the initial user prompt" ([Gemma prompt structure](https://ai.google.dev/gemma/docs/core/prompt-structure)). [Repo] Ollama's gemma3:12b template renders our system message as a separate `<start_of_turn>user` turn right before the real user turn (`ollama show gemma3:12b --template`). The order is unchanged either way.
- **Gemma 4 has a real `system` turn,** and thinking is turned on there ([Gemma 4 formatting](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)). [Source]
- **Llama 3 Instruct allows "a single system message"** before alternating turns ([Meta, Llama 3 prompt format](https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats/meta-llama-3/)). [Source]
- **Qwen3 recommends standardising the output format in the prompt with a JSON example** ("show your choice in the `answer` field …") and keeping only final outputs, not thinking, in history ([Qwen3-8B card](https://huggingface.co/Qwen/Qwen3-8B)). [Source] Today's fresh Turns already satisfy the history rule.
- **Ollama:** pass the schema via `format` and add "return as JSON" to the prompt ([Ollama structured outputs](https://ollama.com/blog/structured-outputs)). [Source] The example answer should match the schema actually sent, which argues for showing `reasoning` in the thinking-off example (Option C does). [Inference]

### 3.5 Listed mode

- Under Listed, the `Legal moves:` list is built from the real board (`board.legal_moves` in `_play_llm_turn`). Listed models play about 96-98% legal (`described-position-2026-10-20.md`; ChessArena 96.2% for Qwen3-8B). A chaos move then happens only when the model leaves the list, so chaos Turns, and with them corrupted records, are rare. [Repo + Source]
- `system_listed.txt` already makes the list authoritative ("Choose your next move from the list"). After a chaos move it still says "the game so far in PGN", so it needs the same honest relabel. A chaos-aware frame or a check step adds cost for little legality gain there. [Inference]
- Dynomight found a listed-moves prompt made gpt-4o play "much worse" in quality (`more-chess`). That is a strength question, not legality, and it doesn't interact with chaos wording. [Source]

## 4. Design constraints from the repo

- **Prompt identity.** `PlayerConfiguration.prompt` is the system prompt's *file name*, and the user message is built in code (`prompt-tooling.md`, brainstorm prerequisite). Chaos games are unrated (CONTEXT.md, ADR 0006), so the rating risk is small. Analyses still compare chaos and Standard legality, though, so each option should get its own file name and be logged per game. [Repo]
- **When to switch.** A separate chaos prompt can apply (i) to the whole Chaos-rules game, or (ii) only from the first chaos ply (`self._first_chaos_ply`). (ii) keeps pre-chaos Turns byte-identical to Standard, so pre-chaos legality stays comparable. It costs a prompt change mid-game; every Turn is fresh anyway. (i) is simpler and honest from move 1, since chaos moves *may* happen. The options below assume (i), with (ii) as a variant. [Repo + Inference]
- **Vocabulary.** CONTEXT.md says to avoid "PGN" for a game with chaos moves and to say "Move record". The prompt should say "moves so far" rather than "PGN". [Repo]
- **Token cost.** Logged prompts grow from about 190 tokens at ply 1 to about 400 at ply 49; the record adds about 0.5 token per character [Repo]. Prompt length is cheap. Extra *output* (reasoning) is what costs time, and is capped only by the Thinking budget (ADR 0007).

## 5. Three prompt options

All three keep the answer in SAN and the `MoveAnswer` / `ReasonedMoveAnswer` schemas unchanged. Each is a drop-in template for `system.txt`, used only under Chaos rules (proposed file names given), with the existing placeholders `$color`, `$opponent`, `$example_pgn`, `$example_fen`, `$example_move` (and `$example_legal_moves` for the Listed variant). New placeholders are named where needed.

### Option A: minimal honest relabel (`system_chaos.txt`)

```
You are playing chess as $color against a human playing $opponent.
Each turn you get the moves so far, as each side wrote them, and the current position in FEN.
Some earlier moves may have broken the rules of chess and were played on the board anyway, so the moves so far may not add up to a legal game.
The FEN is the actual position. Where the moves so far and the FEN disagree, trust the FEN.
Reply with your next move in SAN (e.g. Nf6, exd5, O-O, e8=Q).
Your move must be legal in the position given by the FEN, even if earlier moves were not.

Example:
Moves so far: $example_pgn
FEN: $example_fen
Answer: {"move": "$example_move"}
```

User message:

```
Moves so far: 1. d4 Nf6 2. d5 c6 3. d6 cxd6 4. c3 e5 5. e4 Bc5 6. Nc6 Nxc6
FEN: r1bqk2r/pp1p1ppp/2np1n2/2b1p3/4P3/2P5/PP3PPP/R1BQKBNR w KQkq - 0 7
```

(described position and `Legal moves:` lines appended as today.) Listed variant `system_listed_chaos.txt`: the same three honest lines inserted into `system_listed.txt`, with "PGN" replaced by "moves so far", and "Choose your next move from the list" kept as the last instruction.

- **Code change.**
  - `prompt.py`: `turn_messages` takes a record label (`"PGN"` or `"Moves so far"`), defaulting to today's, so Standard is unchanged.
  - `SYSTEM_PROMPT_FILES` becomes keyed by (constraints, rules), or a second dict `CHAOS_SYSTEM_PROMPT_FILES`.
  - `game.py`: `_play_llm_turn` picks the file and label from `self._chaos`, or from `self._first_chaos_ply is not None` for variant (ii).
  - No schema change.
- **Expected effect.** Small but positive for models that already reason (gemma4, qwen3.8, qwen3.5 with thinking): it makes the choice they reached on their own explicit, and stops attempts to replay the record. For llama3 and gemma3 without thinking I expect a few points at most, by analogy to Shi et al. (+3-5 points from one instruction) and the weak piece-list result here. Evidence: 3.2. It doesn't remove the corrupted record, so the Dinh/Karvonen "bad context" effect stays.
- **Trade-offs.**
  - Smallest change: 3 lines, no new placeholders, about 60 more prompt tokens.
  - Honest and in CONTEXT.md's vocabulary.
  - The closest to Standard prompts, so the cleanest comparison with Standard legality.
  - Risk: "broke the rules … played anyway" may read as permission. The last line addresses that, but it is untested.
  - Least likely to move llama3.

### Option B: position first, history cut to the recent past (`system_chaos_position.txt`)

```
You are playing chess as $color against a human playing $opponent.
Each turn you get the current position: its FEN, and where every piece stands.
That position is the truth. Choose your move from it alone.
You also get the last few moves as they were written. Some of them may have broken the rules of chess and been played on the board anyway; they only show what just happened. Do not work out the position from them.
Reply with your next move in SAN (e.g. Nf6, exd5, O-O, e8=Q).
Your move must be legal in the current position.

Example:
FEN: $example_fen
$example_description
Recent moves: $example_recent
Answer: {"move": "$example_move"}
```

User message (the position first, the record last and short, the in-check line kept):

```
FEN: r1bqk2r/pp1p1ppp/2np1n2/2b1p3/4P3/2P5/PP3PPP/R1BQKBNR w KQkq - 0 7
Your pieces (White): King e1; Queen d1; Rooks a1, h1; Bishops c1, f1; Knight g1; Pawns a2, b2, c3, e4, f2, g2, h2
Opponent's pieces (Black): King e8; Queen d8; Rooks a8, h8; Bishops c5, c8; Knights c6, f6; Pawns a7, b7, d6, d7, e5, f7, g7, h7
Recent moves (as written; some may break the rules): 2. d5 c6 3. d6 cxd6 4. c3 e5 5. e4 Bc5 6. Nc6 Nxc6
```

Listed variant: the same, with `Legal moves: …` after the piece lists and "Choose your next move from the list of legal moves, and reply with it exactly as written there." in place of the SAN line.

- **Code change.**
  - `prompt.py`: `turn_messages` gets a layout switch ("position first"): FEN, then `describe_position` without its "Last move:" line (a new `last_move=None` call does that already), then the legal moves, then `Recent moves (as written; some may break the rules): …`.
  - A helper renders the last N = 10 plies with correct move numbers. A Black-first slice needs the `7...` form.
  - `system_prompt()` gains `$example_description` (the start or after-e4 position via `describe_position`) and `$example_recent`.
  - `game.py`: `_play_llm_turn` passes `self._moves[-10:]` and the starting ply instead of the whole record, and the description always. The position setting is then implied for this prompt, which the log should record (e.g. `position: "described"`).
- **Expected effect.** This is the only option that *removes* most of the conflict rather than asking a small model to resolve it. Once the chaos move is 10 plies old, the model sees no corrupted history at all.
  - It puts the authoritative facts first, against the early-evidence bias (2609.03148), and drops what an 8B model can't use anyway (Hwang: format "not critical"; A1: 0% tracking).
  - It keeps ChessArena's 10-move window for repetition.
  - The piece list was worth only +5 / −5 points in Standard games, so most of any gain must come from removing the stale-board source, which is unproven. I'd expect the biggest gain of the three on llama3 and gemma3 *early* after a chaos move, where the drop was about 20 points (section 2). [Inference]
- **Trade-offs.**
  - The biggest departure from Standard prompts, so chaos and Standard legality are no longer like for like. Running B under Standard rules as well (its honest line is still true: "may") would restore that, as a new configuration.
  - Tokens are about the same: the piece list adds about 70 and the cut record saves 0-150 late in a game.
  - The model loses the opening's name and the game's story, which can hurt move quality in book positions, as in Dynomight's PGN-continuation results (`llm-chess-notation.md`). [Inference]
  - Within 10 plies of a chaos move the conflict is still there, only shorter.

### Option C: explicit chaos-aware frame, a worked chaos example and a structured check (`system_chaos_check.txt`)

```
You are playing chess as $color against a human playing $opponent.
In this game, a move that breaks the rules of chess is not refused: it is played on the board anyway. So pieces may have jumped, appeared or been captured in ways the rules do not allow, and the moves so far may not add up.
Each turn you get the moves so far, as each side wrote them, the current position in FEN, and where every piece stands. The FEN and the piece list are the actual position; trust them over the moves so far.
Your move must still be legal in the actual position.
Before you answer, check your move against the actual position: name the piece you will move and the square it stands on now, the square it goes to, that nothing stands in its way and that no piece of your own is on that square, and that your king is not in check after the move.
Reply with your next move in SAN (e.g. Nf6, exd5, O-O, e8=Q).

Example (the last move shown broke the rules: no piece could legally reach that square):
Moves so far: $example_chaos_pgn
FEN: $example_chaos_fen
Answer: $example_answer
```

The worked examples, computed with this repo's resolver (`chaos.resolve` / `chaos.apply`):

- **LLM is White.**
  - Moves so far: `1. e4 e5 2. Nf3 Bxf3` (a black bishop from c8 jumped to f3)
  - FEN: `rn1qkbnr/pppp1ppp/8/4p3/4P3/5b2/PPPP1PPP/RNBQKB1R w KQkq - 0 3`
  - Answer: `{"reasoning": "A black bishop is on f3. My queen on d1 can take it along d1-e2-f3; e2 is empty, and my king is not in check after it.", "move": "Qxf3"}`
- **LLM is Black.**
  - Moves so far: `1. e4 e5 2. Bxf7+` (a white bishop from c1 jumped to f7)
  - FEN: `rnbqkbnr/pppp1Bpp/8/4p3/4P3/8/PPPP1PPP/RN1QKBNR b KQkq - 0 2`
  - The only legal moves are Kxf7 and Ke7.
  - Answer: `{"reasoning": "I am in check from the white bishop on f7. My king on e8 can take it: f7 is next to e8 and no white piece guards f7.", "move": "Kxf7"}`

With thinking on (schema `MoveAnswer`), `$example_answer` is `{"move": "Qxf3"}` / `{"move": "Kxf7"}`, and the check sentence applies to the thinking.

User message: as Option A, plus the piece list, so that the check has something to point at:

```
Moves so far: 1. d4 Nf6 2. d5 c6 3. d6 cxd6 4. c3 e5 5. e4 Bc5 6. Nc6 Nxc6
FEN: r1bqk2r/pp1p1ppp/2np1n2/2b1p3/4P3/2P5/PP3PPP/R1BQKBNR w KQkq - 0 7
Last move: Nxc6
Your pieces (White): …
Opponent's pieces (Black): …
```

Listed variant: drop the check paragraph's last three clauses (the list already guarantees them) and keep "name the piece and the square it stands on now". The answer must still come from the list.

- **Code change.**
  - `prompt.py`: `system_prompt()` takes a `thinking` flag (or the schema) and chaos-example placeholders `$example_chaos_pgn`, `$example_chaos_fen`, `$example_answer`, from a hard-coded `CHAOS_EXAMPLES` table per colour. The FENs are fixed: they can't come from `push_san`, but a test can rebuild them with `chaos.apply`.
  - `game.py`: `_play_llm_turn` uses the description always under this prompt and passes `side.thinking` to the prompt builder.
  - No schema change. The check lives in the `reasoning` field that `ReasonedMoveAnswer` already puts first. A stricter variant would add a `from_square` field before `move`, which is a schema change and so a new configuration (brainstorm idea 3/4). Its value could be scored against the real board as a board-tracking metric.
- **Expected effect.**
  - It uses every lever with evidence behind it: the explicit conflict instruction (Shi; WikiContradict, largest at 7B), an example *containing* the distraction (Shi's exemplar result; Dynomight's few-shot gains), the position stated as a piece list (ChessQA, Toshniwal), and reasoning steered to the symbolic check where CoT helps (Sprague).
  - Its check points at an outside fact (the FEN and the list), which is the only kind of self-check that works (Huang/Kamoi).
  - I expect the best result for gemma4:26b and the thinking models, which already reason this way. For llama3:8b, CoT's dependence on scale (Wei) and its looping Reasoning (brainstorm) are reasons for doubt. [Inference]
- **Trade-offs.**
  - The largest prompt: about 250 system tokens against about 110 today.
  - Longer Reasoning, so more latency and more Thinking-budget cut-offs (ADR 0007).
  - The example shows a rule-breaking move as normal, which may prime imitation (Dinh/Karvonen effect). It is labelled as breaking the rules, but that is untested.
  - The worked example also fixes the brainstorm's example-schema mismatch, but only for this prompt, so it is not comparable to Standard prompts.
  - The most likely to confuse a small model ("pieces may have jumped" could make it play a jump itself).

## 6. Recommendation and how to test it

**Recommendation.** Make Option A the Chaos-rules prompt now, for both Free and Listed. It is the minimum needed for honesty, since the current prompt mislabels the record and gives no source of truth, and it is the baseline for the other two. Don't choose between B and C without data. My prior is that B helps llama3 and gemma3 most, because it removes the conflict instead of asking an 8B model to resolve it. C should help gemma4:26b and the thinking models most. Under Listed, keep A: the list already does the work.

**Test: a paired replay probe on frozen after-chaos positions,** modelled on `scripts/probe_thinking_budget.py`.

1. **Positions.** Take every first attempt after the first chaos ply from the 18 Chaos-rules logs in `games/`. Each `llm_attempt` logs `pgn` (the Move record), `fen`, `ply` and `color`. That is about 330 positions (llama3 168, gemma3 99, gemma4 51). Add a control set of Standard-rules first attempts at matched move numbers, to check that the new wording doesn't hurt when no chaos has happened. (The Standard record is valid PGN, so A's and C's "may" stays true.)
2. **Conditions.** Today's `system.txt` / `PGN:` vs A vs B vs C. Same model, the sampling from `chessllm/sampling.toml`, one first attempt each, two passes. Build messages with the new `turn_messages` variants, call the game's `OllamaPlayer`, and judge with `chessllm.game.judge` against the logged FEN. Also record whether `chaos.resolve` would have spawned a piece or played a chaos move, and the answer tokens.
3. **Models.** llama3:8b and gemma3:12b without thinking (the problem cases), gemma4:26b without and with thinking (the ceiling), and qwen3.5:9b with thinking (the model that tried to replay the record).
4. **Metric and stopping rule.** Paired first-attempt legality per model, with a McNemar test on the discordant pairs. As in `described-position-2026-10-20.md`, the success mark is +10 points over today's prompt. Also report the share of illegal moves whose from-square is empty or holds the opponent's piece in the FEN (the "stale board" signature), answer tokens, and cut-offs.
5. **Then games, for the winner only.** `uv run python -m chessllm.faceoff_batch --models gemma3:12b llama3:8b --games 6 --rules chaos`, once with today's prompt file and once with the winner. That needs the per-run prompt choice from the code changes above, e.g. a `--chaos-prompt` flag. Analyse with `uv run python -m scripts.analyse_games --mode llm_faceoff --rules chaos --since <start>`. Look at first-attempt legality after the first chaos ply, chaos moves and spawns per game, and King-left-in-check endings.
6. **Listed check.** One small replay of A against today's `system_listed.txt` under `listed`. Expect no change; it only confirms the relabel does no harm.
