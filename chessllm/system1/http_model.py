"""The decision model port over HTTP: `POST {base_url}/v1/systemone`, which Ollama, llama.cpp's `llama-server` and the
publishers' own servers all serve (docs/research/system-1-models.md), so adding a model is configuration, not code."""

import math
import threading
from collections.abc import Sequence
from typing import Any

import httpx

from chessllm.core.config import SYSTEM1_LIST_TIMEOUT_S, SYSTEM1_REPLY_TIMEOUT_S
from chessllm.exceptions import DecisionModelFailed, System1Unavailable

# The id of the one question a turn asks, whose answer is read back by it.
QUESTION_ID = "move"


class SystemOneModel:
    """A System 1 model served at base_url under the name model. Asks one question at a time: llama-server can't
    take two at once (llama.cpp #30402), and a model on one Mac gains nothing from them."""

    def __init__(
        self,
        base_url: str,
        model: str,
        client: httpx.Client | None = None,
        timeout_s: float = SYSTEM1_REPLY_TIMEOUT_S,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/systemone"
        self._model = model
        self._client = client or httpx.Client(timeout=timeout_s)
        self._asking = threading.Lock()

    def decide(self, state: str, question: str, options: Sequence[str]) -> list[float]:
        """The options as the question's criteria, each a key with no description, so the model sees the moves
        themselves. Raises DecisionModelFailed for any failure of the call: no connection, no answer in time, an
        answer that isn't 200 or isn't the question's probabilities for exactly the options."""
        body = {
            "model": self._model,
            "state": state,
            "questions": {
                QUESTION_ID: {"type": "choice", "instructions": question, "criteria": dict.fromkeys(options)}
            },
        }
        try:
            with self._asking:
                response = self._client.post(self._url, json=body)
        except httpx.HTTPError as error:
            raise DecisionModelFailed(f"{self._model} at {self._url}: {error or type(error).__name__}") from error
        if response.status_code != 200:
            raise DecisionModelFailed(f"{self._model} at {self._url} answered {response.status_code}: {response.text[:200]}")
        return self._probabilities(response, options)

    def _probabilities(self, response: httpx.Response, options: Sequence[str]) -> list[float]:
        try:
            answer: Any = response.json()["answers"].get(QUESTION_ID)
        except (ValueError, KeyError, AttributeError, TypeError):
            raise DecisionModelFailed(f"{self._model}'s answer isn't JSON with answers: {response.text[:200]}") from None
        probabilities = answer.get("probabilities") if isinstance(answer, dict) else None
        if not isinstance(probabilities, dict):
            raise DecisionModelFailed(f"{self._model} gave no answer with probabilities to the question")
        if missing := [option for option in options if option not in probabilities]:
            raise DecisionModelFailed(f"{self._model} gave no probability for {', '.join(missing)}")
        if extra := [option for option in probabilities if option not in options]:
            raise DecisionModelFailed(f"{self._model} gave a probability for {', '.join(extra)}, which wasn't offered")
        values = [probabilities[option] for option in options]
        if not all(isinstance(value, int | float) and not isinstance(value, bool) for value in values):
            raise DecisionModelFailed(f"{self._model} gave a probability that is not a number")
        if not all(math.isfinite(value) for value in values):
            raise DecisionModelFailed(f"{self._model} gave a probability that is not a finite number")
        if any(value < 0 for value in values):
            raise DecisionModelFailed(f"{self._model} gave a negative probability")
        total = sum(values)
        if total <= 0:
            raise DecisionModelFailed(f"{self._model}'s probabilities sum to {total:g}")
        return [value / total for value in values]


def missing_models(
    base_url: str, models: list[str], client: httpx.Client | None = None, timeout_s: float = SYSTEM1_LIST_TIMEOUT_S
) -> list[str]:
    """The models the server at base_url doesn't list, in the order given, from its `GET /v1/models`, which the
    servers all have. Raises System1Unavailable if it can't say: it isn't running, doesn't answer within timeout_s,
    or answers with anything but a list of models."""
    ask = client or httpx.Client(timeout=timeout_s)
    url = f"{base_url.rstrip('/')}/v1/models"
    try:
        response = ask.get(url)
        listed = {entry["id"] for entry in response.json()["data"]} if response.status_code == 200 else None
    except httpx.TimeoutException as error:
        raise System1Unavailable(f"the server at {base_url} didn't answer within {timeout_s:g} s") from error
    except httpx.HTTPError as error:
        raise System1Unavailable(f"the server at {base_url} isn't running or can't be reached: {error}") from error
    except (ValueError, KeyError, TypeError):
        raise System1Unavailable(f"the server at {base_url} didn't list its models: {response.text[:200]}") from None
    if listed is None:
        raise System1Unavailable(f"the server at {base_url} answered {response.status_code} to GET /v1/models")
    return [model for model in models if model not in listed]
