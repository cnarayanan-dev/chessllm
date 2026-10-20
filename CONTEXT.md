# ChessLLM

A benchmark of how well small local LLMs play chess, by playing them against humans and against each other (and later engines).

## Language

### Modes

**Mode**:
Who plays each side of a game, fixed for the whole game. One of **Play LLM**, **LLM faceoff** or **Anchor match**.
_Avoid_: Matchup, game type, opponent type

**Play LLM**:
The **Mode** in which a human plays one side and an LLM the other.
_Avoid_: Human vs LLM, single-player

**LLM faceoff**:
The **Mode** in which an LLM plays each side, two different models or one model against itself, so models can be compared with each other.
_Avoid_: LLM vs LLM, self-play, tournament

**Anchor match**:
The **Mode** in which an LLM plays an **Anchor**, run unattended in batches, so the LLM's games have an opponent of known strength.
_Avoid_: Engine game, bot match, calibration game

**Anchor**:
A non-LLM opponent whose strength on the chess.com scale is fixed in advance, such as a random legal mover or a chess engine held to a set skill level.
_Avoid_: Bot, engine (alone), reference player

**Rematch**:
A new game with the same **Mode** and settings as the game just played, the colours swapped: in **Play LLM** the human takes the other side, in an **LLM faceoff** the two LLMs change sides.
_Avoid_: Replay, rerun, play again

**Move cap**:
The number of moves per side after which an unattended game that has not ended by the rules is scored a draw, whatever the position.
_Avoid_: Move limit, adjudication, timeout

### LLM constraints

**LLM constraints**:
The combination of whether the **Legal-move list** is shown and whether **Enforced decoding** is on, fixed for a whole game. One of four: Free, Listed, Blind enforced, Listed enforced.
_Avoid_: Play mode, mode, game type, variant

**Legal-move list**:
The list of every legal move in the current position, shown to the LLM in its prompt.
_Avoid_: Move options, candidate moves

**Enforced decoding**:
Generation of the LLM's reply under a constraint that only lets it produce one of the legal moves, so it cannot propose an illegal move.
_Avoid_: Constrained decoding, grammar mode, structured output

**Free**:
The **LLM constraints** with no **Legal-move list** and no **Enforced decoding**, so the LLM can propose an illegal move.
_Avoid_: Free mode, unconstrained, open

**Listed**:
The **LLM constraints** in which the LLM is shown the **Legal-move list** but not held to it, so it can still propose an illegal move.
_Avoid_: Listed mode, constrained, limited output, legal-only

**Blind enforced**:
The **LLM constraints** with **Enforced decoding** but no **Legal-move list**: the LLM cannot propose an illegal move and is not told what its options are.
_Avoid_: Blind enforced mode, constrained, grammar mode

**Listed enforced**:
The **LLM constraints** with both the **Legal-move list** and **Enforced decoding**: the LLM sees its options and cannot leave them.
_Avoid_: Listed enforced mode, constrained, fully constrained

### Rules

**Standard rules**:
The normal rules of chess, under which an **Illegal move** is never played.
_Avoid_: Normal mode, legal mode

**Chaos rules**:
Rules under which an LLM's **Illegal move** is played on the board anyway, fixed for a whole game, applying to every LLM in it, and only possible under **Free** or **Listed**. Humans and **Anchors** always play legal moves. Games under chaos rules are counted apart from games under **Standard rules** and are unrated.
_Avoid_: Chaos mode, illegal mode, anarchy chess

**Chaos move**:
A rule-breaking or ambiguous **Illegal move** that is played on the board under **Chaos rules**, at its first attempt and without a **Retry**. An illegal move in badly formed notation is never a chaos move; it gets retries as under **Standard rules**.
_Avoid_: Executed illegal move, forced move

**Spawn**:
A **Chaos move** by a piece the LLM does not have on the board, which then appears on its target square from nowhere. A king is never spawned.
_Avoid_: Resurrection, summon, phantom piece

**King capture**:
The end of a game under **Chaos rules** in which a **Chaos move** takes a king; the side left with its king wins at once.
_Avoid_: Regicide, king taken

**King left in check**:
The end of a game under **Chaos rules** in which a **Chaos move** leaves the mover's own king in check, whether it ignores a check or walks into one; the mover loses at once, without the opponent having to take the king.
_Avoid_: Hanging king, self-check, exposed king

**Move record**:
The moves of a game so far in PGN movetext form, each written as it was played, a **Chaos move** in the LLM's own spelling. Under **Standard rules** it is valid PGN; under **Chaos rules** it may not be.
_Avoid_: PGN (for a game with chaos moves), move history

### Moves

**Turn**:
One decision by an LLM in a game: it is shown the current position and replies with a move, including any retries. Each turn starts fresh, without the conversation from earlier turns.
_Avoid_: Round, step

**Thinking**:
The long internal reasoning a model produces before it answers, when thinking is on for its side. Part of the **Player configuration**.
_Avoid_: Chain of thought, reasoning, explanation

**Thinking level**:
One of the effort levels a model offers for its **Thinking**, as Ollama lists them, such as qwen3.8's low, medium and xhigh, sent instead of plain thinking on. Plain on means the model's default level. Set only in the benchmark's commands, never from the app. Part of the **Player configuration**; plain on or off is no level.
_Avoid_: Thinking effort, reasoning effort, thinking mode

**Thinking budget**:
The most tokens of **Thinking** (and answer) a model may produce in one attempt before it is made to answer: it is handed back its thinking so far and gives its move under the same answer format, and under **Enforced decoding** the same legal-move constraint. In tokens, so it means the same on any machine; each **Retry** gets a fresh one. Needs thinking on. Set only in the benchmark's commands, never from the app. Part of the **Player configuration**; no budget is the default.
_Avoid_: Token limit, thinking limit, time budget, max tokens

**Reasoning**:
The short explanation an LLM writes in its answer, before its move, when thinking is off. A model with thinking on gives none.
_Avoid_: Explanation, thinking, justification

**Prompt**:
Everything sent to the LLM in a **Turn**, exactly as it received it: the **System prompt**, the position (with the **Legal-move list** when shown), and for each **Retry** its previous answer and the **Retry feedback**. Recorded as sent, since the system prompt file can change between turns.
_Avoid_: Input, context, query

**System prompt**:
The fixed instructions that open every **Prompt**: the rules of the answer and a worked example, the same for every turn of a side unless its file is edited.
_Avoid_: Instructions, template (for the text sent)

**Illegal move**:
A move proposed by the LLM that cannot be played in the current position: badly formed notation, a rule-breaking move, or an ambiguous move all count, each recorded with its kind.
_Avoid_: Invalid move, wrong move

**Notation slip**:
A legal move the LLM writes in anything other than its exact standard SAN, such as UCI, a needless disambiguation, or a missing or false check sign. It is played, and recorded and shown as a slip; it is not an illegal move.
_Avoid_: Format error, non-SAN move

**Retry**:
A further attempt the LLM gets after an illegal move, told why the previous move was rejected, or after a forced answer that was itself cut off before it gave a move (with a **Thinking budget** only; not an illegal move). The attempts per turn, retries included, are set for the whole game, 1 to 25 and 5 by default, the same for every LLM in it; a Player configuration includes them.
_Avoid_: Re-prompt, second chance

**Retry feedback**:
What the LLM is told after an illegal move. One of three levels: *explained* (the move and the kind of failure, the default), *bare* (only that it was illegal), or *hinted* (also the list of legal moves).
_Avoid_: Error message, hint mode

**Forfeit**:
Loss of the game by an LLM after it uses up its retries without proposing a legal move, or at once when it gives no answer at all (it thinks past the time limit or the call fails).
_Avoid_: Resign, disqualification

**Legal-move streak**:
The number of legal moves an LLM plays in a game before its first illegal move, whether or not a retry later recovers the game. Not applicable under **Enforced decoding**, where it would be true by construction.
_Avoid_: Legal move count, survival length

### Rating

**Player configuration**:
An LLM together with every setting it plays a game with: model, thinking and its **Thinking level** and **Thinking budget**, **LLM constraints**, **Standard rules** or **Chaos rules**, **Retry feedback**, sampling and prompt. Games count towards the same rating only if their player configurations are identical.
_Avoid_: Model (when settings differ), entrant, agent, bot

**Rating**:
The Elo of a **Player configuration** on the chess.com scale, estimated only from its wins, draws and losses, with a **Forfeit** counted as a loss. Games against **Anchors** set the scale; **LLM faceoff** games only place configurations relative to each other, so a configuration with no path to an Anchor has no Rating. **Play LLM** games do not count towards it, since the human's strength is unknown; they count only towards the **Move-quality estimate**. Fitted over all games together, so the order they were played in does not matter. Always given with its uncertainty, or as an upper bound when every game was lost.
_Avoid_: Elo (alone), score, strength, performance

**Move-quality estimate**:
An Elo for a **Player configuration** inferred from its moves, regardless of who won: the human rating whose players would most likely have made the same moves. Given for each game and for each Player configuration; the configuration's estimate pools the moves of all its games rather than averaging the per-game estimates. Shown next to the **Rating** and never combined with it; the gap between the two is itself a finding.
_Avoid_: Estimated rating, accuracy Elo, game rating
