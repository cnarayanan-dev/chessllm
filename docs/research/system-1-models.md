# Which System 1 models to add, 2026-11-05

Research date: 2026-11-05. Scope: **System 1 models** (decision models: a state and typed questions in, a probability for every option out, one forward pass, no generated text) that could play chess in this benchmark on this machine. The state is the position, the question is a `choice` whose options are moves, and the most probable option is played; a **Retry** takes the next-best option. Nothing was downloaded or run for this note.

Selection rule (revised by the user): **five models, each under 10B parameters; two of them around 3B; at least one under 1B; the remaining slots go to the best S1MB-ranked models that run comfortably on an M3 Pro with 36 GB.** Darwin-27B-ZTC-v9 is out (too big), and appears only under Rejected.

Labels:
- **[Source]**: stated in the linked primary source.
- **[Computed]**: my calculation from the S1MB results dataset.
- **[Inference]**: my reading or estimate.

**Update, same day:** the user dropped the size rule. The section [Best-ranked that run on this Mac](#best-ranked-that-run-on-this-mac) goes down the board from #1 and recommends five models of any size that fit in 36 GB. The size-limited five below stay as the small-model set.

## TL;DR

- **Recommended five:** vLLM Semantic Router **d3-flash** (8.4B), PelaAI **KnowLine-4B-Gen5.5** (4.7B), Liquid AI **d1-2B** (1.9B), vLLM Semantic Router **d3-nano** (2.2B) and vLLM Semantic Router **d3-lite** (0.85B). They are the top S1MB entries in each size slot that have downloadable weights. Three are one d3 family, which gives one prompt format at three sizes.
- **One adapter can serve four of the five.** Ollama (v0.40.9+, this Mac has **0.40.0**) and llama.cpp's `llama-server` both implement **`POST /v1/systemone`**. Ollama ships `d3:9b`, `d3:2b` and `d1:2b` with MLX (Apple Silicon) tags. d3-lite isn't on Ollama, but llama.cpp has a `vllm_d3` converter; it also runs under the publisher's `d3_server.py`, which serves the same endpoint. KnowLine ships its own `/v1/systemone` server (`knowline_server.py --backend hf`). So the adapter is one HTTP client for `/v1/systemone` against two or three local servers. [Source, Inference]
- **The 255-option cap is the hard chess limit.** Every recommended runtime accepts up to **255 options** per `choice`. A position has at most 218 legal moves (typically 30-40), so **Listed** play always fits. A list that includes illegal moves has to be bounded (for example legal moves plus pseudo-legal or sampled distractors, capped at 255). Ollama's *generic* encoding stops at **26** options, but the d1/d3/pplx/kev encodings don't use that path. [Source]
- **Option order matters.** Options are shown as short codes (`A`…`Z`, `AA`…, or for d1 `00`…`99` beyond 26) in the order given. d3 ships a `permutation_average` switch (score forward and reversed, then average) because of this; KnowLine has option rotations. Use a fixed move order, for example sorted SAN or UCI. [Source]
- **S1MB has no chess benchmark.** The nearest are `boardgameqa-choice` (rules reasoning in text) and the Open-Jev **`tic-tac-toe-v1-choice`** (pick a move). Every small model scores close to the uniform baseline on tic-tac-toe (target mass 0.29-0.45). Expect near-random chess from all five. Their value is as a new kind of player, not as strong ones. [Computed, Inference]
- **Memory is not the problem, apart from Darwin.** The largest pick needs about 10 GB loaded (Ollama `d3:9b`). Darwin-27B-ZTC-v9 needs about 51 GB of BF16 weights, and its card asks for a CUDA GPU with about 60 GB. It has no quantised package anywhere. [Source]

## How S1MB ranks, and how I read it

S1MB English v1 has 137 benchmarks (Choice, Noul, Score). The leaderboard sorts by **Borda Score**: rank points on every benchmark, averaged over the cohort of complete models. Borda shifts when models are added. **Task Avg** is the mean of the three task scores after baseline adjustment, on a 0-100 scale. A **Generalization tasks only** view keeps just the six synthetic benchmarks that the training sets don't cover. [Source: [S1MB README](https://github.com/hotchpotch/S1MB), [SCORING.md](https://github.com/hotchpotch/S1MB/blob/main/evaluator/SCORING.md)]

I recomputed Borda and Task Avg from `viewer-summary.json` in [hotchpotch/s1mb-result](https://huggingface.co/datasets/hotchpotch/s1mb-result). This is the same file the Space's `/api/display/` serves, generated 2026-11-02, with **212 complete models**. My #1 (Darwin-27B-ZTC-v9, Borda 89.4) matches the leaderboard. Darwin's card cites 90.38 from an earlier, smaller cohort. Ranks below are mine, from that snapshot. [Computed]

Chess-relevant columns are given as **target mass** (the probability the model put on the right option):
- **bgqa**: `boardgameqa-choice`, 3 options;
- **ttt**: `open-jev--tic-tac-toe-v1-choice`, choosing a tic-tac-toe move.

## The recommended five

| # | Model | Publisher | Backbone, params | Licence (code / weights) | S1MB rank, Borda / Task Avg (of 212) | Generalization-only rank (of 214) | bgqa | ttt |
|---|---|---|---|---|---|---|---|---|
| 1 | [d3-flash](https://huggingface.co/vllm-sr/d3-flash) | vLLM Semantic Router (vLLM project) | Qwen3.5-9B, 8.39B incl. 0.46B vision | Apache-2.0 / Apache-2.0 | **19**, 80.6 / 62.6 | 20 | 0.67 | 0.37 |
| 2 | [KnowLine-4B-Gen5.5](https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5) | PelaAI (HF org; card: independent, unaffiliated with TypeSafe/Jev) | Qwen3.5-4B, 4.66B | Apache-2.0 / Apache-2.0 | **20**, 80.5 / **67.0** | 44 | **0.92** | 0.38 |
| 3 | [d1-2B](https://huggingface.co/LiquidAI/d1-2B) | Liquid AI | LFM3-VL-2B, 1.92B | LFM Open License v1.0 (both) | 80, 59.9 / 46.3 | 79 | 0.46 | 0.29 |
| 4 | [d3-nano](https://huggingface.co/vllm-sr/d3-nano) | vLLM Semantic Router | Qwen3.5-2B, 2.21B | Apache-2.0 / Apache-2.0 | **71**, 61.7 / 47.3 | 86 | 0.49 | **0.45** |
| 5 | [d3-lite](https://huggingface.co/vllm-sr/d3-lite) | vLLM Semantic Router | Qwen3.5-0.8B, 0.85B | Apache-2.0 / Apache-2.0 | 115, 49.6 / 38.7 | **123** (best under 1B) | 0.54 | 0.35 |

For scale: Darwin-27B-ZTC-v9 scores bgqa 0.94 and ttt 0.41. The best ttt on the board is 0.70 (autotrust/JEV-27B). [Computed]

**Why these**
1. **d3-flash.** The highest-ranked model under 10B with downloadable weights. The entries above it under 10B (kettei, Superion S1, Fastino GLiDE) are hosted APIs of unstated size. It is in Ollama as `d3:9b`.
2. **KnowLine-4B-Gen5.5.** Level with d3-flash on Borda, with the highest Task Avg and the highest boardgameqa of any model under 10B, at half d3-flash's size. It adds a second publisher and a second readout style: label-token logprobs from the ordinary LM head, where d3 uses a separate 255-way head.
3. **d1-2B (≈3B slot).** Strong on both the full board and the generalization view in the 2-3B band. It is the only pick from a non-Qwen family. It is tested on Apple Silicon (`mps`) by its publisher, and Liquid says it beats its own d1-3B.
4. **d3-nano (≈3B slot).** The top full-board rank in the 2-3B band, and the best tic-tac-toe score of the five. With d3-flash and d3-lite it makes a three-size ladder in one format.
5. **d3-lite (under 1B).** Best under 1B on the generalization view, which matters for an unseen task like chess. It is Apache-2.0. bekko-400m ranks higher on the full board but not here (see Runner-ups).

"Around 3B" is a stretch for both picks. The best-ranked models near 3B are 2B-class (Qwen3.5-2B, LFM3-VL-2B), and the 4B-class Qwen3.5-4B models are 4.5-4.7B. The only literal 3B models are d1-3B (no S1MB English result) and rsi-jev-v5.0-vl-3b (3.25B), which falls to #114 on the generalization view. [Computed]

## Running them on this Mac

| Model | Easiest local route | Memory | Quantised variants | MPS / CUDA-only parts | Own uv environment |
|---|---|---|---|---|---|
| d3-flash | `ollama pull d3:9b` (Ollama ≥ 0.40.9). `/v1/systemone` on :11434 | 10.09 GB peak loaded on Apple Silicon (MXFP8, 4,096 ctx) [Source: Ollama page] | `d3:9b-mxfp8` (MLX, 10 GB), `d3:9b-nvfp4` (MLX, 7.7 GB), `d3:9b-q8_0` (GGUF, 10 GB) | Ollama MLX runner. HF route: `flash-linear-attention` is optional and GPU-only; without it transformers uses its PyTorch reference. No MPS statement on the card | HF route: `uv run --no-project --python 3.12 --with torch --with transformers==5.17.0 --with accelerate --with safetensors --with pillow --with torchvision python d3_server.py` (bf16 ~17 GB) |
| KnowLine-4B-Gen5.5 | `knowline_server.py --backend hf --port 8080` (transformers only, bf16). `/v1/systemone` | ~9.3 GB of bf16 weights plus activations [Source: file sizes] | None published. Its SGLang path quantises to FP8 at load, CUDA only | SGLang is CUDA. The hf backend uses `device_map="auto"` through accelerate, so MPS should work [Inference] | `uv run --no-project --python 3.12 --with torch --with "transformers==5.12.1" --with accelerate --with requests python knowline_server.py ...` |
| d1-2B | `ollama pull d1:2b` (MLX bf16, 3.9 GB) or `d1:2b-mxfp8` (2.4 GB); or `llama-server` | ~4 GB | MLX bf16, MXFP8, NVFP4 tags; GGUF repos | Card code picks `cuda`, then `mps`, then `cpu`, bf16 on MPS. Measured on an M5 Pro: 30 ms per question, 640 ms for a 3.4k-token state [Source] | `--with "transformers>=5.14" --with torch --with torchvision --with pillow` |
| d3-nano | `ollama pull d3:2b` (`d3:2b-mxfp8`, 3.1 GB) | 3.62 GB peak loaded [Source: Ollama page] | MXFP8 (MLX), Q8_0 | as d3-flash | as d3-flash |
| d3-lite | Not on Ollama. Run `d3_server.py` (bf16, 1.7 GB, fine on CPU or MPS), or convert with llama.cpp's `conversion/vllm_d3.py` and serve with `llama-server` | ~2 GB | None published | as d3-flash | as d3-flash |

Notes:
- **Speed.** No figures exist for the M3 Pro. For a chess prompt (FEN, move list and 30-40 coded options, roughly 0.5-1.5k tokens) the cost is mostly prefill. Scaling from d1's M5 Pro figures, I expect about 0.1-0.5 s per move for the 2B models, around 0.5-1 s for 4B and 1-3 s for 9B. That is two orders of magnitude below an LLM thinking. [Inference]
- **NVFP4.** HF NVFP4 checkpoints (for example `autotrust/JEV-35B-NVFP4`) target NVIDIA. Ollama's MLX runner on Apple Silicon does serve its own "nvfp4" tags, and the installed qwen3.8 is one. So an Ollama `-nvfp4` tag is usable here; an HF NVFP4 repo is not. [Source: Ollama kev page, `candidate-models.md`]
- **Quantisation and the readout.** Ollama's kev page reports that quantisation "changed some individual answers and probabilities even where aggregate accuracy was close". Its d3 page says the published scores are for the original checkpoints, not the quantised packages. Prefer MXFP8 or Q8_0 over NVFP4 at these sizes. [Source]
- **Like Maia-2.** Each publisher pins a different transformers (d3 5.17.0, KnowLine 5.12.1, d1 ≥5.14, pplx 5.17.0 with torch 2.14). Each HF-route model therefore needs its own `uv run --no-project` environment that starts a local `/v1/systemone` server, the pattern `chessllm/engines/maia2_model.py` uses. All load with `trust_remote_code=True`, which runs the publisher's Python. Pin a revision.

## Limits that matter for chess

| | d3 (flash, nano, lite) | KnowLine-4B-Gen5.5 | d1-2B |
|---|---|---|---|
| Max options per `choice` | 255 (`MAX_OPTIONS`, 255-way readout) | 255 (`MAX_LABELS`) | 255 in llama.cpp. The HF code assigns any number of single-token codes from a fallback pool |
| Option codes | `A`…`Z`, `AA`…: one token each, shown as `A: <key or key: description>` | `A.`…, `AA.`…, after `Answer:` | `A`…`Z` up to 26, then `00`…`99`, then fallbacks |
| Option order | Matters. `permutation_average=1` scores the reversed order too and averages | Matters. Layout supports rotations | Matters [Inference: positional codes] |
| Context | HF: no `max_length` set (backbone 262k). Ollama packages: 4,096 tokens [Source: Ollama page] | Read-twice applies to requests ≤3,000 tokens. Trained to ~12k (9B card) | 32k (d1-3B card). Ollama `d1:2b`: 125K |
| State | Free text or JSON (FEN plus move list fine). The system prompt says to treat the state as data | Text or chat; JSON rendered | String, JSON or null |
| Questions per request | 1-64 (Ollama) | 1-64 | 1-64 (Ollama) |

Consequences:
- **Listed** (legal moves only) always fits under 255. Use the move strings as option keys with `null` descriptions, so the model sees `A: Nf3`.
- **Free** (illegal moves allowed): the option set has to be defined and stay at 255 or fewer. One option is every pseudo-legal move, which ignores check and is almost always under 255; another is legal moves plus a fixed number of random distractors. The choice changes what "Free" means for a System 1 model, so it belongs in the Player configuration. [Inference]
- **Retries cost nothing extra.** One call returns every option's probability, so the next-best move is already known. [Inference]
- Every option shown is a candidate the model can pick, so **Enforced decoding** has no meaning for these models: the option list *is* the constraint.

## One adapter for all five

The `/v1/systemone` request shape is the same everywhere: `state`, plus `questions: {id: {type, instructions, criteria}}`. The answer is `{"answers": {id: {"choice", "probabilities", "confidence"}}, "usage"}`. It is served by:
- **Ollama** `POST /v1/systemone` with `model`: d3 (all sizes), d1, d1-omni, pplx-decider(-flash), kev, laya, nimble, tev1, clef, strands-decider [Source: [docs](https://github.com/ollama/ollama/blob/main/docs/capabilities/decision.mdx), [library](https://ollama.com/search?c=decision)];
- **llama.cpp** `llama-server` (`tools/server/server-decision.cpp`): vllm-d3, pplx-decider, lfm2/lfm3 d1, kev, laya, clef, vllm-decision2, lev and others, 255 options [Source];
- **Publisher servers**: `d3_server.py` (`GET /v1/models`, `POST /v1/systemone`), `knowline_server.py`, vLLM Semantic Router `vllm-sr serve -e` (`--platform auto|cpu|cuda|rocm`; no Metal).

So one `SystemOnePlayer` taking a base URL and a model name covers all five. Ollama alone covers d3-flash, d3-nano and d1-2B.

Known server bugs worth noting:
- llama.cpp [#30402](https://github.com/ggml-org/llama.cpp/issues/30402): d3 answers change when a shorter request shares the batch. Send one request at a time.
- Ollama [#19292](https://github.com/ollama/ollama/issues/19292): GGUF decision models without a decision head (the KnowLine style) have been refused since 0.40.4.
- Ollama [#19062](https://github.com/ollama/ollama/issues/19062): d1 vision gives repeated HTTP 500s. This affects images only.

## Runner-ups

| Model | Publisher | Params | S1MB full / gen. rank | Why not in the five |
|---|---|---|---|---|
| [KnowLine-9B-Gen1](https://huggingface.co/PelaAI/KnowLine-9B-Gen1) | PelaAI | 9.65B | 23 / **10** | The best under 10B on the generalization view, and the obvious swap for slot 1 or 2. But it is bf16 only (19.3 GB), with no Ollama or GGUF package, and bgqa 0.62 |
| [pplx-decider-flash-v1.2](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2) | Perplexity | 4.54B | 28 / 21 | Close to KnowLine-4B overall. It is on Ollama (`pplx-decider-flash:4b`, MLX tags). Its own code wants CUDA and falls back to float32 (~18 GB) elsewhere |
| [d3-mini](https://huggingface.co/vllm-sr/d3-mini) | vLLM Semantic Router | 4.54B | 27 / 33 | A fourth d3 size; `d3` / `d3:4b` on Ollama |
| [d1-3B](https://huggingface.co/LiquidAI/d1-3B) | Liquid AI | 3.12B | no English S1MB result | The only literal 3B. `d1:3b`, MPS-tested, 32k context. Liquid ranks it below d1-2B |
| [KnowLine-2B-Gen1](https://huggingface.co/PelaAI/KnowLine-2B-Gen1) | PelaAI | 2.27B | 90 / 76 | Alternative to d3-nano for publisher variety |
| [bekko-system-one-v0-400m](https://huggingface.co/hotchpotch/bekko-system-one-v0-400m) | Yuichi Tateno (hotchpotch, the S1MB maintainer) | 0.395B | **63** / 157 | Best under 1B on the full board, but weak on the generalization view, and its card notes 77 training subsets shared with S1MB. **No licence assigned.** It is an encoder whose candidates don't attend to each other, so option order shouldn't matter, and it has a 3,800-token candidate budget |

## Rejected

| Model | Publisher | Reason |
|---|---|---|
| [Darwin-27B-ZTC-v9](https://huggingface.co/FINAL-Bench/Darwin-27B-ZTC-v9) | FINAL-Bench | #1 on S1MB (Borda 89.4 in this snapshot; bgqa 0.94). But it has 25.6B parameters and 51.3 GB of BF16 weights; the card asks for Python 3.12 and **a CUDA GPU with ~60 GB**; it uses its own `autojev` code; and there is no GGUF, MLX, Ollama or llama.cpp support, nor any quantised repo. It doesn't fit in 36 GB, and the user's rule now excludes it |
| kettei-fat / kettei-chub (Sqwish), Superion S1 (Punky Tiger Labs), GLiDE (Fastino), Jev 1.13 / 1.14 (TypeSafe) | various | Hosted APIs with no downloadable weights and unstated size (ranks 2, 4, 22, 25, 33, 38) |
| lihe07/span-02 | lihe07 | Rank 34, but the model repo isn't publicly reachable |
| [rsi-jev-v5.0-vl-3b](https://huggingface.co/shgao/rsi-jev-v5.0-vl-3b) | shgao | 3.25B, rank 78, but #114 on the generalization view. Custom tower/scorer files, no library or server |
| [Lev1-3.7B](https://huggingface.co/theaviv/Lev1-3.7B) | theaviv | Actually 5.06B. Rank 68 |
| [jpt-0.8b](https://huggingface.co/kirp/jpt-0.8b) | kirp | CC-BY-NC-4.0; rank 148 |
| d3-edge, Decision-2.0 Kai/Eos, Jev-Style-0.8B, decider-0.8b/2b/4b (Mapika), laya family (convai innovations), Vela-2.0-0.3B, d1-omni-600M | various | Below d3-lite in the sub-1B band (ranks 142-188), or no English S1MB result (Vela, d1-omni) |
| autotrust JEV-9B / JEV-35B, GEV-26B | autotrust | JEV-9B has no S1MB result. The others are over 10B |

## Open risks

- **Chess strength is unknown and probably near random.** No S1MB benchmark is chess. Tic-tac-toe move choice sits near baseline for every small model, and none was trained on chess. The first games should be checked against the random player and the weakest **Anchor** before anything else. [Inference]
- **Order bias.** With 30-40 coded options, a model may favour early codes. Measure it: replay the same positions with options shuffled (or with d3's `permutation_average=1`), and fix one ordering in the Player configuration.
- **What "Free" means** for a System 1 model has to be decided (which illegal options, how many) and recorded, because 255 is the cap.
- **Ollama upgrade.** Ollama 0.40.0 is installed here, and d3 needs 0.40.9 or later. The d3 packages' 4,096-token context is enough for FEN plus SAN history plus 218 options [Inference], but not for very long prompts.
- **Quantised packages aren't the scored checkpoints.** S1MB and publisher numbers are for BF16. Ollama's MXFP8/NVFP4 tags may change individual answers.
- **KnowLine and d3-lite need Python servers.** They run the publishers' `trust_remote_code`, MPS is unverified for both, and KnowLine's transformers pin (5.12.1) differs from d3's (5.17.0).
- **Licences.** d1-2B is under the LFM Open License: free for research and for companies under US$10M revenue. The others are Apache-2.0.
- **Borda moves with the roster.** Ranks are from the 2026-11-02 snapshot, and new entries arrive daily.
- **A bigger model that would fit.** Outside the rule, Ollama's `d3:27b-nvfp4` (MLX, 17 GB) packages d3 (27B, S1MB #5). It is the way to get a top-five S1MB model onto this Mac if the size rule is ever relaxed.

## Best-ranked that run on this Mac

Rule (user, 2026-11-05): no size limit. Take the best-ranked S1MB models that actually run on this Mac:
- M3 Pro, 36 GB unified memory, no CUDA;
- Ollama can be upgraded to the latest version;
- aim for **≤ ~24 GB loaded**, leaving room for the app and macOS's GPU limit of about 27 GB.

Ranks are from my recomputation of the 2026-11-02 snapshot: full board of 212, generalization view of 214. The table covers the full-board top 32 plus everything in the generalization top 15. Every generalization top-15 entry is already in the full-board top 32.

**How the routes work.** A quantised file is only useful if its runtime keeps the **decision readout**: the extra 255-way head, or the option-label logits of the ordinary LM head. Three kinds of route do:
- llama.cpp's `llama-server` serves `/v1/systemone` for GGUFs that carry decision metadata. Types include `pplx-decider`, `vllm-d3`, `kev`, `vllm-decision2` and `openjev`.
- Ollama's MLX packages serve the same endpoint for the models they package.
- Some publishers ship MLX servers of their own.

A plain community GGUF (for example mradermacher's) has no decision metadata, so it would need a custom adapter that reads label logprobs. NVFP4/AWQ/FP8 safetensors repos are CUDA (vLLM/SGLang) only.

| Rank full / gen. | Model | Publisher | Params | Weights | Best route ≤ ~24 GB here | Fidelity of that route | Verdict |
|---|---|---|---|---|---|---|---|
| 1 / 8 | Darwin-27B-ZTC-v9 | FINAL-Bench | 25.6B | y (51.3 GB bf16) | none: no GGUF/MLX/Ollama, own `autojev` code, card asks for CUDA with ~60 GB | n/a | **No** |
| 2 / 6 | kettei-fat | Sqwish | ? | n (hosted API) | none | n/a | **No** |
| 3 / 3 | [StartLux-Decision-v1.1-27B-Instant](https://huggingface.co/startlux-models/StartLux-Decision-v1.1-27B-Instant) | StartLux | 27.4B | y, CC-BY-NC-4.0 | Publisher [GGUF](https://huggingface.co/startlux-models/StartLux-Decision-v1.1-27B-Instant-GGUF) **Q4_K_M, 16.55 GB**, on mainline `llama-server` (Metal, `-ngl 99`; non-causal flag, so one slot and a micro-batch that holds the whole prompt). Also MLX 4-bit (~16 GB) with the publisher's server | Publisher's own benchmark (DecisionPivot, 7,800 items): Q4_K_M 80.2, Q8_0 80.7, BF16 80.5. Not S1MB. The MLX 4-bit was **not** compared, and their 4B model's 4-bit MLX lost 8.2 points | **Yes** |
| 4 / 50 | Superion S1 | Punky Tiger Labs | ? | n (hosted) | none | n/a | **No** |
| 5 / 7 | [d3](https://huggingface.co/vllm-sr/d3) (27B) | vLLM Semantic Router | 26.1B | y, Apache-2.0 | **Ollama `d3:27b-nvfp4`** (MLX, 17 GB). Or GGUF [`turintech/d3-27B-Artemis` IQ4_XS](https://huggingface.co/turintech/d3-27B-Artemis-GGUF) (14.95 GB, 16.4 GiB peak) or ggml-org Q4_K_M (19.4 GB) on `llama-server`. `d3:27b-mxfp8` needs 28.6 GB, too much | Ollama: only the original's scores are published. TurinTech IQ4_XS: 97.1% same answers as the original on their test set (which chose the file); ggml-org Q4_K_M closer still | **Yes** |
| 6 / 1 | KnowLine-31B-Gen1 | PelaAI | 31.3B (Gemma-4-31B) | y (62.6 GB bf16) | Only plain community GGUFs (mradermacher Q4_K_M 18.7 GB) with no decision metadata; NVFP4 repos are CUDA. Needs a custom label-logprob adapter on llama.cpp | none published. Its S1MB run itself used **FP8 at load** (SGLang) | Possible, not ready |
| 7 / 9 | Darwin-27B-ZTC-v5 | FINAL-Bench | 25.6B | y (53.8 GB) | none | n/a | **No** |
| 8 / 5 | pplx-decider-v1.2 | Perplexity | 26.1B | y (52.2 GB) | Only CUDA NVFP4 (machinez). Ollama's `pplx-decider` packages **v1**, not v1.2, and v1 is not on S1MB | n/a | **No** |
| 9 / 14 | matilda-jev-v1.5 | Maincode | 26.1B | y (52.2 GB) | no quant found | n/a | **No** |
| 10 / 18 | Gimbal-27B | Superwheat | 25.6B | y (51.8 GB) | no quant found | n/a | **No** |
| 11 / 4 | [pplx-decider-v1.1-27b](https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b) | Perplexity | 26.1B | y, Apache-2.0 | GGUF [Livesport Q5_K_M-dyn](https://huggingface.co/Livesport/pplx-decider-v1.1-27b-GGUF) (~18-20 GB), head kept as `cls.output.weight`, mainline `llama-server` (`pplx-decider` type). Or [mlx-community 4-bit](https://huggingface.co/mlx-community/pplx-decider-v1.1-27b-4bit) (~16 GB at runtime) with its own `/v1/systemone` server | Q5_K_M-dyn: KL 0.0008 vs bf16, 1 of 240 decisions flipped. MLX 4-bit: 33 of 33 test rows agree, max Δp 0.03. Not S1MB | **Yes** |
| 12 / 11 | amos-1-large | mukaddamzaid | 27.5B | y (55.4 GB) | no quant found | n/a | **No** |
| 13 / 15 | torchcast-decision-27b | torchcast-ai | 25.6B | y, CC-BY-NC | plain mradermacher GGUFs (Q4_K_M 16.5 GB) without decision metadata; custom adapter | none | Possible, not ready |
| 14 / 13 | KnowLine-35B-A3B-Gen1.5 | PelaAI | 36.0B MoE | y (71.9 GB) | CUDA NVFP4 only | n/a | **No** |
| 15 / 12 | KnowLine-26B-A4B-Gen2.5 | PelaAI | 25.8B MoE (4B active) | y (51.6 GB) | plain mradermacher GGUF Q4_K_M 16.8 GB; custom adapter | none (S1MB run at FP8) | Possible, not ready |
| 16 / 34 | rsi-jev-v6.1-vl-27b | shgao | 26.7B | y (54.5 GB) | none | n/a | **No** |
| 17 / 29 | Darwin-27B-ZTC-v2 | FINAL-Bench | 25.6B | y | none | n/a | **No** |
| 18 / 2 | meta-encoder | Meta | ~30B (Muse-Glimmer) | gated | community MLX 4-bit (~19 GB), but it is an embedding "match" model, and the S1MB score comes from a bespoke adapter (`meta-encoder-cot-combinations-hpc`) with no System One server | n/a | **No** (not reproducible) |
| 19 / 20 | d3-flash | vLLM Semantic Router | 8.4B | y | Ollama `d3:9b` (~10 GB) or bf16 (17 GB) | Ollama packages unmeasured; bf16 is the scored checkpoint | **Yes** |
| 20 / 44 | KnowLine-4B-Gen5.5 | PelaAI | 4.7B | y | bf16 9.3 GB with `knowline_server.py --backend hf` | bf16 is *more* precise than its S1MB run (FP8 at load) | **Yes** |
| 21 / 30 | [jebadiah-27b](https://huggingface.co/frontier-infra/jebadiah-27b) | frontier-infra | 26.9B | y, Apache-2.0 | Publisher GGUF Q4_K_M 16.8 GB (or Q5_K_M 19.5 GB) via `jeb serve` / llama-server `/completion`; MLX 4-bit 15.1 GB. The Ollama route is **capped at 20 options** (top-logprobs) | Q4_K_M: 258 of 260 same as bf16. Q5_K_M: 255 of 260. MLX 4-bit: 248 of 260 | Yes, but only through llama-server (Ollama's 20-option cap rules out chess) |
| 22 / 22 | GLiDE | Fastino | ? | n (hosted) | none | n/a | **No** |
| 23 / 10 | KnowLine-9B-Gen1 | PelaAI | 9.65B | y | bf16 19.3 GB, hf backend | bf16 (S1MB at FP8) | Yes (tight next to another model) |
| 24 / 31 | Decision-2.0-Vega-27B | vLLM Semantic Router | 29.4B | y | Publisher GGUF Q4_K_M 15.9 GB, `llama-server --embeddings --pooling none` (`vllm-decision2` type, now in mainline) | none published | Yes, unvalidated |
| 25 / 27 | kettei-chub | Sqwish | ? | n (hosted) | none | n/a | **No** |
| 26 / 32 | [openjev](https://huggingface.co/openjev/openjev) | OpenJev | 27.4B | y, CC-BY-NC | Publisher GGUF Q4_K_M 16.5 GB / Q5_K_M 19.2 GB / Q6_K 22.1 GB on llama-server; MLX 4-bit ~15 GB with their `/v1/systemone` shim (exact readout) | Q4_K_M agrees with 16-bit on 96.6% of 1,789 rows (−0.34 points); Q8_0 98.2% | Yes |
| 27 / 33 | d3-mini | vLLM Semantic Router | 4.5B | y | Ollama `d3` / `d3:4b` (5.6 GB) | unmeasured package | Yes |
| 28 / 21 | pplx-decider-flash-v1.2 | Perplexity | 4.5B | y | Ollama `pplx-decider-flash:4b` (MLX) or GGUF | unmeasured package | Yes |
| 29 / 25 | kev-27b | Jared Palmer | 25.6B | y, Apache-2.0 | GGUF [kdercksen Q4_K_M](https://huggingface.co/kdercksen/Kev-27B-GGUF) 15.8 GB (head at Q8_0), mainline llama-server. Ollama `kev:27b-nvfp4` uses **25.6 GiB resident** (M5 Max), above the target | Ollama page: 27B NVFP4 205/231 public JevBench vs 202/231 bf16 (one public set) | Yes (GGUF) |
| 30 / 23 | JEV-27B | autotrust | 27.1B | y | Ollama `autotrust-jev:27b-vl` packages the **VL sibling**, which is not on S1MB. Community GGUFs are of unclear lineage | n/a | Not the ranked checkpoint |
| 31 / 19 | AutoJev-27B | denis-pplx | 26.1B | y | GGUF Q4_K_M 15.8 GB, but only on the `jev.cpp` fork | none | Fork only |
| 32 / 80 | Whittle-Reflex-25B-A3B | logic65 | 25.6B MoE (3B active) | y, Apache-2.0 | Publisher GGUF **Q4_K_M 15.7 GB** or Q6_K 21.1 GB on mainline llama-server (`pplx-decider` type) | **Its S1MB score was measured on a GGUF (Q8_0, 27.2 GB, too big here).** On the publisher's slice, Q4_K_M gave the same answers as Q8_0 on 64 of 64 checks. Trained on S1MB's own train splits (card's overlap note) | Yes |

Sources: model cards and quant repos linked above; [Ollama d3](https://ollama.com/library/d3), [kev](https://ollama.com/library/kev) and [pplx-decider](https://ollama.com/library/pplx-decider) pages (which name their source checkpoints); S1MB per-result `model.settings` (KnowLine: "SGLang (FP8 at load)"; Whittle: "llama.cpp llama-server … Q8_0.gguf"; all others bf16 on CUDA).

### The five

| | Model | Publisher | Rank full / gen. | Route here | Loaded (approx.) |
|---|---|---|---|---|---|
| 1 | **StartLux-Decision-v1.1-27B-Instant** | StartLux | 3 / 3 | Publisher GGUF Q4_K_M on `llama-server -ngl 99` | ~17-18 GB |
| 2 | **d3 (27B)** | vLLM Semantic Router | 5 / 7 | Ollama `d3:27b-nvfp4`, or TurinTech IQ4_XS / ggml-org Q4_K_M GGUF | ~16-20 GB |
| 3 | **pplx-decider-v1.1-27b** | Perplexity | 11 / 4 | Livesport GGUF Q5_K_M-dyn on `llama-server`, or mlx-community 4-bit with its server | ~16-20 GB |
| 4 | **d3-flash** | vLLM Semantic Router | 19 / 20 | Ollama `d3:9b` (MXFP8/Q8_0) | ~10 GB |
| 5 | **KnowLine-4B-Gen5.5** | PelaAI | 20 / 44 | bf16, `knowline_server.py --backend hf` | ~10 GB |

That is four publishers, all served over `/v1/systemone`. These are the five best-ranked entries with a working route here. Everything ranked above #20 is a hosted API, has no quantised route, or needs a custom adapter (KnowLine-31B, KnowLine-26B-A4B, torchcast).

- **Runner-ups:** jebadiah-27b (#21; best-documented quantisation, but llama-server only), openjev (#26; good quantisation evidence, NC licence), kev-27b (#29), Whittle-Reflex-25B-A3B (#32; the only S1MB score measured on a GGUF, and the fastest 25B-class here with 3B active, but trained on S1MB train splits), KnowLine-9B-Gen1 (#23, #10 on the generalization view).
- **One 27B at a time.** Two 27B models (~17-20 GB each) cannot both stay loaded within ~24-27 GB of GPU memory. A faceoff between two of them reloads every turn. Pair a 27B with d3-flash or KnowLine-4B, or play it against an Anchor or an LLM.
- **Speed.** A dense 27B prefilling a ~1k-token chess prompt on an M3 Pro is likely several seconds per move. The 4-9B models take about a second; Whittle (3B active) about a second. [Inference]

### Where quantisation is a real risk to the readout

- **d3 27B on Ollama `d3:27b-nvfp4`: real risk, unmeasured.** Ollama publishes only the original's scores. Its kev page notes that quantisation changed individual answers, and NVFP4 is the most aggressive format here. Prefer ggml-org's Q4_K_M (closest to the original per TurinTech's comparison) or TurinTech IQ4_XS (97.1% agreement) on `llama-server`. The bf16 original doesn't run here, so check on a sample of chess positions by comparing the two quantised routes with each other. Also: llama.cpp #30402 (d3 answers change when batched with a shorter request) means one slot.
- **StartLux: low risk for GGUF Q4_K_M, high for MLX 4-bit.** The publisher measured the GGUFs within half a point of BF16, but did not test the MLX 4-bit, and in their own study a 4-bit MLX build of a sibling model lost 8.2 points. Use the GGUF.
- **pplx-decider-v1.1-27b: low risk.** Q5_K_M-dyn flipped 1 of 240 decisions (KL 0.0008); MLX 4-bit agreed on 33 of 33 rows.
- **d3-flash: low to moderate.** MXFP8/Q8_0 at 9B, unmeasured. Use `d3:9b-q8_0` or `-mxfp8`, not `-nvfp4`.
- **KnowLine-4B-Gen5.5: none here.** bf16 is the full checkpoint. Its S1MB score was at FP8, so it should be at least as good here.
- **Chess-specific risk for all of them.** Every published agreement figure is on tasks with 2 to about 20 options. A chess position has 30-40 options, many of them near-tied, and those are exactly the decisions a quantisation flip changes. Expect more top-move changes than the published rates, and measure: the same positions on two quantisations, counting how often the top move changes. [Inference]

## Sources

- S1MB: [leaderboard](https://huggingface.co/spaces/hotchpotch/S1MB-leaderboard), [results dataset](https://huggingface.co/datasets/hotchpotch/s1mb-result) (`viewer-summary.json`, 2026-11-02), [repo](https://github.com/hotchpotch/S1MB), [SCORING.md](https://github.com/hotchpotch/S1MB/blob/main/evaluator/SCORING.md)
- Model cards and code: [d3-flash](https://huggingface.co/vllm-sr/d3-flash), [d3-mini](https://huggingface.co/vllm-sr/d3-mini) (`d3_format.py`, `d3_runtime.py`, `d3_server.py`, `requirements.txt`), [d3-nano](https://huggingface.co/vllm-sr/d3-nano), [d3-lite](https://huggingface.co/vllm-sr/d3-lite), [KnowLine-4B-Gen5.5](https://huggingface.co/PelaAI/KnowLine-4B-Gen5.5) (`INFERENCE.md`, `knowline_server.py`), [KnowLine-9B-Gen1](https://huggingface.co/PelaAI/KnowLine-9B-Gen1), [d1-2B](https://huggingface.co/LiquidAI/d1-2B), [d1-3B](https://huggingface.co/LiquidAI/d1-3B) (`prompt.py`), [d1-3B-GGUF](https://huggingface.co/LiquidAI/d1-3B-GGUF), [pplx-decider-flash-v1.2](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2), [bekko-system-one-v0-400m](https://huggingface.co/hotchpotch/bekko-system-one-v0-400m), [Darwin-27B-ZTC-v9](https://huggingface.co/FINAL-Bench/Darwin-27B-ZTC-v9)
- Ollama: [decision docs](https://github.com/ollama/ollama/blob/main/docs/capabilities/decision.mdx), `decision/*.go`, `docs/openapi.yaml`, library pages [d3](https://ollama.com/library/d3), [d1](https://ollama.com/library/d1), [pplx-decider-flash](https://ollama.com/library/pplx-decider-flash), [kev](https://ollama.com/library/kev)
- llama.cpp: `tools/server/server-decision.cpp`, `conversion/vllm_d3.py`, issues #30402, #31150
- HF model list: `https://huggingface.co/api/models?filter=system-one&sort=downloads`
