"""Trimming a conversation that outgrows the context: before each attempt, the oldest whole earlier turns are dropped
until the conversation, as Ollama last measured it plus the text added since, fits the model's context with room
left for the reply. The System prompt is always kept, and each turn records how many earlier turns it remembered."""

import json

import pytest
from tests.conftest import Raw, ScriptedPlayer

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import full_prompt, reply_reserve
from chessllm.game.records import GameState
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import BenchmarkLlmSide, LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog
from chessllm.logs.llm_turns import logged_llm_turns

LLAMA_CHAT = LlmSide(model="llama3:8b", turn_memory="chat_position")
QWEN_CHAT = LlmSide(model="qwen3.5:9b", thinking=True, turn_memory="chat_position")


def move(san: str) -> str:
    return json.dumps({"move": san})


def measured(*prompt_tokens: int | None) -> list[dict]:
    """The usage of each scripted reply: the prompt tokens Ollama reports for what it was sent."""
    return [{"prompt_tokens": tokens} for tokens in prompt_tokens]


def play(tmp_path, white: LlmSide, players: dict[Color, ScriptedPlayer], plies: int) -> GameState:
    """Play the first plies of an LLM faceoff, black a fresh llama3:8b."""
    settings = Settings("llm_faceoff", white, LlmSide())
    settings.check(LLM_MODELS)
    game = GameSession(players, settings, GameLog(tmp_path, *settings.side_names()))
    for _ in range(plies):
        game.play_llm_turn()
    return game.state()


def logged(tmp_path) -> GameState:
    [log] = tmp_path.glob("*.jsonl")
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return GameState.model_construct(llm_turns=logged_llm_turns(events))


def white_prompts(state: GameState) -> list[list[Message]]:
    """The whole Prompt of every attempt of White, rebuilt from the records."""
    return [
        [Message(message.role, message.content) for message in full_prompt(state.llm_turns, turn.ply, number)]
        for turn in state.llm_turns
        if turn.color == "white"
        for number in range(1, len(turn.attempts) + 1)
    ]


def test_once_the_conversation_would_pass_the_context_its_oldest_whole_turns_are_dropped(tmp_path):
    white = ScriptedPlayer(["Qxf7", "f3", "g4", "h3"])
    white.usage = measured(500, 600, 7660, 900)
    black = ScriptedPlayer(["e5", "d6", "c6"])

    state = play(tmp_path, LLAMA_CHAT, {"white": white, "black": black}, 5)

    _, _, second, third = white.prompts
    system = second[0]
    # Measured at 7,660 tokens, the conversation with turn 3's message and 512 tokens for the reply passes 8,192:
    # turn 1 goes whole, its illegal attempt, Retry feedback and played move together, and turn 2 is kept.
    assert third == [system, *second[5:], Message("assistant", move("g4")), third[-1]]
    assert third[0].role == "system" and third[-1].content.startswith("PGN: 1. f3 e5 2. g4 d6\n")
    assert "Qxf7" not in json.dumps([message.content for message in third])
    assert [turn.remembered for turn in state.llm_turns if turn.color == "white"] == [0, 1, 1]


def test_remembered_counts_the_turns_sent_and_the_rebuilt_prompt_is_what_was_sent_after_trimming(tmp_path):
    white = ScriptedPlayer(["f3", "g4", "h3", "a3"])
    white.usage = measured(500, 7660, 600, 700)
    black = ScriptedPlayer(["e5", "d6", "c6"])

    state = play(tmp_path, LLAMA_CHAT, {"white": white, "black": black}, 7)

    remembered = [turn.remembered for turn in state.llm_turns if turn.color == "white"]
    assert remembered == [0, 1, 1, 2]  # trimmed once, at turn 3; then it grows again
    sent_earlier = [(len(prompt) - 2) // 2 for prompt in white.prompts]  # each earlier turn: its message and move
    assert sent_earlier == remembered
    assert white_prompts(state) == white.prompts
    assert logged(tmp_path).llm_turns == state.llm_turns
    assert white_prompts(logged(tmp_path)) == white.prompts


def test_a_retry_that_would_pass_the_context_drops_earlier_turns_mid_turn_and_its_attempt_records_it(tmp_path):
    white = ScriptedPlayer(["f3", "g4", "Qxf7", "h3"])
    white.usage = measured(500, 600, 7660, 800)
    black = ScriptedPlayer(["e5", "d6", "c6"])

    state = play(tmp_path, LLAMA_CHAT, {"white": white, "black": black}, 5)

    third = state.llm_turns[4]
    assert third.remembered == 2  # what the turn's first attempt remembered
    assert [attempt.remembered for attempt in third.attempts] == [None, 1]  # set only where it differs
    *_, illegal, retried = white.prompts
    assert retried == [illegal[0], *illegal[3:], Message("assistant", move("Qxf7")), retried[-1]]
    assert white_prompts(state) == white.prompts
    assert logged(tmp_path).llm_turns == state.llm_turns
    [log] = tmp_path.glob("*.jsonl")
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    white_attempts = [event for event in events if event["type"] == "llm_attempt" and event["color"] == "white"]
    assert [event["remembered"] for event in white_attempts] == [0, 1, 2, 1]  # each attempt's own


def test_without_a_measurement_the_whole_conversation_is_estimated_at_three_characters_per_token(tmp_path):
    white = ScriptedPlayer([Raw(json.dumps({"reasoning": "x" * 25_000, "move": "f3"})), "g4"])

    state = play(tmp_path, LLAMA_CHAT, {"white": white, "black": ScriptedPlayer(["e5"])}, 3)

    assert [turn.remembered for turn in state.llm_turns if turn.color == "white"] == [0, 0]
    assert [message.role for message in white.prompts[1]] == ["system", "user"]


def test_a_measurement_that_may_have_reached_the_end_of_the_context_is_not_trusted(tmp_path):
    white = ScriptedPlayer(["f3", "g4"])
    white.usage = measured(7900)  # with 512 for the reply past 8,192: Ollama may have cut it, and its count

    state = play(tmp_path, LLAMA_CHAT, {"white": white, "black": ScriptedPlayer(["e5"])}, 3)

    assert state.llm_turns[2].remembered == 1  # estimated at three characters per token instead: it fits


def test_a_turn_that_alone_does_not_fit_is_sent_and_its_attempt_logs_that_it_may_be_cut(tmp_path):
    long_illegal = Raw(json.dumps({"reasoning": "x" * 25_000, "move": "Qxf7"}))
    white = ScriptedPlayer([long_illegal, "f3"])

    state = play(tmp_path, LLAMA_CHAT, {"white": white, "black": ScriptedPlayer([])}, 1)

    assert [turn.remembered for turn in state.llm_turns] == [0]
    [log] = tmp_path.glob("*.jsonl")
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    attempts = [event for event in events if event["type"] == "llm_attempt"]
    assert [event.get("context_may_be_cut") for event in attempts] == [None, True]


@pytest.mark.parametrize(
    "side, reserve",
    [
        # The forced answer adds the thinking handed back, up to the budget, its closing sentence and the answer.
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=1024), 1024 + 30 + 64),
        (LlmSide(model="qwen3.5:9b", thinking=True), 4096),
        (LlmSide(model="llama3:8b"), 512),
    ],
)
def test_the_room_kept_for_the_reply_is_the_thinking_budget_or_follows_thinking(side, reserve):
    assert reply_reserve(side) == reserve


@pytest.mark.parametrize(
    "side, remembered",
    [
        (QWEN_CHAT, 0),  # 4,080 tokens and 4,096 for thinking and the answer pass 8,192
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=1024, turn_memory="chat_position"), 1),
        (LLAMA_CHAT, 1),  # 512 for the answer, with thinking off
        # 4,000 for the budget's thinking alone would fit; with what the forced answer adds it doesn't.
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=4000, turn_memory="chat_position"), 0),
    ],
)
def test_whether_a_conversation_is_trimmed_follows_the_room_kept_for_the_reply(tmp_path, side, remembered):
    white = ScriptedPlayer(["f3", "g4"])
    white.usage = measured(4080, 4200)

    state = play(tmp_path, side, {"white": white, "black": ScriptedPlayer(["e5"])}, 3)

    assert state.llm_turns[2].remembered == remembered
