import json

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from chessllm.app import create_app
from chessllm.game import Color, Settings
from chessllm.players import LlmReply, Message


class Raw(str):
    """A scripted reply sent to the game exactly as written, instead of wrapped as {"move": ...}."""


def play_llm(human_color: Color = "white", **llm) -> dict:
    """The new-game request body for Play LLM: the human plays human_color, and the LLM the other side, with the
    given LLM settings (the defaults for the rest)."""
    llm_color = "black" if human_color == "white" else "white"
    return {"mode": "play_llm", human_color: {"player": "human"}, llm_color: {"player": "llm", **llm}}


def llm_faceoff(white: dict | None = None, black: dict | None = None) -> dict:
    """The new-game request body for an LLM faceoff, with the given settings for each LLM (the defaults for the rest)."""
    return {"mode": "llm_faceoff", "white": {"player": "llm", **(white or {})}, "black": {"player": "llm", **(black or {})}}


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
        self.colors: list[Color] = []  # the side each build was for

    def for_settings(self, settings: Settings, color: Color) -> "ScriptedPlayer":
        self.built_for.append(settings)
        self.colors.append(color)
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


@pytest.fixture
def faceoff(tmp_path):
    """Makes an app with a separate ScriptedPlayer per side, and starts an LLM faceoff between them with the given
    settings per side. Returns the client, the start state and the two players."""

    def make(
        white: list[str | Exception], black: list[str | Exception], white_settings=None, black_settings=None, **options
    ) -> tuple[TestClient, dict, dict[str, ScriptedPlayer]]:
        players = {"white": ScriptedPlayer(white), "black": ScriptedPlayer(black)}
        options.setdefault("games_dir", tmp_path / "games")
        options.setdefault("sampling_file", tmp_path / "no-sampling.toml")
        client = TestClient(create_app(lambda settings, color: players[color].for_settings(settings, color), **options))
        response = client.post("/api/games", json=llm_faceoff(white_settings, black_settings))
        assert response.status_code == 200, response.text
        return client, response.json(), players

    return make
