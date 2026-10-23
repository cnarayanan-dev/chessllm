"""The Legal counterpart in a conversation kept by Turn memory: asked at the end of the side's conversation so far,
under Listed enforced, then dropped from it. The LLM answers with what it knew when it made the chaos move and
never remembers being asked, so the switch changes nothing its later turns are sent. Its Prompt is recorded as its
request alone, and rebuilt from the records (ADR 0009)."""

import json

import pytest

from tests.conftest import ScriptedPlayer
from tests.game.test_turn_memory import as_messages, events

from chessllm.game.llm_turn.conversation import counterpart_prompt
from chessllm.game.records import GameState
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog
from chessllm.logs.llm_turns import logged_llm_turns

LLAMA_CHAT = LlmSide(model="llama3:8b", turn_memory="chat_position")  # thinking off: 512 tokens kept for the reply
LLAMA_MOVES = LlmSide(model="llama3:8b", turn_memory="chat_moves")
# White's knight goes out and back, then its queen jumps over the e2 pawn to h5, a chaos move; Black's knight goes
# out and back and Black then plays on legally.
WHITE = ["Nc3", "Nb1", "Qh5", "a3", "b3"]
BLACK = ["Nc6", "Nb8", "a6", "h6"]
CHAOS_PLY = 5


def play(
    tmp_path, white: LlmSide, white_replies: list, legal_counterpart: bool, usage: list[dict] | None = None
) -> tuple[GameSession, ScriptedPlayer]:
    """Play the first nine plies of an LLM faceoff under Chaos rules, White on the side given, Black a fresh llama3:8b.
    With the switch on, White's player is asked once more after its chaos move, its fourth call."""
    white_player, black_player = ScriptedPlayer(white_replies), ScriptedPlayer(BLACK)
    white_player.usage = list(usage or [])
    black_side = LlmSide(model="llama3:8b")
    settings = Settings("llm_faceoff", white, black_side, rules="chaos", legal_counterpart=legal_counterpart)
    settings.check(LLM_MODELS)
    game = GameSession(
        {"white": white_player, "black": black_player}, settings, GameLog(tmp_path / "games", *settings.side_names())
    )
    for _ in range(9):
        game.play_llm_turn()
    return game, white_player


def with_counterpart(replies: list[str], counterpart: str = "e4") -> list[str]:
    """White's replies with the Legal counterpart's after the chaos move's."""
    return [*replies[:3], counterpart, *replies[3:]]


def logged_state(tmp_path) -> GameState:
    """The game's LLM turns as read back from its log."""
    return GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))


def test_the_counterparts_prompt_is_the_conversation_so_far_and_its_request_and_the_next_turn_holds_neither(tmp_path):
    _, white = play(tmp_path, LLAMA_MOVES, with_counterpart(WHITE), legal_counterpart=True)

    _, _, chaos, counterpart, after, _ = white.prompts
    request = counterpart[-1]
    assert counterpart == [*chaos, Message("assistant", json.dumps({"move": "Qh5"})), request]
    assert request.role == "user"
    # Asked under Listed enforced: the request carries the Legal-move list, and the answer is held to it.
    first_line, listed = request.content.split("\n")
    assert first_line == "Your move is illegal in this position. Reply with a legal move instead."
    legal_moves = listed.removeprefix("Legal moves: ").split()
    assert len(legal_moves) == 20 and "e4" in legal_moves and "Qh5" not in legal_moves
    assert sorted(white.allowed_moves[3] or []) == sorted(legal_moves)
    assert white.allowed_moves[2] is None  # the turn itself under the side's own LLM constraints, Free
    # The conversation's own System prompt is kept: the side's, not the Listed enforced one.
    assert counterpart[0] == chaos[0]
    # The next turn goes on from the chaos move's answer, and was never asked for the counterpart.
    assert after[: len(chaos) + 1] == counterpart[:-1]
    assert request not in after and Message("assistant", json.dumps({"move": "e4"})) not in after


@pytest.mark.parametrize("side", [LLAMA_CHAT, LLAMA_MOVES])
def test_the_same_game_with_the_switch_on_and_off_sends_the_same_prompts_to_every_turn_after_the_chaos_move(
    tmp_path, side
):
    # The counterpart's call reports far more prompt tokens than the conversation holds: measured into it, they
    # would have the next turns drop earlier ones to fit the context.
    usage = [{"prompt_tokens": 500}, {"prompt_tokens": 600}, {"prompt_tokens": 700}]
    _, on = play(tmp_path / "on", side, with_counterpart(WHITE), True, [*usage, {"prompt_tokens": 7_900}])
    _, off = play(tmp_path / "off", side, WHITE, False, usage)

    assert len(on.prompts) == len(off.prompts) + 1
    assert on.prompts[:3] + on.prompts[4:] == off.prompts
    # The turn after the chaos move opens with its Chaos move report, not with the counterpart.
    assert on.prompts[4][-1].content.startswith("Your Qh5 was played as: queen d1→h5 ")


def test_the_counterparts_record_holds_only_its_request_and_its_prompt_is_rebuilt_from_the_records(tmp_path):
    game, white = play(tmp_path, LLAMA_MOVES, with_counterpart(WHITE), legal_counterpart=True)

    state = game.state()
    chaos_turn = next(turn for turn in state.llm_turns if turn.ply == CHAOS_PLY)
    assert chaos_turn.legal_counterpart is not None
    attempt = chaos_turn.legal_counterpart.attempt
    assert [(message.role, message.content) for message in attempt.prompt or []] == [
        ("user", white.prompts[3][-1].content)
    ]
    assert (attempt.move, chaos_turn.legal_counterpart.move) == ("e4", "e2e4")
    for rebuilt_from in (state, logged_state(tmp_path)):
        assert as_messages(counterpart_prompt(rebuilt_from.llm_turns, CHAOS_PLY)) == white.prompts[3]
    [logged] = [event for event in events(tmp_path / "games") if event["type"] == "legal_counterpart"]
    assert logged["remembered"] == 2


def test_a_counterpart_that_would_not_fit_drops_earlier_turns_for_itself_alone(tmp_path):
    # The chaos move's call reports the conversation so close to the context that its request no longer fits with
    # the 512 tokens of the reply: its Prompt drops the oldest turn, which the conversation itself keeps.
    usage = [{"prompt_tokens": 500}, {"prompt_tokens": 600}, {"prompt_tokens": 7_600}]
    game, white = play(tmp_path, LLAMA_CHAT, with_counterpart(WHITE), True, usage)

    _, second, chaos, counterpart, _, _ = white.prompts
    assert counterpart[0] == chaos[0]
    assert counterpart[1] == second[3]  # the first turn is gone whole, its answer too
    assert counterpart[1:-1] == chaos[3:] + [Message("assistant", json.dumps({"move": "Qh5"}))]
    state = game.state()
    chaos_turn = next(turn for turn in state.llm_turns if turn.ply == CHAOS_PLY)
    assert chaos_turn.remembered == 2
    assert chaos_turn.legal_counterpart is not None and chaos_turn.legal_counterpart.attempt.remembered == 1
    for rebuilt_from in (state, logged_state(tmp_path)):
        assert as_messages(counterpart_prompt(rebuilt_from.llm_turns, CHAOS_PLY)) == counterpart


def test_a_fresh_sides_counterpart_is_still_asked_with_a_fresh_prompt_recorded_whole(tmp_path):
    game, white = play(tmp_path, LlmSide(model="llama3:8b"), with_counterpart(WHITE), legal_counterpart=True)

    counterpart = white.prompts[3]
    assert len(counterpart) == 2 and counterpart[1].content.startswith("PGN: 1. Nc3 Nc6 2. Nb1 Nb8\n")
    assert as_messages(counterpart_prompt(game.state().llm_turns, CHAOS_PLY)) == counterpart
