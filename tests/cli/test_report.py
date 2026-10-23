"""The games report (chessllm/cli/report.py, `games-report`), on synthetic logs in a temporary games directory."""

import json

import chess

from chessllm.cli.report import Filters, analyse, load_games, main, opponent_label

LLAMA = {"player": "llm", "model": "llama3:8b", "thinking": False, "llm_constraints": "free", "retry_feedback": "explained"}
GEMMA = LLAMA | {"model": "gemma3:12b"}


def dragon(skill):
    return {"player": "anchor", "engine": "dragon", "skill": skill}


def write_log(games_dir, name, events):
    games_dir.mkdir(parents=True, exist_ok=True)
    path = games_dir / f"{name}.jsonl"
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return path


def game(white, black, sans, result=None, reason=None, mode=None, illegal=None, started="2026-10-19T10:00:00+02:00"):
    """A version 2 log of the moves in sans, each LLM move logged as an llm_attempt (after the illegal moves given for
    its ply in illegal, {ply: [move, ...]}) and each Anchor move as an anchor_move. Ends with game_end if result."""
    mode = mode or ("anchor_match" if "anchor" in (white["player"], black["player"]) else "llm_faceoff")
    start = {"type": "game_start", "game_id": "x", "log_version": 2, "mode": mode, "white": white, "black": black,
             "sampling": "model_default", "max_retries": 3, "started_at": started}
    events, board = [start], chess.Board()
    for ply, san in enumerate(sans, start=1):
        color = "white" if board.turn == chess.WHITE else "black"
        side = white if color == "white" else black
        if side["player"] == "anchor":
            board.push_san(san)
            events.append({"type": "anchor_move", "color": color, "ply": ply, "move": san, "fen_after": board.fen()})
            continue
        bad = (illegal or {}).get(ply, [])
        attempts = [*[(move, "illegal") for move in bad], (san, "legal")]
        for number, (move, outcome) in enumerate(attempts, start=1):
            events.append({"type": "llm_attempt", "color": color, "ply": ply, "attempt": number, "fen": board.fen(),
                           "move": move, "san": san if outcome == "legal" else None, "result": outcome,
                           "notation_slip": False, "latency_s": 1.0})
        board.push_san(san)
    if result is not None:
        # No legal_move_streak, so the script counts it from the attempts.
        stats = {color: {"notation_slips": 0} if side["player"] == "llm" else None
                 for color, side in (("white", white), ("black", black))}
        events.append({"type": "game_end", "result": result, "reason": reason, "plies": len(sans), "stats": stats})
    return events


VERSION_1 = [
    {"type": "game_start", "game_id": "y", "model": "llama3:8b", "llm_color": "black", "mode": "free",
     "thinking": False, "sampling": "model_default", "retry_feedback": "explained", "max_retries": 3,
     "started_at": "2026-10-18T21:00:00+02:00"},
    {"type": "human_move", "ply": 1, "move": "e4", "fen_after": "x"},
    {"type": "llm_attempt", "ply": 2, "attempt": 1, "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", "move": "Nc5", "result": "illegal", "latency_s": 3.0},
    {"type": "game_end", "result": "1-0", "reason": "forfeit", "plies": 1, "legal_move_streak": 0,
     "illegal_moves": {"invalid": 0, "illegal": 1, "ambiguous": 0}, "recovered_turns": 0},
]


def logs(tmp_path):
    games_dir = tmp_path / "games"
    # LLM black mates Dragon at Skill 2; LLM white walks into the Fool's mate against Dragon at Skill 3.
    write_log(games_dir, "2026-10-19T10-00-00_a", game(dragon(2), LLAMA, ["f3", "e5", "g4", "Qh4#"], "0-1", "checkmate"))
    write_log(games_dir, "2026-10-19T10-00-01_b",
              game(LLAMA, dragon(3), ["f3", "e5", "g4", "Qh4#"], "0-1", "checkmate", illegal={1: ["Ke2", "Ke2"]}))
    write_log(games_dir, "2026-10-19T10-00-02_c", game(LLAMA, GEMMA, ["e4", "e5", "Nf3", "Nc6"], "1/2-1/2", "move_cap"))
    write_log(games_dir, "2026-10-19T10-00-03_d", game(LLAMA, GEMMA, ["e4", "e5"]))  # unfinished
    write_log(games_dir, "2026-10-18T21-00-00_e", VERSION_1)
    (games_dir / "2026-10-19T10-00-04_f.jsonl").write_text("not json\n", encoding="utf-8")
    return games_dir


def by_label(report):
    return {(c["configuration"]["model"], c["configuration"]["llm_constraints"]): c for c in report["configurations"]}


def test_record_counts_each_llm_side_and_splits_anchor_matches_by_skill(tmp_path):
    games, skipped = load_games(logs(tmp_path))

    report = analyse(games, Filters())

    assert [name for name, _ in skipped] == ["2026-10-19T10-00-04_f.jsonl"]
    assert report["games"] == 4  # the unfinished game is left out by default
    llama = by_label(report)[("llama3:8b", "free")]
    # Won against Skill 2, lost to Skill 3, drew the faceoff, forfeited the version 1 game.
    assert {key: llama["record"][key] for key in ("games", "wins", "draws", "losses")} == {
        "games": 4, "wins": 1, "draws": 1, "losses": 2
    }
    assert llama["record"]["score"] == 1.5 / 4
    assert llama["by_anchor"]["Dragon skill 2"]["wins"] == 1
    assert llama["by_anchor"]["Dragon skill 3"]["losses"] == 1
    assert by_label(report)[("gemma3:12b", "free")]["record"]["draws"] == 1
    assert report["end_reasons"] == {"checkmate": 2, "move_cap": 1, "forfeit": 1}


def test_the_random_mover_is_named_as_an_opponent_without_a_skill():
    assert opponent_label({"player": "anchor", "engine": "random", "seed": 7}) == "Random mover"
    assert opponent_label(dragon(3)) == "Dragon skill 3"


def test_a_side_with_turn_memory_is_a_configuration_of_its_own(tmp_path):
    games_dir = tmp_path / "games"
    chat = LLAMA | {"turn_memory": "chat_position"}
    write_log(games_dir, "a", game(chat, LLAMA, ["f3", "e5", "g4", "Qh4#"], "0-1", "checkmate"))
    games, _ = load_games(games_dir)

    labels = sorted(c["configuration"]["label"] for c in analyse(games, Filters())["configurations"])

    assert labels == [
        "llama3:8b / free / no thinking / standard / explained feedback",
        "llama3:8b / free / no thinking / standard / explained feedback / chat_position",
    ]


def test_themes_find_illegal_moves_mates_and_openings(tmp_path):
    games, _ = load_games(logs(tmp_path))

    themes = by_label(analyse(games, Filters()))[("llama3:8b", "free")]["themes"]

    assert themes["illegal_kinds"] == {"illegal": 3}
    assert themes["top_illegal_moves"][0] == ("Ke2", 2)
    assert themes["repeated_rejected_moves"] == 1
    assert themes["illegal_phases"] == {"opening": 3}
    assert themes["recovered_turns"] == 1
    # Streaks: 2 (mated Dragon), 0 (illegal first move), 2 (faceoff), 0 (logged by the version 1 game).
    assert (themes["legal_move_streak_mean"], themes["legal_move_streak_median"]) == (1.0, 1.0)
    assert themes["forfeit_rate"] == 1 / 4
    assert themes["losses_by"] == {"checkmate": 1, "forfeit": 1}
    assert themes["allowed_mate_in_one"] == 1  # g4 in the Fool's mate
    assert themes["missed_mate_in_one"] == 0  # Qh4# was played
    report = analyse(games, Filters())
    assert ("1. f3 e5 2. g4 Qh4#", 2) in report["openings"]


def test_filters(tmp_path):
    games, _ = load_games(logs(tmp_path))

    assert analyse(games, Filters(mode="anchor_match"))["games"] == 2
    assert analyse(games, Filters(finished_only=False))["games"] == 5
    assert analyse(games, Filters(model="gemma"))["llm_sides"] == 1
    assert analyse(games, Filters(constraints="listed"))["games"] == 0
    assert analyse(games, Filters(rules="chaos"))["games"] == 0


def test_command_prints_tables_or_json(tmp_path, capsys):
    games_dir = logs(tmp_path)

    assert main(["--games-dir", str(games_dir), "--since", "2026-10-19", "--model", "llama3"]) == 0
    text = capsys.readouterr().out
    assert "3 games selected of 6 logs (1 skipped)" in text
    assert "vs Dragon skill 3" in text

    assert main(["--games-dir", str(games_dir), "--json", "--include-unfinished"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["games"] == 5
    assert report["end_reasons"]["unfinished"] == 1


QWEN = LLAMA | {"model": "qwen3.5:9b", "thinking": True}


def test_token_statistics_per_configuration_and_none_from_logs_without_them(tmp_path, capsys):
    games_dir = tmp_path / "games"
    events = game(QWEN, GEMMA, ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "d3", "d6", "c3", "Nf6"], "1/2-1/2",
                  "move_cap", illegal={1: ["Ke2"] * 4, 3: ["Ke2"]})
    qwen_attempts = [event for event in events if event["type"] == "llm_attempt" and event["color"] == "white"]
    for number, attempt in enumerate(qwen_attempts, start=1):  # 10 attempts: 100 to 1000 thinking tokens
        attempt |= {"thinking_tokens": 100 * number, "answer_tokens": 8, "prompt_tokens": 600 + number,
                    "stop_reason": "length" if number in (4, 9) else "stop", "token_split_estimated": True}
    write_log(games_dir, "2026-10-19T10-00-00_a", events)
    write_log(games_dir, "2026-10-19T10-00-01_b", game(LLAMA, GEMMA, ["e4", "e5"], "1/2-1/2", "move_cap"))

    report = analyse(load_games(games_dir)[0], Filters())

    qwen = by_label(report)[("qwen3.5:9b", "free")]["themes"]
    assert (qwen["thinking_tokens_median"], qwen["thinking_tokens_p90"]) == (550, 910)
    assert qwen["prompt_tokens_median"] == 605.5
    assert qwen["length_stops"] == 2
    llama = by_label(report)[("llama3:8b", "free")]["themes"]
    assert (llama["thinking_tokens_median"], llama["thinking_tokens_p90"], llama["prompt_tokens_median"]) == (None,) * 3
    assert llama["length_stops"] == 0
    assert main(["--games-dir", str(games_dir)]) == 0
    text = capsys.readouterr().out
    assert "thinking tokens median 550, p90 910; prompt tokens median 606; stopped for length: 2" in text


def test_a_budget_is_its_own_configuration_with_its_forced_share_and_a_cut_off_is_not_an_illegal_move(
    tmp_path, capsys
):
    games_dir = tmp_path / "games"
    budgeted = QWEN | {"thinking_budget": 512}
    events = game(budgeted, GEMMA, ["e4", "e5", "Nf3", "Nc6"], "1/2-1/2", "move_cap", illegal={1: ["Ke2"]})
    cut, _, forced = [event for event in events if event["type"] == "llm_attempt" and event["color"] == "white"]
    cut |= {"move": ' {"mo', "result": "cut_off", "forced": True, "stop_reason": "length"}
    forced |= {"forced": True, "stop_reason": "stop"}
    write_log(games_dir, "2026-10-19T10-00-00_a", events)
    write_log(games_dir, "2026-10-19T10-00-01_b", game(QWEN, GEMMA, ["e4", "e5"], "1/2-1/2", "move_cap"))

    report = analyse(load_games(games_dir)[0], Filters())

    by_name = {entry["configuration"]["label"]: entry["themes"] for entry in report["configurations"]}
    themes = by_name["qwen3.5:9b / free / thinking, budget 512 / standard / explained feedback"]
    # Two of the three answered attempts were forced: the cut-off one and the last.
    assert (themes["forced_answers"], themes["forced_share"], themes["cut_offs"]) == (2, 2 / 3, 1)
    assert (themes["illegal_attempts_per_turn"], themes["illegal_turn_rate"], themes["recovered_turns"]) == (0, 0, 0)
    assert themes["legal_move_streak_median"] == 2
    unbudgeted = by_name["qwen3.5:9b / free / thinking / standard / explained feedback"]
    assert (unbudgeted["forced_answers"], unbudgeted["forced_share"], unbudgeted["cut_offs"]) == (0, None, 0)
    assert main(["--games-dir", str(games_dir)]) == 0
    text = capsys.readouterr().out
    # For the budgeted configuration, and for all sides together, whose share is of the budgeted attempts only.
    assert text.count("forced answers: 2 of 3 attempts with a budget (67%); cut off without an answer: 1") == 2


def test_a_thinking_level_is_its_own_configuration_and_plain_thinking_on_keeps_its_label(tmp_path):
    games_dir = tmp_path / "games"
    qwen38 = QWEN | {"model": "qwen3.8:latest"}
    write_log(games_dir, "2026-10-19T10-00-00_a", game(qwen38, GEMMA, ["e4", "e5"], "1/2-1/2", "move_cap"))
    write_log(games_dir, "2026-10-19T10-00-01_b",
              game(qwen38 | {"thinking_level": "xhigh"}, GEMMA, ["e4", "e5"], "1/2-1/2", "move_cap"))

    report = analyse(load_games(games_dir)[0], Filters())

    labels = sorted(entry["configuration"]["label"] for entry in report["configurations"])
    assert labels == [
        "gemma3:12b / free / no thinking / standard / explained feedback",
        "qwen3.8:latest / free / thinking / standard / explained feedback",
        "qwen3.8:latest / free / thinking xhigh / standard / explained feedback",
    ]
