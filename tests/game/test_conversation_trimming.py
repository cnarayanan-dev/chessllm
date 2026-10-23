"""Trimming a conversation that outgrows the context: under a Turn memory that keeps one conversation, the oldest
whole turns are dropped by us, never silently by Ollama, so that the conversation fits the model's 8,192-token
context with room left for the reply. Its size is the last call's prompt_tokens, as Ollama reported them, plus the
text added since at 1.5 characters a token. The System prompt always stays."""

import json

import pytest

from tests.conftest import Raw, ScriptedPlayer

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import full_prompt
from chessllm.game.records import GameState
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import BenchmarkLlmSide, LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog
from chessllm.logs.llm_turns import logged_llm_turns

LLAMA_CHAT = LlmSide(model="llama3:8b", turn_memory="chat_position")  # thinking off: 512 tokens kept for the reply
# White's knight goes out and back, Black's too, then each develops: a game long enough to fill a conversation.
WHITE = ["Nc3", "Nb1", "Nc3", "e3", "d3"]
BLACK = ["Nc6", "Nb8", "Nc6", "e6", "d6"]


def faceoff(tmp_path, white: LlmSide, players: dict[Color, ScriptedPlayer]) -> GameState:
    """Play an LLM faceoff against a fresh llama3:8b to its end, unattended, logging to tmp_path / "games"."""
    settings = Settings("llm_faceoff", white, LlmSide(model="llama3:8b"))
    settings.check(LLM_MODELS)
    log = GameLog(tmp_path / "games", *settings.side_names())
    return play_anchor_match(settings, dict(players), {}, log)


def reporting(replies: list, prompt_tokens: list[int]) -> ScriptedPlayer:
    """A scripted LLM whose calls report these prompt_tokens, in order."""
    player = ScriptedPlayer(replies)
    player.usage = [{"prompt_tokens": tokens} for tokens in prompt_tokens]
    return player


def white_turns(state: GameState):
    return [turn for turn in state.llm_turns if turn.color == "white"]


def rebuilt(state: GameState, color: Color) -> list[list[Message]]:
    """The whole Prompt of every attempt of a side, rebuilt from the records."""
    return [
        [Message(message.role, message.content) for message in full_prompt(state.llm_turns, turn.ply, number)]
        for turn in state.llm_turns
        if turn.color == color
        for number in range(1, len(turn.attempts) + 1)
    ]


def events(games_dir) -> list[dict]:
    [log] = games_dir.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_once_the_conversation_would_pass_the_context_its_oldest_whole_turns_are_dropped(tmp_path):
    # The first answer is long, so the second call reports 3,000 tokens more; by the fourth turn the conversation
    # would leave less than the 512 tokens of a thinking-off reply, and dropping the first turn makes room.
    long_answer = Raw(json.dumps({"reasoning": "x" * 9_000, "move": "Nc3"}))
    white = reporting([long_answer, *WHITE[1:]], [1_000, 4_000, 7_650, 4_700, 4_760])
    black = ScriptedPlayer(BLACK[:4])  # then Black forfeits

    state = faceoff(tmp_path, LLAMA_CHAT, {"white": white, "black": black})

    first, second, third, fourth, fifth = white.prompts
    system = first[0]
    assert fourth[0] == system  # the System prompt stays
    assert fourth[1:] == third[3:] + [Message("assistant", json.dumps({"move": "Nc3"})), fourth[-1]]
    assert fourth[1] == second[3]  # the second turn's message: the first turn is gone whole, its answer too
    assert "x" * 100 not in json.dumps([message.content for message in fourth])
    assert fifth[: len(fourth)] == fourth  # nothing more to drop
    assert [turn.remembered for turn in white_turns(state)] == [0, 1, 2, 2, 3]


def test_remembered_counts_the_turns_sent_and_the_rebuilt_prompt_is_what_was_sent_after_trimming(tmp_path):
    long_answer = Raw(json.dumps({"reasoning": "x" * 9_000, "move": "Nc3"}))
    white = reporting([long_answer, *WHITE[1:]], [1_000, 4_000, 7_650, 4_700, 4_760])

    state = faceoff(tmp_path, LLAMA_CHAT, {"white": white, "black": ScriptedPlayer(BLACK[:4])})

    sent_turns = [sum(message.role == "user" for message in prompt) - 1 for prompt in white.prompts]
    assert [turn.remembered for turn in white_turns(state)] == sent_turns == [0, 1, 2, 2, 3]
    logged = [event for event in events(tmp_path / "games") if event["type"] == "llm_attempt"]
    assert [event["remembered"] for event in logged if event["color"] == "white"] == sent_turns
    assert rebuilt(state, "white") == white.prompts
    assert rebuilt(logged_state(tmp_path), "white") == white.prompts


def test_a_retry_that_no_longer_fits_drops_more_turns_and_records_how_many_it_still_held(tmp_path):
    # The third turn's first answer is long and illegal: kept with its Retry feedback, it leaves too little room for
    # the retry's reply until the first turn is dropped.
    long_illegal = Raw(json.dumps({"reasoning": "x" * 9_000, "move": "Qxf7"}))
    white = reporting(["Nc3", "Nb1", long_illegal, "Nc3", "e3"], [1_000, 1_600, 1_650, 7_600, 7_650])

    state = faceoff(tmp_path, LLAMA_CHAT, {"white": white, "black": ScriptedPlayer(BLACK[:3])})

    _, second, first_attempt, retry, _ = white.prompts
    third = white_turns(state)[2]
    assert third.remembered == 2 and first_attempt[:4] == second  # the first attempt held both earlier turns
    assert retry[1] == second[3]  # the retry the second only
    assert [attempt.remembered for attempt in third.attempts] == [None, 1]
    logged = [event for event in events(tmp_path / "games") if event["type"] == "llm_attempt"]
    assert [event["remembered"] for event in logged if event["color"] == "white"] == [0, 1, 2, 1, 2]
    assert rebuilt(state, "white") == white.prompts
    assert rebuilt(logged_state(tmp_path), "white") == white.prompts


def logged_state(tmp_path) -> GameState:
    """The game's LLM turns as read back from its log."""
    return GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))


@pytest.mark.parametrize(
    ("side", "remembered"),
    [
        (LLAMA_CHAT, 2),  # thinking off: 512 tokens for the reply
        (LlmSide(model="qwen3.5:9b", thinking=True, turn_memory="chat_position"), 1),  # thinking on: 4,096
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=1_024, turn_memory="chat_position"), 2),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=4_096, turn_memory="chat_position"), 1),
        # The budget alone would fit, but not with the forced answer's call: its cap and the sentence handed back.
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=3_072, turn_memory="chat_position"), 1),
    ],
)
def test_the_room_kept_for_the_reply_follows_the_thinking_budget_or_else_whether_the_side_thinks(
    tmp_path, side, remembered
):
    # By the third turn the conversation is some 5,070 tokens, the first turn's long answer nearly 4,000 of them.
    long_answer = Raw(json.dumps({"reasoning": "x" * 4_000, "move": "Nc3"}))
    white = reporting([long_answer, "Nb1", "Nc3"], [1_000, 5_000, 1_100])

    state = faceoff(tmp_path, side, {"white": white, "black": ScriptedPlayer(BLACK[:2])})

    assert white_turns(state)[2].remembered == remembered


def test_a_conversation_that_cannot_fit_even_with_every_earlier_turn_dropped_logs_that_it_may_be_cut(tmp_path):
    # The first answer is illegal and so long that its retry can't fit: there is no earlier turn to drop.
    too_long = Raw(json.dumps({"reasoning": "x" * 25_000, "move": "Qxf7"}))
    white = reporting([too_long, "Nc3", "Nb1"], [1_000, 9_400, 1_100])

    faceoff(tmp_path, LLAMA_CHAT, {"white": white, "black": ScriptedPlayer(BLACK[:1])})

    logged = [event for event in events(tmp_path / "games") if event["type"] == "llm_attempt"]
    assert [event.get("context_may_be_cut") for event in logged if event["color"] == "white"] == [None, True, None]
