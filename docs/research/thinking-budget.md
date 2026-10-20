# Limiting how long a local model thinks, 2026-10-20

Research date: 2026-10-20. The question: how to bound the **Thinking** of local reasoning models (9-30B, Ollama, M3 Pro 36 GB) so a **Turn** ends well inside the 300 s limit, and what that costs in chess strength. Nothing was run for this note: a qwen3.8 vs gemma3:12b faceoff had the GPU. Facts come from Ollama's docs and its source at tag `v0.40.0` (the installed version), papers, and this repo's game logs.

Labels:

- **[Source]**: stated in the linked primary source.
- **[Measured]**: from this repo's game logs.
- **[Inference]**: my reading or estimate.

## TL;DR

- **Recommendation: a token budget, enforced in two calls.** Call 1 sets `num_predict` to the budget. If it stops with `done_reason == "length"`, call 2 resends the conversation with the thinking so far as an assistant prefill, closes the thinking, and asks for the answer under the same `format` schema. This is s1's "budget forcing" and Qwen3's "thinking budget". It works with Ollama 0.40.0 as it is, it caps thinking exactly, and it doesn't depend on hardware. [Source + Inference, see Implementation]
- **Make it a setting, `thinking_budget` (tokens per attempt, None = unbounded), in the Player configuration.** Keep the 300 s timeout as a safety net: a Turn that still times out is a Forfeit, as now. Tokens, not seconds, so a game means the same on any machine.
- **Effort levels are a second, softer knob.** For qwen3.8, `think="low"` only adds a system-prompt sentence ("Keep your thinking brief...") and caps nothing. qwen3.5:9b has no levels, only on/off. [Source: Ollama `model/renderers/qwen35.go`]
- **The repo's `think=True` already runs qwen3.8 at `medium`, not the model's default `xhigh`.** Ollama maps `true` to `"medium"`, and the qwen3.8 renderer adds no instruction for medium. Measured here: median ~1,000 thinking tokens per attempt, max ~3,200, ~12.7 tok/s, so 300 s is about 3,700 tokens. LLM Chess's qwen3.8 (Elo 846) used about 12,800 completion tokens per move. **Our qwen3.8 is not the configuration LLM Chess measured.** [Source + Measured]
- **More thinking helps chess a lot for weaker models, then saturates.** On LLM Chess, with effort levels: o3-mini goes from −184 (low, 660 tokens/move) to 403 (high, 6,500 tokens); gpt-5-nano from −117 to 683; gpt-5-mini from −56 to 759. Strong models are flat between medium and high (gpt-5.5: 1532 vs 1528). [Source: LLM Chess data]
- **Truncated thinking can be worse than no thinking at small budgets.** At 700 tokens, R1-Distill-32B scored 28.9 with truncated thinking and 51.3 with thinking skipped (AMC 2023). For Qwen3, thinking off matched or beat thinking at every shared budget up to 2,048 tokens on GSM8K and MATH-500. [Source: NoThinking, Coupling Tax] So pick a budget that only cuts the long tail, and measure it. No published study sweeps a forced thinking budget in chess.

## What the repo does today

- `OllamaPlayer.reply` (`chessllm/ollama_player.py`) makes one non-streaming `chat` call with `think=self._thinking` (a bool), `format=<schema>`, and sampling options. An `httpx.TimeoutException` after `TIMEOUT_S = 300` s raises `LlmTimeout`, which `game.py` logs as `result: "timeout"`. The Turn ends in a Forfeit.
- **`think=True` on qwen3.8 means `medium`.** `ThinkValue.String()` returns `"medium"` for `true`. `qwen38ReasoningInstructions` adds nothing for `medium`, the "low" sentence for `low`, and an "xhigh" sentence for `xhigh`, for any other string, and when `think` is unset. [Source: [types/model/thinking.go](https://github.com/ollama/ollama/blob/v0.40.0/types/model/thinking.go), [model/renderers/qwen35.go](https://github.com/ollama/ollama/blob/v0.40.0/model/renderers/qwen35.go)] `ollama show` lists `default medium` locally, but the renderer's `Thinking()` says `xhigh`, and so does Qwen's card ([Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)). Pass the level explicitly so the default doesn't matter.
- **`format` and thinking now work in one pass.** Since [PR #18479](https://github.com/ollama/ollama/pull/18479) (merged 2026-09-22, in v0.40.0), the server sends the parser's thinking-close string (`</think>` for Qwen) with the schema. The runner leaves thinking free and constrains only what follows. Before that, Ollama ran an unconstrained pass, cancelled it, and re-prompted under the grammar. Two details matter here: [Source]
  - "A model that answers without thinking stays unconstrained." The grammar waits for a `</think>` that never comes.
  - "A raw generate prompt keeps the format from its first token."
- **`num_predict` counts thinking and answer together.** A cap hit inside the thinking returns an empty `content`. Ollama reports this in issues [#16583](https://github.com/ollama/ollama/issues/16583) and [#17561](https://github.com/ollama/ollama/issues/17561). Here `judge` would read `""` as an `invalid` move and use up a retry. So a bare cap silently turns "no answer" into an illegal move.
- **Measured qwen3.8 thinking, `think=True`** (32 attempts in `games/*.jsonl`; tokens ≈ characters / 4): median ~1,030 thinking tokens, p90 ~2,050, max ~3,200. A linear fit gives latency ≈ 7.4 s + 0.079 s per token, i.e. ~12.7 tok/s, so 300 s ≈ 3,700 tokens. The median attempt took 79 s, the slowest 249 s. Other models shared the GPU in some of these games. [Measured]
- **Thinking off can run long too.** qwen3.5:9b with thinking off spelled out the FEN in its `reasoning` field and ran past 120 s on 6 of 7 prompts under load (`board-images.md`). [Measured]

## The ways to limit thinking

| Method | Hard cap? | Works in Ollama 0.40.0? | Hardware-independent? | Cost |
|---|---|---|---|---|
| (a) Effort levels (`think: "low"`) | No | Yes, only for models with levels (qwen3.8, gpt-oss; not qwen3.5:9b) | Yes | none |
| (b) `num_predict` alone | Yes | Yes | Yes | **loses the answer when it binds** |
| (c) Budget forcing: cap, then a forced answer | Yes | Yes, as two calls | Yes (tokens) | a second short call; prefix cached [Inference] |
| (d) Prompt ("think briefly") | No | Yes | Yes | a new prompt; poor control |
| (e) Wall-clock streaming, then a forced answer | Yes | Yes | **No** | streaming code |
| (f) Length-trained models (L1) | Soft, trained | No suitable model | Yes | none available at 9-30B |
| Sampler-enforced `think_budget` | Yes | **Not merged** ([PR #17566](https://github.com/ollama/ollama/pull/17566), open) | Yes | one call |

**(a) Effort levels.** `think` takes a bool or "a supported level from `thinking.values`"; "unsupported names use the model default" ([Ollama thinking docs](https://docs.ollama.com/capabilities/thinking), [API: chat](https://docs.ollama.com/api/chat)). What a level does depends on the model:

- **qwen3.8:** a system-prompt sentence. `low` adds "Reasoning effort is set to low. Keep your thinking brief and focused, moving directly to the conclusion without unnecessary elaboration." `medium` adds nothing; `xhigh` asks for thorough validation. [Source: renderer] Qwen gives no per-level token or accuracy numbers ([card](https://huggingface.co/Qwen/Qwen3.8-27B)).
- **gpt-oss:** trained levels set by "Reasoning: low" in the system prompt, with "smooth test-time scaling" ([gpt-oss model card](https://arxiv.org/html/2508.10925)). gpt-oss-20b on AIME 2025 scores 37.1, 72.1 and 91.7 at low, medium and high.
- **qwen3.5:9b:** `false/true` only. Its card says Qwen3.5 "does not officially support the soft switch" `/think` `/nothink` ([Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)).
- **Gemma 4:** on/off only, no levels or budget ([Gemma thinking docs](https://ai.google.dev/gemma/docs/capabilities/thinking)).

Reliable in direction, not in length: nothing stops a long think at `low`. Cheap: it is one string.

**(b) `num_predict` alone.** An exact cap on generated tokens, thinking included. When it binds inside the thinking there is no answer. One chess-commentary study gave Qwen3 2,048 tokens with thinking on. Qwen3-8B produced no final answer on 46 of 50 positions, Qwen3-32B on 31 of 50, and the authors switched to no-think ([arXiv 2608.04240](https://arxiv.org/html/2608.04240v1), App. C.3). Only useful as phase 1 of (c).

**(c) Budget forcing.** Stop the thinking at N tokens, write the end-of-thinking marker, optionally a sentence, and let the model answer.

- s1 forces "the end-of-thinking token delimiter" and optionally "Final Answer:". It reports 100% control, against 40-60% for asking for a length in the prompt, since "our model cannot reliably count tokens" ([s1](https://arxiv.org/html/2501.19393v3), Table 3).
- Qwen3 does the same: "when the length of the model's thinking reaches a user-defined threshold, we manually halt the thinking process and insert the stop-thinking instruction: 'Considering the limited time by the user, I have to give the solution based on the thinking directly now.\n</think>.\n\n'". The ability "emerges naturally" from mixing thinking and non-thinking training ([Qwen3 report](https://arxiv.org/html/2505.09388), §4.3).
- llama.cpp (`--reasoning-budget N`, `--reasoning-budget-message`; [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)) and vLLM (`thinking_token_budget`; [reasoning outputs](https://docs.vllm.ai/en/stable/features/reasoning_outputs/)) build this into the sampler.
- Ollama doesn't: [#10925](https://github.com/ollama/ollama/issues/10925) has been open since May 2025, and [PR #17566](https://github.com/ollama/ollama/pull/17566) (`options.think_budget`, passed to llama-server's budget sampler) is still open.

How to do it through Ollama today:

- **Chat prefill (recommended).** Send the messages plus `{"role": "assistant", "thinking": <thinking so far + message>, "content": " "}`. The Qwen renderer writes an assistant message that comes last without `<|im_end|>`, as `<think>\n{thinking}\n</think>\n\n{content}`. So the model continues right after the closed thinking. [Source: renderer]
  - `content` must be non-empty. The Qwen parser starts in content mode only if the prefill has content (`assistantPrefill := ... lastMessage.Content != ""`). Only then does `ThinkingClose()` return nil, so the format applies from the first token.
  - With `content: ""` the parser expects thinking, the grammar waits for a second `</think>`, and the JSON comes back unconstrained in `message.thinking`.
  - The renderer trims content, so `" "` renders as nothing. [Source: [parsers/qwen35.go](https://github.com/ollama/ollama/blob/v0.40.0/model/parsers/qwen35.go), [server/routes.go](https://github.com/ollama/ollama/blob/v0.40.0/server/routes.go)]
  - Pass the same `think` value in both calls. qwen3.5 renders the thinking block only when thinking is on, and qwen3.8's system sentence must match for the prompt prefix to be reused.
- **Raw `/api/generate`.** Build the whole prompt yourself: chat template, `<think>\n…\n</think>\n\n`, `raw=True`. With raw, `format` applies from the first token. [Source: routes.go comment] It works for any model. But the template, and qwen3.8's level sentence, then live in our code, and images need the template's vision tokens. `/api/chat` with `"_debug_render_only": true` returns the rendered prompt, so ours can be checked against Ollama's.

Reliability: the cap is exact. Answer quality after a cut is the open question (see the evidence below). Cost: one extra call of ~10-60 tokens. Its prompt is the first call's prompt plus the thinking, which the runner should mostly reuse from its KV cache [Inference: check `prompt_eval_count` on call 2].

**(d) Prompt instructions.** "Think briefly" or "use at most 500 tokens" give unreliable control. s1's prompt-based length control reached 40-60% control and lower accuracy ([s1](https://arxiv.org/html/2501.19393v3), Table 3). qwen3.8's `low` is this method, in a sentence Qwen chose. A new prompt is a new Player configuration anyway.

**(e) Wall-clock streaming with a fallback.** Stream, stop at T seconds, close the connection (Ollama stops generating), then force the answer as in (c).

- Pros: it bounds what users wait for, and no Turn is lost to the clock.
- Con: what the model gets to think depends on the machine and on what else shares the GPU. The same configuration plays differently on an M3 Pro and an M4 Max, or with a faceoff's second model loaded.
- Streaming also changes timeouts: httpx's read timeout applies per chunk, so `TIMEOUT_S` no longer bounds a streamed call. The loop must keep its own deadline.

**(f) Length-controlled training.** L1 (LCPO) trains a model to follow a token target in its prompt. It "outperforms S1 by up to 100% relative and 20% absolute" at the same budget, and calls S1's truncation one that "severely degrades performance" ([L1](https://arxiv.org/html/2503.04697)). ThinkPrune halves reasoning length for a 2% drop ([arXiv 2504.01296](https://arxiv.org/abs/2504.01296)). Both are 1.5B math models. There is no such chess model at 9-30B in Ollama, so this is not an option now.

## What the evidence says about strength

**Chess, more thinking via effort levels** ([LLM Chess data](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv), 2026-10-10; Elo ±95%, completion tokens per move):

| Model | low | medium | high / xhigh |
|---|---|---|---|
| o3-mini | −184 ± 81 (663) | 82 ± 70 (2,338) | 403 ± 64 (6,524) |
| o4-mini | 104 ± 72 (659) | 240 ± 64 (2,156) | 440 ± 57 (5,695) |
| gpt-5-nano | −117 ± 99 (1,102) | 413 ± 77 (5,103) | 683 ± 81 (10,933) |
| gpt-5-mini | −56 ± 119 (291) | 349 ± 106 (1,651) | 759 ± 117 (7,125) |
| gpt-5.4 | 348 ± 92 (587) | 1253 ± 112 (2,713) | 1322 ± 133 (4,925) |
| gpt-5.5 | | 1532 ± 148 (2,528) | 1528 ± 179 (3,666) |
| gemini-3.8-flash | | 1527 ± 135 (2,585) | 1546 ± 170 (8,285) |
| gpt-oss-20b | −300 ± 141 (3,930) | −232 ± 129 (4,091) | −258 ± 133 (4,209) |
| Claude 3.7 Sonnet, budget 1,024 / 5,000 / 10,000 | −36 ± 108 (369) | −36 ± 108 (575) | −1 ± 115 (671) |

- **Gains are large where the model is weak and the levels are trained.** The paper: "increases of up to 15% from low to medium" in Win/Loss. o4-mini blunders 11.2% of plies at low and 4.2% at medium ([LLM Chess paper](https://arxiv.org/html/2512.01992v1), §3.1, §3.3).
- **They saturate for strong models** (gpt-5.5, gemini-3.8-flash).
- **They vanish where something else fails first.** gpt-oss-20b's games last ~8 moves on protocol errors. Claude 3.7 never used its budget: it spent 370-670 tokens whatever the cap.
- **These are trained levels, not truncation.** A forced cut of the same length is likely worse (see below). [Inference]
- **Local reference points:** qwen3.8-27b 846 ± 166 at 12,814 tokens per move; qwen3.5-9b thinking −200 ± 127 at 6,629; qwen3.5-9b without thinking −258 ± 133. LLM Chess makes several calls per move (board, legal moves, move), so per-call thinking is lower than the per-move total. [Source + Inference]
- **No published study sweeps a forced budget in chess.** I found none. ChessQA reports that explicit reasoning adds +14.7 points on average, with no budget sweep ([ChessQA](https://arxiv.org/pdf/2510.23948)).

**Truncated thinking vs no thinking (not chess):**

- **NoThinking** (R1-Distill-Qwen-32B): with thinking budget-forced to 700 tokens, AMC 2023 pass@1 was 28.9. Skipping thinking with a prefilled empty think block scored 51.3. Without a budget, thinking wins at pass@1 ([arXiv 2504.09858](https://arxiv.org/html/2504.09858)).
- **Coupling Tax** (Qwen3, three sizes): "non-thinking mode matches or outperforms thinking mode on GSM8K and MATH-500 at every budget up to 2048 tokens". The crossover moves to larger budgets on harder tasks ([arXiv 2605.07686](https://arxiv.org/abs/2605.07686)).
- **L1:** S1-style truncation at 512-1,024 tokens trails a length-trained model by 20-25 points ([L1](https://arxiv.org/html/2503.04697)).

**Diminishing returns and overthinking:**

- **Qwen3-235B** shows "scalable and smooth performance improvements correlated to the allocated thinking budget" on math, code and STEM ([Qwen3 report](https://arxiv.org/html/2505.09388), §4.7, Fig. 2).
- **Medical QA, Qwen3 1.7B-235B**, native thinking budget from 64 to 1,024 tokens: "rapid improvement up to 256 tokens and diminishing returns beyond 512" ([arXiv 2508.12140](https://arxiv.org/html/2508.12140v1)).
- **Accuracy can fall with length.** Accuracy over chain-of-thought length is an inverted U, and the best length falls as the model gets stronger ([Wu et al., ICLR 2026](https://arxiv.org/html/2502.07266v3)). Longer reasoning can also lower accuracy outright, e.g. through distraction and lost focus on long deductions ([Inverse Scaling in Test-Time Compute](https://arxiv.org/abs/2507.14417)).

**What this means here** [Inference]:

1. **A budget that cuts only the long tail should cost little.** For qwen3.8 at medium, ~3,000 tokens is above p90 here. The longest thinks are often loops or hard positions where more tokens add little.
2. **A tight budget may be worse than thinking off.** For qwen3.5:9b, a cap at 512-1,024 tokens could lose to thinking off, as in NoThinking and Coupling Tax. Measure it.
3. **Raising qwen3.8's effort is the likely way up toward LLM Chess's 846.** qwen3.8 at `xhigh`, or unbounded medium, may be stronger than what we play. But at ~12.7 tok/s, 12,000 tokens is ~16 minutes per move, so a budget has to fit the machine. That is a benchmark-design choice, not a bug.

## Implementation sketches

Written against `OllamaPlayer` and the `ollama` Python client 0.6.3. Untested: nothing could be run today.

**(a) Effort levels.** `thinking` becomes `bool | str`, checked against the model's levels:

```python
@dataclass(frozen=True)
class LlmModel:
    name: str
    thinking: tuple[bool | str, ...]  # the values `ollama show` lists, e.g. (False, "low", "medium", "xhigh")

# OllamaPlayer.reply: unchanged apart from passing the level through
response = self._chat(model=self._model, messages=history, think=self._thinking, format=schema, options=self._sampling)
```

`Side.thinking` and `PlayerConfiguration.thinking` widen to `bool | str`. A level is a new configuration; `True` stays what old logs mean (medium on qwen3.8).

**(b) Token budget with a forced answer (the recommendation).**

```python
# Qwen3's own stop-thinking sentence, from the Qwen3 report, with the task's word for "solution".
BUDGET_MESSAGE = "\n\nConsidering the limited time, I have to give my move now, based on the thinking so far."
ANSWER_TOKENS = 64  # {"move": "Nbd7"} is about 8 tokens

def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
    schema = (MoveAnswer if self._thinking else ReasonedMoveAnswer).model_json_schema()
    if allowed_moves is not None:
        schema["properties"]["move"] = schema["properties"]["move"] | {"enum": allowed_moves}
    history = [{"role": message.role, "content": message.content} for message in messages]
    sampling = dict(self._sampling or {})
    request = dict(model=self._model, think=self._thinking, format=schema)
    started = time.perf_counter()
    try:
        options = sampling | ({"num_predict": self._budget} if self._budget else {})
        response = self._chat(messages=history, options=options or None, **request)
        thinking = response.message.thinking or ""
        forced = bool(self._budget) and response.done_reason == "length"
        if forced:
            # Cut inside the thinking (no content yet): close it with the budget sentence. Cut inside the
            # answer: the thinking was complete, so close it as it was. The content " " puts Ollama's parser
            # in content mode, so the schema applies from the first new token.
            closed = thinking + (BUDGET_MESSAGE if not response.message.content else "")
            prefill = {"role": "assistant", "thinking": closed, "content": " "}
            response = self._chat(
                messages=[*history, prefill], options=sampling | {"num_predict": ANSWER_TOKENS}, **request
            )
    except httpx.TimeoutException:
        raise LlmTimeout(self.timeout_s) from None
    return LlmReply(
        raw=response.message.content or "",
        thinking=thinking or None,
        latency_s=time.perf_counter() - started,
        # new fields, logged per attempt: whether the budget cut in, and how long the thinking was
        forced=forced,
        thinking_tokens=...,  # call 1's eval_count, minus the answer's share when it wasn't forced
    )
```

Notes:

- **The budget is per attempt,** like the timeout. A retry gets a fresh budget.
- **It bounds thinking plus answer.** If the answer itself is cut, call 2 re-answers from the complete thinking.
- **If call 2 produces an illegal move, it is an ordinary illegal move,** and the usual Retry applies.
- **Only qwen3.5/3.8's renderer and parser were checked.** For any other model (gpt-oss harmony, Gemma 4), first confirm with `_debug_render_only` that a prefilled `thinking` renders as a closed think block.
- **One real call should confirm the format applies in call 2.** Under Enforced decoding, it must not be able to answer outside the enum.

**(c) Streaming with a wall-clock or chunk budget, then the same forced answer.** For Play LLM, or as an emergency stop:

```python
def think_until(client: ollama.Client, deadline_s: float | None, max_chunks: int | None, **request) -> tuple[str, str, bool]:
    """Stream the reply. Returns (thinking, content, cut). Stops only during thinking, never mid-answer."""
    started, thinking, content = time.perf_counter(), [], []
    stream = client.chat(stream=True, **request)
    try:
        for chunk in stream:
            thinking.append(chunk.message.thinking or "")
            content.append(chunk.message.content or "")
            if chunk.done:
                return "".join(thinking), "".join(content), False
            out_of_time = deadline_s is not None and time.perf_counter() - started > deadline_s
            out_of_chunks = max_chunks is not None and len(thinking) >= max_chunks
            if not any(content) and (out_of_time or out_of_chunks):
                break
    finally:
        stream.close()  # closes the HTTP response, so Ollama stops generating
    return "".join(thinking), "", True  # then call 2 as in (b)
```

A streamed chunk is about one token, but not exactly; use `num_predict` (b) when the count must be exact.

## Verified, 2026-10-20

The forced answer (sketch (b)), tried against Ollama 0.40.0 for each thinking model (spike #70). Throwaway scripts called the HTTP API directly with the request `OllamaPlayer` sends: `turn_messages` with the Listed system prompt and the legal-move list, `format` = the `MoveAnswer` schema with `move` as an enum of the legal moves (**Listed enforced**), `think` as below, no sampling options (model defaults). Position: `docs/research/board-images-positions.json` #1 (`r1bqkb1r/ppp2ppp/3p1n2/n3p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 6`, 33 legal moves, prompt 372-405 tokens), plus #0 (a late middlegame, prompt 680 tokens) for one qwen3.8 run. In this section **[Measured]** means these calls, not game logs.

Each run: call 1 with `options.num_predict` = the cap; if `done_reason == "length"` with empty `content`, call 2 with the thinking so far + the budget sentence handed back as `{"role": "assistant", "thinking": ..., "content": " "}`, the same `think` and `format`, and `num_predict: 64`. Call 2's prompt was checked with `"_debug_render_only": true` (the rendered text comes back in `_debug_info.rendered_template`; `ollama show --template` prints only `{{ .Prompt }}` for all three, since they use built-in Go renderers). Two checks on top: call 2 three more times, and call 2 with the enum swapped for three unlikely moves (`Kf1`, `Rg1`, `a3`), to show the grammar holds from call 2's first token rather than the model happening to comply.

### Verdict

| Model (runner) | Chat route | Forced answers (JSON, in enum) | Restricted enum held | Generation speed | Build |
|---|---|---|---|---|---|
| qwen3.5:9b, `think: true` (llama.cpp) | works | 8/8 | 2/2 | 19.7-21.9 tok/s | chat prefill |
| qwen3.8, `think: "medium"` (MLX) | works | 12/12 (2 positions, 3 caps) | 2/2 | 18.0-20.5 tok/s | chat prefill |
| gemma4:26b, `think: true` (MLX) | works, but as a new turn | 5/5 chat, 3/3 raw | 1/1 chat, 1/1 raw | 36.1-41.7 tok/s | chat prefill; raw verified as fallback |

[Measured] Every forced answer was valid JSON (`{"move": "..."}`, 7-10 tokens, `done_reason: "stop"`, empty `thinking`) and every move was in the enum. With `content: ""` instead of `" "`, call 2 failed for both families: the model thought again into `message.thinking`, hit the 64-token cap, and `content` was empty (qwen3.8 5/5, gemma4 5/5; once qwen3.8 even wrote `{"move": "Bb5+"}` outside the restricted enum, inside its thinking). **`content: " "` is required.** [Measured]

### qwen3.5:9b

- **Render** [Measured]: the thinking appears closed, in Qwen's format, and the assistant turn is left open:

  ```
  ...Legal moves: Bxf7+ Be6 Ba6 ... b4 a4<|im_end|>
  <|im_start|>assistant
  <think>
  {thinking so far}

  Considering the limited time, I have to give my move now, based on the thinking so far.
  </think>

  ```

  With `think: false` the renderer drops the handed-back thinking entirely and ends at `<|im_start|>assistant\n`, so call 2 must send the same `think` as call 1 (a budget with thinking off is refused anyway).
- **Chat route: works.** Cap 256: forced answer `{"move": "Bxf7+"}`; repeats `Ba6`, `Ng5`, `Be2`. Cap 1,024: `Ng5`; repeats `O-O`, `Bxf7+`, `Ba6`. Restricted enum: `a3` both times. [Measured]
- **Speed** [Measured]: 19.7 tok/s (256 tokens), 21.9 tok/s (1,024); another client's unbounded qwen3.5:9b turn in the server log held 22.5 tok/s out to 6,618 tokens. Prompt 405 tokens cold in 1.8 s. Call 2 reused the cache: 0.28 s of prompt for 1,453 tokens, 0.6-0.7 s in all.
- **Time limit** [Inference]: budget ÷ 20 tok/s + ~2 s prompt + ~1 s call 2. 2,048 tokens ≈ 105 s, 4,096 ≈ 210 s, 6,144 ≈ 310 s.

### qwen3.8

- **Render** [Measured]: identical to qwen3.5:9b after the system prompt (renderer `qwen3.8`, parser `qwen3.5`). `low` and `xhigh` prepend their sentence to the system prompt ("Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, ..."); `medium` adds nothing. So call 2 must send the same level as call 1, or the prompt (and its cache) differs.
- **Chat route: works.** Position #1, cap 256: `{"move": "Bb5+"}`; repeats `Bxf7+` ×3. Cap 1,024: `Ba6`; repeats `Bxf7+`, `Ba6`, `Bb5+`. Position #0, cap 1,536: `Nxc5` (×4). Restricted enum: `a3` both times on #1. A cap of 2,048 on #1 didn't bind: it finished at 524 tokens with `Ba6`. [Measured]
- **Speed** [Measured]: 18.0-20.5 tok/s alone on the GPU (16.9-18.8 while another client's game was swapping models in and out). That is faster than the 12.7 tok/s fitted from game logs above, which shared the GPU and include prompt time. Prompt processing cold: ~78 tok/s (405 tokens in 5.1 s, 2,240 in 28.7 s).
- **Call 2's cache is not reliable on MLX** [Measured]: after the 256 cap, call 2 reprocessed 25 of 685 tokens (0.4 s). After the 1,024 cap, the MLX prefix cache matched 1,428 tokens but held only the 404 of the prompt, so it reprocessed 1,049 tokens (13.3 s; the server log: `cache hit total=1453 matched=1428 cached=404 left=1049`). After the 1,536 cap another client's request had swapped the model out, so call 2 reloaded it (17.4 s) and reprocessed all 2,240 tokens (28.7 s). In a real game call 2 follows call 1 at once, so a swap between them shouldn't happen; the re-prefill can.
- **Time limit** [Inference]: worst case = prompt (~10 s for a late-game prompt) + budget ÷ 18 tok/s + call 2 re-prefilling prompt + budget at ~78 tok/s + 64 ÷ 18 ≈ 4 s. 2,048 tokens ≈ 10 + 114 + 33 + 4 ≈ 160 s; **3,072 ≈ 10 + 171 + 47 + 4 ≈ 230 s**; 4,096 ≈ 10 + 228 + 60 + 4 ≈ 300 s. Add ~10-20 s of model load when a faceoff swaps models between turns (`load_s` 6.8-20.9 s measured).

### gemma4:26b

- **Render** [Measured]: the thinking appears closed in Gemma's own channel format, but **Ollama's gemma4 renderer closes the handed-back assistant message as a finished turn and opens a new model turn** (no prefill continuation):

  ```
  <bos><|turn>system
  <|think|>
  You are playing chess as White ...<turn|>
  <|turn>user
  PGN: ... Legal moves: Bxf7+ Be6 ... b4 a4<turn|>
  <|turn>model
  <|channel>thought
  {thinking so far}

  Considering the limited time, I have to give my move now, based on the thinking so far.
  <channel|><turn|>
  <|turn>model

  ```

  The thought is carried, not dropped, despite the card's advice not to carry earlier thinking in the history. The model then sees a thought-only turn and answers in a fresh turn. The rendered text is the same for `content: " "` and `""`. The difference is the parser state: with `" "` the parser starts in content mode, so the grammar applies from the first token of the new turn and the model can't open a new `<|channel>thought`. With `""` it re-thinks (see the Verdict). With `think: false` the renderer also adds an empty `<|channel>thought\n<channel|>` after the new `<|turn>model\n`. That shows Gemma's in-turn answer format: content follows `<channel|>` directly.
- **Chat route: works.** Cap 256: `{"move": "Bb3"}`. Cap 1,024: `Bxf7+`; repeats `Bxf7+`, `Bb3`, `d3`. Restricted enum: `a3` (7 tokens, no thinking). [Measured]
- **Raw route: also works** [Measured]. `/api/generate` with `raw: true`, the same `format` and `num_predict: 64`, and the prompt = the `_debug_render_only` render of the turn's messages (with `think: true`, so `<|think|>` is in the system turn; it ends `<turn|>\n<|turn>model\n`) + `<|channel>thought\n` + thinking so far + budget sentence + `\n<channel|>`. That continues the same model turn, as Gemma would produce it. 3/3: `{"move": "d3"}` twice, and `a3` under the restricted enum, 7 tokens each, empty `thinking`, prompt 651 tokens in 0.5-1.6 s. The rendered text starts with the literal `<bos>`; it worked as is.
- **Speed** [Measured]: 36.1-41.7 tok/s; prompt 372 tokens cold in 1.7 s. Call 2 reused the cache (1,424 tokens in 0.23 s).
- **Time limit** [Inference]: budget ÷ 36 tok/s + ~2 s + ~1 s. 3,072 tokens ≈ 90 s, 6,144 ≈ 175 s.

### What #72 and #73 should build

- **Thinking budget (#72), all three models, one code path.** Call 1: today's `chat` request plus `options.num_predict = budget` (merged into the sampling options). If `done_reason == "length"` and `content` is empty: call 2 = the same `model`, `think` (the identical value, level included) and `format` (the same schema object, enum included), `messages = [*turn messages, {"role": "assistant", "thinking": thinking + "\n\nConsidering the limited time, I have to give my move now, based on the thinking so far.", "content": " "}]`, `options = sampling | {"num_predict": 64}`. Answers took 7-10 tokens, so 64 has ample room. Token counts come from call 1's `eval_count` and `prompt_eval_count`. The thinking/answer split isn't reported, so derive it from where the answer starts, or treat call 1's `eval_count` as thinking when it was cut while thinking. [Measured + Inference]
- **Gemma 4 (#73): use the same chat route.** It is verified, needs no Gemma-specific code, and the answer stays under the same `format`. Its live test should assert the forced flag and a move from the enum. [Inference] Keep the raw route as the documented fallback if a later Ollama renderer changes: `POST /api/generate {"model": "gemma4:26b", "prompt": render + "<|channel>thought\n" + thinking + BUDGET + "\n<channel|>", "raw": true, "format": schema, "stream": false, "options": sampling | {"num_predict": 64}}`, where `render` comes from `/api/chat` with the same messages, `think: true` and `"_debug_render_only": true`. Open question for the probe: whether answering in a new turn (chat) plays worse than continuing the turn (raw). Both give legal moves; this spike didn't measure their quality.
- **Time limit: derive it from the budget, and refuse budgets that don't fit the context window.** Deriving can't refuse a sane budget because of this machine's speed, and it keeps the "tokens, not seconds" meaning. A per-call `timeout_s = max(300, 60 + 1.5 × budget ÷ speed)`, with a conservative speed per model in the model list (qwen3.5:9b 20, qwen3.8 18, gemma4:26b 36 tok/s), covers the worst cases above with ~50% margin, the 60 s covering prompt, re-prefill and a model swap. For qwen3.8 at 3,072 it gives 316 s. `ollama.Client(timeout=...)` is httpx's per-read timeout, and a non-streamed call sends nothing until it is done, so each of the two calls gets the limit separately; call 2 is short except for the re-prefill. [Inference] **Refuse** instead what can't work at all: every model loaded here with `CONTEXT 8192` (`ollama ps`), so prompt (≤ ~1,500 tokens late in a long game) + budget + 64 must stay under 8,192. A budget above ~6,144 needs a larger `num_ctx`, which would be a new setting. [Measured: `ollama ps`; Inference: the bound]

### Caveats of this check

- **Ollama wasn't free.** Another client's game (qwen3.5:9b and qwen3.8, later gemma3:12b) ran through the same server and swapped models during the spike. Speeds are from `eval_duration`, which counts generation only, but loads and some prompt times are inflated. Treat the speeds as a lower bound for a free GPU.
- One position for most runs, model-default sampling (temperature 1), 2-6 forced answers per model. Mechanism only, not move quality: that is the probe's job.
- `qwen3.5:9b` resolved to the llama.cpp build (`c97eb11d70b1`). The second, ggml build of the same name wasn't tried.
- Models were left to Ollama's keep-alive rather than force-stopped. gemma4:26b and qwen3.5:9b had already been evicted; qwen3.8 and gemma3:12b were in use by the other game.

## Recommendations for this benchmark

1. **Adopt (b): a token Thinking budget enforced by `num_predict` and a forced answer.** It is exact, it works on Ollama 0.40.0, it costs one short call, and it doesn't depend on the machine. Should [PR #17566](https://github.com/ollama/ollama/pull/17566) ship (`options.think_budget`, enforced in the sampler), switch to it. It does the same thing in one call, but needs llama-server-runner models and its own check on MLX models.
2. **Add `thinking_budget: int | None` to the Player configuration** (`Side`, `PlayerConfiguration`, `game_start` log, the settings modal, the batch scripts' `--thinking-budget`).
   - None means unbounded: today's behaviour, so old logs keep their configurations.
   - Games with different budgets don't share a Rating (ADR 0005 on the Rating: a configuration doesn't change).
   - Widen `thinking` to `bool | str` for levels at the same time.
   - Proposed glossary entry for `CONTEXT.md`: **Thinking budget**: the most tokens of Thinking (and answer) a model may produce in one attempt before it is made to answer; part of the Player configuration.
3. **Compare Turns by tokens, not seconds.**
   - A token is the same on any machine and with any load. Seconds are not: the same config gets ~3,700 tokens in 300 s here, alone on the GPU, and fewer next to a second model.
   - Tokenizers differ between families, by maybe 10-20% for this text [Inference]. That is small next to hardware differences, and nil within a family (qwen3.5 vs qwen3.8).
   - Log per attempt: `thinking_tokens` (from `eval_count`), `forced`, and latency.
4. **Keep the wall-clock limit as a safety net only.**
   - Set `TIMEOUT_S` above the budget's worst case on this machine: budget ÷ ~12 tok/s + ~10 s + call 2. For example, 4,096 tokens needs about 360 s for qwen3.8.
   - A timeout stays a Forfeit. With a budget it should become rare, and when it happens it says the machine was too slow.
   - Wall-clock forcing (c) suits only Play LLM, where a human is waiting and games don't count towards the Rating.
5. **Don't use `num_predict` alone, and don't treat a cut as a move.** Today an empty answer from a cut would be judged `invalid` and eat a Retry. With (b) a cut always leads to a forced answer. If one ever happens without it, log it as a distinct result (`"length"`), not as an illegal move.
6. **Default budgets** (to confirm with the experiment):
   - **qwen3.8, `medium`, 3,072 tokens.** That is above p90 here and about 250 s, so it should almost never bind and removes the timeout risk.
   - **qwen3.5:9b: the smallest budget that matches unbounded** in the experiment.
   - Also try qwen3.8 at `xhigh` with the same budget. The level changes how it spends the tokens, and that may be where LLM Chess's strength comes from.
7. **Thinking off has the same problem in its Reasoning field.** A `maxLength` on `reasoning` in the `ReasonedMoveAnswer` schema would cap it inside the grammar. llama.cpp's JSON-schema grammar supports string lengths [Inference: verify for Ollama's converter and the MLX runner]. It is a schema change, so a new configuration.

## Experiment plan (to run later, on a free GPU)

`scripts/probe_thinking_budget.py`, offline like `scripts/probe_board_images.py`, reusing its frozen 60 positions (`board-images-positions.json`), `turn_messages`, `judge` and `OllamaPlayer`. One model loaded at a time, nothing else on the GPU.

- **Conditions:** one first attempt per position, no Retry, sampling from `sampling.toml`.
  - **qwen3.5:9b:** thinking off; budgets 256, 512, 1,024, 2,048, 4,096; unbounded (300 s).
  - **qwen3.8:** off; `low` unbounded; `medium` unbounded; `medium` at 512, 1,024, 2,048; `xhigh` at 3,072.
- **LLM constraints: Listed enforced** for move quality, since every answer is legal and so comparable across conditions. **Free** on the first 20 positions for legality.
- **Measures per answer:**
  - legal, invalid, or no answer;
  - `forced`;
  - thinking tokens (`eval_count`) and latency;
  - call 2's `prompt_eval_count`, to check the cache;
  - Stockfish centipawn loss of the chosen move, at fixed depth or nodes, as `scripts/analyse_games.py` uses;
  - blunder rate (loss ≥ 200 cp);
  - agreement with the unbounded condition's move.
- **Before the run:** one `_debug_render_only` call to check the prefill prompt, and one forced call under Listed enforced to check the enum holds in call 2.
- **Analysis:** paired per position. Plot centipawn loss and legality against median thinking tokens per condition, with bootstrap 95% intervals. Temperature is 1, so if the intervals are wide, run 2 samples per position for the budgets near the knee.
- **Decision:** the smallest budget whose centipawn loss and legality are within noise of unbounded becomes the default. If a budget below ~1,024 is worse than thinking off, record that: it is the chess version of NoThinking.
- **Time:** qwen3.8 at ~12.7 tok/s is about 80 s per position unbounded and less under budgets, so ~6-7 h for its 7 conditions. qwen3.5:9b is faster, ~3 h. Run overnight, one model per night, with resumable output like the board-image probe.

## Caveats

- Ollama facts are from source at `v0.40.0`. The prefill trick (`content: " "`) rests on the Qwen parser's `Init`. The format-after-prefill behaviour rests on `ThinkingClose()` returning nil in content mode. Both are internal and could change, so pin them with a test that renders and parses a prefilled request.
- I couldn't confirm which runner serves qwen3.8 (`nvfp4`, no `runner` line in `ollama show`; likely MLX). PR #18479 says both MLX and llama-server constrain only after the close strings, but KV-cache reuse for call 2 is unmeasured on either.
- Thinking tokens here are characters ÷ 4, not token counts, and some games shared the GPU with other models. The log has only 32 qwen3.8 thinking attempts.
- LLM Chess Elos come from a different protocol: several calls per move, a legal-move tool, playing Black against random and Dragon. Its effort levels are trained, not truncation. The truncation evidence is all math or medical QA, mostly not at 9-30B.
- qwen3.8's `low` level is a prompt sentence; whether it shortens thinking much in chess is unmeasured.

## Sources

- Ollama: [thinking docs](https://docs.ollama.com/capabilities/thinking), [API: chat](https://docs.ollama.com/api/chat), [API: generate](https://docs.ollama.com/api/generate); source at v0.40.0: [renderers/qwen35.go](https://github.com/ollama/ollama/blob/v0.40.0/model/renderers/qwen35.go), [parsers/qwen35.go](https://github.com/ollama/ollama/blob/v0.40.0/model/parsers/qwen35.go), [types/model/thinking.go](https://github.com/ollama/ollama/blob/v0.40.0/types/model/thinking.go), [server/routes.go](https://github.com/ollama/ollama/blob/v0.40.0/server/routes.go); [PR #18479](https://github.com/ollama/ollama/pull/18479) (format in one pass), [PR #17566](https://github.com/ollama/ollama/pull/17566) and [issue #17561](https://github.com/ollama/ollama/issues/17561) (think_budget, open), [issue #10925](https://github.com/ollama/ollama/issues/10925), [issue #16583](https://github.com/ollama/ollama/issues/16583)
- llama.cpp [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) (`--reasoning-budget`); vLLM [reasoning outputs](https://docs.vllm.ai/en/stable/features/reasoning_outputs/) (`thinking_token_budget`)
- Models: [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B), [Qwen3 technical report](https://arxiv.org/html/2505.09388), [gpt-oss model card](https://arxiv.org/html/2508.10925), [Gemma thinking](https://ai.google.dev/gemma/docs/capabilities/thinking)
- Budget control: [s1](https://arxiv.org/html/2501.19393v3), [L1 / LCPO](https://arxiv.org/html/2503.04697), [ThinkPrune](https://arxiv.org/abs/2504.01296), [NoThinking](https://arxiv.org/html/2504.09858), [Coupling Tax](https://arxiv.org/abs/2605.07686), [thinking budget in medical reasoning](https://arxiv.org/html/2508.12140v1)
- Overthinking: [When More is Less](https://arxiv.org/html/2502.07266v3), [Inverse Scaling in Test-Time Compute](https://arxiv.org/abs/2507.14417)
- Chess: [LLM Chess paper](https://arxiv.org/html/2512.01992v1), [LLM Chess elo_refined.csv](https://github.com/maxim-saplin/llm_chess/blob/main/data/elo_refined.csv), [ChessQA](https://arxiv.org/pdf/2510.23948), [LLM chess commentary, App. C.3](https://arxiv.org/html/2608.04240v1)
