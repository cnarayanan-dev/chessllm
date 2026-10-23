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
The list of every legal move in the current position, shown to the LLM in its prompt. Shown only when the **LLM constraints** say so: a **Turn template** must place it then, and must not otherwise, so the constraints are always what the LLM was actually given.
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

**Evaluation**:
Stockfish's judgement of a position at a fixed search, in pawns, capped at ±10, or a mate in so many moves. Shown live in an **LLM faceoff** from White's point of view, and never during a **Play LLM** game. A position a **Chaos move** left that isn't valid chess, such as one with a pawn on a back rank, has none: it is shown as not judged, with the reason, and never patched up to be judged.
_Avoid_: Eval, score, centipawns (when shown)

**Chaos gain**:
How much a **Chaos move** gained its mover over a legal alternative: Stockfish's evaluation after the chaos move minus its evaluation of the alternative, in pawns from the mover's point of view, each evaluation capped at ±10 (a **King capture** counting as +10 after the move, a **King left in check** as −10), so the gain itself is capped at ±20: taking a queen for free instead of giving one away is worth more than 10. Negative when breaking the rules did worse. A side's Chaos gains added up are its Chaos gain score, shown with its other rule-breaking counts. Not judged when a position it needs has no **Evaluation**; such moves are counted, but left out of every average. Measured against a **Gain baseline**. Recorded in every **Mode**, and shown in every Mode, live, but only over the **Legal counterpart**: with its switch off no Chaos gain is shown.
_Avoid_: Illegal-move gain, cheat value, chaos advantage

**Gain baseline**:
The legal alternative a **Chaos gain** is measured against: the **Legal counterpart**, or Stockfish's best move, which is Stockfish's evaluation of the position before the chaos move. The gain over Stockfish's best move is always recorded but never shown; the gain over the Legal counterpart is recorded only when one was asked for, and is the only one shown.
_Avoid_: Comparison mode, reference move

**Legal counterpart**:
The legal move an LLM gives for the same position after its move there was a **Chaos move**. It is asked for once more under **Listed enforced**, whatever the side's own **LLM constraints**, in one attempt without a **Retry**. Its Thinking and Answer are recorded, but it is never played. Under a conversation kept by **Turn memory**, it is asked at the end of that conversation and then dropped from it, so the LLM answers with what it knew when it made the chaos move and never remembers being asked. Asking for it is a switch, on by default under **Chaos rules**; it is not part of the **Player configuration**, since the moves played are the same either way. Its time is not **Time used**, and if it fails the game goes on without it; it never causes a **Forfeit**.
_Avoid_: Shadow move, fallback move, legal alternative

**Move record**:
The moves of a game so far in PGN movetext form, each written as it was played, a **Chaos move** in the LLM's own spelling. Under **Standard rules** it is valid PGN; under **Chaos rules** it may not be.
_Avoid_: PGN (for a game with chaos moves), move history

### Moves

**Ply**:
One move by one side: a human's move, an **Anchor**'s, or the move an LLM's **Turn** ends with, a **Chaos move** included. Numbered from 1 for White's first move, so White plays the odd plies; a move number in the **Move record** covers two plies, and the **Move cap** of 150 moves per side is 300 plies.
_Avoid_: Half-move, move (when one side's single move is meant)

**Turn**:
One decision by an LLM in a game: it is shown the current position and replies with a move, including any retries. Whether it starts fresh or continues the conversation of earlier turns is its side's **Turn memory**.
_Avoid_: Round, step

**Turn memory**:
Whether an LLM's **Turns** in a game share one conversation, fixed for the whole game and chosen for each side. One of three: *fresh* (every turn starts a new conversation with the position, the default), *chat with position* (one conversation for the whole game, each turn adding the position as a fresh turn would show it), or *chat with moves* (one conversation, each turn adding only the opponent's last move, so the LLM must keep track of the board itself). A conversation keeps every attempt and its **Retry feedback**, but never the **Thinking**. When it no longer fits the model's context, its oldest turns are dropped whole, and each turn records how many earlier turns it still remembered. The last two are for exploring how a conversation changes an LLM's play.
_Avoid_: History, context, memory mode, chat mode

**Chaos move report**:
The line at the start of a turn, in a conversation kept by **Turn memory**, saying what each **Chaos move** since that side's last turn actually did, its own and its opponent's, in the resolver's words, e.g. "Your Bd3 was played as: bishop c1→d3". Legal moves get none. A fresh turn gets none, since its position already shows the board.
_Avoid_: Resolution message, chaos feedback

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

**Tool**:
A question about the game an LLM may ask the benchmark during its **Turn**, before it gives its move, and get an answer to. There are four, none taking any input, each answering about the current position: *board* (a diagram, the FEN, whose move it is, castling rights and the en passant square), *move history* (the moves so far as PGN), *legal moves* (every legal move, in random order like the **Legal-move list**) and *material* (each side's pieces and points, and the balance from the caller's side). Which tools a side has, none, any of them or all four, is fixed for the whole game, set only in the benchmark's commands, never from the app, possible only under **Free** or **Blind enforced** (the **Legal-move list** would make the legal moves tool pointless), only under **Standard rules** and *fresh* **Turn memory**, only with **Thinking** on (at any **Thinking level**) and no **Thinking budget**, and only for a model that can call tools natively, never through a text protocol of the benchmark's own, and is part of the **Player configuration**, so a model with tools and the same model without them are rated apart. Every tool call is recorded with the **Attempt** it was made in.
_Avoid_: Skill, agent call, function, action

**Tool-call cap**:
The most **Tool** calls an LLM may make in one **Attempt**, 10 by default, each call counted even when several come in one reply; each **Retry** gets a fresh one. When the LLM answers without calling a tool, or has used its last call, it is asked once more for its move under the **Answer format**, and under **Enforced decoding** the same legal-move constraint. Tool calls and that last answer count towards the turn's **Time used**. Part of the **Player configuration**, with the tools.
_Avoid_: Tool limit, max turns, step limit

**Prompt**:
Everything sent to the LLM in a **Turn**, exactly as it received it: the **System prompt**, the **Turn template** filled in for the position, the **Answer format**, and for each **Retry** its previous answer and the **Retry feedback**. Under a conversation kept by **Turn memory** it also holds the earlier turns the LLM still remembers. A side's **Prompt template** is fixed for the whole game: a changed one is played only from a new game. Recorded as sent; in a conversation each attempt records only what it added, and the whole prompt is rebuilt from the game's earlier records.
_Avoid_: Input, context, query

**System prompt**:
The instructions that open every **Prompt**, written as text by the human for each LLM side, or the default one when they write none. It is identified by its text, never by a file name.
_Avoid_: Instructions, template (for the text sent)

**Turn template**:
The text, written by the human for each LLM side, that becomes the message of every **Turn** after the **System prompt**, with placeholders filled in from the game, such as the moves so far, the FEN, where every piece stands or the **Legal-move list**. Which of these the LLM is given is the template's choice, except the Legal-move list, which the **LLM constraints** decide. A default one is used when they write none. Identified by its text.
_Avoid_: User message, position message

**Prompt template**:
A **System prompt** and a **Turn template** written for each other and kept together in the **Prompt library**, which an LLM side plays with. It fits the **LLM constraints** that show the **Legal-move list** only if its Turn template places it. It fits *chat with moves* **Turn memory** only if its Turn template places the opponent's last move and never the position, and the other Turn memories only if it doesn't.
_Avoid_: Preset, saved prompt, prompt pair

**Prompt library**:
The Prompt templates the human has saved, each with an ID given on saving and an optional name, together with the default ones. A saved Prompt template never changes: saving an edit makes a new one with a new ID, and an old one can only be hidden. A game records the full text of the Prompt template each side played with, not only its ID.
_Avoid_: Prompt store, prompt collection

**Prompt lab**:
The tools for experimenting with prompts: choosing a side's **Prompt template**, **Probes** and **Pause**. Switched on in the app's preferences, off by default; it changes which tools are shown, never how a game is played. With it off, every side plays with a default Prompt template.
_Avoid_: Prompt mode (a **Mode** is a kind of game), prompt editor, playground

**Pause**:
Holding a game in which LLMs move on their own (an **LLM faceoff** or an **Anchor match**) after the **Turn** running, so no new turn starts until it is resumed. Asking for a **Probe** while such a game runs pauses it first, so a probe never runs alongside a real turn. Nothing in the game changes, and **Time used** does not grow while it is paused.
_Avoid_: Stop, suspend, break

**Probe**:
One question to an LLM about the position of a past **Turn**, asked outside the game with any **Prompt template**, by the same model and settings as the side that played it, and judged as an attempt would be. Always a fresh prompt for that position, even for a side whose **Turn memory** keeps a conversation. Never part of the game: it changes no move, record of play or **Rating**. Kept apart from the game's record, with the full text of its Prompt template and its answer, so probes can be added up across games later.
_Avoid_: Try (in records; "Try" is only the button's name), retry, replay, rerun

**Answer format**:
The shape the LLM's answer must take: its move, and its **Reasoning** when thinking is off. Set by the benchmark, not by the human, and added to every **Prompt** whatever its System prompt and Turn template say.
_Avoid_: Output format, schema

**Illegal move**:
A move proposed by the LLM that cannot be played in the current position: badly formed notation, a rule-breaking move, or an ambiguous move all count, each recorded with its kind.
_Avoid_: Invalid move, wrong move

**Notation slip**:
A legal move the LLM writes in anything other than its exact standard SAN, such as UCI, a needless disambiguation, or a missing or false check sign. It is played, and recorded and shown as a slip; it is not an illegal move. Under **Chaos rules** slips are still recorded but not shown, since there an illegal move is played anyway.
_Avoid_: Format error, non-SAN move

**Attempt**:
One try within an LLM's **Turn**: the **Prompt** sent, the model's answer, and how it was judged. A turn's first attempt is its first try; every further attempt is a **Retry**. The turn ends with the attempt whose move is played, or in a **Forfeit**.
_Avoid_: Try (in code and records), request, call

**Retry**:
A further attempt the LLM gets after an illegal move, told about it as its **Retry feedback** says, or after a forced answer that was itself cut off before it gave a move (with a **Thinking budget** only; not an illegal move). The attempts per turn, retries included, are set for the whole game, 1 to 25 and 5 by default, the same for every LLM in it; a Player configuration includes them.
_Avoid_: Re-prompt, second chance

**Retry feedback**:
What the LLM is told after an illegal move. One of four levels: *explained* (the move and the kind of failure, the default), *bare* (only that it was illegal), *hinted* (also the list of legal moves), or *repeat* (nothing: the turn's first **Prompt** is sent again unchanged, so the LLM never sees its rejected move; in a conversation kept by **Turn memory** the rejected attempt is left out of it, though the game still records it).
_Avoid_: Error message, hint mode

**Forfeit**:
Loss of the game by an LLM after it uses up its retries without proposing a legal move, or at once when it gives no answer at all (it thinks past the time limit or the call fails).
_Avoid_: Resign, disqualification

**Time used**:
The total time a side has spent on its moves in a game, added up move by move and shown for both sides in every **Mode**. For an LLM, the time its **Turns** ran, from when each started to its move or **Forfeit**, so a game nobody is driving charges no one; for an **Anchor**, from when its move is asked for to its move. For the human, the time from their position being ready to their move. It stops when the game ends. Not a time control: no side loses on it.
_Avoid_: Clock, move timer, latency (one call's time)

**Legal-move streak**:
The number of legal moves an LLM plays in a game before its first illegal move, whether or not a retry later recovers the game. Not applicable under **Enforced decoding**, where it would be true by construction.
_Avoid_: Legal move count, survival length

### Rating

**Player configuration**:
An LLM together with every setting it plays a game with: model, thinking and its **Thinking level** and **Thinking budget**, **LLM constraints**, **Standard rules** or **Chaos rules**, **Retry feedback**, **Turn memory**, **Tools**, sampling and **Prompt template**, chosen per LLM side when a game starts. Games count towards the same rating only if their player configurations are identical.
_Avoid_: Model (when settings differ), entrant, agent, bot

**Reference configuration**:
The one set of settings, everything in a **Player configuration** but the model, under which every model is compared with every other: thinking off, **Free**, **Standard rules**, 5 attempts per turn with *explained* **Retry feedback**, *fresh* **Turn memory**, no **Tools**, the default **Prompt template** and the model's own sampling. Chosen to be what a model can do unaided and what most games were played under, not where it plays best. A model's **Rating** under it is the model's overall number; every other Player configuration of that model is shown as how far it moves the Rating from there. A model without games under it has no overall number.
_Avoid_: Default settings, baseline, standard configuration, overall rating (pooled over settings)

**Ranking**:
The models in order of their **Rating** under the **Reference configuration**, each with its **Move-quality estimate** and its record, counting only games under the Reference configuration. It can be narrowed to some **Modes**, and then every number in it comes from those games alone, so a Mode with no path to an **Anchor** gives no Rating. It ranks models, never Player configurations.
_Avoid_: Leaderboard (for a list of Player configurations), standings, model rating

**Setting effect**:
How far changing exactly one setting of the **Reference configuration** moves a model's **Rating**: the Rating of that Player configuration minus the model's Rating under the Reference configuration, given with its uncertainty, which comes from both Ratings. None when either Rating is only an upper bound. A Player configuration that differs from the Reference configuration in more than one setting has a Rating, but no setting effect: which setting did what can't be told apart.
_Avoid_: Parameter effect, rule effect, delta, impact

**Rating**:
The Elo of a **Player configuration** on the chess.com scale, estimated only from its wins, draws and losses, with a **Forfeit** counted as a loss. Games against **Anchors** set the scale; **LLM faceoff** games only place configurations relative to each other, so a configuration with no path to an Anchor has no Rating. **Play LLM** games do not count towards it, since the human's strength is unknown; they count only towards the **Move-quality estimate**. Fitted over all games together, so the order they were played in does not matter. Always given with its uncertainty, or as an upper bound when every game was lost.
_Avoid_: Elo (alone), score, strength, performance

**Move-quality estimate**:
An Elo for a **Player configuration** inferred from its moves, regardless of who won: the human rating whose players would most likely have made the same moves. Given for each game and for each Player configuration; the configuration's estimate pools the moves of all its games rather than averaging the per-game estimates. Shown next to the **Rating** and never combined with it; the gap between the two is itself a finding.
_Avoid_: Estimated rating, accuracy Elo, game rating
