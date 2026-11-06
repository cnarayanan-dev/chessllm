"""The games report over logs with System 1 sides (ADR 0012): each System 1 Player configuration's record, its share of
moves that were its top option and its Move-quality estimate, with the illegal-move statistics not applicable (ADR 0003)
rather than zero. Reports over logs without System 1 sides are unchanged."""

import json

from tests.analytics.test_analysis import PeakedMoveModel
from tests.cli.test_report import GEMMA, LLAMA, dragon, game, logs, write_log
from tests.system1.logs import Turn, anchor_side, system1_game, system1_side

from chessllm.analytics.analysis import analyse_games
from chessllm.cli.report import Filters, analyse, load_games, main

FOOLS_MATE = ["f3", Turn("e5", {"e5": 0.7, "d5": 0.3}), "g4", Turn("Qh4#", {"Qh4#": 1.0})]
# White plays; after 4...Qxf2+ its only legal move is Kxf2, which is not asked. It plays its favourite at plies 1 and 7,
# one of two tied favourites at ply 3 and not its favourite at ply 5.
FORCED_KING_MOVE = [
    Turn("e3", {"e3": 0.6, "e4": 0.4}), "e5", Turn("c4", {"c4": 0.5, "d4": 0.5}), "Qe7",
    Turn("g4", {"g4": 0.1, "Nf3": 0.9}), "Qf6", Turn("e4", {"e4": 1.0}), "Qxf2+", Turn("Kxf2"),
]
FORFEIT = ["f3", Turn("e5", {"e5": 1.0}), "g4", Turn(None, {"Qh4#": None, "d5": None})]
ILLEGAL_MOVE_STATISTICS = ("illegal_turn_rate", "illegal_attempts_per_turn", "illegal_kinds", "illegal_phases",
                           "top_illegal_moves", "repeated_rejected_moves", "no_answers", "legal_move_streak_mean",
                           "legal_move_streak_median", "recovered_turns", "notation_slips", "chaos_gain")


def report(tmp_path, *logs_, filters=None, **options):
    games_dir = tmp_path / "games"
    for number, events in enumerate(logs_):
        write_log(games_dir, f"2026-10-20T10-00-{number:02d}", events)
    games, _ = load_games(games_dir)
    return analyse(games, filters or Filters(), **options)


def only_configuration(report_):
    [configuration] = report_["system1_configurations"]
    return configuration


def test_the_share_of_moves_that_were_the_top_option_counts_ties_and_leaves_out_turns_that_were_not_asked(tmp_path):
    result = report(
        tmp_path,
        system1_game(system1_side(), anchor_side(), FORCED_KING_MOVE, "1/2-1/2", "move_cap"),
        system1_game(anchor_side(), system1_side(), FORFEIT, "1-0", "forfeit"),
    )

    themes = only_configuration(result)["themes"]

    # Plies 1, 3 (a tie) and 7 of the first game and ply 2 of the second were its top option; ply 5 was not. Ply 9 had no
    # choice and ply 4 of the second game was a Forfeit, which played no move.
    assert (themes["top_option_moves"], themes["top_option_turns"]) == (4, 5)
    assert themes["top_option_share"] == 0.8


def test_a_system_1_side_has_its_record_against_each_anchor_and_a_forfeit_counts_as_a_loss(tmp_path):
    result = report(
        tmp_path,
        system1_game(anchor_side(2), system1_side(), FOOLS_MATE, "0-1", "checkmate"),
        system1_game(anchor_side(3), system1_side(), FORFEIT, "1-0", "forfeit"),
    )

    configuration = only_configuration(result)

    assert configuration["record"] == {"games": 2, "wins": 1, "draws": 0, "losses": 1, "unfinished": 0, "score": 0.5}
    assert configuration["by_anchor"]["Dragon skill 2"]["wins"] == 1
    assert configuration["by_anchor"]["Dragon skill 3"]["losses"] == 1
    assert configuration["themes"]["forfeit_rate"] == 0.5
    assert configuration["themes"]["losses_by"] == {"forfeit": 1}


def test_the_illegal_move_statistics_are_not_applicable_for_a_system_1_side_never_zero(tmp_path):
    result = report(tmp_path, system1_game(anchor_side(), system1_side(), FOOLS_MATE, "0-1", "checkmate"))

    themes = only_configuration(result)["themes"]

    assert {name: themes[name] for name in ILLEGAL_MOVE_STATISTICS} == dict.fromkeys(ILLEGAL_MOVE_STATISTICS)


def test_a_configuration_is_its_model_choice_temperature_and_prompt_template(tmp_path):
    other_prompt = {"id": "system1@0badf00d", "name": "Terse", "system_prompt": "Move?", "turn_template": "$fen"}
    sides = [system1_side(), system1_side(), system1_side(choice_temperature=0.5), system1_side(model="d3:9b"),
             system1_side(template=other_prompt)]

    result = report(tmp_path, *[system1_game(anchor_side(), side, FOOLS_MATE, "0-1", "checkmate") for side in sides])

    games = {
        (entry["configuration"]["model"], entry["configuration"]["choice_temperature"],
         entry["configuration"]["prompt_template"]): entry["record"]["games"]
        for entry in result["system1_configurations"]
    }
    assert games == {("d3:2b", 1.0, "system1@6b0c92ff"): 2, ("d3:2b", 0.5, "system1@6b0c92ff"): 1,
                     ("d3:9b", 1.0, "system1@6b0c92ff"): 1, ("d3:2b", 1.0, "system1@0badf00d"): 1}


def test_a_system_1_side_gets_a_move_quality_estimate_from_its_analysed_games(tmp_path):
    games_dir = tmp_path / "games"
    write_log(games_dir, "2026-10-20T10-00-00", system1_game(anchor_side(), system1_side(), FOOLS_MATE, "0-1", "checkmate"))
    analyse_games(games_dir, PeakedMoveModel(black_peak=1400))

    result = report(tmp_path)

    quality = only_configuration(result)["themes"]["move_quality"]
    assert (quality["games"], quality["moves"], quality["lichess_rapid"]["estimate"]) == (1, 2, 1400)


def test_the_model_filter_selects_system_1_sides_and_the_constraints_filter_leaves_them_out(tmp_path):
    events = system1_game(anchor_side(), system1_side(), FOOLS_MATE, "0-1", "checkmate")

    assert len(report(tmp_path, events, filters=Filters(model="D3"))["system1_configurations"]) == 1
    assert report(tmp_path, events, filters=Filters(model="llama"))["games"] == 0
    assert report(tmp_path, events, filters=Filters(constraints="free"))["games"] == 0


def test_a_folder_of_llm_anchor_and_system_1_games_is_reported_with_the_llm_report_unchanged(tmp_path):
    games_dir = logs(tmp_path)
    before = analyse(load_games(games_dir)[0], Filters(finished_only=False))
    write_log(games_dir, "2026-10-20T10-00-00", system1_game(anchor_side(2), system1_side(), FOOLS_MATE, "0-1", "checkmate"))
    write_log(games_dir, "2026-10-20T10-00-01", system1_game(system1_side(), anchor_side(), FORCED_KING_MOVE))
    write_log(games_dir, "2026-10-20T10-00-02", system1_game(
        system1_side(), system1_side(model="d3:9b"),
        [Turn("e4", {"e4": 0.5, "d4": 0.5}), Turn("e5", {"e5": 0.5, "d5": 0.5})], "1/2-1/2", "move_cap",
        mode="llm_faceoff"))

    after = analyse(load_games(games_dir)[0], Filters(finished_only=False))

    assert after["configurations"] == before["configurations"]
    assert after["overall_themes"] == before["overall_themes"]
    assert after["llm_sides"] == before["llm_sides"]
    assert [entry["configuration"]["model"] for entry in after["system1_configurations"]] == ["d3:2b", "d3:9b"]
    assert {game["file"] for game in after["game_list"]} >= {"2026-10-20T10-00-00.jsonl", "2026-10-20T10-00-02.jsonl"}


def test_reports_over_logs_without_system_1_sides_have_no_system_1_part(tmp_path, capsys):
    games_dir = logs(tmp_path)

    assert "system1_configurations" not in analyse(load_games(games_dir)[0], Filters())
    main(["--games-dir", str(games_dir)])

    assert "System 1" not in capsys.readouterr().out


def test_the_command_prints_the_system_1_configurations_with_their_top_option_share_and_what_is_not_applicable(
    tmp_path, capsys
):
    games_dir = tmp_path / "games"
    write_log(games_dir, "a", system1_game(system1_side(), anchor_side(), FORCED_KING_MOVE, "1/2-1/2", "move_cap"))
    write_log(games_dir, "b", game(dragon(2), LLAMA, ["f3", "e5", "g4", "Qh4#"], "0-1", "checkmate"))
    write_log(games_dir, "c", game(LLAMA, GEMMA, ["e4", "e5", "Nf3", "Nc6"], "1/2-1/2", "move_cap"))

    assert main(["--games-dir", str(games_dir)]) == 0
    text = capsys.readouterr().out
    assert main(["--games-dir", str(games_dir), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)

    [section] = [part for part in text.split("\n\n") if part.startswith("5. System 1")]
    assert "d3:2b / Choice temperature 1 / system1@6b0c92ff" in text
    assert "top option 3 of 4 moves (75%)" in text
    assert "not applicable: illegal moves, retries, Legal-move streak, notation slips, Chaos gain" in text
    assert section
    assert data["system1_configurations"][0]["themes"]["top_option_share"] == 0.75
    assert data["system1_sides"] == 1
