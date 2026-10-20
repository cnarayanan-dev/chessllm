# Does a board image help small vision LLMs play legal moves? 2026-10-20

A small offline probe of idea 13 in `forfeit-solutions-brainstorm.md`: show the model a picture of the board. The models lose track of the board. They move onto their own pieces and move pieces from squares they left (`gemma-vs-llama-faceoffs-2026-10-19.md`). The hope was that a picture would make the current position obvious. **It doesn't.** On these samples the image did not raise first-attempt legality for gemma3:12b. It changed what kind of mistake gemma made: moves onto its own pieces more than doubled. Neither model could read the board from the image. The one positive sign, for qwen3.5:9b, rests on 7 positions and is mostly about speed, not about reading the board.

## What is known already

- **Ollama.** `/api/chat` takes `images` on a message: "Optional list of inline images for multimodal models", each item "Base64-encoded image content" ([Ollama API: chat](https://docs.ollama.com/api/chat)). The Python client also accepts raw bytes. `ollama show` lists `vision` for gemma3:12b, qwen3.5:9b and qwen3.8:latest. llama3:8b has none.
- **gemma3.** Images are "normalized to 896 x 896 resolution and encoded to 256 tokens each" ([Gemma 3 model card](https://ai.google.dev/gemma/docs/core/model_card_3)). Our 512 px boards are scaled up to fit, so 256 tokens cover 64 squares, about 4 tokens per square.
- **qwen3.5.** The model card calls it a "Causal Language Model with Vision Encoder" with "early fusion training on multimodal tokens". It gives no image resolution or token count for still images ([Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)). Alibaba's API docs give "h x w / (32 x 32) + 2" tokens per image for its Qwen vision models ([Model Studio](https://help.aliyun.com/en/model-studio/vision-model/)) [Unverified for the Ollama build]. On that rule a 512 px board would be about 258 tokens.
- **Published results.** Text usually beats images:
  - IsoBench gives the same problems, chess included, as an image or as text. Models show a "consistent preference towards textual representations". Images cost GPT-4 Turbo 18.7 points and Claude 3 Opus 28.7 ([IsoBench, arXiv 2404.01266](https://arxiv.org/abs/2404.01266)).
  - SEAM is the exception: "In chess and chemistry, models frequently demonstrate comparable or slightly superior performance with vision inputs". Across its domains it blames visual perception failures "that lead to hallucinations" ([SEAM, arXiv 2508.18179](https://arxiv.org/html/2508.18179)). It tests large models (Qwen2.5-VL-72B and up), not 9-12B ones.
  - Neither benchmark asks for a legal move without a list of legal moves.
  - I found no published results for 8-12B local VLMs reading a board diagram.

## What was tested

`scripts/probe_board_images.py`, offline and not wired into the game.

- **Positions.** 60 positions were sampled once from the first attempts of LLM Turns in `games/`, Free sides under Standard rules only, and frozen in `board-images-positions.json`.
  - They are spread by ply: opening ≤ 20, middlegame 21-50, late > 50.
  - The logs hold no true endgames: no logged position has ≤ 26 points of pieces, because the games rarely trade down.
  - 8 of the 60 have the side to move in check, far more than the ~2% in real games, so checks are over-represented on purpose.
  - The sample is interleaved, so any first N positions are spread too. Only the first 20 were run (5 opening, 5 middlegame, 5 late, 5 in check).
- **Image.** `chess.svg.board`, rasterised with resvg (`resvg-py`, a new dev dependency), 512 × 512. The board is seen from the mover's side, with files and ranks labelled. There is no last-move or check highlight.
- **Conditions,** each one first attempt with no Retry. Every request is otherwise the game's: `OllamaPlayer`, `think=False`, the `ReasonedMoveAnswer` schema, and sampling from `sampling.toml` (model defaults).
  - **text**: `turn_messages` exactly as the game builds it (system prompt, then PGN and FEN).
  - **text+image**: the same, plus one line, "Board image: the current position, seen from your side (Black at the bottom).", with the image on the user message.
  - **image**: the image and a short instruction only (colour, "Black to move", reply in SAN). No PGN and no FEN, so castling and en passant rights are not given.
- **Judging.** `chessllm.game.judge` decides legality. A legal move not in exact SAN is a Notation slip. An illegal move is given an error kind:
  - own piece on target;
  - no such piece (no piece of that type, or the named from-square doesn't hold it);
  - king in check (the move would leave or put its king in check);
  - unreachable (the piece exists but can't move there).
- **Perception check** on the first 8 positions (4 for qwen). The model is asked to list the side to move's pieces, once from the image alone and once from the FEN alone. The list is scored against the real board.
- **Models.** gemma3:12b on 20 positions. qwen3.5:9b on 7 positions; the run was cut short, see Caveats. qwen3.8 was not run (Caveats).

## Results

First attempt, one answer per position and condition:

| Model | Condition | n | Legal | Own piece on target | No such piece | Unreachable | King in check | Notation slips | Latency median / mean | No answer (timeout) |
|---|---|---|---|---|---|---|---|---|---|---|
| gemma3:12b | text | 20 | **5 (25%)** | 5 | 1 | 7 | 2 | 0 | 14.6 / 17.2 s | 0 |
| gemma3:12b | text+image | 20 | **5 (25%)** | 12 | 0 | 3 | 0 | 1 | 17.3 / 20.0 s | 0 |
| gemma3:12b | image | 20 | 4 (20%) | 11 | 0 | 4 | 1 | 0 | 15.6 / 16.5 s | 0 |
| qwen3.5:9b | text | 7 | 0 of 1 answered | 1 | 0 | 0 | 0 | 0 | 109 s (one answer) | **6 of 7** |
| qwen3.5:9b | text+image | 7 | 4 of 6 answered | 1 | 0 | 1 | 0 | 0 | 14.6 / 32.4 s | 1 of 7 |
| qwen3.5:9b | image | 6 | 1 of 5 answered | 2 | 0 | 2 | 0 | 1 | 12.1 / 15.3 s | 1 of 6 |

gemma3:12b by stage (legal / positions):

| | opening | middlegame | late | in check |
|---|---|---|---|---|
| text | 0/5 | 3/5 | 1/5 | 1/5 |
| text+image | 1/5 | 2/5 | 2/5 | 0/5 |
| image | 2/5 | 1/5 | 1/5 | 0/5 |

Paired, with the same 20 positions for gemma: text+image was legal where text was not in 4 positions, and the reverse in 4. Image only: +3 / −4.

Perception, the side to move's pieces listed and scored against the board (all its pieces, about 12-16):

| Model | Read from | n | Recall | Precision | Exactly right |
|---|---|---|---|---|---|
| gemma3:12b | FEN | 8 | 16% | 17% | 0 of 8 |
| gemma3:12b | image | 8 | 42% | 41% | 0 of 8 |
| qwen3.5:9b | FEN | 4 | 28% | 36% | 0 of 4 |
| qwen3.5:9b | image | 4 | 35% | 41% | 0 of 4 |

Raw rows, with every reply, are in `board-images-results.jsonl`. `uv run python -m scripts.probe_board_images --summary` prints the tables.

## What it means

1. **For gemma3:12b the image adds nothing to legality.**
   - Text and text+image are both 5 of 20, with 4 positions won and 4 lost.
   - The image changes the kind of error. Moves onto its own pieces go from 5 to 12 of the 15 illegal moves; "unreachable" moves go from 7 to 3.
   - The answers with the image look like generic developing moves. Its 12 own-piece moves include Nc3 with a knight on c3, Ne2 onto e2, and Qf6 onto f6.
2. **With the image alone, gemma plays an opening from memory.**
   - 17 of its 20 image-only answers are knight moves, 14 of them to Nf3, Nf6, Nc3 or Nc6, whatever the position. 8 of those knight moves landed on its own pieces.
   - It sees "a chess board" and answers with the most common move, not the position in front of it.
3. **Neither model can read the board,** from either source.
   - gemma got 42% of its pieces right from the image and 16% from the FEN. Its lists put kings on a1, five pawns on a2, and a pawn on h8. Not one list was exactly right.
   - The image beats the FEN as a source of perception, but 40% recall is not a usable board. The "stale board" errors in the faceoffs are perception errors, made at the very start of the Turn.
   - Small models doing poorly with FEN fits Hwang et al.'s 0% board-state score for 3-8B models (`llm-chess-notation.md`). The images confirm SEAM's "visual perception failures that lead to hallucinations".
4. **qwen3.5:9b: the image mostly made it answer in time.**
   - With thinking off, its `reasoning` field decodes the FEN character by character ("r3kb1r is 8 chars: r, ., ., k, b, ., r -> no, wait"). Under the GPU load here it ran past 120 s on 6 of 7 text prompts.
   - With the image it answered 6 of 7, 4 of them legal. That is a hint, not a result: 7 positions, and the gain is mostly answers that arrived in time.
   - Its perception from the image was as poor as gemma's.
5. **Latency.** The image cost gemma about 2-3 s per call (about 256 extra prompt tokens). Under the game's 300 s limit that is not a problem.

## Caveats

- **The sample is small.** 20 positions for gemma, 7 for qwen3.5 and 4-8 for perception, with one sample per condition at the models' default temperature (1.0). A ±4 swing at n = 20 is noise. The test can only rule out a large effect: an image turning gemma's 25% into 50%+ would very likely have shown up.
- **The sample is harder than a typical Turn.** It over-represents checks and late positions, and it comes from games full of illegal moves. gemma's 25% here is not comparable with its 53% first-attempt legality in the faceoffs.
- **Latencies are inflated.** A gemma3:12b vs llama3:8b faceoff was running on the same GPU throughout.
  - gemma calls share that runner, which takes one request at a time, so they queued behind the faceoff.
  - With qwen3.5:9b loaded as well, the 36 GB machine swapped hard: 13-14 GB of swap, and gemma fell to 0.5 tokens/s for a while. Ollama also unloaded gemma once to fit qwen, so the faceoff had to reload it.
  - qwen's timeouts are partly this load; the game's limit is 300 s, not the 120 s used here. A single text call made earlier, while only the faceoff was running, answered in 25 s (256 tokens).
- **qwen3.5 was cut at 7 of 12 positions,** and **qwen3.8 (18 GB) was not run.** Loading it next to the faceoff's two models would have forced Ollama to unload them, and the probe was already past its 60-minute budget.
- **Only one rendering was tried:** 512 px, python-chess's default style, no highlights. A last-move or check highlight might help in-check positions; gemma was 0 of 5 there with an image.
- The image-only condition omits castling and en passant rights, so a legal castle there would be luck.

## Recommendation

**Don't add an image option to the Player configuration now.** On this evidence it doesn't raise legality for gemma3:12b, the only fast vision model here. It also makes gemma's commonest error, moving onto its own pieces, more common. The models can't read a board from an image, which is the job the image was supposed to do. Cheaper text ideas aim at the same problem and work for every model, llama3:8b included: a piece list, status lines, and diagnosed Retry feedback (brainstorm ideas 1, 2 and 5). A per-model image option would also split vision and non-vision models into configurations that can't be compared.

Worth one more look later: qwen3.5:9b with thinking off and an image, uncontended, on 60 positions, text vs text+image. That is about 40 minutes on a free GPU (`--models qwen3.5:9b --limit 60 --conditions text text+image --perception 0 --timeout 300`).

If it is ever built, it takes:

- **`OllamaPlayer`**: the `images` field on the user message of each Turn (base64 or bytes). `Message` in `chessllm/players.py` would need an optional image, or the player would render the board from the FEN itself. Retries resend the same image.
- **Rendering in the app**: resvg-py (or cairosvg plus a system cairo) becomes a runtime dependency, not a dev one.
- **A new Player configuration setting**, e.g. `board_image: bool`, on `LlmSide` and `Settings`. It also needs `PlayerConfiguration` in `chessllm/leaderboard.py`, the game log's side description (ADR 0004), the batch CLIs and the Settings modal. The setting is allowed only for models whose Ollama capabilities include `vision`.
- **ADRs.** CONTEXT.md says games count towards the same Rating only if their Player configurations are identical (ADR 0005). An image changes what the model is shown, so it must be a configuration setting and never a silent default. The game-log ADR 0004 gets one more side field. It also runs into the prompt-identity gap the brainstorm notes: the user message is built in code and not part of the configuration's identity, so the image setting has to be explicit.

## Files

- `scripts/probe_board_images.py`: the probe (sampling, rendering, prompts, judging, perception scoring, summary).
- `tests/test_probe_board_images.py`: tests for its pure parts.
- `docs/research/board-images-positions.json`: the frozen 60-position sample.
- `docs/research/board-images-results.jsonl`: every call, with the raw reply.
