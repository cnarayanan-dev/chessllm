"""The Legal counterpart: after an LLM's Chaos move, the same LLM is asked once more, under Listed enforced, for a
legal move in the same position. It is recorded, but never played, and never causes a Forfeit."""

import json
import threading

import pytest
from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from chessllm.exceptions import LlmTimeout
from chessllm.game.llm_turn.prompt import LISTED_SYSTEM_PROMPT_FILE, system_prompt
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.llm.players import LlmReply, Message
from chessllm.logs.game_log import GameLog
from tests.conftest import Raw, ScriptedPlayer, play_llm, play_move
from tests.fakes import FakeClock
from tests.analytics.test_leaderboard import configurations as leaderboard_configurations

CHAOS = {"rules": "chaos"}
AFTER_E4_E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


def events(games_dir, kind=None):
    [log] = sorted(games_dir.glob("*.jsonl"))
    logged = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [event for event in logged if kind is None or event["type"] == kind]


def chaos_game(scripted, replies, *ucis, **new_game):
    """Start a Play LLM game under Chaos rules, the human as White, and play the human's moves, each followed by
    the LLM's turn. Returns the client, the player and the last state."""
    client, player = scripted(replies)
    response = client.post("/api/games", json=play_llm() | CHAOS | new_game)
    assert response.status_code == 200, response.text
    state = response.json()
    for uci in ucis:
        response = play_move(client, uci)
        assert response.status_code == 200, response.text
        state = response.json()
    return client, player, state


def test_a_chaos_move_is_followed_by_one_call_for_a_legal_move_under_listed_enforced(scripted):
    _, player, _ = chaos_game(scripted, ["Bc5", "e5"], "e2e4")  # Bc5 goes through the e7 pawn

    assert len(player.prompts) == 2
    system, position = player.prompts[1]
    assert system.content == system_prompt("black", LISTED_SYSTEM_PROMPT_FILE)
    pgn, fen, listed = position.content.splitlines()
    assert (pgn, fen) == ("PGN: 1. e4", "FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    legal_moves = listed.removeprefix("Legal moves: ").split()
    assert len(legal_moves) == 20 and "e5" in legal_moves and "Nf6" in legal_moves
    assert sorted(player.allowed_moves[1]) == sorted(legal_moves)
    assert player.allowed_moves[0] is None  # the turn itself is under the side's own LLM constraints, Free


def test_the_legal_counterpart_is_kept_with_the_chaos_moves_turn_but_never_played(scripted):
    _, _, state = chaos_game(scripted, ["Bc5", "e5"], "e2e4")

    assert state["pgn"] == "1. e4 Bc5"
    turn = state["llm_turn"]
    assert [attempt["move"] for attempt in turn["attempts"]] == ["Bc5"]
    counterpart = turn["legal_counterpart"]
    assert (counterpart["move"], counterpart["san"], counterpart["fen_after"]) == ("e7e5", "e5", AFTER_E4_E5)
    attempt = counterpart["attempt"]
    assert (attempt["move"], attempt["san"], attempt["result"]) == ("e5", "e5", "legal")
    assert attempt["raw_reply"] == '{"move": "e5"}'
    assert attempt["prompt"][0]["content"] == system_prompt("black", LISTED_SYSTEM_PROMPT_FILE)
    assert state["llm_turns"][-1] == turn


def test_the_game_log_records_the_switch_and_each_legal_counterpart_after_its_chaos_moves_attempt(scripted, tmp_path):
    replies = [Raw('{"reasoning": "Through the pawn.", "move": "Bc5"}'), Raw('{"reasoning": "The centre.", "move": "e5"}')]
    chaos_game(scripted, replies, "e2e4")

    start, *_ = events(tmp_path / "games")
    assert start["legal_counterpart"] is True
    logged = [event["type"] for event in events(tmp_path / "games")]
    assert logged == ["game_start", "human_move", "llm_attempt", "legal_counterpart"]
    [counterpart] = events(tmp_path / "games", "legal_counterpart")
    assert (counterpart["color"], counterpart["ply"], counterpart["pgn"]) == ("black", 2, "1. e4")
    assert counterpart["fen"] == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    shown = counterpart["prompt"][1]["content"].split("Legal moves: ")[1]
    assert counterpart["legal_moves"] == shown  # as shown, in the order shown
    assert (counterpart["move"], counterpart["san"], counterpart["result"]) == ("e5", "e5", "legal")
    assert (counterpart["uci"], counterpart["fen_after"]) == ("e7e5", AFTER_E4_E5)
    assert counterpart["thinking"] == "The centre."  # the Reasoning, logged as an attempt's is
    assert counterpart["raw_reply"] == '{"reasoning": "The centre.", "move": "e5"}'
    assert counterpart["error"] is None and "resolution" not in counterpart


def test_with_the_switch_off_no_legal_counterpart_is_asked(scripted, tmp_path):
    _, player, state = chaos_game(scripted, ["Bc5", "Nf6"], "e2e4", "g1f3", legal_counterpart=False)

    assert state["settings"]["legal_counterpart"] is False
    assert len(player.prompts) == 2  # the two turns, nothing more
    assert state["pgn"] == "1. e4 Bc5 2. Nf3 Nf6"
    assert all("legal_counterpart" not in turn for turn in state["llm_turns"])
    assert events(tmp_path / "games")[0]["legal_counterpart"] is False
    assert events(tmp_path / "games", "legal_counterpart") == []


def test_the_switch_is_on_by_default_under_chaos_rules(scripted):
    client, _ = scripted([])

    assert client.get("/api/games/defaults").json()["legal_counterpart"] is True
    state = client.post("/api/games", json=play_llm() | CHAOS).json()
    assert state["settings"]["legal_counterpart"] is True


def test_the_switch_is_ignored_under_standard_rules(scripted, tmp_path):
    client, player = scripted(["Bc5", "e5"])
    state = client.post("/api/games", json=play_llm() | {"legal_counterpart": True}).json()

    assert "legal_counterpart" not in state["settings"]
    assert "legal_counterpart" not in events(tmp_path / "games")[0]
    state = play_move(client, "e2e4").json()
    assert state["pgn"] == "1. e4 e5"  # Bc5 got a Retry, as under Standard rules, and no counterpart was asked
    assert len(player.prompts) == 2 and "legal_counterpart" not in state["llm_turn"]


@pytest.mark.parametrize(
    "failing",
    [LlmTimeout(300.0), RuntimeError("connection refused"), Raw("I would rather not."), "Bc5"],
    ids=["timeout", "failed-call", "no-move", "illegal-move"],
)
def test_a_failed_legal_counterpart_leaves_the_game_playing_with_no_forfeit_and_no_retry(scripted, failing):
    _, player, state = chaos_game(scripted, ["Bc5", failing, "Nf6"], "e2e4", "g1f3")

    assert state["status"] == "playing"
    assert state["pgn"] == "1. e4 Bc5 2. Nf3 Nf6"  # the next turn got its own reply: the counterpart had one call
    assert len(player.prompts) == 3
    counterpart = state["llm_turns"][0]["legal_counterpart"]
    assert (counterpart["move"], counterpart["san"], counterpart["fen_after"]) == (None, None, None)
    assert counterpart["attempt"]["result"] != "legal"
    assert state["stats"]["black"]["illegal_moves"] == {"invalid": 0, "illegal": 1, "ambiguous": 0}  # Bc5 alone


def test_a_timed_out_legal_counterpart_records_why(scripted):
    _, _, state = chaos_game(scripted, ["Bc5", LlmTimeout(300.0)], "e2e4")

    attempt = state["llm_turn"]["legal_counterpart"]["attempt"]
    assert (attempt["result"], attempt["raw_reply"], attempt["latency_s"]) == ("timeout", None, None)
    assert attempt["error"] == "Too long thinking: llama3:8b gave no answer within 5 minutes."


def test_the_legal_counterparts_time_is_none_of_the_turns(scripted, tmp_path):
    client, player = scripted(["Bc5", "e5"])
    player.usage = [{"latency_s": 2.0}, {"latency_s": 7.5}]
    client.post("/api/games", json=play_llm() | CHAOS)

    state = play_move(client, "e2e4").json()

    turn = state["llm_turn"]
    assert [attempt["latency_s"] for attempt in turn["attempts"]] == [2.0]
    assert turn["legal_counterpart"]["attempt"]["latency_s"] == 7.5
    # The turn's time is its attempts', which are the game log's llm_attempt events; the counterpart has an event of
    # its own.
    assert [event["latency_s"] for event in events(tmp_path / "games", "llm_attempt")] == [2.0]
    assert [event["latency_s"] for event in events(tmp_path / "games", "legal_counterpart")] == [7.5]


def test_a_chaos_move_that_ends_the_game_still_has_its_legal_counterpart(scripted):
    _, _, state = chaos_game(scripted, ["Qe1", "e5"], "e2e4")  # King capture

    assert (state["status"], state["end_reason"]) == ("over", "king_capture")
    assert state["llm_turn"]["legal_counterpart"]["san"] == "e5"


class HeldPlayer(ScriptedPlayer):
    """A ScriptedPlayer that holds its reply to the held-th call until released."""

    def __init__(self, replies: list[str | BaseException], held: int) -> None:
        super().__init__(replies)
        self.held = held
        self.asked = threading.Event()
        self.release = threading.Event()

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        if len(self.prompts) + 1 == self.held:
            self.asked.set()
            assert self.release.wait(timeout=5)
        return super().reply(messages, allowed_moves)


def abandon_during_call(tmp_path, held: int) -> tuple[HeldPlayer, dict, list]:
    """Start a chaos game with the LLM as White, whose first move, Bc4, is a chaos move with e4 as its counterpart;
    hold the held-th call, start a new game, then release it. Returns the player, the old game's log events and its
    LLM turn's response."""
    player = HeldPlayer(["Bc4", "e4"], held)
    client = TestClient(
        create_app(player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml")
    )
    old = client.post("/api/games", json=play_llm("black") | CHAOS).json()
    responses: list = []
    running = threading.Thread(target=lambda: responses.append(client.post("/api/games/current/llm-turn")))
    running.start()
    assert player.asked.wait(timeout=5)
    assert client.post("/api/games", json=play_llm("white")).status_code == 200
    player.release.set()
    running.join(timeout=5)
    logs = [
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for path in (tmp_path / "games").glob("*.jsonl")
    ]
    [logged] = [events for events in logs if events[0]["game_id"] == old["game_id"]]
    return player, logged, responses


def test_a_game_abandoned_during_its_chaos_move_asks_for_no_legal_counterpart(tmp_path):
    player, logged, [response] = abandon_during_call(tmp_path, held=1)

    assert len(player.prompts) == 1
    assert [event["type"] for event in logged] == ["game_start", "llm_attempt"]
    assert response.json()["llm_turns"] == []


def test_a_game_abandoned_during_its_legal_counterpart_never_publishes_or_logs_it(tmp_path):
    player, logged, [response] = abandon_during_call(tmp_path, held=2)

    assert len(player.prompts) == 2
    assert [event["type"] for event in logged] == ["game_start", "llm_attempt"]
    assert (response.json()["llm_turns"], response.json()["status"]) == ([], "playing")


def test_the_sides_clock_stands_still_while_its_legal_counterpart_is_asked(tmp_path):
    clock = FakeClock()
    player = HeldPlayer(["Bc5", "e5"], held=2)
    player.clock, player.reply_s = clock, [3.0, 5.0]  # Bc5 takes 3 s, its counterpart 5 s once released
    game = GameSession({"black": player}, Settings(rules="chaos"), GameLog(tmp_path, "human", "llama3:8b"), clock=clock)
    game.play_human_move("e2e4")
    running = threading.Thread(target=game.play_llm_turn)
    running.start()
    assert player.asked.wait(timeout=5)
    clock.advance(20.0)

    asking = game.state()
    player.release.set()
    running.join(timeout=5)

    assert (asking.running_s, asking.time_used.black, asking.llm_turns) == (3.0, 0.0, [])
    landed = game.state()
    assert landed.llm_turn is not None and landed.llm_turn.legal_counterpart is not None
    assert (landed.plies[-1].time_s, landed.llm_turn.time_s, landed.time_used.black) == (3.0, 3.0, 3.0)
    assert landed.running_s == 0.0  # the human's move has just started


def test_the_switch_is_not_part_of_the_player_configuration(scripted, tmp_path):
    client, _ = scripted(["Qe1", "e5", "Qe1"])  # each game ends at once in a King capture
    for switch in (True, False):
        client.post("/api/games", json=play_llm() | CHAOS | {"legal_counterpart": switch})
        assert play_move(client, "e2e4").json()["status"] == "over"

    [configuration] = leaderboard_configurations(tmp_path / "games")
    assert configuration["games"] == 2
