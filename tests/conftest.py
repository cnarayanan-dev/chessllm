import threading

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from chessllm.api.app import create_app
from chessllm.core.types import Color
from chessllm.game.settings import Settings
from chessllm.llm.players import LlmReply, Message, Tools
from tests.fakes import FakeClock, Raw, ScriptedAnchor, ScriptedPlayer  # the tests import them from here


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


class BlockingPlayer(ScriptedPlayer):
    """Test fake for the LLM player port: a ScriptedPlayer that holds each reply until released, so a turn can be
    kept running. asked is set once it has been asked to move."""

    def __init__(self, replies: list[str | BaseException]) -> None:
        super().__init__(replies)
        self.asked = threading.Event()
        self.release = threading.Event()

    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Tools | None = None
    ) -> LlmReply:
        self.asked.set()
        assert self.release.wait(timeout=5)
        return super().reply(messages, allowed_moves, tools)

@pytest.fixture
def scripted(tmp_path):
    """Makes an app playing against a ScriptedPlayer. Game logs go to tmp_path / "games" unless games_dir is given,
    there is no sampling config unless sampling_file is given, and the Prompt library holds only the defaults unless
    prompt_library_dir is given. Its moves are timed by a FakeClock that stands still, unless a clock is given, so
    every time is 0 and a state is the same however long the test takes."""

    def make(
        replies: list[str | Exception], thinking: list[str] | None = None, **options
    ) -> tuple[TestClient, ScriptedPlayer]:
        player = ScriptedPlayer(replies, thinking)
        options.setdefault("games_dir", tmp_path / "games")
        options.setdefault("sampling_file", tmp_path / "no-sampling.toml")
        options.setdefault("prompt_library_dir", tmp_path / "prompt_library")
        options.setdefault("clock", FakeClock())
        return TestClient(create_app(player.for_settings, **options)), player

    return make


@pytest.fixture
def faceoff(tmp_path):
    """Makes an app with a separate ScriptedPlayer per side, and starts an LLM faceoff between them with the given
    settings per side, timed like scripted's. Returns the client, the start state and the two players."""

    def make(
        white: list[str | Exception], black: list[str | Exception], white_settings=None, black_settings=None, **options
    ) -> tuple[TestClient, dict, dict[str, ScriptedPlayer]]:
        players = {"white": ScriptedPlayer(white), "black": ScriptedPlayer(black)}
        options.setdefault("games_dir", tmp_path / "games")
        options.setdefault("sampling_file", tmp_path / "no-sampling.toml")
        options.setdefault("prompt_library_dir", tmp_path / "prompt_library")
        options.setdefault("clock", FakeClock())
        client = TestClient(create_app(lambda settings, color: players[color].for_settings(settings, color), **options))
        response = client.post("/api/games", json=llm_faceoff(white_settings, black_settings))
        assert response.status_code == 200, response.text
        return client, response.json(), players

    return make
