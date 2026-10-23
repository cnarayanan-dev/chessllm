"""Time used: each side's total time on its moves, timed on the server with a monotonic clock, here a fake one."""

import json
import threading

import chess
import pytest

from tests.analytics.test_analysis import PeakedMoveModel
from tests.analytics.test_leaderboard import configurations
from tests.conftest import BlockingPlayer, ScriptedAnchor, ScriptedPlayer, play_llm, play_move
from tests.fakes import FakeClock

from chessllm.analytics.analysis import analyse_game
from chessllm.exceptions import AnchorUnavailable, LlmTimeout
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import AnchorSide, LlmSide
from chessllm.logs.game_log import GameLog


def events(log: GameLog, event_type: str) -> list[dict]:
    lines = map(json.loads, log.path.read_text(encoding="utf-8").splitlines())
    return [event for event in lines if event["type"] == event_type]


def play_llm_game(tmp_path, replies: list, reply_s: list[float]) -> tuple[GameSession, FakeClock, GameLog]:
    """Play LLM with the human as White, timed by a fake clock, the LLM's replies taking reply_s each."""
    clock = FakeClock()
    player = ScriptedPlayer(replies)
    player.clock, player.reply_s = clock, reply_s
    log = GameLog(tmp_path, "human", "llama3:8b")
    return GameSession({"black": player}, Settings(), log, clock=clock), clock, log


def test_a_human_move_takes_the_time_from_the_position_being_ready_to_the_move(tmp_path):
    game, clock, log = play_llm_game(tmp_path, [], [])
    clock.advance(7.25)

    game.play_human_move("e2e4")

    state = game.state()
    [ply] = state.plies
    assert ply.time_s == 7.25
    assert (state.time_used.white, state.time_used.black) == (7.25, 0.0)
    [human_move] = events(log, "human_move")
    assert human_move["time_s"] == 7.25


def test_an_llm_move_takes_its_whole_turn_retries_included_and_not_the_wait_before_it(tmp_path):
    game, clock, log = play_llm_game(tmp_path, ["Qh4", "e5"], [3.0, 4.5])  # Qh4 is illegal: a Retry
    game.play_human_move("e2e4")
    clock.advance(2.0)  # the page asks for the LLM's turn

    game.play_llm_turn()

    state = game.state()
    assert state.plies[-1].time_s == 7.5
    assert state.llm_turn is not None and state.llm_turn.time_s == 7.5
    assert (state.time_used.white, state.time_used.black) == (0.0, 7.5)
    assert ["turn_time_s" in attempt for attempt in events(log, "llm_attempt")] == [False, True]
    assert events(log, "llm_attempt")[-1]["turn_time_s"] == 7.5


def test_the_humans_next_move_starts_once_the_llms_move_is_played(tmp_path):
    game, clock, _ = play_llm_game(tmp_path, ["e5"], [4.0])
    clock.advance(1.0)
    game.play_human_move("e2e4")
    game.play_llm_turn()
    clock.advance(2.5)

    game.play_human_move("g1f3")

    state = game.state()
    assert [ply.time_s for ply in state.plies] == [1.0, 4.0, 2.5]
    assert (state.time_used.white, state.time_used.black) == (3.5, 4.0)


def test_an_anchor_move_takes_the_time_from_it_being_asked_for_to_the_move(tmp_path):
    clock = FakeClock()
    llm, anchor = ScriptedPlayer(["e4"]), ScriptedAnchor(["e5"])
    llm.clock, llm.reply_s, anchor.clock, anchor.move_s = clock, [6.0], clock, [0.25]
    settings = Settings("anchor_match", LlmSide(), AnchorSide(engine="dragon", skill=1))
    log = GameLog(tmp_path, *settings.side_names())
    game = GameSession({"white": llm}, settings, log, {"black": anchor}, clock=clock)
    game.play_llm_turn()
    clock.advance(3.0)  # the Anchor's move is asked for later

    game.play_anchor_turn()

    state = game.state()
    assert [ply.time_s for ply in state.plies] == [6.0, 0.25]
    assert (state.time_used.white, state.time_used.black) == (6.0, 0.25)
    [anchor_move] = events(log, "anchor_move")
    assert anchor_move["time_s"] == 0.25


def test_a_forfeited_turn_has_its_time_and_counts_in_time_used_to_the_end_of_the_game(tmp_path):
    game, clock, log = play_llm_game(tmp_path, ["e5", LlmTimeout(300)], [1.5, 300.0])
    clock.advance(2.0)
    game.play_human_move("e2e4")
    game.play_llm_turn()
    clock.advance(4.0)
    game.play_human_move("g1f3")

    game.play_llm_turn()

    state = game.state()
    assert (state.status, state.end_reason) == ("over", "forfeit")
    assert [turn.time_s for turn in state.llm_turns] == [1.5, 300.0]
    assert len(state.plies) == 3  # the forfeited turn has no ply
    assert (state.time_used.white, state.time_used.black) == (6.0, 301.5)
    assert events(log, "llm_attempt")[-1]["turn_time_s"] == 300.0
    [game_end] = events(log, "game_end")
    assert game_end["time_used"] == {"white": 6.0, "black": 301.5}


def test_times_are_kept_to_the_millisecond(tmp_path):
    game, clock, _ = play_llm_game(tmp_path, [], [])
    clock.advance(0.1 + 0.2 + 0.0004)

    game.play_human_move("e2e4")

    assert game.state().time_used.white == 0.3


def test_the_humans_running_move_shows_in_the_state_and_no_one_elses_until_asked_for(tmp_path):
    game, clock, _ = play_llm_game(tmp_path, [], [])
    clock.advance(3.25)
    assert game.state().running_s == 3.25

    game.play_human_move("e2e4")
    clock.advance(10.0)  # nobody asks for the LLM's turn

    state = game.state()
    assert state.running_s is None
    assert (state.time_used.white, state.time_used.black) == (3.25, 0.0)


def test_a_paused_faceoff_charges_no_one_for_the_pause_nor_for_a_probe_asked_during_it(tmp_path):
    """Pause is the page's: it asks for no next turn. A game nobody is driving charges no one."""
    clock = FakeClock()
    white, black = ScriptedPlayer(["e4", "e5", "Nf3"]), ScriptedPlayer(["e5"])  # White's "e5" answers the probe
    white.clock, white.reply_s, black.clock, black.reply_s = clock, [2.0, 9.0, 3.0], clock, [4.0]
    settings = Settings("llm_faceoff", LlmSide(), LlmSide())
    log = GameLog(tmp_path, *settings.side_names())
    game = GameSession({"white": white, "black": black}, settings, log, clock=clock)
    game.play_llm_turn()
    game.play_llm_turn()
    clock.advance(60.0)  # paused: no turn is asked for

    game.probe(1, "white")
    clock.advance(60.0)
    paused = game.state()
    game.play_llm_turn()  # resumed

    assert paused.running_s is None
    assert (paused.time_used.white, paused.time_used.black) == (2.0, 4.0)
    state = game.state()
    assert [ply.time_s for ply in state.plies] == [2.0, 4.0, 3.0]
    assert (state.time_used.white, state.time_used.black) == (5.0, 4.0)


def test_a_running_llm_turn_shows_only_how_long_it_has_run(tmp_path):
    """The state shows running_s while the turn runs, never the running turn itself (#81)."""
    clock = FakeClock()
    player = BlockingPlayer(["e5"])
    game = GameSession({"black": player}, Settings(), GameLog(tmp_path, "human", "llama3:8b"), clock=clock)
    game.play_human_move("e2e4")
    running = threading.Thread(target=game.play_llm_turn)
    running.start()
    assert player.asked.wait(timeout=5)
    clock.advance(12.5)

    waiting = game.state()
    player.release.set()
    running.join(timeout=5)

    assert waiting.running_s == 12.5
    assert (waiting.llm_turns, waiting.time_used.black) == ([], 0.0)
    landed = game.state()
    assert landed.time_used.black == 12.5
    assert landed.running_s == 0.0  # the human's move has just started


def test_no_move_is_running_once_the_game_is_over(tmp_path):
    game, clock, _ = play_llm_game(tmp_path, ["e5", "Qh4#"], [1.0, 1.0])
    for uci in ("f2f3", "g2g4"):
        game.play_human_move(uci)
        game.play_llm_turn()
    clock.advance(60.0)

    state = game.state()
    assert (state.status, state.running_s) == ("over", None)
    assert (state.time_used.white, state.time_used.black) == (0.0, 2.0)


def test_an_abandoned_game_never_adds_its_running_turn_and_writes_no_time_used(tmp_path):
    clock = FakeClock()
    player = BlockingPlayer(["e5"])
    log = GameLog(tmp_path, "human", "llama3:8b")
    game = GameSession({"black": player}, Settings(), log, clock=clock)
    clock.advance(1.0)
    game.play_human_move("e2e4")
    running = threading.Thread(target=game.play_llm_turn)
    running.start()
    assert player.asked.wait(timeout=5)
    clock.advance(20.0)

    game.abandon()
    player.release.set()
    running.join(timeout=5)

    state = game.state()
    assert (state.time_used.white, state.time_used.black) == (1.0, 0.0)
    assert events(log, "game_end") == []


class PeekingClock(FakeClock):
    """A FakeClock that, once a scripted move has taken its time, has another thread read the game's state at every
    later read by the thread that moved: at each point the game reads its clock while that move lands."""

    def __init__(self) -> None:
        super().__init__()
        self.mover: int | None = None
        self.peek = lambda: None

    def advance(self, seconds: float) -> None:
        super().advance(seconds)
        self.mover = threading.get_ident()

    def __call__(self) -> float:
        if threading.get_ident() == self.mover:
            self.peek()
        return super().__call__()


def test_a_state_read_while_the_llm_move_lands_shows_its_time_with_the_move(tmp_path):
    clock = PeekingClock()
    player = ScriptedPlayer(["e5"])
    player.clock, player.reply_s = clock, [4.0]
    game = GameSession({"black": player}, Settings(), GameLog(tmp_path, "human", "llama3:8b"), clock=clock)
    game.play_human_move("e2e4")
    seen, readers = [], []

    def peek() -> None:
        reader = threading.Thread(target=lambda: seen.append(game.state()))
        reader.start()
        reader.join(timeout=0.2)  # one that waits for the move to land reads once it has
        readers.append(reader)

    clock.peek = peek
    game.play_llm_turn()
    for reader in readers:
        reader.join(timeout=5)

    assert any(len(state.plies) == 2 for state in seen)  # a read was made while the move landed
    for state in seen:
        landed = len(state.plies) == 2
        assert (state.time_used.black, state.running_s) == ((4.0, 0.0) if landed else (0.0, 4.0))


TIME_KEYS = ("time_s", "turn_time_s", "time_used")


def test_a_log_from_before_time_used_reads_as_one_with_it_in_the_leaderboard_and_analysis(scripted, tmp_path):
    """The new keys are additive: the same game logged without them, as every version 1 log and the version 2 logs
    from before them are, gives the same leaderboard and the same analysis."""
    client, _ = scripted(["e5", "Nc6", "Nf6"])
    client.post("/api/games", json=play_llm(model="qwen3.5:9b"))
    for uci in ("e2e4", "f1c4", "d1h5", "h5f7"):  # Scholar's mate
        play_move(client, uci)
    [timed] = (tmp_path / "games").glob("*.jsonl")
    untimed = tmp_path / "untimed" / timed.name
    untimed.parent.mkdir()
    lines = [json.loads(line) for line in timed.read_text(encoding="utf-8").splitlines()]
    assert any(key in line for line in lines for key in TIME_KEYS)
    stripped = [{key: value for key, value in line.items() if key not in TIME_KEYS} for line in lines]
    untimed.write_text("".join(json.dumps(line) + "\n" for line in stripped), encoding="utf-8")

    def read(log):
        board = configurations(log.parent)
        analyse_game(log, PeakedMoveModel())
        return board, json.loads(log.with_name(f"{log.stem}.analysis.json").read_text(encoding="utf-8"))

    timed_board, timed_analysis = read(timed)
    assert timed_board
    assert read(untimed) == (timed_board, timed_analysis)


class FailingAnchor:
    """An Anchor that fails, or answers with an illegal move."""

    def __init__(self, illegal: bool) -> None:
        self.illegal = illegal

    def move(self, board):
        if self.illegal:
            return chess.Move.from_uci("e7e4")
        raise AnchorUnavailable("Dragon crashed")

    def close(self) -> None:
        pass


@pytest.mark.parametrize("illegal", [False, True])
def test_a_failed_anchor_move_leaves_no_move_running(tmp_path, illegal):
    clock = FakeClock()
    llm = ScriptedPlayer(["e4"])
    settings = Settings("anchor_match", LlmSide(), AnchorSide(engine="dragon", skill=1))
    log = GameLog(tmp_path, *settings.side_names())
    game = GameSession({"white": llm}, settings, log, {"black": FailingAnchor(illegal)}, clock=clock)
    game.play_llm_turn()

    with pytest.raises(AnchorUnavailable):
        game.play_anchor_turn()
    clock.advance(30.0)

    state = game.state()
    assert (state.running_s, state.time_used.black, len(state.plies)) == (None, 0.0, 1)
