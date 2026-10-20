# Which LLMs to add next, 2026-10-20

Research date: 2026-10-20. Scope: models the benchmark could add beyond llama3:8b, gemma3:12b, qwen3.5:9b and qwen3.8:latest. That means local models via Ollama on this machine, chess-specialised fine-tunes, and hosted reference points. Nothing was pulled or run for this note.

Labels:
- **[Source]**: stated in the linked primary source.
- **[Measured]**: from this repo's game logs.
- **[Inference]**: my reading or estimate.

## TL;DR

- **Reasoning is the strongest lever, and the size class has moved on since the current four were picked.** On LLM Chess, the open models with a positive Elo are almost all thinking models of about 27-30B. The leader is **qwen3.8-27b at 846 ± 166**, which is already installed. qwen3.5-9b (also installed) sits at −258 without thinking and −200 with it. Non-reasoning models average 0.7% wins against 45.4% for reasoning models. [Source: [LLM Chess data](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv), [paper](https://arxiv.org/html/2512.01992v1)]
- **The catch on this machine is time, not memory.** A dense 27-30B model thinking takes a median of **92 s per attempt** here, at most 249 s, against the 300 s turn timeout. [Measured] Mixture-of-experts (MoE) models with about 3-4B active parameters (gemma4:26b, gpt-oss:20b, qwen3.6:35b) should think 4-5x faster for the same memory. [Inference]
- **Gemma 4 is the obvious same-class upgrade, and nobody has measured its chess.** gemma4:12b (8 GB) and gemma4:26b (MoE, 18 GB) are Apache 2.0, with vision, tools and a thinking switch. They are absent from every chess leaderboard found. [Source: [Ollama](https://ollama.com/library/gemma4), [Google](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html)]
- **Meta's Muse Glimmer 30B has the lowest wrong-move rate of any model on LLM Chess: 0.7 per 1000 moves** (Elo 214 ± 178). That bears directly on this benchmark's forfeit problem. [Source: LLM Chess data]
- **Chess fine-tunes that fit the chat/JSON format are rare.** The useful one is **Qwen3-8B-Chess** (ChessArena, SFT+RL, Apache 2.0). It has an 87.6% legal-move rate *without* a legal-move list, against 9.8% for base Qwen3-8B. It is published only as safetensors, so it needs a GGUF conversion. [Source: [ChessArena](https://arxiv.org/html/2509.24239v4), [HF](https://huggingface.co/ljcnju/Qwen3-8B-Chess)] The strong small "chess LLMs" are engines with a language-model tokeniser, not chat models.
- **Vision is a weak lever on the evidence, but it is no longer one model's quirk.** `ollama show` lists `vision` for qwen3.5:9b and qwen3.8 as well as gemma3:12b, and for every shortlisted model but two. The forfeit brainstorm's "fits one model only" is out of date. SEAM found chess about equal from a board image or from FEN. [Source: [SEAM](https://arxiv.org/html/2508.18179v1)]

## This machine

- Apple M3 Pro, 36 GB unified memory, 65 GB free disk (85% of 460 GB used). Ollama's store is 42 GB.
- In use now: a gemma3:12b vs llama3:8b faceoff batch (about 15 GB resident for the two runners).
- **What fits.** One model of up to about 20 GB on disk fits comfortably. macOS lets the GPU use roughly two thirds to three quarters of unified memory by default, about 24-27 GB. [Inference] Two ~18 GB models in one faceoff can't both stay loaded, so Ollama would reload on every turn. Pair a big model with a small one, or play it against itself.
- **Speed.** The M3 Pro has 150 GB/s of memory bandwidth, and generating a token reads every active weight once. [Inference] Upper bounds:
  - about 9 tok/s for a dense 27-30B model at 4-bit (~17 GB);
  - about 20 tok/s for a 12B;
  - about 40-50 tok/s for an MoE with ~4B active.
- **Measured latency per attempt** (`games/*.jsonl`, all LLM constraints mixed): [Measured]

| Model | Thinking | Attempts | Median | p90 | Max |
|---|---|---|---|---|---|
| llama3:8b | off | 1390 | 1.4 s | 1.9 s | 6 s |
| gemma3:12b | off | 725 | 6.4 s | 9.9 s | 56 s |
| qwen3.8:latest | off | 86 | 13.4 s | 40.6 s | 106 s |
| qwen3.8:latest | on | 23 | 92 s | 195 s | 249 s |

- **How a model is added today.** One line in `LLM_MODELS` (`chessllm/models.py`): `LlmModel(name, thinking: bool)`. `OllamaPlayer` (`chessllm/ollama_player.py`) always sends `format=<JSON schema>` (an enum under Enforced decoding) and `think=<bool>`, with a 300 s timeout. Three gaps matter for the candidates below:
  1. **`think` is a bool.** Ollama also takes a level string matching the model's `thinking.values` (e.g. gpt-oss `low/medium/high`, qwen3.8 `low/medium/xhigh`), and `false` works only "if the model permits it". gpt-oss has no `false`, so its thinking can't be turned off. [Source: [Ollama thinking docs](https://docs.ollama.com/capabilities/thinking)] Sending `think=False` to it would log a configuration as "thinking off" while it thinks. Needs: a thinking level on `LlmModel`/`LlmSide`, part of the Player configuration (S-M).
  2. **No images.** `Message` has only role and content. A board image needs an `images` field, a renderer (python-chess SVG to PNG) and a `vision` flag on `LlmModel` (M).
  3. **Chat only.** A base model continuing PGN needs `/api/generate` with `raw=True` and a different prompt and parser: a second player adapter (M).

## What plays chess better, and why

LLM Chess plays the LLM as Black against a random player and Komodo Dragon, and fits an Elo on the same Dragon scale as this project's Anchors: Skill s = 125 × (s + 1), so Skill 1 = 250. The random player is −122. The LLM gets a board and a legal-move tool on demand, and answers in UCI. Its Elo therefore predicts this benchmark's **Listed** play more than **Free**. [Source: [README](https://github.com/maxim-saplin/llm_chess), [paper](https://arxiv.org/html/2512.01992v1); data last updated 2026-10-10]

| Model (as listed) | Elo ± 95% | Wrong moves / 1000 | Note |
|---|---|---|---|
| qwen3.8-27b@q4_k_m | **846 ± 166** | 63 | best open model; installed here |
| unsloth qwen3.8-27b@q2_k_xl | 541 ± 183 | 50 | same model, 2-bit: −300 Elo |
| Ternary-Bonsai-2-27B (high) | 403 ± 172 | 92 | ternary Qwen3.8-27B, 8.3 GB |
| deepseek-r1-0528 (671B) | 300 ± 134 | 8 | |
| qwen3.6-27b@q4_k_s | 270 ± 149 | 20 | |
| muse-glimmer-30b@q4_k_m | 214 ± 178 | **0.7** | fewest illegal moves |
| qwen3.5-35b-a3b@q4_k_m | −26 ± 144 | 32 | MoE, 3B active |
| nemotron-3-nano | −200 ± 94 | 73 | |
| qwen3.5-9b thinking (bf16) | −200 ± 127 | 71 | installed here |
| gpt-oss-20b medium | −232 ± 129 | 25 | games last ~7 moves: protocol failures |
| qwen3.5-9b (q8, no thinking) | −258 ± 133 | 49 | installed here |
| llama3.1-8b | −796 ± 280 | 77 | |
| gemma-3-12b, llama3-8b, ministral-8b, phi-4, mistral-small-24b, magistral-small | no Elo (0 wins) | 18-212 | lose on instruction-following |
| Frontier: gpt-6-astra-high, claude-opus-5-5-high, gemini-3.8-flash-high | 1614 / 1575 / 1546 | | reference points |

Not on LLM Chess: Gemma 4, Ministral 3, Granite 4.x, OLMo 3, qwen3.6-35b-a3b.

Findings:

1. **Reasoning models win, non-reasoning ones don't.** [Source: [LLM Chess paper](https://arxiv.org/html/2512.01992v1)] Reasoning models average 45.4% wins against 0.7%, and 24.4% against 71.9% instruction-following errors. Every ~8B non-reasoning model scored 0% win/loss. ChessQA found GPT-5 at 79.3% with thinking against 44.0% without ([ChessQA](https://arxiv.org/html/2510.23948v1)).
2. **Quantisation matters at this size.** The same Qwen3.8-27B drops from 846 (Q4_K_M) to 541 (Q2_K_XL) to 403 (ternary). [Source] The installed qwen3.8 is `nvfp4`, which LLM Chess hasn't measured; expect close to Q4. [Inference]
3. **Chess-specific RL fixes legality more than any prompt.** [Source: [ChessArena](https://arxiv.org/html/2509.24239v4)] Qwen3-8B-Chess (SFT on ChessGPT data and arena games, then GRPO with Stockfish rewards) reached:
   - 87.6% legal moves without a list, against 9.8% for base Qwen3-8B;
   - Glicko 1776 against 1335, on ChessArena's own pool. That pool puts the random player at 1524 and Maia-1100 at 2220, so 1776 is well below a 1100 human.
4. **Completion-style prompting of base models is the only route to strong *Free* play, and only at GPT-3.5-instruct scale.** [Source: [Dynomight 1](https://dynomight.net/chess/), [Dynomight 2](https://dynomight.net/more-chess/), [Acher](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/)] gpt-3.5-turbo-instruct was about 1750 with an illegal move in 0.3% of moves. Every open base model Dynomight tried (Llama-3.2-3B up to 70B, Qwen-2.5-72B) lost every game, and instruction tuning made each base/instruct pair worse. That is the prior for an 8B base model: weak chess, but possibly fewer stale-board errors than its instruct twin. [Inference] (See also `llm-chess-notation.md`.)
5. **Frontier models are far ahead, but still fail Free.** Game Arena (FEN + PGN in, SAN out, no list, retries then forfeit, the closest protocol to Free): Gemini 3 Pro and Flash needed fewer than 0.2 rethinks per game; DeepSeek V3.2 and Claude Haiku 4.5 often needed more than 5-10. [Source: [Game Arena report](https://arxiv.org/html/2609.31473v1)]

## Candidates

Sizes are Ollama's default 4-bit tags. RAM is about the size on disk plus context. All tags are from [ollama.com/library](https://ollama.com/library), checked 2026-10-20.

### (a) Direct upgrades in the same size class (7-14B, thinking optional)

| Model | Tag, disk | Capabilities | Licence | Why | Expected strength | To add |
|---|---|---|---|---|---|---|
| **Gemma 4 12B** | `gemma4:12b`, ~8 GB | vision, audio, tools, thinking | Apache 2.0 ([Google](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html), [release log](https://ai.google.dev/gemma/docs/releases): 12B added 2026-06-03) | Successor of gemma3:12b at the same size. Thinking on/off in one model, which gemma3 can't do. | Unmeasured. Gemma 4 makes large reasoning gains over Gemma 3 (AIME 2026: 26B 88.3% against Gemma 3 27B 20.8%, [Ollama](https://ollama.com/library/gemma4)). Expect it above gemma3 with thinking on. [Inference] | `LlmModel("gemma4:12b", thinking=True)`. Confirm the thinking levels with `ollama show` after pulling. Speed like gemma3 with thinking off. |
| Ministral 3 14B | `ministral-3:14b`, 9.1 GB | vision, tools, JSON | Apache 2.0 | A third non-Google, non-Qwen family as a non-thinking comparator. | Ministral-8B (2024) scored 0 wins on LLM Chess. Expect gemma3-like. | `thinking=False`. |
| Granite 4.2 8B | `granite4.2:8b`, 5.3 GB | tools, JSON, thinking (low/high, default on) | Apache 2.0 | Enterprise model with structured output; small thinker. | Granite 3.1 8B: 0 wins on LLM Chess. Low. | Needs thinking levels (gap 1). |
| OLMo 3 7B Think | `olmo-3:7b-think` / `:7b-instruct` | tools, thinking | Apache 2.0, open training data | The only family whose training data can be searched for PGN, which helps explain results. | Unmeasured. Likely low. | `thinking=True`. |
| Qwen 3.5 4B | `qwen3.5:4b`, 3.3 GB | vision, tools, thinking | Apache 2.0 | A floor below qwen3.5:9b for a size curve. | −558 thinking on LLM Chess. | `thinking=True`. |

### (b) Reasoning / thinking models (where the chess strength is)

| Model | Tag, disk | Arch | Capabilities | Licence | Why | Expected strength | Cost here | To add |
|---|---|---|---|---|---|---|---|---|
| **Gemma 4 26B A4B** | `gemma4:26b`, 18 GB (`26b-a4b-it-qat` 16 GB) | MoE, 3.8B active | vision, tools, thinking | Apache 2.0 | A big reasoning model that can think within 300 s. GPQA 82.3%. | Unmeasured. Its reasoning benchmarks are close to Qwen3.6-27B-class, so I expect 0-800 on LLM Chess's scale. [Inference] | ~40 tok/s; faceoff with a small model only | `thinking=True` |
| **Muse Glimmer 30B** (Meta) | `muse-glimmer:30b`, 18 GB | dense, ~30B, released 2026-08-10 | vision, tools, adjustable thinking | Apache 2.0 | Fewest illegal moves on LLM Chess (0.7/1000). Meta's successor to the llama3 already here. | 214 ± 178 | Like qwen3.8: ~13 s off, ~90 s+ thinking | Thinking levels (gap 1). Check `ollama show` |
| **gpt-oss 20B** | `gpt-oss:20b`, 14 GB | MoE, 4-bit MXFP4 | tools, thinking low/medium/high, **can't be turned off** | Apache 2.0 | The most-used local reasoning model, with a known LLM Chess number for cross-checks. | −232 (medium). Its LLM Chess games lasted ~7 moves from protocol errors, which a JSON schema avoids. | ~40-50 tok/s | **Needs** thinking levels (gap 1). Its Reasoning field doesn't exist (thinking always on). |
| Qwen 3.6 35B A3B | `qwen3.6:35b`, 24 GB | MoE, 3B active | vision, tools, thinking | Apache 2.0 (Qwen) | A fast Qwen thinker beside the slow qwen3.8. | qwen3.5-35b-a3b: −26; 3.6 unmeasured | Fast, but 24 GB leaves no room for a second model | `thinking=True` |
| Ternary Bonsai 2 27B | `bonsai-2:27b`, 8.3 GB | ternary Qwen3.8-27B ([HF card](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf)) | vision, tools, thinking | Apache 2.0 | A quantisation axis: the same model as qwen3.8 at a third of the size. | 403 ± 172 | Small, but uses custom ternary kernels; check that Ollama's runner speed holds up | `thinking=True` |
| Nemotron 3 Nano 30B | `nemotron-3-nano:30b`, 18-24 GB | Mamba-MoE, 3.5B active | tools, thinking | NVIDIA Open Model Licence | Another fast thinker. | −200 | Fast | `thinking=True` |
| Phi-4-reasoning 14B, DeepSeek-R1 8B, Magistral 24B | `phi4-reasoning:14b`, `deepseek-r1:8b`, `magistral:24b` | dense | thinking (Phi: always) | MIT / MIT / Apache 2.0 | Older reasoners. | R1 distills and Magistral: 0 wins on LLM Chess | slow for their strength | Skip |

The installed qwen3.8 is already the strongest open model on LLM Chess. **Running it with thinking under Listed and Listed enforced is the cheapest way to get a model that wins games,** before pulling anything. Its thinking time (median 92 s, max 249 s) is close to the 300 s timeout, so raise `TIMEOUT_S` or use the `low` level. [Measured, Inference]

### (c) Vision models (the board-image idea)

- **Already here.** gemma3:12b, qwen3.5:9b and qwen3.8 all report `vision` in `ollama show`. So do every Gemma 4 size, Muse Glimmer, Ministral 3, Qwen 3.6 and Bonsai 2.
- **No dedicated vision model is worth a pull.** The open question is the prompt, not the model.
- **The evidence is weak.** SEAM gave the same chess positions as images and as FEN. Models were "comparable or slightly superior" with images on chess, but gemma-3-12b was worse from images overall (0.401 against 0.458 from text). [Source: [SEAM](https://arxiv.org/html/2508.18179v1)]
- **What it would show.** Whether a stale board is a reading problem (an image fixes it) or a tracking problem (it doesn't).
- **Cost.** M: gap 2 above, and a new prompt, hence a new Player configuration.
- **Test.** Replay logged positions with and without an image, as in the forfeit brainstorm's idea 1.
- If a small dedicated VLM is wanted anyway: `qwen3-vl:8b` (vision, thinking).

### (d) Chess-specialised models

| Model | Format | Fits chat/JSON? | Strength | Licence | To add |
|---|---|---|---|---|---|
| **Qwen3-8B-Chess** ([HF](https://huggingface.co/ljcnju/Qwen3-8B-Chess), RL; also `-SFT`) | Qwen3 chat. FEN (+ optional legal list) in; UCI in `<answer>` tags out ([ChessArena](https://arxiv.org/html/2509.24239v4)) | Mostly. It speaks chat. A JSON schema with a free `move` string should work; UCI answers count as Notation slips (ADR 0002). It was trained without PGN history, so the current prompt is off its training distribution. | 87.6% legal without a list; 1776 Glicko (ChessArena pool) | Apache 2.0 | **M.** Download 16 GB safetensors (`Qwen3ForCausalLM`, 8.2B), convert with llama.cpp `convert_hf_to_gguf.py`, quantise with `llama-quantize` to Q4_K_M (~5 GB), then `ollama create qwen3-8b-chess -f Modelfile` with the Qwen3 template ([Ollama import](https://docs.ollama.com/import): Ollama doesn't quantise GGUF on import). Pull `qwen3:8b` (5.2 GB) as its untuned control. A variant prompt in its own format (FEN, UCI) would be a separate Player configuration. |
| Qwen2.5-7B-Chess-MMXL-GRPO | GGUF exists ([HF](https://huggingface.co/mradermacher/Qwen2.5-7B-Chess-MMXL-GRPO-GGUF)) | Chat | 0 wins on LLM Chess (`qwen2.5-7b-chess-mmxl`) | none stated | Skip. |
| ChessGPT-chat-v1 (2.8B, 2023) | Pythia-style chat; community GGUF | Loosely | Research model ([paper](https://arxiv.org/abs/2306.09200)) | Apache 2.0 | Skip: superseded. |
| LFM2.5-230M-Chess ([HF](https://huggingface.co/mlabonne/LFM2.5-230M-Chess)) | 80-token board encoding; one token per move; host masks illegal moves | **No**: an engine with an LM interface | ~1500 raw, ~2004 with depth-3 search | LFM 1.0 | Not a Player. Possibly a cheap, calibrated-ish **Anchor**, needing its own adapter. |
| chess-llama 23M ([HF](https://huggingface.co/lazy-guy12/chess-llama)) | UCI movetext, Lichess games | No | ~1400 (author) | none stated | As above. |
| Praxis chess reasoner (Qwen3.5 2B/4B, GGUF + Modelfile) | Explains mistakes from an evidence graph | No: not a move player | n/a | Apache 2.0 | Skip. |
| Base models for PGN completion: `llama3:8b-text`, `llama3.1:8b-text-q4_K_M` | Raw text | No: needs gap 3 (completion adapter) | Expected weak at 8B (Dynomight) | Llama 3 / 3.1 Community | **M.** `llama3:8b-text` (4.7 GB) is the base of the installed `llama3:8b`, so it isolates the effect of instruction tuning. Enforced decoding still works: `format` as a string enum. |

### (e) Reference points

- **Ollama cloud models, no new adapter.**
  - Tags such as `gemma4:31b-cloud`, `gpt-oss:120b-cloud`, `deepseek-v4.1-flash`, `kimi-k3`, `glm-5.3` and `mistral-large-4` run on ollama.com but are called through the same local API after `ollama signin` ([Ollama cloud](https://docs.ollama.com/cloud)).
  - Adding one is a `models.py` line, if `format` and `think` are honoured for cloud models. The docs don't say, so test one call first.
  - Costs: usage limits per plan, network latency, and weights that may change under the same name. Record the date of each game.
- **Frontier APIs** (Claude Opus 5.5, GPT-6, Gemini 3.8 Flash: about 1550-1610 on LLM Chess).
  - **What it takes:** a new player adapter implementing the `players.py` port (`reply(messages, allowed_moves) -> LlmReply`) for each provider, about S-M each. Enforced decoding maps to each provider's JSON-schema output with an enum. Thinking maps to its effort setting.
  - **Also needed:** API keys, cost per game (dozens of calls, more with retries), a longer timeout, and the provider and model version in the Player configuration.
  - **Value:** a ceiling for the Rating scale, and a check that the harness itself doesn't cause forfeits.

## Recommended shortlist, in order

Disk: about 73 GB for all six (including `qwen3:8b`) with the conversion's leftovers removed, and 65 GB are free. **Pull the first three (~44 GB) now and decide on the rest after their first games.** For 5, also allow ~21 GB of working space during the conversion (16 GB download plus the 5 GB result).

1. **Gemma 4 12B.** The same-size upgrade of gemma3:12b, with thinking on/off in one model. Works with the current code.
   `ollama pull gemma4:12b`, ~8 GB.
2. **Gemma 4 26B A4B.** A reasoning MoE fast enough to think within the 300 s timeout. It tests "reasoning wins" on a model that is practical here.
   `ollama pull gemma4:26b`, ~18 GB (or `gemma4:26b-a4b-it-qat`, 16 GB).
3. **Muse Glimmer 30B.** The fewest illegal moves of any model on LLM Chess, aimed at the forfeit problem. Meta's successor to llama3. Needs thinking levels to set its effort.
   `ollama pull muse-glimmer:30b`, 18 GB.
4. **gpt-oss 20B.** The standard local reasoning baseline, with a known LLM Chess number. Needs thinking levels first (gap 1), because its thinking can't be turned off.
   `ollama pull gpt-oss:20b`, 14 GB.
5. **Qwen3-8B-Chess, with `qwen3:8b` as its control.** Chess RL took legality from 9.8% to 87.6% without a list; this is the only chess fine-tune that fits the chat format. Needs a GGUF conversion (see (d)).
   `ollama pull qwen3:8b`, 5.2 GB; the converted fine-tune is ~5 GB.
6. **llama3:8b-text.** The base of the installed llama3:8b, testing whether PGN completion beats instruction tuning. Needs the completion adapter (gap 3).
   `ollama pull llama3:8b-text`, 4.7 GB.

**Before any pull:** play the installed qwen3.8 with thinking (`low` or default) under Listed and Listed enforced, with a longer timeout. It is the best open chess model measured, and it is already on disk.

## Caveats

- LLM Chess Elos come from a different protocol (a legal-move tool, UCI, playing Black against random and Dragon), and many intervals are ±150-250. Use them to rank candidates, not to predict this benchmark's Free results.
- Gemma 4, Ministral 3, Granite 4.2, OLMo 3 and Qwen 3.6 35B have no published chess numbers. Their expected strengths above are inferences from general reasoning benchmarks.
- Some library facts come from Ollama's pages, not the vendors' (e.g. Gemma 4 12B's size; Muse Glimmer's architecture, where secondary sources agree it is dense). The thinking levels of each model must be read from `ollama show` after pulling.
- Speeds for unpulled models are bandwidth estimates, not measurements.

## Sources

- Ollama library: [newest](https://ollama.com/library?sort=newest), [gemma4](https://ollama.com/library/gemma4) and [tags](https://ollama.com/library/gemma4/tags), [qwen3.8](https://ollama.com/library/qwen3.8), [qwen3.6](https://ollama.com/library/qwen3.6/tags), [qwen3.5](https://ollama.com/library/qwen3.5/tags), [gpt-oss](https://ollama.com/library/gpt-oss), [muse-glimmer](https://ollama.com/library/muse-glimmer), [ministral-3](https://ollama.com/library/ministral-3), [granite4.2](https://ollama.com/library/granite4.2), [olmo-3](https://ollama.com/library/olmo-3/tags), [bonsai-2](https://ollama.com/library/bonsai-2), [nemotron-3-nano](https://ollama.com/library/nemotron-3-nano), [llama3 tags](https://ollama.com/library/llama3/tags)
- Ollama docs: [thinking](https://docs.ollama.com/capabilities/thinking), [import](https://docs.ollama.com/import), [cloud](https://docs.ollama.com/cloud)
- Google: [Gemma 4 under Apache 2.0](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html), [Gemma releases](https://ai.google.dev/gemma/docs/releases)
- Meta Muse Glimmer: evaluation report linked from the Ollama page (research.meta.ai/static/muse-glimmer-methodology); release date and licence from [AI Weekly](https://aiweekly.co/node/9642) (secondary)
- Prism ML: [Ternary-Bonsai-2-27B card](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf)
- LLM Chess: [repo](https://github.com/maxim-saplin/llm_chess), [data/elo_refined.csv](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv) (2026-10-10), [notes](https://github.com/maxim-saplin/llm_chess/blob/main/docs/notes.md), [paper](https://arxiv.org/html/2512.01992v1)
- [ChessArena](https://arxiv.org/html/2509.24239v4); [Qwen3-8B-Chess](https://huggingface.co/ljcnju/Qwen3-8B-Chess)
- [Game Arena technical report](https://arxiv.org/html/2609.31473v1)
- [ChessQA](https://arxiv.org/html/2510.23948v1); [SEAM](https://arxiv.org/html/2508.18179v1)
- Dynomight: [chess](https://dynomight.net/chess/), [more chess](https://dynomight.net/more-chess/); [Acher](https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/)
- Chess models: [LFM2.5-230M-Chess](https://huggingface.co/mlabonne/LFM2.5-230M-Chess), [chess-llama](https://huggingface.co/lazy-guy12/chess-llama), [ChessGPT](https://huggingface.co/Waterhorse/chessgpt-chat-v1), [Qwen2.5-7B-Chess-MMXL-GRPO GGUF](https://huggingface.co/mradermacher/Qwen2.5-7B-Chess-MMXL-GRPO-GGUF), [Praxis reasoner](https://huggingface.co/praxis-chess/praxis-chess-reasoner-qwen3.5-4b-GGUF)
