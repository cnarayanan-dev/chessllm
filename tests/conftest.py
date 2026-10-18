import json

import pytest
from fastapi.testclient import TestClient

from chessllm.app import create_app
from chessllm.players import LlmReply, Message


class Raw(str):
    """A scripted reply sent to the game exactly as written, instead of wrapped as {"move": ...}."""


class ScriptedPlayer:
    """Test fake for the LLM player port: answers with the scripted SAN moves in order, as the JSON
    {"move": "<san>"}, and records every prompt. Thinking texts, if given, go with the replies in order."""

    def __init__(self, replies: list[str], thinking: list[str] | None = None) -> None:
        self.replies = list(replies)
        self.thinking = list(thinking) if thinking is not None else None
        self.prompts: list[list[Message]] = []

    def reply(self, messages: list[Message]) -> LlmReply:
        self.prompts.append(messages)
        move = self.replies.pop(0)
        raw = move if isinstance(move, Raw) else json.dumps({"move": move})
        thinking = self.thinking.pop(0) if self.thinking is not None else None
        return LlmReply(raw=raw, thinking=thinking, latency_s=0.0)


@pytest.fixture
def scripted():
    def make(replies: list[str], thinking: list[str] | None = None, **settings) -> tuple[TestClient, ScriptedPlayer]:
        player = ScriptedPlayer(replies, thinking)
        return TestClient(create_app(player, **settings)), player

    return make
