"""The Legal counterpart in a conversation kept by Turn memory: asked at the end of the side's conversation so far,
under Listed enforced as a fresh side's is, then dropped from it. The LLM answers with what it knew when it made the
chaos move and never remembers being asked, so the switch changes nothing any later turn is sent. Its attempt records
only the request it added, and its whole Prompt is rebuilt from the records (ADR 0009)."""

import json

import pytest

from tests.conftest import Raw, ScriptedPlayer

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import counterpart_prompt, full_prompt
from chessllm.game.llm_turn.counterpart import counterpart_request
from chessllm.game.records import GameState
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide, TurnMemory
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog
from chessllm.logs.llm_turns import logged_llm_turns

# 1. Bd3 (chaos: the e2 pawn is in the way; its counterpart e4) Bc5 (chaos: the e7 pawn is in the way; its
# counterpart e5) 2. Nf3 Nf6 3. O-O Nc6, then White has no reply left and forfeits.
WHITE = ["Bd3", "e4", "Nf3", "O-O"]
BLACK = ["Bc5", "e5", "Nf6", "Nc6"]
WITHOUT_COUNTERPARTS = {"white": ["Bd3", "Nf3", "O-O"], "black": ["Bc5", "Nf6", "Nc6"]}


def move(san: str) -> str:
    return json.dumps({"move": san})


def faceoff(tmp_path, side: LlmSide, replies: dict[Color, list[str]], legal_counterpart: bool = True):
    """Play an LLM faceoff of two such sides under Chaos rules to its end, unattended. Returns its last state and each
    side's player, which keeps the Prompts it got."""
    settings = Settings("llm_faceoff", side, side, rules="chaos", legal_counterpart=legal_counterpart)
    settings.check(LLM_MODELS)
    players = {color: ScriptedPlayer(moves) for color, moves in replies.items()}
    log = GameLog(tmp_path / "games", *settings.side_names())
    return play_anchor_match(settings, dict(players), {}, log), players


def events(games_dir) -> list[dict]:
    [log] = games_dir.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def as_messages(prompt) -> list[Message]:
    return [Message(message.role, message.content) for message in prompt]


def side_prompts(state: GameState, color: Color) -> list[list[Message]]:
    """The whole Prompt of every attempt of a side's turns, rebuilt from the records."""
    return [
        as_messages(full_prompt(state.llm_turns, turn.ply, number))
        for turn in state.llm_turns
        if turn.color == color
        for number in range(1, len(turn.attempts) + 1)
    ]


def test_under_chat_moves_the_counterpart_is_asked_at_the_end_of_the_conversation_and_dropped_from_it(tmp_path):
    state, players = faceoff(tmp_path, LlmSide(turn_memory="chat_moves"), {"white": WHITE, "black": BLACK})

    first, counterpart, second, *_ = players["white"].prompts
    assert first[-1] == Message("user", "You play White. Make the first move.")
    *conversation, request = counterpart
    assert conversation == [*first, Message("assistant", move("Bd3"))]  # the conversation so far, the chaos move last
    # Under Listed enforced, as a fresh side's counterpart is asked: the Legal-move list, and the answer held to it.
    legal_moves = request.content.split("Legal moves: ")[1].split()
    assert request == Message("user", counterpart_request(" ".join(legal_moves)))
    assert sorted(players["white"].allowed_moves[1] or []) == sorted(legal_moves) and len(legal_moves) == 20
    assert players["white"].allowed_moves[0] is None  # the side's own turns are under Free
    # The next turn continues the conversation as if it had never been asked.
    assert second == [
        *first,
        Message("assistant", move("Bd3")),
        Message("user", "Your Bd3 was played as: bishop f1→d3 (the bishop on f1 moves).\n"
                        "Opponent played Bc5 as: bishop f8→c5 (the bishop on f8 moves)."),
    ]
    requests = [players[color].prompts[1][-1] for color in ("white", "black")]
    later = [prompt for color in ("white", "black") for prompt in players[color].prompts[2:]]
    assert not any(message in requests for prompt in later for message in prompt)
    assert state.llm_turns[0].legal_counterpart is not None and state.llm_turns[0].legal_counterpart.san == "e4"


@pytest.mark.parametrize("turn_memory", ["chat_position", "chat_moves"])
def test_with_the_switch_on_or_off_every_later_turn_is_sent_the_same_prompts(tmp_path, turn_memory: TurnMemory):
    side = LlmSide(turn_memory=turn_memory)

    on, asked = faceoff(tmp_path / "on", side, {"white": WHITE, "black": BLACK})
    off, unasked = faceoff(tmp_path / "off", side, WITHOUT_COUNTERPARTS, legal_counterpart=False)

    white_turns = [prompt for number, prompt in enumerate(asked["white"].prompts) if number != 1]
    black_turns = [prompt for number, prompt in enumerate(asked["black"].prompts) if number != 1]
    assert (white_turns, black_turns) == (unasked["white"].prompts, unasked["black"].prompts)
    assert on.pgn == off.pgn == "1. Bd3 Bc5 2. Nf3 Nf6 3. O-O Nc6"


def test_the_counterpart_records_only_its_request_and_its_whole_prompt_is_rebuilt_from_the_state_and_the_log(tmp_path):
    state, players = faceoff(tmp_path, LlmSide(turn_memory="chat_position"), {"white": WHITE, "black": BLACK})

    white_counterpart, black_counterpart = (turn.legal_counterpart for turn in state.llm_turns[:2])
    assert white_counterpart is not None and black_counterpart is not None
    request = players["white"].prompts[1][-1]
    assert as_messages(white_counterpart.attempt.prompt or []) == [request]
    assert white_counterpart.attempt.remembered is None  # it remembered what its chaos move's turn did
    logged = GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))
    assert logged.llm_turns == state.llm_turns  # the counterparts included
    for rebuilt_from in (state, logged):
        assert as_messages(counterpart_prompt(rebuilt_from.llm_turns, 1)) == players["white"].prompts[1]
        assert as_messages(counterpart_prompt(rebuilt_from.llm_turns, 2)) == players["black"].prompts[1]
        assert side_prompts(rebuilt_from, "white") == [players["white"].prompts[0], *players["white"].prompts[2:]]
    counterparts = [event for event in events(tmp_path / "games") if event["type"] == "legal_counterpart"]
    assert [event["remembered"] for event in counterparts] == [0, 0]
    assert counterparts[0]["prompt"] == [{"role": "user", "content": request.content}]


def test_a_fresh_sides_counterpart_records_its_whole_prompt(tmp_path):
    state, players = faceoff(tmp_path, LlmSide(), {"white": WHITE, "black": BLACK})

    [system, position] = players["white"].prompts[1]
    assert system.role == "system" and position.content.startswith("PGN: (no moves yet)\nFEN: ")
    assert as_messages(counterpart_prompt(state.llm_turns, 1)) == [system, position]
    logged = [event for event in events(tmp_path / "games") if event["type"] == "legal_counterpart"]
    assert len(logged) == 2 and not any("remembered" in event for event in logged)


def test_a_counterpart_that_would_pass_the_context_is_trimmed_alone_and_its_attempt_records_it(tmp_path):
    side = LlmSide(model="llama3:8b", turn_memory="chat_position")
    white = ScriptedPlayer(["f3", "Bd3", "e4", "g4"])  # 1. f3 e5 2. Bd3 (chaos: the e2 pawn is in the way)
    # Measured at 7,650 tokens, the conversation with the chaos move's answer, the request and 512 tokens for the
    # reply passes 8,192, so the counterpart is sent it without turn 1. Its own measurement is never the
    # conversation's: had it been, turn 3 would have kept turn 1.
    white.usage = [{"prompt_tokens": tokens} for tokens in (500, 7650, 100, 700)]
    settings = Settings("llm_faceoff", side, LlmSide(), rules="chaos")
    settings.check(LLM_MODELS)
    players = {"white": white, "black": ScriptedPlayer(["e5", "d6"])}
    state = play_anchor_match(settings, dict(players), {}, GameLog(tmp_path / "games", *settings.side_names()))

    _, chaos, counterpart, third = white.prompts
    assert counterpart == [chaos[0], *chaos[3:], Message("assistant", move("Bd3")), counterpart[-1]]
    # The next turn trimmed turn 1 by the conversation's own measure.
    assert third == [chaos[0], *chaos[3:], Message("assistant", move("Bd3")), third[-1]]
    chaos_turn = state.llm_turns[2]
    assert chaos_turn.remembered == 1
    assert chaos_turn.legal_counterpart is not None and chaos_turn.legal_counterpart.attempt.remembered == 0
    assert as_messages(counterpart_prompt(state.llm_turns, 3)) == counterpart
    logged = GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))
    assert as_messages(counterpart_prompt(logged.llm_turns, 3)) == counterpart


def chat_game(tmp_path, side: LlmSide, white: ScriptedPlayer, black_moves: list[str]) -> GameState:
    """Play an LLM faceoff under Chaos rules, side as White and a fresh Black, to its end, unattended."""
    settings = Settings("llm_faceoff", side, LlmSide(), rules="chaos")
    settings.check(LLM_MODELS)
    players = {"white": white, "black": ScriptedPlayer(black_moves)}
    return play_anchor_match(settings, dict(players), {}, GameLog(tmp_path / "games", *settings.side_names()))


def test_a_failed_counterpart_in_a_conversation_records_its_request_and_its_prompt_is_rebuilt(tmp_path):
    white = ScriptedPlayer(["f3", "Bd3", RuntimeError("connection refused"), "g4"])

    state = chat_game(tmp_path, LlmSide(turn_memory="chat_position"), white, ["e5", "d6"])

    counterpart = state.llm_turns[2].legal_counterpart
    assert counterpart is not None and counterpart.attempt.result == "error" and counterpart.move is None
    _, _, asked, after = white.prompts
    assert as_messages(counterpart.attempt.prompt or []) == asked[-1:] and counterpart.attempt.remembered is None
    logged = GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))
    assert logged.llm_turns == state.llm_turns
    for rebuilt_from in (state, logged):
        assert as_messages(counterpart_prompt(rebuilt_from.llm_turns, 3)) == asked
    [event] = [event for event in events(tmp_path / "games") if event["type"] == "legal_counterpart"]
    assert event["remembered"] == 1
    assert after[:-1] == asked[:-1]  # the next turn goes on from the chaos move, the request dropped


@pytest.mark.parametrize("retry_feedback", ["explained", "repeat"])
def test_a_chaos_move_on_a_retry_has_its_counterpart_asked_after_the_turn_as_the_conversation_kept_it(
    tmp_path, retry_feedback
):
    side = LlmSide(turn_memory="chat_position", retry_feedback=retry_feedback)
    # 1. f3 e5 2. (no move: a Retry) Bd3 (chaos: the e2 pawn is in the way), its counterpart e4.
    white = ScriptedPlayer(["f3", Raw("I would rather not."), "Bd3", "e4", "g4"])

    state = chat_game(tmp_path, side, white, ["e5", "d6"])

    _, _, retried, asked, _ = white.prompts
    assert asked[:-1] == [*retried, Message("assistant", move("Bd3"))]
    if retry_feedback == "repeat":  # the answer with no move was left out of the conversation
        assert "I would rather not." not in json.dumps([message.content for message in asked])
    else:
        assert asked[-4] == Message("assistant", "I would rather not.")
    logged = GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))
    assert logged.llm_turns == state.llm_turns
    for rebuilt_from in (state, logged):
        assert as_messages(counterpart_prompt(rebuilt_from.llm_turns, 3)) == asked
        assert side_prompts(rebuilt_from, "white") == [*white.prompts[:3], white.prompts[4]]


def test_a_counterpart_logged_before_it_was_asked_inside_the_conversation_is_rebuilt_as_recorded(tmp_path):
    # A chat game logged after Legal counterparts came (#100) but before they were asked inside the conversation:
    # its counterpart was sent a fresh Prompt, logged whole, with no remembered.
    chat_game(tmp_path, LlmSide(turn_memory="chat_position"), ScriptedPlayer(["f3", "Bd3", "e4", "g4"]), ["e5", "d6"])
    fresh = [{"role": "system", "content": "The System prompt."}, {"role": "user", "content": "PGN: 1. f3 e5\n..."}]
    old = []
    for event in events(tmp_path / "games"):
        if event["type"] == "legal_counterpart":
            event = {key: value for key, value in event.items() if key != "remembered"} | {"prompt": fresh}
        old.append(event)

    llm_turns = logged_llm_turns(old)

    counterpart = llm_turns[2].legal_counterpart
    assert counterpart is not None and counterpart.attempt.remembered is None
    assert [message.model_dump() for message in counterpart_prompt(llm_turns, 3)] == fresh
