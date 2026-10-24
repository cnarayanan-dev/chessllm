"""Turn memory: an LLM side's Turns either start fresh, or share one conversation for the whole game, each turn
adding its message as a fresh turn has it (chat_position). In a conversation each attempt records only the messages
it added, and the whole Prompt is rebuilt from the records (ADR 0009)."""

import json

from tests.conftest import Raw, ScriptedAnchor, ScriptedPlayer

from chessllm.analytics.leaderboard import llm_configuration, settings_configuration
from chessllm.cli.anchor_match import main as anchor_match
from chessllm.cli.faceoff_batch import main as faceoff_batch
from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import full_prompt
from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES
from chessllm.game.records import GameState
from chessllm.game.runner import play_anchor_match
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog
from chessllm.logs.llm_turns import logged_llm_turns

START = "FEN: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_F3_E5 = "PGN: 1. f3 e5\nFEN: rnbqkbnr/pppp1ppp/8/4p3/8/5P2/PPPPP1PP/RNBQKBNR w KQkq - 0 2"
QWEN_CHAT = LlmSide(model="qwen3.5:9b", thinking=True, turn_memory="chat_position")
LLAMA_CHAT = LlmSide(model="llama3:8b", turn_memory="chat_position")


def move(san: str) -> str:
    """A scripted reply as the LLM sends it, and so as the conversation keeps it."""
    return json.dumps({"move": san})


def faceoff(tmp_path, white: LlmSide, black: LlmSide, players: dict[Color, ScriptedPlayer]) -> GameState:
    """Play an LLM faceoff to its end, unattended as the batch commands play it, logging to tmp_path / "games"."""
    settings = Settings("llm_faceoff", white, black)
    settings.check(LLM_MODELS)
    log = GameLog(tmp_path / "games", *settings.side_names())
    return play_anchor_match(settings, {color: player for color, player in players.items()}, {}, log)


def events(games_dir) -> list[dict]:
    [log] = games_dir.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def as_messages(prompt) -> list[Message]:
    """A recorded Prompt as the LLM player received its messages."""
    return [Message(message.role, message.content) for message in prompt]


def side_prompts(state: GameState, color: Color) -> list[list[Message]]:
    """The whole Prompt of every attempt of a side, rebuilt from the state's records."""
    return [
        as_messages(full_prompt(state.llm_turns, turn.ply, number))
        for turn in state.llm_turns
        if turn.color == color
        for number in range(1, len(turn.attempts) + 1)
    ]


def test_under_chat_position_each_turn_continues_the_conversation_of_the_earlier_ones(tmp_path):
    white = ScriptedPlayer(["f3", "Qxf7", "g4"], thinking=["f3, a quiet start.", "The queen takes f7.", "g4 then."])
    black = ScriptedPlayer(["e5", "Qh4#"])

    faceoff(tmp_path, QWEN_CHAT, LlmSide(), {"white": white, "black": black})

    first, second, retried = white.prompts
    system = first[0]
    assert system.role == "system"
    assert first == [system, Message("user", f"PGN: (no moves yet)\n{START}")]
    feedback = (
        'Your move "Qxf7" is illegal in this position (kind: illegal move). Attempt 1 of 5. '
        "Reply with a different legal move."
    )
    assert retried == [
        system,
        Message("user", f"PGN: (no moves yet)\n{START}"),
        Message("assistant", move("f3")),
        Message("user", AFTER_F3_E5),
        Message("assistant", move("Qxf7")),
        Message("user", feedback),
    ]
    assert second == retried[:4]  # the turn's first attempt: before the illegal answer and its feedback
    sent = "".join(message.content for prompt in white.prompts for message in prompt)
    assert "quiet start" not in sent and "queen takes" not in sent  # never the Thinking


def test_under_fresh_every_turn_starts_a_new_conversation_and_records_its_whole_prompt(tmp_path):
    black = ScriptedPlayer(["e5", "Qh4#"])

    state = faceoff(tmp_path, QWEN_CHAT, LlmSide(), {"white": ScriptedPlayer(["f3", "g4"]), "black": black})

    first, second = black.prompts
    assert [message.role for message in second] == ["system", "user"]
    assert second[1].content.startswith("PGN: 1. f3 e5 2. g4\n")
    black_turns = [turn for turn in state.llm_turns if turn.color == "black"]
    assert [as_messages(turn.attempts[0].prompt or []) for turn in black_turns] == [first, second]
    assert all(turn.remembered is None for turn in black_turns)
    logged = [event for event in events(tmp_path / "games") if event["type"] == "llm_attempt"]
    assert all("remembered" not in event for event in logged if event["color"] == "black")
    assert all("context_may_be_cut" not in event for event in logged)


def test_in_a_conversation_each_attempt_records_only_the_messages_it_added(tmp_path):
    white = ScriptedPlayer(["f3", "Qxf7", "g4"])

    state = faceoff(tmp_path, QWEN_CHAT, LlmSide(), {"white": white, "black": ScriptedPlayer(["e5", "Qh4#"])})

    first, second = [turn for turn in state.llm_turns if turn.color == "white"]
    system = white.prompts[0][0]
    assert (first.remembered, second.remembered) == (0, 1)
    assert as_messages(first.attempts[0].prompt or []) == [system, Message("user", f"PGN: (no moves yet)\n{START}")]
    [position], [feedback] = (as_messages(attempt.prompt or []) for attempt in second.attempts)
    assert position == Message("user", AFTER_F3_E5)
    assert feedback.role == "user" and feedback.content.startswith('Your move "Qxf7" is illegal')
    logged = [event for event in events(tmp_path / "games") if event["type"] == "llm_attempt"]
    assert [event["remembered"] for event in logged if event["color"] == "white"] == [0, 1, 1]


def test_the_rebuilt_prompt_of_every_attempt_is_what_the_llm_received_from_the_state_and_the_log(tmp_path):
    white = ScriptedPlayer([Raw('{"reasoning": "A quiet start.", "move": "f3"}'), "Qxf7", "Ke3", "g4", "h3"])
    black = ScriptedPlayer(["e5", "Qxf3", "d6", "Qh4#"], thinking=["e5.", "The queen.", "d6.", "Mate."])

    state = faceoff(tmp_path, LLAMA_CHAT, QWEN_CHAT, {"white": white, "black": black})

    assert state.end_reason == "checkmate"
    logged = GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))
    assert logged.llm_turns == state.llm_turns  # the log holds the same records
    for rebuilt_from in (state, logged):
        assert side_prompts(rebuilt_from, "white") == white.prompts
        assert side_prompts(rebuilt_from, "black") == black.prompts


def test_under_retry_feedback_repeat_a_rejected_attempt_is_left_out_of_the_conversation(tmp_path):
    side = LlmSide(model="llama3:8b", retry_feedback="repeat", turn_memory="chat_position")
    white = ScriptedPlayer(["f3", "Qxf7", "Ke3", "g4", "h3"])

    state = faceoff(tmp_path, side, LlmSide(), {"white": white, "black": ScriptedPlayer(["e5", "d6", "Qh4#"])})

    _, second, *repeats, third = white.prompts
    assert repeats == [second, second]  # sent again unchanged, the rejected moves unseen
    assert third == [*second, Message("assistant", move("g4")), third[-1]]  # only the move played is kept
    assert "Qxf7" not in json.dumps([message.content for message in third])
    assert side_prompts(state, "white") == white.prompts
    [rejected, rejected_too, played] = state.llm_turns[2].attempts
    assert (rejected.raw_reply, rejected_too.raw_reply) == (move("Qxf7"), move("Ke3"))  # still recorded
    assert (rejected_too.prompt, played.prompt) == ([], [])


def test_a_conversations_system_prompt_is_filled_in_once_from_the_template_read_at_game_start(tmp_path, monkeypatch):
    prompt_file = tmp_path / "system.txt"
    prompt_file.write_text("You play $color. The first instructions.", encoding="utf-8")
    monkeypatch.setitem(SYSTEM_PROMPT_FILES, "free", prompt_file)
    white, black = ScriptedPlayer(["f3", "g4"]), ScriptedPlayer(["e5", "Qh4#"])
    settings = Settings("llm_faceoff", LLAMA_CHAT, LlmSide())
    game = GameSession({"white": white, "black": black}, settings, GameLog(tmp_path, *settings.side_names()))
    game.play_llm_turn()
    game.play_llm_turn()

    prompt_file.write_text("You play $color. Edited mid-game.", encoding="utf-8")
    game.play_llm_turn()
    game.play_llm_turn()

    assert [prompt[0].content for prompt in white.prompts] == ["You play White. The first instructions."] * 2
    assert [prompt[0].content for prompt in black.prompts] == ["You play Black. The first instructions."] * 2


def test_a_faceoff_batch_with_turn_memory_logs_it_and_is_its_own_player_configuration(tmp_path, capsys):
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])

    code = faceoff_batch(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "1", "--turn-memory", "chat_position", "--games-dir",
         str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    assert capsys.readouterr().err == ""  # trimmed to the context, so nothing to warn of
    start, *_ = events(tmp_path)
    assert start["white"]["turn_memory"] == start["black"]["turn_memory"] == "chat_position"
    assert [len(prompt) for prompt in player.prompts] == [2, 2, 4, 4]  # each side's second turn continues its first
    chat = llm_configuration(start, "white", start["white"])
    fresh = llm_configuration(start, "white", {k: v for k, v in start["white"].items() if k != "turn_memory"})
    assert (chat.turn_memory, fresh.turn_memory) == ("chat_position", None)
    assert chat.id() != fresh.id()
    assert chat == settings_configuration(player.built_for[0], "white")


def test_an_anchor_match_takes_turn_memory_too(tmp_path):
    player = ScriptedPlayer(["e5", "Qh4#"])

    code = anchor_match(
        ["--model", "llama3:8b", "--color", "black", "--turn-memory", "chat_position", "--games-dir", str(tmp_path)],
        player_for=player.for_settings,
        anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    start, *_ = events(tmp_path)
    assert start["black"]["turn_memory"] == "chat_position"
    assert [len(prompt) for prompt in player.prompts] == [2, 4]


def test_fresh_is_left_out_of_the_log_and_the_configuration_so_its_id_is_unchanged(tmp_path, capsys):
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])

    faceoff_batch(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "1", "--turn-memory", "fresh", "--games-dir",
         str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert capsys.readouterr().err == ""
    start, *_ = events(tmp_path)
    assert "turn_memory" not in start["white"]
    assert [len(prompt) for prompt in player.prompts] == [2, 2, 2, 2]
    explicit = llm_configuration(start, "white", start["white"] | {"turn_memory": "fresh"})
    assert explicit.id() == llm_configuration(start, "white", start["white"]).id()
    # The id of llama3:8b in the committed samples' Anchor match, from before Turn memory existed.
    sample = llm_configuration(
        {"max_retries": 4, "sampling": {"temperature": 0.7, "top_k": 40}, "prompt_file": "system.txt"},
        "white",
        {"model": "llama3:8b", "thinking": False, "llm_constraints": "free", "retry_feedback": "explained"},
    )
    assert sample.id() == "7ec8267cd89b"

