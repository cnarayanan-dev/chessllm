import json

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from chessllm.app import create_app
from chessllm.game import Settings
from chessllm.players import LlmReply, Message


class Raw(str):
    """A scripted reply sent to the game exactly as written, instead of wrapped as {"move": ...}."""


def play_move(client: TestClient, uci: str) -> Response:
    """Post the human's move, then ask for the LLM's turn as the page does while the game goes on.
    Returns the last response: the move's if it was rejected or ended the game, else the LLM turn's."""
    response = client.post("/api/games/current/moves", json={"uci": uci})
    if response.status_code != 200 or response.json()["status"] != "playing":
        return response
    return client.post("/api/games/current/llm-turn")


class ScriptedPlayer:
    """Test fake for the LLM player port: answers with the scripted SAN moves in order, as the JSON
    {"move": "<san>"}, and records every prompt and the allowed moves it came with. A scripted exception is
    raised instead of answering.
    Thinking texts, if given, go with the replies in order. It serves every game, recording the settings
    of each game it is built for."""

    def __init__(self, replies: list[str | Exception], thinking: list[str] | None = None) -> None:
        self.replies = list(replies)
        self.thinking = list(thinking) if thinking is not None else None
        self.prompts: list[list[Message]] = []
        self.allowed_moves: list[list[str] | None] = []
        self.built_for: list[Settings] = []

    def for_settings(self, settings: Settings) -> "ScriptedPlayer":
        self.built_for.append(settings)
        return self

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        self.prompts.append(messages)
        self.allowed_moves.append(allowed_moves)
        move = self.replies.pop(0)
        if isinstance(move, Exception):
            raise move
        raw = move if isinstance(move, Raw) else json.dumps({"move": move})
        thinking = self.thinking.pop(0) if self.thinking is not None else None
        return LlmReply(raw=raw, thinking=thinking, latency_s=0.0)


@pytest.fixture
def scripted(tmp_path):
    """Makes an app playing against a ScriptedPlayer. Game logs go to tmp_path / "games" unless games_dir is given,
    and there is no sampling config unless sampling_file is given."""

    def make(
        replies: list[str | Exception], thinking: list[str] | None = None, **options
    ) -> tuple[TestClient, ScriptedPlayer]:
        player = ScriptedPlayer(replies, thinking)
        options.setdefault("games_dir", tmp_path / "games")
        options.setdefault("sampling_file", tmp_path / "no-sampling.toml")
        return TestClient(create_app(player.for_settings, **options)), player

    return make
