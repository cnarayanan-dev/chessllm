"""The /v1/systemone adapter of the decision model port, against a fake HTTP server (no model server needed)."""

import json
import threading
import time

import httpx
import pytest

from chessllm.exceptions import DecisionModelFailed, System1Unavailable
from chessllm.system1.http_model import SystemOneModel, missing_models

BASE_URL = "http://localhost:11434"
STATE = "FEN: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
QUESTION = "Which move should White play?"


def serving(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def answering(probabilities):
    """A fake server that answers every request as /v1/systemone does, and records the requests it got."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        answer = {"type": "choice", "choice": "e4", "probabilities": probabilities, "confidence": 0.5}
        return httpx.Response(200, json={"model": "d3:9b", "answers": {"move": answer}, "usage": {}})

    return handler, requests


def test_the_position_is_sent_as_one_choice_question_whose_criteria_are_the_options():
    handler, requests = answering({"e4": 0.5, "d4": 0.3, "Nf3": 0.2})
    model = SystemOneModel(BASE_URL, "d3:9b", client=serving(handler))

    model.decide(STATE, QUESTION, ["e4", "d4", "Nf3"])

    [request] = requests
    assert (request.method, str(request.url)) == ("POST", f"{BASE_URL}/v1/systemone")
    assert json.loads(request.content) == {
        "model": "d3:9b",
        "state": STATE,
        "questions": {
            "move": {"type": "choice", "instructions": QUESTION, "criteria": {"e4": None, "d4": None, "Nf3": None}}
        },
    }


def test_each_options_probability_is_mapped_back_in_the_order_the_options_were_given():
    handler, _ = answering({"Nf3": 0.2, "e4": 0.5, "d4": 0.3})  # the server's order is not the options'
    model = SystemOneModel(BASE_URL, "d3:9b", client=serving(handler))

    assert model.decide(STATE, QUESTION, ["e4", "d4", "Nf3"]) == pytest.approx([0.5, 0.3, 0.2])


def test_probabilities_are_renormalised_to_sum_to_one():
    handler, _ = answering({"e4": 0.5, "d4": 0.25, "Nf3": 0.2499})
    model = SystemOneModel(BASE_URL, "d3:9b", client=serving(handler))

    assert sum(model.decide(STATE, QUESTION, ["e4", "d4", "Nf3"])) == pytest.approx(1.0)


def server_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, text="boom")


def not_json(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>")


def no_answers(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"model": "d3:9b", "answers": {}})


def refusing(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused")


def stalling(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out")


def answer_with(probabilities):
    return answering(probabilities)[0]


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (refusing, "connection refused"),
        (stalling, "timed out"),
        (server_error, "500"),
        (not_json, "isn't JSON"),
        (no_answers, "no answer"),
        (answer_with({"e4": 0.6, "d4": 0.4}), "Nf3"),  # a probability missing
        (answer_with({"e4": 0.5, "d4": 0.3, "Nf3": 0.1, "a3": 0.1}), "a3"),  # one for a move not offered
        (answer_with({"e4": 0.5, "d4": -0.3, "Nf3": 0.8}), "negative"),
        (answer_with({"e4": "high", "d4": 0.3, "Nf3": 0.2}), "not a number"),
        (answer_with({"e4": 0.0, "d4": 0.0, "Nf3": 0.0}), "sum to 0"),
    ],
)
def test_every_failure_of_the_call_is_the_one_exception(handler, reason):
    model = SystemOneModel(BASE_URL, "d3:9b", client=serving(handler))

    with pytest.raises(DecisionModelFailed, match=reason):
        model.decide(STATE, QUESTION, ["e4", "d4", "Nf3"])


def test_requests_go_one_at_a_time():
    running, most = 0, 0
    guard = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal running, most
        with guard:
            running += 1
            most = max(most, running)
        time.sleep(0.02)
        with guard:
            running -= 1
        return answer_with({"e4": 0.5, "d4": 0.5})(request)

    model = SystemOneModel(BASE_URL, "d3:9b", client=serving(handler))
    threads = [threading.Thread(target=model.decide, args=(STATE, QUESTION, ["e4", "d4"])) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert most == 1


def listing(*models: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.method, str(request.url)) == ("GET", f"{BASE_URL}/v1/models")
        return httpx.Response(200, json={"object": "list", "data": [{"id": model} for model in models]})

    return handler


def test_the_models_a_server_doesnt_list_are_missing():
    client = serving(listing("d3:9b", "d1:2b"))

    assert missing_models(BASE_URL, ["d3:2b", "d3:9b"], client=client) == ["d3:2b"]


@pytest.mark.parametrize("handler", [refusing, stalling, server_error, not_json])
def test_a_server_that_cant_say_which_models_it_has_is_unavailable(handler):
    with pytest.raises(System1Unavailable, match=BASE_URL):
        missing_models(BASE_URL, ["d3:9b"], client=serving(handler))
