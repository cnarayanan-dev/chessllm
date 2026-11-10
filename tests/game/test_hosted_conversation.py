"""A conversation kept by Turn memory is trimmed to the context of its model: a Hosted model's holds a million tokens
(ADR 0013), so a conversation that would outgrow a local model's 8,192 is kept whole."""

import json

from tests.conftest import Raw, ScriptedPlayer
from tests.game.test_conversation_trimming import BLACK, WHITE, reporting, white_turns

from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.models import KNOWN_MODELS
from chessllm.logs.game_log import GameLog


def test_a_hosted_models_conversation_is_not_trimmed_where_a_local_models_would_be(tmp_path):
    long_answer = Raw(json.dumps({"reasoning": "x" * 9_000, "move": "Nc3"}))
    white = reporting([long_answer, *WHITE[1:]], [1_000, 4_000, 7_650, 4_700, 4_760])
    settings = Settings(
        "llm_faceoff", LlmSide(model="claude-haiku-5-5", turn_memory="chat_position"), LlmSide(model="llama3:8b")
    )
    settings.check(KNOWN_MODELS)
    log = GameLog(tmp_path / "games", *settings.side_names())

    state = play_anchor_match(settings, {"white": white, "black": ScriptedPlayer(BLACK[:4])}, {}, log)

    assert [turn.remembered for turn in white_turns(state)] == [0, 1, 2, 3, 4]
