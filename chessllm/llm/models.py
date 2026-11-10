"""The models the game can be played against, and the sampling settings from the config file."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from chessllm.core.config import SAMPLING_FILE, claude_token_from_environment
from chessllm.core.types import Sampling
from chessllm.exceptions import InvalidSamplingConfig


# The Ollama options that change how a model samples its reply. Others (num_ctx, stop, ...) aren't sampling.
SAMPLING_OPTIONS = frozenset(
    {
        "temperature",
        "top_k",
        "top_p",
        "min_p",
        "typical_p",
        "repeat_penalty",
        "repeat_last_n",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "mirostat",
        "mirostat_tau",
        "mirostat_eta",
    }
)


# The context Ollama loads every model here with (`ollama ps`). A Thinking budget must fit in it with the prompt (up
# to about 1,500 tokens late in a long game) and the forced answer, so at most 6,144, rounded down to a multiple of
# 1,024; a budget smaller than the forced answer's cap can't hold an answer (ADR 0007).
CONTEXT_TOKENS = 8192


@dataclass(frozen=True)
class LlmModel:
    name: str  # the Ollama model name, or for a Hosted model its provider's id
    # The thinking values `ollama show` lists for it: false and true for on/off, or false and its Thinking levels,
    # e.g. "xhigh". Empty when it can't think (no "thinking" capability).
    thinking_values: tuple[bool | str, ...] = ()
    # A conservative generation speed in tokens per second on this machine, from which a Thinking budget's time
    # limit is derived (ADR 0007). None for a model that can't think, which can't have a budget.
    tokens_per_s: float | None = None
    # Whether it can call tools natively, the "tools" capability `ollama show` lists for it: only then may it have
    # Tools (ADR 0011). Hand-set, like thinking_values.
    tools: bool = False
    # Whether it is a Hosted model (ADR 0013): run on a provider's servers, never asked of Ollama, offered only with
    # the provider's token. Only the settings its provider allows apply to it: thinking on or off, never sampling, a
    # Thinking level, a Thinking budget or Tools.
    hosted: bool = False
    # The tokens its context holds, which a conversation kept by Turn memory is trimmed to; None for the context Ollama
    # loads every local model with, CONTEXT_TOKENS.
    context_tokens: int | None = None

    @property
    def thinking(self) -> bool:
        """Whether it can think before it answers. Thinking on is always offered then, at Ollama's default level."""
        return any(value is not False for value in self.thinking_values)

    @property
    def thinking_levels(self) -> tuple[str, ...]:
        """The Thinking levels it offers besides on and off, e.g. ("low", "medium", "xhigh")."""
        return tuple(value for value in self.thinking_values if isinstance(value, str))


# The models offered in the New game sheet, with the thinking values `ollama show` lists for each under Ollama
# 0.40.0, checked on 2026-10-20 (and their capabilities on 2026-10-19 against the Ollama library:
# ollama.com/library/qwen3.5, ollama.com/library/llama3, ollama.com/library/gemma3). The thinking models' speeds are
# the low end of those measured on 2026-10-20 (docs/research/thinking-budget.md, "Verified"). The thinking models
# are also the ones with the "tools" capability; Llama 3 and Gemma 3 have neither (`ollama show`, 2026-10-23).
LLM_MODELS = [
    # Qwen 3.5, 9.7B parameters; thinking on by default
    LlmModel("qwen3.5:9b", (False, True), tokens_per_s=20, tools=True),
    # Qwen 3.8, 27.8B parameters. Thinking on means Ollama's default level, medium.
    LlmModel("qwen3.8:latest", (False, "low", "medium", "xhigh"), tokens_per_s=18, tools=True),
    LlmModel("llama3:8b"),  # Llama 3, 8B parameters
    LlmModel("gemma3:12b"),  # Gemma 3, 11.8B parameters
    # Gemma 4, 26.2B parameters (a 16 GB nvfp4 build). Thinking on by default, so the player must always send it.
    LlmModel("gemma4:26b", (False, True), tokens_per_s=36, tools=True),
]

# The cap on a forced answer, given when a Thinking budget runs out: the JSON move took 7-10 tokens in the spike.
FORCED_ANSWER_TOKENS = 64
# Closes the thinking handed back when a Thinking budget runs out, so the model gives its move (ADR 0007).
BUDGET_SENTENCE = "\n\nConsidering the limited time, I have to give my move now, based on the thinking so far."
THINKING_BUDGET_RANGE = range(FORCED_ANSWER_TOKENS, 6144 + 1)

# The Hosted models (ADR 0013): a single hard-coded entry, so adding another is one line. Claude Haiku 5.5 thinks on
# or off (adaptive thinking), has a 1M-token context, and none of the local models' other capabilities here.
HOSTED_MODELS = [LlmModel("claude-haiku-5-5", (False, True), hosted=True, context_tokens=1_000_000)]
# Every model a command can be asked to play, whether or not the app has access to its provider.
KNOWN_MODELS = [*LLM_MODELS, *HOSTED_MODELS]


def offered_models() -> list[LlmModel]:
    """The models the New game sheet offers: the local ones, and the Hosted ones only while the app has access to
    their provider (a token is set), read when asked."""
    return list(KNOWN_MODELS if claude_token_from_environment() is not None else LLM_MODELS)


def is_hosted(model: str) -> bool:
    """Whether the named model is a Hosted model (ADR 0013)."""
    return any(known.hosted and known.name == model for known in KNOWN_MODELS)


def context_tokens(model: str) -> int | None:
    """The tokens the named model's context holds, or None for Ollama's CONTEXT_TOKENS: a local model's, and that of
    a model not in the lists."""
    return next((known.context_tokens for known in KNOWN_MODELS if known.name == model), None)


def load_sampling(path: Path = SAMPLING_FILE) -> Sampling:
    """The sampling options set in the config file. Empty (or no file) means the model's own defaults.

    The file is read at the start of every game, so edits apply to the next game without restarting the app.
    Raises InvalidSamplingConfig if it isn't TOML, or sets anything but numbers for the sampling options."""
    if not path.exists():
        return {}
    try:
        sampling = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise InvalidSamplingConfig(str(error)) from error
    unknown = sorted(set(sampling) - SAMPLING_OPTIONS)
    if unknown:
        raise InvalidSamplingConfig(f"{path.name}: unknown sampling options {', '.join(unknown)}")
    not_numbers = sorted(name for name, value in sampling.items() if type(value) not in (int, float))
    if not_numbers:
        raise InvalidSamplingConfig(f"{path.name}: sampling options must be numbers: {', '.join(not_numbers)}")
    return sampling
