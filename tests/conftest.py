import pytest
from fastapi.testclient import TestClient

from chessllm.app import create_app
from chessllm.players import LlmReply, Message


class ScriptedPlayer:
    """Test fake for the LLM player port: replies with scripted SAN moves in order and records every prompt."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[list[Message]] = []

    def reply(self, messages: list[Message]) -> LlmReply:
        self.prompts.append(messages)
        return LlmReply(raw=self.replies.pop(0), thinking=None, latency_s=0.0)


@pytest.fixture
def scripted():
    def make(replies: list[str]) -> tuple[TestClient, ScriptedPlayer]:
        player = ScriptedPlayer(replies)
        return TestClient(create_app(player)), player

    return make
