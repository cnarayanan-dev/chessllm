"""The Claude adapter for the LLM player port: a Hosted model, played through Anthropic's Messages API (ADR 0013)."""

import time
from collections.abc import Callable, Sequence
from typing import Any

import anthropic
from anthropic.types import Message as ClaudeMessage

from chessllm.core.config import OLLAMA_REPLY_TIMEOUT_S
from chessllm.exceptions import HostedModelFailed, LlmTimeout, ReplyDeclined
from chessllm.llm.ollama_player import split_tokens
from chessllm.llm.players import LlmReply, Message, MoveAnswer, ReasonedMoveAnswer, Tool

# The effort a Hosted model plays at. Fixed, not a setting: the provider's own default for this model, so that the
# Player configuration needs no effort to tell games apart (ADR 0013).
EFFORT = "medium"
# The most tokens a reply may use, thinking included. Far above what a move takes: it is a guard against a runaway
# reply, below the size at which the SDK insists on streaming.
MAX_TOKENS = 16_000


class ClaudePlayer:
    """Asks a Hosted model, Claude, for a move, with the answer shaped by the move schema as OllamaPlayer's is.

    With thinking off, the provider's thinking is turned off and the schema asks for the reasoning before the move.
    With thinking on it is adaptive, and what is recorded as the Thinking is the summary the provider gives, never
    the raw reasoning. Under Enforced decoding the move is an enum of the allowed moves in a structured output, so
    the model can only produce one of them.

    Nothing about sampling is ever sent: the provider rejects non-default values. A Thinking budget, Thinking level
    and Tools do not apply to a Hosted model, and Settings refuses them.

    A reply that takes longer than timeout_s is a LlmTimeout, a Forfeit. A reply the model declines for its content is
    a ReplyDeclined, also a Forfeit. Any other failure of the call, once the client has retried it (it retries rate
    limits, outages and dropped connections itself), is not the model's play: it raises HostedModelFailed, which ends
    the game as an Aborted game."""

    def __init__(
        self,
        model: str,
        thinking: bool = True,
        token: str | None = None,
        create: Callable[..., ClaudeMessage] | None = None,
        timeout_s: float = OLLAMA_REPLY_TIMEOUT_S,
    ) -> None:
        """create is the client's messages.create, by default the Anthropic client's with the token as its API key;
        the token is held only by the client."""
        self._model = model
        self._thinking = thinking
        self._create = create or anthropic.Anthropic(api_key=token, timeout=timeout_s).messages.create
        self.timeout_s = timeout_s

    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Sequence[Tool] = ()
    ) -> LlmReply:
        assert not tools, "Tools do not apply to a Hosted model"
        schema = (MoveAnswer if self._thinking else ReasonedMoveAnswer).model_json_schema()
        if allowed_moves is not None:
            schema["properties"]["move"] = schema["properties"]["move"] | {"enum": allowed_moves}
        system = "\n\n".join(message.content for message in messages if message.role == "system")
        turn = [{"role": message.role, "content": message.content} for message in messages if message.role != "system"]
        thinking: dict[str, Any] = (
            {"type": "adaptive", "display": "summarized"} if self._thinking else {"type": "disabled"}
        )
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "messages": turn,
            "thinking": thinking,
            "output_config": {
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)},
            },
        }
        if system:
            request["system"] = system
        started = time.perf_counter()
        response = self._call(request)
        if response.stop_reason == "refusal":
            raise ReplyDeclined(f"{self._model} declined to answer{declined_why(response)}")
        raw = "".join(block.text for block in response.content if block.type == "text")
        summary = "".join(block.thinking for block in response.content if block.type == "thinking")
        thinking_tokens, answer_tokens, estimated = split_tokens(response.usage.output_tokens, summary, raw)
        return LlmReply(
            raw=raw,
            thinking=summary if self._thinking else None,
            latency_s=time.perf_counter() - started,
            thinking_tokens=thinking_tokens,
            answer_tokens=answer_tokens,
            prompt_tokens=response.usage.input_tokens,
            stop_reason=response.stop_reason,
            # The thinking is only the provider's summary, so its share of the characters is a lower bound
            token_split_estimated=estimated,
        )

    def _call(self, request: dict[str, Any]) -> ClaudeMessage:
        try:
            return self._create(**request)
        except anthropic.APITimeoutError:
            raise LlmTimeout(self.timeout_s) from None
        except anthropic.APIError as error:
            raise HostedModelFailed(f"{self._model}: {failure_reason(error)}") from None


def declined_why(response: ClaudeMessage) -> str:
    """Why the provider says it declined, if it says: its category and explanation, as ": category, explanation"."""
    details = getattr(response, "stop_details", None)
    said = [text for text in (getattr(details, "category", None), getattr(details, "explanation", None)) if text]
    return f": {', '.join(said)}" if said else ""


def failure_reason(error: anthropic.APIError) -> str:
    """Why a call failed that is not the model's play, in words, with what the provider said. Never the token: the
    provider's messages do not hold it."""
    message = getattr(error, "message", str(error))
    if isinstance(error, anthropic.AuthenticationError):
        what = "the provider refused the token"
    elif isinstance(error, anthropic.PermissionDeniedError):
        what = "the token is not allowed to do this"
    elif isinstance(error, anthropic.RateLimitError):
        what = "rate limited, even after retrying"
    elif isinstance(error, anthropic.APIConnectionError):
        what = "could not reach the provider"
    elif isinstance(error, anthropic.APIStatusError) and error.status_code >= 500:
        what = f"the provider is down ({error.status_code} outage), even after retrying"
    elif isinstance(error, anthropic.APIStatusError) and (
        error.status_code == 402 or "credit" in message.lower() or "billing" in message.lower()
    ):
        what = "no credit left, or a billing problem"
    elif isinstance(error, anthropic.APIStatusError):
        what = f"the provider refused the request ({error.status_code})"
    else:
        what = "the call failed"
    return f"{what}: {message}"
