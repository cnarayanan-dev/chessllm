"""Tools as a setting of the Player configuration (ADR 0011): an LLM side's tool set and Tool-call cap, set only from
the benchmark's commands, refused where v1 doesn't allow them, logged in game_start and kept apart wherever games are
grouped by configuration. Calling them is tested in test_tool_calls.py."""

import json

import pytest

from tests.conftest import ScriptedAnchor, ScriptedPlayer, play_llm

from chessllm.analytics.leaderboard import PlayerConfiguration, llm_configuration, settings_configuration
from chessllm.cli.anchor_match import main as anchor_match
from chessllm.cli.faceoff_batch import main as faceoff_batch
from chessllm.cli.report import Filters, analyse, load_games
from chessllm.exceptions import InvalidSettings
from chessllm.game.ladder import earlier_games
from chessllm.game.settings import Settings
from chessllm.game.sides import DEFAULT_TOOL_CALL_CAP, TOOLS, BenchmarkLlmSide, LlmSide
from chessllm.llm.models import LLM_MODELS

FOOLS_MATE = ["f3", "e5", "g4", "Qh4#"]
QWEN_TOOLS = BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, tools=frozenset({"legal_moves", "board"}))


def events(games_dir) -> list[dict]:
    [log] = games_dir.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def faceoff(tmp_path, *args: str) -> tuple[int, ScriptedPlayer]:
    player = ScriptedPlayer(FOOLS_MATE)
    code = faceoff_batch(
        ["--games", "1", *args, "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )
    return code, player


def test_the_tools_are_the_four_and_the_cap_is_ten_by_default():
    assert TOOLS == ("board", "move_history", "legal_moves", "material")
    assert DEFAULT_TOOL_CALL_CAP == 10
    side = BenchmarkLlmSide()
    assert (side.tools, side.tool_call_cap) == (frozenset(), 10)


def test_the_models_that_can_call_tools_natively_are_set_by_hand_like_thinking():
    assert {model.name: model.tools for model in LLM_MODELS} == {
        "qwen3.5:9b": True,
        "qwen3.8:latest": True,
        "llama3:8b": False,
        "gemma3:12b": False,
        "gemma4:26b": True,
    }


def test_a_faceoff_batch_gives_one_side_tools_and_a_cap_and_logs_them_sorted(tmp_path):
    code, player = faceoff(
        tmp_path, "--models", "qwen3.5:9b", "gemma3:12b", "--thinking-for", "qwen3.5:9b",
        "--tools-for", "qwen3.5:9b=legal_moves,board", "--tool-call-cap-for", "qwen3.5:9b=4",
    )

    assert code == 0
    start, *_ = events(tmp_path)
    assert (start["white"]["tools"], start["white"]["tool_call_cap"]) == (["board", "legal_moves"], 4)
    assert "tools" not in start["black"] and "tool_call_cap" not in start["black"]
    assert list(start["white"])[-1] == "prompt_template"  # still last
    settings = player.built_for[0]
    assert isinstance(settings.white, BenchmarkLlmSide) and isinstance(settings.black, BenchmarkLlmSide)
    assert (settings.white.tools, settings.white.tool_call_cap) == (frozenset({"board", "legal_moves"}), 4)
    assert settings.black.tools == frozenset()


def test_a_bare_tools_for_gives_all_four(tmp_path):
    code, _ = faceoff(
        tmp_path, "--models", "qwen3.5:9b", "gemma4:26b", "--thinking", "--tools-for", "qwen3.5:9b",
        "--tools-for", "gemma4:26b=material",
    )

    assert code == 0
    start, *_ = events(tmp_path)
    assert start["white"]["tools"] == sorted(TOOLS)
    assert (start["black"]["tools"], start["black"]["tool_call_cap"]) == (["material"], 10)


def test_an_anchor_match_takes_tools_bare_for_all_four_or_a_list_and_a_cap(tmp_path):
    for games_dir, tools in ((tmp_path / "all", []), (tmp_path / "two", ["move_history,material"])):
        player = ScriptedPlayer(["e5", "Qh4#"])
        code = anchor_match(
            ["--model", "qwen3.8:latest", "--thinking-level", "xhigh", "--color", "black", "--tools", *tools,
             "--tool-call-cap", "3", "--games-dir", str(games_dir)],
            player_for=player.for_settings,
            anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
            sampling_file=tmp_path / "no-sampling.toml",
        )
        assert code == 0

    every, *_ = events(tmp_path / "all")
    two, *_ = events(tmp_path / "two")
    assert (every["black"]["tools"], every["black"]["tool_call_cap"]) == (sorted(TOOLS), 3)
    assert two["black"]["tools"] == ["material", "move_history"]


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--tools-for", "qwen3.5:9b=board,fen"], "no tool 'fen'"),
        (["--tools-for", "qwen3.5:9b=board,"], "no tool ''"),
        (["--tools-for", "qwen3.5:9b="], "no tools in ''"),
        (["--tools-for", "qwen3.5:9b=,"], "no tools in ','"),
        (["--tools-for", "=board"], "not MODEL[=LIST]: '=board'"),
        (["--tool-call-cap-for", "=4"], "not MODEL=N: '=4'"),
    ],
)
def test_a_faceoff_batch_refuses_a_tool_list_or_model_it_cant_read(tmp_path, capsys, args, error):
    with pytest.raises(SystemExit):
        faceoff(tmp_path, "--models", "qwen3.5:9b", "gemma3:12b", "--thinking", *args)

    assert error in capsys.readouterr().err


@pytest.mark.parametrize("tools", [",", "", "material,,board"])
def test_an_anchor_match_takes_all_four_tools_only_from_a_bare_flag(tmp_path, capsys, tools):
    with pytest.raises(SystemExit):
        anchor_match(["--model", "qwen3.5:9b", "--thinking", "--tools", tools, "--games-dir", str(tmp_path)])

    assert "no tool" in capsys.readouterr().err


def no_anchor(side):
    raise AssertionError("refused before any Anchor starts")


@pytest.mark.parametrize(
    ("command", "args", "reason"),
    [
        (anchor_match, ["--model", "qwen3.5:9b", "--thinking", "--tool-call-cap", "10"],
         "--tool-call-cap 10 needs --tools"),
        (faceoff_batch, ["--models", "qwen3.5:9b", "gemma3:12b", "--thinking-for", "qwen3.5:9b",
                         "--tool-call-cap-for", "qwen3.5:9b=10"], "gives qwen3.5:9b a cap but --tools-for no tools"),
    ],
)
def test_a_cap_given_without_tools_is_refused_even_the_default(tmp_path, capsys, command, args, reason):
    options = {"anchor_for": no_anchor} if command is anchor_match else {}
    code = command(
        [*args, "--games-dir", str(tmp_path)],
        player_for=ScriptedPlayer([]).for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
        **options,
    )

    assert code == 1
    assert reason in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))


@pytest.mark.parametrize(
    ("side", "rules", "reason"),
    [
        (QWEN_TOOLS, "standard", None),
        (BenchmarkLlmSide(model="qwen3.8:latest", thinking=True, thinking_level="xhigh", tools=frozenset({"board"})),
         "standard", None),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, llm_constraints="blind_enforced",
                          tools=frozenset(TOOLS)), "standard", None),
        (BenchmarkLlmSide(model="llama3:8b", tools=frozenset({"board"})), "standard",
         "llama3:8b (white) has tools, but can't call tools natively"),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, llm_constraints="listed", tools=frozenset({"board"})),
         "standard", "qwen3.5:9b (white) has tools, so its LLM constraints must be free or blind_enforced, not listed"),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, llm_constraints="listed_enforced",
                          tools=frozenset({"board"})), "standard",
         "its LLM constraints must be free or blind_enforced, not listed_enforced"),
        (QWEN_TOOLS, "chaos", "qwen3.5:9b (white) has tools, so it must play under Standard rules, not chaos"),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, turn_memory="chat_position", tools=frozenset({"board"})),
         "standard", "qwen3.5:9b (white) has tools, so its Turn memory must be fresh, not chat_position"),
        (BenchmarkLlmSide(model="qwen3.5:9b", tools=frozenset({"board"})), "standard",
         "qwen3.5:9b (white) has tools, so thinking must be on"),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, thinking_budget=3072, tools=frozenset({"board"})),
         "standard", "qwen3.5:9b (white) has tools, so it can't have a Thinking budget"),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, tools=frozenset({"board"}), tool_call_cap=0),
         "standard", "qwen3.5:9b (white) has a Tool-call cap of 0: at least 1"),
        (BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, tool_call_cap=5), "standard",
         "qwen3.5:9b (white) has a Tool-call cap of 5 but no tools to call"),
    ],
)
def test_tools_are_refused_before_any_game_unless_v1_allows_them(side, rules, reason):
    settings = Settings("llm_faceoff", side, LlmSide(), rules=rules)

    if reason is None:
        settings.check(LLM_MODELS)
        return
    with pytest.raises(InvalidSettings) as refused:
        settings.check(LLM_MODELS)
    assert reason in str(refused.value)


def test_a_command_refuses_tools_before_any_game_with_the_reason(tmp_path, capsys):
    code, _ = faceoff(tmp_path, "--models", "qwen3.5:9b", "gemma3:12b", "--tools-for", "qwen3.5:9b")

    assert code == 1
    assert "qwen3.5:9b (white) has tools, so thinking must be on" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))


def test_the_api_refuses_tools_and_its_output_has_none(scripted):
    client, _ = scripted([])

    for setting in ({"tools": ["board"]}, {"tool_call_cap": 3}):
        refused = client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True, **setting))
        assert refused.status_code == 422 and next(iter(setting)) in refused.text
    response = client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True))
    assert response.status_code == 200
    assert "tool" not in json.dumps(response.json()["settings"])


def test_the_tool_set_and_cap_are_part_of_the_player_configuration_and_none_keeps_its_id(tmp_path):
    faceoff(tmp_path / "tools", "--models", "qwen3.5:9b", "gemma3:12b", "--thinking-for", "qwen3.5:9b",
            "--tools-for", "qwen3.5:9b=board,legal_moves")
    faceoff(tmp_path / "none", "--models", "qwen3.5:9b", "gemma3:12b", "--thinking-for", "qwen3.5:9b")

    tools_start, *_ = events(tmp_path / "tools")
    none_start, *_ = events(tmp_path / "none")
    with_tools = llm_configuration(tools_start, "white", tools_start["white"])
    without = llm_configuration(none_start, "white", none_start["white"])
    assert (with_tools.tools, with_tools.tool_call_cap) == (("board", "legal_moves"), 10)
    assert (without.tools, without.tool_call_cap) == (None, None)
    assert with_tools.id() != without.id()
    # A side with tools plays the Tools template by default, so its prompt differs too; with the same prompt, the
    # tools alone make another configuration, and no tools gives the id the side had before tools existed.
    assert with_tools.prompt.startswith("tools@") and without.prompt == "system.txt"
    same_prompt = llm_configuration(none_start, "white", none_start["white"] | {"tools": ["board"], "tool_call_cap": 10})
    assert same_prompt.id() != without.id()
    assert without.id() == llm_configuration(none_start, "white", none_start["white"] | {"tools": []}).id()
    # Out of the API's output, like the Thinking level: only the id tells them apart.
    assert not {"tools", "tool_call_cap"} & set(with_tools.model_dump())
    # Another cap, or another tool set, is another configuration; the order the tools are given in is not.
    other_cap = llm_configuration(tools_start, "white", tools_start["white"] | {"tool_call_cap": 4})
    other_set = llm_configuration(tools_start, "white", tools_start["white"] | {"tools": ["board"]})
    reordered = llm_configuration(tools_start, "white", tools_start["white"] | {"tools": ["legal_moves", "board"]})
    assert len({with_tools.id(), other_cap.id(), other_set.id()}) == 3
    assert reordered == with_tools and reordered.id() == with_tools.id()
    # No tools means no cap, however the cap was given.
    capped = llm_configuration(none_start, "white", none_start["white"] | {"tool_call_cap": 4})
    assert capped.tool_call_cap is None and capped.id() == without.id()
    no_tools = PlayerConfiguration.model_validate(without.__dict__ | {"tools": [], "tool_call_cap": 7})
    assert no_tools.tool_call_cap is None


def test_settings_configuration_has_the_tools_as_the_log_records_them(tmp_path):
    _, player = faceoff(tmp_path, "--models", "qwen3.5:9b", "gemma3:12b", "--thinking-for", "qwen3.5:9b",
                        "--tools-for", "qwen3.5:9b=legal_moves,board", "--tool-call-cap-for", "qwen3.5:9b=6")

    start, *_ = events(tmp_path)
    settings = player.built_for[0]
    for color in ("white", "black"):
        assert settings_configuration(settings, color) == llm_configuration(start, color, start[color])


def test_the_ladder_keeps_tool_and_no_tool_games_apart(tmp_path):
    def play(*args: str) -> Settings:
        player = ScriptedPlayer(["e5", "Qh4#"])
        anchor_match(
            ["--model", "qwen3.5:9b", "--thinking", "--color", "black", *args, "--games-dir", str(tmp_path)],
            player_for=player.for_settings,
            anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
            sampling_file=tmp_path / "no-sampling.toml",
        )
        return player.built_for[0]

    with_tools = play("--tools", "board")
    without = play()
    play("--tools", "board")

    assert len(earlier_games(tmp_path, settings_configuration(with_tools, "black"))) == 2
    assert len(earlier_games(tmp_path, settings_configuration(without, "black"))) == 1


def test_the_games_report_groups_a_tool_set_apart_and_labels_it(tmp_path):
    from tests.cli.test_report import game, write_log

    qwen = {"player": "llm", "model": "qwen3.5:9b", "thinking": True, "llm_constraints": "free",
            "retry_feedback": "explained"}
    games_dir = tmp_path / "games"
    write_log(games_dir, "a", game(qwen | {"tools": ["board", "legal_moves"], "tool_call_cap": 10}, qwen, FOOLS_MATE,
                                   "0-1", "checkmate"))
    write_log(games_dir, "b", game(qwen | {"tools": ["material"], "tool_call_cap": 4}, qwen, FOOLS_MATE, "0-1",
                                   "checkmate"))
    games, _ = load_games(games_dir)

    labels = sorted(c["configuration"]["label"] for c in analyse(games, Filters())["configurations"])

    assert labels == [
        "qwen3.5:9b / free / thinking / standard / explained feedback",
        "qwen3.5:9b / free / thinking / standard / explained feedback / tools board+legal_moves",
        "qwen3.5:9b / free / thinking / standard / explained feedback / tools material, cap 4",
    ]
