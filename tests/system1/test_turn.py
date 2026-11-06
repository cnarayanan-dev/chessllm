"""A System 1 model's Turn in the game session (ADR 0012): the legal moves as options, a move drawn from the model's
probabilities at the Choice temperature, a single attempt, and the turn record in the game log. Driven as the batches
drive a game, with a fake decision model."""

import json

import chess
import pytest

from tests.conftest import FakeClock, FakeDecisionModel, ScriptedAnchor, ScriptedPlayer
from tests.game.test_move_cap import MOVE_CAP_PLIES, long_game, sans

from chessllm.core.types import Color
from chessllm.exceptions import DecisionModelFailed, InvalidSettings, RefusedSystem1Turn
from chessllm.game.records import GameState
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import AnchorSide, LlmSide, PromptTemplate, System1Side
from chessllm.logs.game_log import GameLog

BASE_URL = "http://localhost:11434"


def side(**settings) -> System1Side:
    return System1Side(model="d3:2b", base_url=BASE_URL, **settings)


def start(
    tmp_path,
    model: FakeDecisionModel,
    anchor_moves: list[str],
    system1: System1Side | None = None,
    color: Color = "black",
    seed: int | None = 1,
    clock: FakeClock | None = None,
) -> GameSession:
    """An Anchor match between a System 1 side (Black unless given) and a scripted Anchor."""
    anchor = AnchorSide(engine="dragon", skill=1)
    sides = (anchor, system1 or side()) if color == "black" else (system1 or side(), anchor)
    settings = Settings("anchor_match", *sides)
    log = GameLog(tmp_path / "games", *settings.side_names())
    clock = clock or FakeClock()
    model.clock = clock
    anchors = {("white" if color == "black" else "black"): ScriptedAnchor(anchor_moves)}
    return GameSession(
        {}, settings, log, anchors, clock=clock, decision_models={color: model}, seed=seed
    )


def play_out_one_round(game: GameSession) -> None:
    """The Anchor (White) moves, then the System 1 side (Black)."""
    game.play_anchor_turn()
    game.play_system1_turn()


def play_out(game: GameSession, color: Color = "black") -> GameState:
    """Play the game to its end, each turn by the side to move: the System 1 side's (color) or the Anchor's."""
    while (state := game.state()).status == "playing":
        if state.turn == color:
            game.play_system1_turn()
        else:
            game.play_anchor_turn()
    return state


def events(game: GameSession, event_type: str) -> list[dict]:
    lines = map(json.loads, game.log_path.read_text(encoding="utf-8").splitlines())
    return [event for event in lines if event["type"] == event_type]


def test_a_system_1_side_plays_the_moves_it_is_given_all_the_probability_and_mates(tmp_path):
    model = FakeDecisionModel.favouring("e5", "Qh4#")
    game = start(tmp_path, model, ["f3", "g4"])

    state = play_out(game)

    assert state.pgn == "1. f3 e5 2. g4 Qh4#"
    assert (state.result, state.end_reason) == ("0-1", "checkmate")


def test_it_is_asked_the_position_as_the_state_and_the_question_for_its_colour_with_the_legal_moves_as_options(tmp_path):
    model = FakeDecisionModel.favouring("e5", "Qh4#")
    game = start(tmp_path, model, ["f3", "g4"])

    play_out(game)

    first, second = model.asked
    after_f3 = chess.Board()
    after_f3.push_san("f3")
    assert first.question == "Which move should Black play?"
    assert after_f3.fen() in first.state and "Moves so far: 1. f3" in first.state
    assert sorted(first.options) == sorted(after_f3.san(move) for move in after_f3.legal_moves)
    assert len(first.options) == 20 and "Qh4#" in second.options


def test_a_system_1_side_playing_white_is_asked_which_move_white_should_play(tmp_path):
    model = FakeDecisionModel.favouring("e4", "Qh5")
    game = start(tmp_path, model, ["e5", "Nc6"], color="white")

    game.play_system1_turn()

    [asked] = model.asked
    assert asked.question == "Which move should White play?"
    assert len(asked.options) == 20
    assert game.state().pgn == "1. e4"


def test_the_state_gives_the_fen_where_every_piece_stands_and_the_moves_so_far(tmp_path):
    model = FakeDecisionModel.favouring("e5")
    game = start(tmp_path, model, ["e4"])

    play_out_one_round(game)

    [asked] = model.asked
    assert asked.state == (
        "Moves so far: 1. e4\n"
        "FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1\n"
        "Last move: e4\n"
        "Your pieces (Black): King e8; Queen d8; Rooks a8, h8; Bishops c8, f8; Knights b8, g8; "
        "Pawns a7, b7, c7, d7, e7, f7, g7, h7\n"
        "Opponent's pieces (White): King e1; Queen d1; Rooks a1, h1; Bishops c1, f1; Knights b1, g1; "
        "Pawns a2, b2, c2, d2, e4, f2, g2, h2"
    )


def test_game_start_logs_the_side_and_the_seed_without_what_an_llm_side_has(tmp_path):
    game = start(tmp_path, FakeDecisionModel(), [], system1=side(choice_temperature=0.5), seed=1234)

    [game_start] = events(game, "game_start")

    black = game_start["black"]
    assert list(black) == ["player", "model", "base_url", "choice_temperature", "prompt_template"]
    assert (black["player"], black["model"], black["base_url"], black["choice_temperature"]) == (
        "system1", "d3:2b", BASE_URL, 0.5
    )
    assert black["prompt_template"]["id"].startswith("system1@")
    assert black["prompt_template"]["system_prompt"] == "Which move should $color play?"
    assert "$fen" in black["prompt_template"]["turn_template"]
    assert game_start["seed"] == 1234
    assert game_start["white"] == {"player": "anchor", "engine": "dragon", "skill": 1}
    assert game.state().prompt_templates["black"].id == black["prompt_template"]["id"]


def test_a_game_without_a_system_1_side_logs_no_seed(tmp_path):
    settings = Settings("anchor_match", AnchorSide(engine="dragon", skill=1), AnchorSide(engine="dragon", skill=2))
    game = GameSession({}, settings, GameLog(tmp_path, *settings.side_names()))

    [game_start] = events(game, "game_start")

    assert "seed" not in game_start


def test_a_game_without_a_given_seed_gets_a_fresh_one_logged(tmp_path):
    first = start(tmp_path / "a", FakeDecisionModel(), [], seed=None)
    second = start(tmp_path / "b", FakeDecisionModel(), [], seed=None)

    seeds = [events(game, "game_start")[0]["seed"] for game in (first, second)]

    assert all(isinstance(seed, int) for seed in seeds) and seeds[0] != seeds[1]


def test_each_turn_is_logged_with_its_options_in_the_order_shown_their_probabilities_and_the_move_drawn(tmp_path):
    model = FakeDecisionModel([{"e5": 3, "d5": 1}])
    game = start(tmp_path, model, ["e4"], system1=side(choice_temperature=0))

    play_out_one_round(game)

    [turn] = events(game, "system1_turn")
    [asked] = model.asked
    assert [option["san"] for option in turn["options"]] == asked.options
    assert {option["san"]: option["probability"] for option in turn["options"] if option["probability"]} == {
        "e5": 0.75, "d5": 0.25
    }
    assert (turn["color"], turn["ply"], turn["asked"]) == ("black", 2, True)
    assert (turn["state"], turn["question"]) == (asked.state, asked.question)
    assert (turn["move"], turn["san"]) == ("e7e5", "e5")
    assert turn["time_s"] == 0.0 and "error" not in turn


def test_the_options_are_shuffled_from_the_seed_so_a_seed_replays_the_order(tmp_path):
    def options_for(seed: int, name: str) -> list[str]:
        model = FakeDecisionModel()
        play_out_one_round(start(tmp_path / name, model, ["e4"], seed=seed))
        return model.asked[0].options

    assert options_for(7, "a") == options_for(7, "b")
    assert options_for(7, "a") != options_for(8, "c")
    assert options_for(7, "a") != sorted(options_for(7, "a"))


def drawn_replies(tmp_path, weights: dict[str, float], games: int, **settings) -> dict[str, int]:
    """How often each reply of Black to 1. e4 is drawn over games seeds, from the model's weights."""
    counts: dict[str, int] = {}
    for seed in range(games):
        game = start(tmp_path / str(seed), FakeDecisionModel([weights]), ["e4"], system1=side(**settings), seed=seed)
        play_out_one_round(game)
        reply = game.state().pgn.split()[-1]
        counts[reply] = counts.get(reply, 0) + 1
    return counts


def test_at_choice_temperature_1_each_move_is_drawn_as_often_as_its_probability(tmp_path):
    counts = drawn_replies(tmp_path, {"e5": 3, "d5": 1}, games=400)

    assert set(counts) == {"e5", "d5"}
    assert 270 <= counts["e5"] <= 330  # 75 % of 400, give or take 4 standard deviations


def test_a_lower_choice_temperature_draws_the_favourites_more_often(tmp_path):
    counts = drawn_replies(tmp_path, {"e5": 3, "d5": 1}, games=400, choice_temperature=0.5)

    assert counts["e5"] >= 340  # 3^2 : 1 is 90 %


def test_choice_temperature_0_always_plays_the_top_option(tmp_path):
    counts = drawn_replies(tmp_path, {"e5": 3, "d5": 2, "c5": 2}, games=40, choice_temperature=0)

    assert counts == {"e5": 40}


def test_choice_temperature_0_breaks_a_tie_by_the_shuffled_order(tmp_path):
    for seed in range(10):
        model = FakeDecisionModel([{"e5": 1, "d5": 1}])
        game = start(tmp_path / str(seed), model, ["e4"], system1=side(choice_temperature=0), seed=seed)

        play_out_one_round(game)

        first_shown = next(option for option in model.asked[0].options if option in ("e5", "d5"))
        assert game.state().pgn.split()[-1] == first_shown


def test_a_game_with_a_fixed_seed_and_fixed_answers_is_reproduced(tmp_path):
    def whole_game(name: str) -> str:
        model = FakeDecisionModel([{"e5": 1, "d5": 1, "Nf6": 1, "c5": 1}] * 5)
        game = start(tmp_path / name, model, ["e4", "Nf3", "Bc4", "O-O"], seed=99)
        for _ in range(4):
            play_out_one_round(game)
        return game.state().pgn

    assert whole_game("a") == whole_game("b")


def test_a_failed_call_is_a_forfeit_logged_with_its_error_and_no_move(tmp_path):
    model = FakeDecisionModel([DecisionModelFailed("d3:2b at http://localhost:11434/v1/systemone: timed out")])
    game = start(tmp_path, model, ["e4"])

    state = play_out(game)

    assert (state.result, state.end_reason, state.pgn) == ("1-0", "forfeit", "1. e4")
    [turn] = events(game, "system1_turn")
    assert turn["error"] == "d3:2b at http://localhost:11434/v1/systemone: timed out"
    assert (turn["asked"], turn["ply"]) == (True, 2)
    assert "move" not in turn and "san" not in turn
    assert [option["san"] for option in turn["options"]] == model.asked[0].options
    assert all("probability" not in option for option in turn["options"])
    [game_end] = events(game, "game_end")
    assert (game_end["result"], game_end["reason"]) == ("1-0", "forfeit")


def test_a_forfeit_by_white_loses_the_game_for_white(tmp_path):
    model = FakeDecisionModel([DecisionModelFailed("refused")])
    game = start(tmp_path, model, [], color="white")

    state = play_out(game, "white")

    assert (state.result, state.end_reason) == ("0-1", "forfeit")


def test_a_failed_call_is_not_retried(tmp_path):
    model = FakeDecisionModel([DecisionModelFailed("refused"), {"e5": 1}])
    game = start(tmp_path, model, ["e4"])

    play_out(game)

    assert len(model.asked) == 1


def test_a_single_legal_move_is_played_without_asking_the_model(tmp_path):
    model = FakeDecisionModel.favouring("f6")
    game = start(tmp_path, model, ["e3", "Qh5+"])

    game.play_anchor_turn()
    game.play_system1_turn()  # 1... f6
    game.play_anchor_turn()  # 2. Qh5+, which g6 alone answers
    game.play_system1_turn()

    assert game.state().pgn == "1. e3 f6 2. Qh5+ g6"
    assert len(model.asked) == 1
    forced = events(game, "system1_turn")[-1]
    assert forced == {
        "type": "system1_turn", "color": "black", "ply": 4, "asked": False, "options": [{"san": "g6"}],
        "move": "g7g6", "san": "g6", "time_s": 0.0,
    }


def test_a_turn_takes_the_time_from_it_starting_to_the_move_drawn_and_adds_to_the_sides_time_used(tmp_path):
    clock = FakeClock()
    model = FakeDecisionModel.favouring("e5", "Nf6")
    model.think_s = [2.5, 4.25]
    game = start(tmp_path, model, ["e4", "Nf3"], clock=clock)
    game.play_anchor_turn()
    clock.advance(10)  # the wait before the turn is not its time

    game.play_system1_turn()
    game.play_anchor_turn()
    game.play_system1_turn()

    state = game.state()
    assert [ply.time_s for ply in state.plies if ply.color == "black"] == [2.5, 4.25]
    assert (state.time_used.white, state.time_used.black) == (0.0, 6.75)
    assert [turn["time_s"] for turn in events(game, "system1_turn")] == [2.5, 4.25]
    assert events(game, "game_end") == []


def test_a_forfeited_turn_still_counts_its_time(tmp_path):
    model = FakeDecisionModel([DecisionModelFailed("timed out")])
    model.think_s = [30.0]
    game = start(tmp_path, model, ["e4"])

    state = play_out(game)

    assert state.time_used.black == 30.0
    assert events(game, "game_end")[0]["time_used"] == {"white": 0.0, "black": 30.0}


def test_an_unattended_game_not_ended_by_the_rules_is_a_draw_at_the_move_cap(tmp_path):
    moves = long_game(MOVE_CAP_PLIES + 2)
    board, asked = chess.Board(), []  # Black's moves, but those that are its only legal move: it isn't asked
    for move in moves:
        if board.turn == chess.BLACK and board.legal_moves.count() > 1:
            asked.append(board.san(move))
        board.push(move)
    model = FakeDecisionModel.favouring(*asked)
    game = start(tmp_path, model, sans(moves)["white"])

    state = play_out(game)

    assert (state.result, state.end_reason) == ("1/2-1/2", "move_cap")
    assert len(state.plies) == MOVE_CAP_PLIES


def test_a_system_1_side_has_no_llm_stats_and_is_never_offered_to_a_human(tmp_path):
    game = start(tmp_path, FakeDecisionModel.favouring("e5"), ["e4"])
    game.play_anchor_turn()
    assert game.state().human_legal_moves == []

    game.play_system1_turn()

    state = game.state()
    assert (state.stats.white, state.stats.black) == (None, None)
    assert state.llm_turns == []
    assert state.settings.black == side()
    assert state.model_dump(mode="json")["settings"]["black"]["player"] == "system1"


def test_a_system_1_turn_is_refused_when_it_is_not_one_s_turn_or_the_game_is_over(tmp_path):
    game = start(tmp_path, FakeDecisionModel.favouring("e5", "Qh4#"), ["f3", "g4"])

    with pytest.raises(RefusedSystem1Turn) as refused:
        game.play_system1_turn()  # White, an Anchor, is to move
    assert refused.value.code == "not_system1_turn"

    play_out(game)
    with pytest.raises(RefusedSystem1Turn) as refused:
        game.play_system1_turn()
    assert refused.value.code == "game_over"


def test_a_system_1_model_plays_an_llm(tmp_path):
    settings = Settings("llm_faceoff", LlmSide(), side())
    log = GameLog(tmp_path / "games", *settings.side_names())
    model = FakeDecisionModel.favouring("e5", "Qh4#")
    game = GameSession(
        {"white": ScriptedPlayer(["f3", "g4"])}, settings, log, clock=FakeClock(), decision_models={"black": model}
    )
    while (state := game.state()).status == "playing":
        if state.turn == "white":
            game.play_llm_turn()
        else:
            game.play_system1_turn()

    assert (state.pgn, state.result) == ("1. f3 e5 2. g4 Qh4#", "0-1")
    assert state.stats.white is not None and state.stats.black is None
    assert [turn.color for turn in state.llm_turns] == ["white", "white"]


def test_two_system_1_models_play_each_other_from_one_seed(tmp_path):
    def faceoff(name: str, seed: int) -> GameState:
        settings = Settings("llm_faceoff", side(), System1Side(model="d3:9b", base_url=BASE_URL))
        log = GameLog(tmp_path / name, *settings.side_names())
        models = {"white": FakeDecisionModel(), "black": FakeDecisionModel()}
        game = GameSession({}, settings, log, decision_models=models, seed=seed)
        while (state := game.state()).status == "playing":
            game.play_system1_turn()
        return state

    first = faceoff("a", seed=5)

    assert first.status == "over" and first.result is not None
    assert faceoff("b", seed=5).pgn == first.pgn
    assert faceoff("c", seed=6).pgn != first.pgn


def test_a_negative_choice_temperature_is_refused(tmp_path):
    settings = Settings("anchor_match", AnchorSide(engine="dragon", skill=1), side(choice_temperature=-0.5))

    with pytest.raises(InvalidSettings, match="Choice temperature"):
        settings.check([])


def test_a_prompt_template_placing_the_legal_moves_is_refused_for_a_system_1_side(tmp_path):
    template = PromptTemplate("mine@1", None, "Which move should $color play?", "FEN: $fen\nOptions: $legal_moves")
    settings = Settings("anchor_match", AnchorSide(engine="dragon", skill=1), side(prompt_template=template))

    with pytest.raises(InvalidSettings, match=r"\$legal_moves") as refused:
        settings.check([])
    assert refused.value.code == "invalid_prompt_template"


def test_a_system_1_side_plays_with_a_prompt_template_of_its_own(tmp_path):
    template = PromptTemplate("position@1", "Position", "Pick a move for $color.", "$fen")
    model = FakeDecisionModel.favouring("e5")
    game = start(tmp_path, model, ["e4"], system1=side(prompt_template=template))

    play_out_one_round(game)

    [asked] = model.asked
    assert asked.question == "Pick a move for Black."
    assert asked.state == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    assert events(game, "game_start")[0]["black"]["prompt_template"] == {
        "id": "position@1", "name": "Position", "system_prompt": "Pick a move for $color.", "turn_template": "$fen",
    }
