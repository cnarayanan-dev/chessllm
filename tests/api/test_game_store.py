"""The GameStore holds the one current game of a server: starting a game replaces it and abandons the old one."""

import pytest

from tests.conftest import Raw, ScriptedPlayer

from chessllm.api.state import GameStore
from chessllm.exceptions import NoGameStarted
from chessllm.game.session import GameSession, HumanSide, LlmSide, Settings
from chessllm.logs.game_log import GameLog


def new_game(tmp_path, player: ScriptedPlayer) -> GameSession:
    """A game with the LLM as White, so its first turn is the LLM's."""
    settings = Settings(white=LlmSide(), black=HumanSide())
    return GameSession({"white": player}, settings, GameLog(tmp_path, *settings.side_names()))


def test_there_is_no_current_game_until_one_starts():
    with pytest.raises(NoGameStarted):
        GameStore().current()


def test_the_game_started_is_the_current_one(tmp_path):
    store = GameStore()
    game = new_game(tmp_path, ScriptedPlayer([]))

    store.start(game)

    assert store.current() is game


def test_starting_a_game_replaces_the_current_one_and_abandons_it(tmp_path):
    store = GameStore()
    old_player = ScriptedPlayer([Raw("{}")])
    old, new = new_game(tmp_path, old_player), new_game(tmp_path, ScriptedPlayer([]))
    store.start(old)

    store.start(new)

    assert store.current() is new
    old.play_llm_turn()  # an abandoned game's turn is never played
    assert old_player.prompts == []
