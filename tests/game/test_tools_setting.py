"""Tools as a setting of the Player configuration (ADR 0011): in the benchmark only, an LLM side can have a set of
Tools and a Tool-call cap, fixed for the game, refused where v1 doesn't allow them, logged in game_start when it has
any, and part of the configuration wherever games are grouped. No tool is called yet (#119)."""

import json

import pytest

from tests.conftest import ScriptedAnchor, ScriptedPlayer, play_llm

from chessllm.analytics.leaderboard import llm_configuration, settings_configuration
from chessllm.cli.anchor_match import main as anchor_match
from chessllm.cli.faceoff_batch import main as faceoff_batch
from chessllm.cli.report import Filters, analyse, load_games
from chessllm.game.runner import play_anchor_match as play_game
from chessllm.game.settings import Settings
from chessllm.game.sides import BenchmarkLlmSide, LlmSide
from chessllm.logs.game_log import GameLog

QWEN = "qwen3.5:9b"
# A faceoff of a thinking Qwen 3.5 as White against Gemma 3, which can neither think nor call tools.
THINKING_QWEN = ("--models", QWEN, "gemma3:12b", "--thinking-for", QWEN)


def game_start(games_dir) -> dict:
    [log] = sorted(games_dir.glob("*.jsonl"))
    return json.loads(log.read_text(encoding="utf-8").splitlines()[0])


def play_anchor_match(tmp_path, *args: str) -> tuple[int, ScriptedPlayer]:
    """One Anchor match of the LLM as White (f3, g4) against a scripted Anchor (e5, Qh4#), logged to tmp_path."""
    player = ScriptedPlayer(["f3", "g4"])
    code = anchor_match(
        ["--games-dir", str(tmp_path), *args],
        player_for=player.for_settings,
        anchor_for=lambda side: ScriptedAnchor(["e5", "Qh4#"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )
    return code, player


def play_faceoff(tmp_path, *args: str) -> tuple[int, ScriptedPlayer]:
    """One faceoff, the first model as White, to Fool's mate, logged to tmp_path."""
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])
    code = faceoff_batch(
        ["--games", "1", *args, "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )
    return code, player


def test_an_anchor_match_with_tools_logs_them_sorted_with_the_default_cap(tmp_path):
    code, player = play_anchor_match(tmp_path, "--model", QWEN, "--thinking", "--tools", "material,board")

    assert code == 0
    white = game_start(tmp_path)["white"]
    assert (white["tools"], white["tool_call_cap"]) == (["board", "material"], 10)
    assert player.built_for[0].white.tools == frozenset({"board", "material"})


def test_bare_tools_are_all_four_and_the_cap_can_be_set(tmp_path):
    code, _ = play_anchor_match(tmp_path, "--model", QWEN, "--thinking", "--tools", "--tool-call-cap", "3")

    assert code == 0
    white = game_start(tmp_path)["white"]
    assert (white["tools"], white["tool_call_cap"]) == (["board", "legal_moves", "material", "move_history"], 3)


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (["--model", "llama3:8b"], "llama3:8b (white) cannot call tools natively, so it can't have Tools"),
        (["--model", QWEN], f"{QWEN} (white) has Tools, so thinking must be on"),
        (
            ["--model", QWEN, "--thinking", "--llm-constraints", "listed"],
            f"{QWEN} (white) has Tools, so its LLM constraints must be free or blind_enforced, not listed",
        ),
        (
            ["--model", QWEN, "--thinking", "--llm-constraints", "listed_enforced"],
            f"{QWEN} (white) has Tools, so its LLM constraints must be free or blind_enforced, not listed_enforced",
        ),
        (
            ["--model", QWEN, "--thinking", "--rules", "chaos", "--engine", "stockfish"],
            f"{QWEN} (white) has Tools, so it must play under Standard rules",
        ),
        (
            ["--model", QWEN, "--thinking", "--turn-memory", "chat_position"],
            f"{QWEN} (white) has Tools, so its Turn memory must be fresh, not chat_position",
        ),
        (
            ["--model", QWEN, "--thinking", "--thinking-budget", "3072"],
            f"{QWEN} (white) has Tools, so it can't have a Thinking budget",
        ),
        (["--model", QWEN, "--thinking", "--tool-call-cap", "0"], f"{QWEN} (white) has a Tool-call cap of 0"),
    ],
)
def test_tools_v1_doesnt_allow_are_refused_before_any_game(tmp_path, capsys, args, reason):
    code, player = play_anchor_match(tmp_path, *args, "--tools")

    assert code == 1
    assert reason in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl")) and not player.built_for


def test_a_cap_without_tools_is_refused(tmp_path, capsys):
    code, _ = play_anchor_match(tmp_path, "--model", QWEN, "--thinking", "--tool-call-cap", "5")

    assert code == 1
    assert "--tool-call-cap 5 gives a Tool-call cap without Tools" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("tools", "reason"),
    [
        ("board,engine", "no Tool engine: the Tools are board, move_history, legal_moves, material"),
        ("", "no Tools in '': give them joined by commas, e.g. board,legal_moves"),
        ("board,", "an empty Tool name in 'board,': give the Tools joined by commas, e.g. board,legal_moves"),
    ],
)
def test_an_unknown_or_empty_tool_is_refused(tmp_path, capsys, tools, reason):
    with pytest.raises(SystemExit):
        play_anchor_match(tmp_path, "--model", QWEN, "--thinking", "--tools", tools)

    assert reason in capsys.readouterr().err


def test_an_empty_list_of_tools_for_a_faceoff_model_is_refused_not_taken_as_all_four(tmp_path, capsys):
    with pytest.raises(SystemExit):
        play_faceoff(tmp_path, *THINKING_QWEN, "--tools-for", f"{QWEN}=")

    assert "no Tools in '': give them joined by commas" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))


def test_tools_at_a_thinking_level_are_allowed(tmp_path):
    code, _ = play_anchor_match(tmp_path, "--model", "qwen3.8:latest", "--thinking-level", "xhigh", "--tools", "board")

    assert code == 0
    assert game_start(tmp_path)["white"]["tools"] == ["board"]


def test_tools_under_blind_enforced_are_allowed(tmp_path):
    code, _ = play_anchor_match(
        tmp_path, "--model", QWEN, "--thinking", "--llm-constraints", "blind_enforced", "--tools", "legal_moves"
    )

    assert code == 0


def test_a_faceoff_gives_tools_and_a_cap_per_side(tmp_path):
    code, player = play_faceoff(
        tmp_path, "--models", QWEN, "gemma4:26b", "--thinking",
        "--tools-for", f"{QWEN}=legal_moves,board", "--tool-call-cap-for", f"{QWEN}=4", "--tools-for", "gemma4:26b",
    )

    assert code == 0
    start = game_start(tmp_path)
    assert (start["white"]["tools"], start["white"]["tool_call_cap"]) == (["board", "legal_moves"], 4)
    assert (start["black"]["tools"], start["black"]["tool_call_cap"]) == (
        ["board", "legal_moves", "material", "move_history"], 10
    )
    settings = player.built_for[0]
    assert (settings.white.tool_call_cap, settings.black.tool_call_cap) == (4, 10)


def test_a_faceoff_side_without_tools_logs_none(tmp_path):
    code, _ = play_faceoff(tmp_path, *THINKING_QWEN, "--tools-for", QWEN)

    assert code == 0
    black = game_start(tmp_path)["black"]
    assert "tools" not in black and "tool_call_cap" not in black


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (["--tools-for", "gemma3:12b"], "gemma3:12b (black) cannot call tools natively, so it can't have Tools"),
        (["--tool-call-cap-for", f"{QWEN}=5"], f"--tool-call-cap-for {QWEN}=5 gives a Tool-call cap without Tools"),
        (
            ["--tools-for", f"{QWEN}=board", "--tools-for", f"{QWEN}=material"],
            f"--tools-for gives {QWEN} two sets of Tools, board and material",
        ),
    ],
)
def test_a_faceoffs_tools_that_cant_work_are_refused_before_any_game(tmp_path, capsys, args, reason):
    code, player = play_faceoff(tmp_path, *THINKING_QWEN, *args)

    assert code == 1
    assert reason in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl")) and not player.built_for


def test_the_api_refuses_tools(scripted):
    client, player = scripted([])

    for setting in ({"tools": ["board"]}, {"tool_call_cap": 5}):
        refused = client.post("/api/games", json=play_llm(model=QWEN, thinking=True, **setting))
        assert refused.status_code == 422 and next(iter(setting)) in refused.text
    assert not player.built_for


def test_a_benchmark_games_state_leaves_its_tools_out_of_the_apis_output(tmp_path):
    side = BenchmarkLlmSide(model=QWEN, thinking=True, tools=frozenset({"board"}), tool_call_cap=3)
    settings = Settings("llm_faceoff", side, LlmSide())
    players = {"white": ScriptedPlayer(["f3", "g4"]), "black": ScriptedPlayer(["e5", "Qh4#"])}

    state = play_game(settings, players, {}, GameLog(tmp_path, *settings.side_names()))

    dumped = json.dumps(state.settings.model_dump())
    assert "tools" not in dumped and "tool_call_cap" not in dumped


def test_tools_and_their_cap_are_part_of_the_player_configuration_and_no_tools_keeps_its_id(tmp_path):
    play_faceoff(tmp_path / "board", *THINKING_QWEN, "--tools-for", f"{QWEN}=board")
    play_faceoff(tmp_path / "all", *THINKING_QWEN, "--tools-for", QWEN)
    capped_cap = ("--tools-for", QWEN, "--tool-call-cap-for", f"{QWEN}=3")
    _, capped = play_faceoff(tmp_path / "capped", *THINKING_QWEN, *capped_cap)
    _, player = play_faceoff(tmp_path / "none", *THINKING_QWEN)

    starts = {name: game_start(tmp_path / name) for name in ("board", "all", "capped", "none")}
    ids = {name: llm_configuration(start, "white", start["white"]).id() for name, start in starts.items()}
    assert len(set(ids.values())) == 4
    # The id this configuration had before Tools existed, from a log of that time.
    assert ids["none"] == "6225640759c7"
    # As the ladder's history matches a batch's configuration against the logged ones.
    for name, built in (("none", player), ("capped", capped)):
        logged = llm_configuration(starts[name], "white", starts[name]["white"])
        assert logged == settings_configuration(built.built_for[0], "white")


def test_the_leaderboard_shows_a_configuration_with_tools_without_them_under_its_own_id(scripted, tmp_path):
    play_faceoff(tmp_path / "games", *THINKING_QWEN, "--tools-for", QWEN)
    play_faceoff(tmp_path / "games", *THINKING_QWEN)
    client, _ = scripted([], games_dir=tmp_path / "games")

    configurations = client.get("/api/leaderboard").json()["configurations"]

    qwen = [entry for entry in configurations if entry["configuration"]["model"] == QWEN]
    assert len(qwen) == 2 and qwen[0]["id"] != qwen[1]["id"]
    assert qwen[0]["configuration"] == qwen[1]["configuration"]
    assert "tools" not in qwen[0]["configuration"]


def test_the_report_groups_tools_apart_and_labels_them(tmp_path):
    games = tmp_path / "games"
    play_faceoff(games, *THINKING_QWEN, "--tools-for", f"{QWEN}=legal_moves,board")
    play_faceoff(games, *THINKING_QWEN, "--tools-for", QWEN, "--tool-call-cap-for", f"{QWEN}=3")
    play_faceoff(games, *THINKING_QWEN)

    report = analyse(load_games(games)[0], Filters(model="qwen"))

    assert sorted(entry["configuration"]["label"] for entry in report["configurations"]) == [
        f"{QWEN} / free / thinking / standard / explained feedback",
        f"{QWEN} / free / thinking / standard / explained feedback / tools board+legal_moves",
        f"{QWEN} / free / thinking / standard / explained feedback / tools board+legal_moves+material+move_history, "
        "cap 3",
    ]
